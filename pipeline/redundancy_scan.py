"""WP2 — Redundanz-/Synthese-Erkennung über einen bestehenden Vault (Detection + Report).

Prüft einen Vault (read-only) auf Dubletten und Synthese-Potenzial und schreibt
zwei Reports — **niemals** mutiert es den Vault (Option-B-Teil-Reversal, R12):
``merged_from`` bleibt leer, kein Auto-Merge, kein Löschen, keine Vector-DB.

Pipeline pro Doc-Paar (a, b):

1. **exact**  — identischer normalisierter Body (SHA-256).
2. **near-dup** — TF-IDF-Cosine ≥ ``tfidf_threshold`` (lexikalisch nah).
3. **semantic-dup** — Embedding-Cosine ≥ ``embedding_dup_threshold`` bei niedrigem
   TF-IDF (Paraphrase: semantisch hoch, lexikalisch niedrig).
4. **thematic** — Embedding-Cosine im Mittelband
   ``[embedding_thematic_low, embedding_dup_threshold)`` (thematische Überschneidung).

Aus den thematischen Kanten werden **Synthese-Kandidaten** gebildet: zusammen-
hängende Komponenten mit ≥ ``synthesis_min_members`` Docs.

Korpus-Finding: 96,5 % der Paare liegen < 0,6 → erwartet wird eine **kleine,
hochsignifikante** Kandidatenmenge (gewollt — Detection, kein Clustering).

Embeddings (mpnet) werden über ``pipeline.phase_6_embeddings`` (reaktivierter Code,
in-memory, numpy/sklearn) berechnet. ``use_embeddings=False`` = Fallback nur
Hash + TF-IDF. Optional (Default aus) bewertet ein injizierbarer ``qwen_evaluator``
jedes Kandidaten-Paar (low temp, JSON, Schema-validiert).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from pipeline.schemas import QwenPairVerdict, RedundancyBand, RedundancyPair, SynthesisCandidate

log = structlog.get_logger()

# Injizierbarer Qwen-Bewerter: (pair, body_a, body_b) -> Verdict | None.
QwenEvaluator = Callable[[RedundancyPair, str, str], QwenPairVerdict | None]

_FM_DELIM = "---\n"
_WS_RE = re.compile(r"\s+")


@dataclass
class VaultDoc:
    """Ein gelesener Vault-Artikel (read-only)."""

    slug: str
    body: str
    sources_docs: list[str] = field(default_factory=list)
    source_chunks: list[str] = field(default_factory=list)


@dataclass
class Thresholds:
    """Schwellen der Band-Klassifikation (aus config.redundancy_scan)."""

    tfidf_near: float = 0.72
    embedding_dup: float = 0.85
    embedding_thematic_low: float = 0.60
    synthesis_min_members: int = 3


@dataclass
class ScanResult:
    """Ergebnis eines Scans (für Reports + Abschluss-Counts)."""

    n_docs: int
    pairs: list[RedundancyPair]
    candidates: list[SynthesisCandidate]
    thresholds: Thresholds
    used_embeddings: bool
    input_hash: str

    def counts(self) -> dict[str, int]:
        """Anzahl Paare je Band + Synthese-Kandidaten."""
        out: dict[str, int] = {b: 0 for b in ("exact", "near-dup", "semantic-dup", "thematic")}
        for p in self.pairs:
            out[p.band] += 1
        out["synthesis_candidates"] = len(self.candidates)
        return out


# === Doc-Laden (read-only) ====================================================


def _split_frontmatter(text: str) -> tuple[dict[str, object] | None, str]:
    """``.md`` → ``(frontmatter_dict | None, body)``."""
    if not text.startswith(_FM_DELIM):
        return None, text
    m = re.search(r"\n---\s*\n", text[4:])
    if not m:
        return None, text
    import yaml

    fm = yaml.safe_load(text[4 : 4 + m.start()])
    return (fm if isinstance(fm, dict) else None), text[4 + m.end() :]


def load_vault_docs(vault_dir: Path) -> list[VaultDoc]:
    """Liest alle Artikel-``.md`` eines Vaults (ohne ``_index.md``), sortiert nach Slug.

    Read-only: öffnet Dateien ausschließlich lesend.
    """
    docs: list[VaultDoc] = []
    for p in sorted(vault_dir.rglob("*.md")):
        if p.name == "_index.md" or p.name.endswith(".body.md"):
            continue
        fm, body = _split_frontmatter(p.read_text(encoding="utf-8"))
        fm = fm or {}
        slug = str(fm.get("slug") or p.stem)
        docs.append(
            VaultDoc(
                slug=slug,
                body=body,
                sources_docs=_str_list(fm.get("sources_docs")),
                source_chunks=_str_list(fm.get("source_chunks")),
            )
        )
    return docs


def _str_list(value: object) -> list[str]:
    """Frontmatter-Wert → ``list[str]`` (leer, wenn kein Listentyp)."""
    return [str(s) for s in value] if isinstance(value, list) else []


# === Ähnlichkeiten ============================================================


def _normalize_body(text: str) -> str:
    """Body für exakten Hash normalisieren (Whitespace kollabieren, trimmen)."""
    return _WS_RE.sub(" ", text).strip()


def _body_hashes(docs: list[VaultDoc]) -> list[str]:
    return [hashlib.sha256(_normalize_body(d.body).encode("utf-8")).hexdigest() for d in docs]


def tfidf_similarity(
    texts: list[str], *, ngram_range: tuple[int, int], max_features: int, min_df: int
) -> np.ndarray:
    """Dichte NxN-Matrix der paarweisen TF-IDF-Cosine-Similarity (L2-normalisiert)."""
    n = len(texts)
    if n == 0:
        return np.zeros((0, 0), dtype=np.float32)
    effective_min_df = 1 if n < 10 else min(min_df, max(1, n // 10))
    vec = TfidfVectorizer(
        ngram_range=ngram_range,
        max_features=max_features,
        min_df=effective_min_df,
        sublinear_tf=True,
    )
    matrix = normalize(vec.fit_transform(texts), norm="l2", copy=False)
    return np.asarray((matrix @ matrix.T).todense(), dtype=np.float32)


def embed_similarity(
    texts: list[str], *, model_name: str, device: str, batch_size: int
) -> np.ndarray:
    """Dichte NxN-Embedding-Cosine-Matrix (mpnet; reuse phase_6 Device-Resolution)."""
    from sentence_transformers import SentenceTransformer

    from pipeline.phase_6_embeddings import _resolve_device

    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    model = SentenceTransformer(model_name, device=_resolve_device(device))
    emb = model.encode(
        texts, batch_size=batch_size, convert_to_numpy=True, normalize_embeddings=True
    ).astype(np.float32)
    return np.asarray(emb @ emb.T, dtype=np.float32)


# === Band-Klassifikation (pure) ===============================================


def classify_band(exact: bool, tfidf: float, emb: float, th: Thresholds) -> RedundancyBand | None:
    """Ordnet ein Paar einem Band zu (Präzedenz exact→near→semantic→thematic) oder ``None``."""
    if exact:
        return "exact"
    if tfidf >= th.tfidf_near:
        return "near-dup"
    if emb >= th.embedding_dup:
        return "semantic-dup"  # hohe Semantik, niedrige Lexik (TF-IDF < near)
    if emb >= th.embedding_thematic_low:
        return "thematic"
    return None


# === Synthese-Komponenten (Union-Find über thematische Kanten) =================


def synthesis_components(edges: list[tuple[int, int]], min_members: int) -> list[list[int]]:
    """Zusammenhängende Komponenten der thematischen Kanten mit ≥ ``min_members`` Knoten."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)

    groups: dict[int, list[int]] = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    return [sorted(g) for g in groups.values() if len(g) >= min_members]


# === Scan-Kern (über vorab berechnete Matrizen, gut testbar) ==================


def scan_pairs(
    docs: list[VaultDoc],
    hashes: list[str],
    tfidf_sim: np.ndarray,
    emb_sim: np.ndarray | None,
    th: Thresholds,
) -> tuple[list[RedundancyPair], list[SynthesisCandidate]]:
    """Klassifiziert alle Doc-Paare in Bänder und bildet Synthese-Kandidaten."""
    n = len(docs)
    pairs: list[RedundancyPair] = []
    thematic_edges: list[tuple[int, int]] = []

    for i, j in combinations(range(n), 2):
        exact = hashes[i] == hashes[j]
        t = float(tfidf_sim[i, j]) if tfidf_sim.size else 0.0
        e = float(emb_sim[i, j]) if emb_sim is not None and emb_sim.size else 0.0
        band = classify_band(exact, t, e, th)
        if band is None:
            continue
        a, b = (docs[i], docs[j]) if docs[i].slug <= docs[j].slug else (docs[j], docs[i])
        pairs.append(
            RedundancyPair(
                slug_a=a.slug,
                slug_b=b.slug,
                band=band,
                exact=exact,
                tfidf=round(max(0.0, min(1.0, t)), 4),
                embedding=round(max(-1.0, min(1.0, e)), 4),
                sources_a=a.sources_docs,
                sources_b=b.sources_docs,
                chunks_a=a.source_chunks,
                chunks_b=b.source_chunks,
            )
        )
        if band == "thematic":
            thematic_edges.append((i, j))

    pairs.sort(key=lambda p: (p.band, -p.embedding, -p.tfidf, p.slug_a, p.slug_b))

    candidates: list[SynthesisCandidate] = []
    comps = synthesis_components(thematic_edges, th.synthesis_min_members)
    comps.sort(key=lambda c: (-len(c), docs[c[0]].slug))
    for idx, comp in enumerate(comps):
        sims = (
            [float(emb_sim[a, b]) for a, b in combinations(comp, 2)] if emb_sim is not None else []
        )
        edge_count = sum(1 for a, b in thematic_edges if a in comp and b in comp)
        sources: list[str] = []
        for node in comp:
            for s in docs[node].sources_docs:
                if s not in sources:
                    sources.append(s)
        candidates.append(
            SynthesisCandidate(
                candidate_id=f"SC_{idx:03d}",
                slugs=sorted(docs[node].slug for node in comp),
                mean_similarity=round(float(np.mean(sims)), 4) if sims else 0.0,
                pair_count=edge_count,
                sources=sources,
            )
        )
    return pairs, candidates


# === Orchestrierung ===========================================================


def run_redundancy_scan(
    vault_dir: Path,
    *,
    thresholds: Thresholds,
    use_embeddings: bool = True,
    model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    device: str = "mps",
    batch_size: int = 32,
    ngram_range: tuple[int, int] = (1, 2),
    max_features: int = 20000,
    min_df: int = 2,
    qwen_evaluator: QwenEvaluator | None = None,
) -> ScanResult:
    """Vollständiger Scan eines Vaults (read-only). Schreibt nichts — nur Erkennung."""
    docs = load_vault_docs(vault_dir)
    if not docs:
        raise FileNotFoundError(f"Keine Artikel-.md in {vault_dir} gefunden")

    texts = [d.body for d in docs]
    hashes = _body_hashes(docs)
    input_hash = hashlib.sha256("\x00".join(sorted(hashes)).encode("utf-8")).hexdigest()[:16]

    tfidf_sim = tfidf_similarity(
        texts, ngram_range=ngram_range, max_features=max_features, min_df=min_df
    )
    emb_sim: np.ndarray | None = None
    if use_embeddings:
        log.info("redundancy_scan_embedding", n_docs=len(docs), model=model_name)
        emb_sim = embed_similarity(
            texts, model_name=model_name, device=device, batch_size=batch_size
        )

    pairs, candidates = scan_pairs(docs, hashes, tfidf_sim, emb_sim, thresholds)

    if qwen_evaluator is not None:
        body_by_slug = {d.slug: d.body for d in docs}
        _apply_qwen(pairs, candidates, body_by_slug, qwen_evaluator)

    log.info(
        "redundancy_scan_done",
        n_docs=len(docs),
        pairs=len(pairs),
        candidates=len(candidates),
        used_embeddings=use_embeddings,
    )
    return ScanResult(
        n_docs=len(docs),
        pairs=pairs,
        candidates=candidates,
        thresholds=thresholds,
        used_embeddings=use_embeddings,
        input_hash=input_hash,
    )


def _apply_qwen(
    pairs: list[RedundancyPair],
    candidates: list[SynthesisCandidate],
    body_by_slug: dict[str, str],
    evaluator: QwenEvaluator,
) -> None:
    """Bewertet Kandidaten-Paare (near/semantic/thematic) via Qwen (best-effort)."""
    candidate_slugs = {s for c in candidates for s in c.slugs}
    for p in pairs:
        if p.band == "exact":
            continue
        if p.band == "thematic" and not ({p.slug_a, p.slug_b} & candidate_slugs):
            continue
        verdict = evaluator(p, body_by_slug.get(p.slug_a, ""), body_by_slug.get(p.slug_b, ""))
        if verdict is not None:
            p.qwen_relation = verdict.relation
            p.qwen_recommendation = verdict.recommendation
            p.qwen_confidence = verdict.confidence


# === Reports (deterministisch/idempotent: kein Wall-Clock im Body) =============


def render_redundancy_report(result: ScanResult) -> str:
    """``redundancy_report.md`` — exakte/near/semantische Dubletten mit Provenance."""
    th = result.thresholds
    c = result.counts()
    lines = [
        "# Redundancy-Report (WP2 — Detection, kein Merge)",
        "",
        f"<!-- input_hash: {result.input_hash} · reproduzierbar, kein Wall-Clock im Body -->",
        "",
        f"- Docs gescannt: **{result.n_docs}**",
        f"- Embeddings: **{'ja (mpnet)' if result.used_embeddings else 'nein (nur Hash + TF-IDF)'}**",
        f"- Schwellen: TF-IDF≥{th.tfidf_near} · emb-dup≥{th.embedding_dup} · "
        f"thematic∈[{th.embedding_thematic_low}, {th.embedding_dup})",
        "",
        "| Band | Paare |",
        "|---|---:|",
        f"| exact | {c['exact']} |",
        f"| near-dup | {c['near-dup']} |",
        f"| semantic-dup | {c['semantic-dup']} |",
        f"| thematic | {c['thematic']} |",
        "",
    ]
    dup_bands = ("exact", "near-dup", "semantic-dup")
    dup_pairs = [p for p in result.pairs if p.band in dup_bands]
    lines += ["## Dubletten (exact / near / semantic)", ""]
    if not dup_pairs:
        lines += ["_keine_", ""]
    else:
        lines += [
            "| Band | Slug A | Slug B | TF-IDF | Embedding | sources_docs (A→B) | Qwen |",
            "|---|---|---|---:|---:|---|---|",
        ]
        for p in dup_pairs:
            qwen = (
                f"{p.qwen_relation}/{p.qwen_recommendation}/{p.qwen_confidence}"
                if p.qwen_relation
                else "—"
            )
            prov = f"{','.join(p.sources_a) or '—'} → {','.join(p.sources_b) or '—'}"
            lines.append(
                f"| {p.band} | `{p.slug_a}` | `{p.slug_b}` | {p.tfidf:.3f} | "
                f"{p.embedding:.3f} | {prov} | {qwen} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def render_synthesis_report(result: ScanResult) -> str:
    """``synthesis_candidates.md`` — thematische Komponenten (≥ N) als Synthese-Vorschläge."""
    th = result.thresholds
    thematic = [p for p in result.pairs if p.band == "thematic"]
    lines = [
        "# Synthesis-Candidates (WP2 — Vorschläge, KEIN Auto-Merge)",
        "",
        f"<!-- input_hash: {result.input_hash} -->",
        "",
        f"- thematische Paare (Mittelband): **{len(thematic)}**",
        f"- Synthese-Kandidaten (Komponenten ≥ {th.synthesis_min_members}): "
        f"**{len(result.candidates)}**",
        "",
    ]
    if not result.candidates:
        lines += [
            "_keine Komponente erreicht die Mindestgröße — erwartbar bei "
            "schwach vernetztem Korpus._",
            "",
        ]
    for cand in result.candidates:
        lines += [
            f"## {cand.candidate_id} — {len(cand.slugs)} Docs "
            f"(Ø-Sim {cand.mean_similarity:.3f}, {cand.pair_count} Kanten)",
            "",
            "**Mitglieder:** " + ", ".join(f"`{s}`" for s in cand.slugs),
            "",
            "**sources_docs (vereinigt):** " + (", ".join(cand.sources) or "—"),
            "",
            "**Status:** `detected` — manuelle Kuratierung nötig (Cross-Link oder "
            "Synthese), `merged_from` bleibt leer.",
            "",
        ]
    return "\n".join(lines) + "\n"


def write_reports(result: ScanResult, output_dir: Path) -> tuple[Path, Path]:
    """Schreibt beide Reports nach ``output_dir`` (z. B. work/). Gibt die Pfade zurück."""
    output_dir.mkdir(parents=True, exist_ok=True)
    red = output_dir / "redundancy_report.md"
    syn = output_dir / "synthesis_candidates.md"
    red.write_text(render_redundancy_report(result), encoding="utf-8")
    syn.write_text(render_synthesis_report(result), encoding="utf-8")
    return red, syn


# === Optionale Qwen-Paar-Bewertung (togglebar, Default aus) ===================

_PAIR_PROMPT = """Du bewertest die Beziehung zweier Wissens-Artikel (deutsch).
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in einem ```json-Block:
{{"relation": "duplicate|overlap|complementary|unrelated",
  "recommendation": "merge|cross-link|keep-separate",
  "confidence": "low|medium|high",
  "rationale": "max 1 Satz"}}

## Artikel A ({slug_a})
{body_a}

## Artikel B ({slug_b})
{body_b}
"""


def _extract_json(raw: str) -> dict[str, object] | None:
    """Erstes JSON-Objekt aus einer Qwen-Antwort (```json-Block oder erstes {...})."""
    import json as _json

    m = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = m.group(1) if m else None
    if candidate is None:
        start = raw.find("{")
        end = raw.rfind("}")
        candidate = raw[start : end + 1] if start != -1 and end > start else None
    if candidate is None:
        return None
    try:
        data = _json.loads(candidate)
    except (ValueError, _json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def make_qwen_evaluator(
    *,
    endpoint: str,
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    timeout: int = 600,
    body_cap: int = 4000,
) -> QwenEvaluator:
    """Baut einen Qwen-Bewerter gegen den LM-Studio/OpenAI-Endpunkt.

    json_mode bleibt aus (Reasoning-Modell-inkompatibel); JSON wird im Prompt
    erzwungen und frei geparst. ``max_tokens`` ist bewusst gecappt (Hang-Mitigation,
    siehe docs/04_qwen_prompts §11). Parse-/Schema-Fehler → ``None`` (best-effort).
    """
    import openai

    client = openai.OpenAI(base_url=endpoint, api_key="not-needed", timeout=timeout)

    def _evaluate(pair: RedundancyPair, body_a: str, body_b: str) -> QwenPairVerdict | None:
        prompt = _PAIR_PROMPT.format(
            slug_a=pair.slug_a,
            slug_b=pair.slug_b,
            body_a=body_a[:body_cap],
            body_b=body_b[:body_cap],
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover - Netzwerk/Endpoint
            log.warning(
                "qwen_pair_eval_failed",
                slug_a=pair.slug_a,
                slug_b=pair.slug_b,
                error=str(exc)[:200],
            )
            return None
        data = _extract_json(raw)
        if data is None:
            return None
        try:
            return QwenPairVerdict.model_validate(data)
        except Exception:  # pragma: no cover - Schema-Drift
            return None

    return _evaluate
