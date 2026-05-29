"""Phase 10 — Kontroll-Berichte.

Generiert drei Markdown-Reports aus bestehenden Pipeline-Outputs:
  corpus_report.md     — Übersicht Korpus (Größen, Typen, Sprachen)
  duplicate_report.md  — Duplikate und Kanten
  cluster_report.md    — Cluster-Verteilung (Gate-1-Input)

Inputs (alle aus data/02_pipeline_output/):
  files_manifest.jsonl, documents_structured.jsonl, segments.jsonl,
  exact_duplicates.json, near_duplicate_edges.jsonl, cluster_proposals.json,
  batches/batch_*.md

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 10):
  - Reports regenerierbar (idempotent via Input-Hash)
  - Mensch-lesbar Markdown mit gültigem Frontmatter
"""

import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pipeline.schemas import (
    ClusterProposal,
    DocumentRecord,
    ExactDuplicateGroup,
    NearDuplicateEdge,
    StructuredDocumentRecord,
)

log = structlog.get_logger()

_UNSORTED_ID = "C_unsortiert"

_DE_WORDS = frozenset(
    [
        "und",
        "der",
        "die",
        "das",
        "ist",
        "auch",
        "mit",
        "von",
        "zu",
        "für",
        "nicht",
        "sich",
        "nach",
        "noch",
        "oder",
        "aber",
        "wenn",
        "bei",
        "wie",
        "eine",
        "einen",
        "einem",
        "einer",
        "eines",
        "werden",
        "wird",
        "wurde",
    ]
)
_EN_WORDS = frozenset(
    [
        "the",
        "and",
        "is",
        "are",
        "of",
        "to",
        "for",
        "this",
        "that",
        "with",
        "from",
        "have",
        "has",
        "not",
        "can",
        "will",
        "they",
        "you",
        "your",
        "which",
        "been",
        "were",
        "their",
        "there",
    ]
)


# === Helpers ==================================================================


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _combined_hash(paths: list[Path]) -> str:
    """Kombinierter SHA-256 aus mehreren Dateien (nur existierende)."""
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _is_cached(output_path: Path, meta_path: Path, input_hash: str) -> bool:
    if not output_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("input_hash") == input_hash
    except Exception:
        return False


def _write_meta(
    meta_path: Path,
    input_hash: str,
    output_path: Path,
    phase: str,
    pipeline_version: str,
    duration_seconds: float,
) -> None:
    output_hash = f"sha256:{_sha256_file(output_path)}" if output_path.exists() else ""
    meta: dict[str, Any] = {
        "phase": phase,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": {},
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _meta_path_for(output_path: Path) -> Path:
    return output_path.parent / f".{output_path.name}.meta.json"


def _doc_id_from_segment_id(seg_id: str) -> str:
    """Extrahiert doc_id aus segment_id (D_slug-S0003 → D_slug)."""
    return re.sub(r"-S\d{4}$", "", seg_id)


def _detect_language(text: str) -> str:
    """Heuristisch: 'de' | 'en' | 'mixed' | 'unklar' via Stoppwörter."""
    words = re.findall(r"\b[a-zäöüß]{2,}\b", text[:1000].lower())
    de = sum(1 for w in words if w in _DE_WORDS)
    en = sum(1 for w in words if w in _EN_WORDS)
    if de == 0 and en == 0:
        return "unklar"
    if de >= en * 2:
        return "de"
    if en >= de * 2:
        return "en"
    return "mixed"


def _iso_date() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


# === Loaders ==================================================================


def _load_manifest(path: Path) -> list[DocumentRecord]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(DocumentRecord.model_validate_json(line))
    return records


def _load_structured(path: Path) -> dict[str, StructuredDocumentRecord]:
    result: dict[str, StructuredDocumentRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = StructuredDocumentRecord.model_validate_json(line)
            result[rec.doc_id] = rec
    return result


def _load_segment_counts(path: Path) -> int:
    """Zählt nur die Zeilen in segments.jsonl (keine Text-Deserialisierung)."""
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _load_clusters(path: Path) -> list[ClusterProposal]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ClusterProposal.model_validate(item) for item in data]


def _load_edges(path: Path) -> list[NearDuplicateEdge]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            result.append(NearDuplicateEdge.model_validate_json(line))
    return result


def _load_exact_duplicates(path: Path) -> list[ExactDuplicateGroup]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ExactDuplicateGroup.model_validate(item) for item in data]


def _load_language_map(cleaned_path: Path) -> dict[str, str]:
    """Lädt {doc_id: language} via Stoppwort-Heuristik auf Body-Text."""
    result: dict[str, str] = {}
    for line in cleaned_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            result[d["doc_id"]] = _detect_language(d.get("body", ""))
    return result


_FM_LINE_RE = re.compile(r"^(\w+):\s*(.*)", re.MULTILINE)


def _load_batch_infos(batches_dir: Path) -> list[dict[str, Any]]:
    """Liest Frontmatter aus allen batch_*.md-Dateien (Regex, kein YAML-Parse).

    Kein yaml.safe_load hier — label_guess kann Markdown-Syntax enthalten
    (z.B. **bold**), die YAML als Alias interpretiert.
    """
    infos: list[dict[str, Any]] = []
    for batch_file in sorted(batches_dir.glob("batch_*.md")):
        content = batch_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        end = content.find("---", 3)
        if end == -1:
            continue
        fm_text = content[3:end]
        fm: dict[str, Any] = {"_path": batch_file}
        for m in _FM_LINE_RE.finditer(fm_text):
            key, val = m.group(1), m.group(2).strip()
            if val.isdigit():
                fm[key] = int(val)
            else:
                fm[key] = val
        infos.append(fm)
    return infos


# === Cluster-Report Helpers ===================================================


def _build_seg_cluster_map(clusters: list[ClusterProposal]) -> dict[str, str]:
    """Baut {segment_id: cluster_id} aus allen Cluster-Proposals."""
    mapping: dict[str, str] = {}
    for c in clusters:
        for sid in c.segment_ids:
            mapping[sid] = c.cluster_id
    return mapping


def _count_intra_inter(
    edges: list[NearDuplicateEdge], seg_cluster: dict[str, str]
) -> tuple[int, int]:
    """Zählt Kanten innerhalb vs. zwischen Clustern."""
    intra = 0
    inter = 0
    for e in edges:
        ca = seg_cluster.get(e.segment_id_a)
        cb = seg_cluster.get(e.segment_id_b)
        if ca is not None and cb is not None:
            if ca == cb:
                intra += 1
            else:
                inter += 1
    return intra, inter


def _cluster_size_histogram(
    clusters: list[ClusterProposal],
    doc_counts: dict[str, int],
) -> dict[str, int]:
    """Histogramm nach Doc-Anzahl pro Cluster (ohne C_unsortiert)."""
    hist: dict[str, int] = {"1": 0, "2": 0, "3-5": 0, "6-10": 0, "11-50": 0, "> 50": 0}
    for c in clusters:
        if c.cluster_id == _UNSORTED_ID:
            continue
        n = doc_counts.get(c.cluster_id, 0)
        if n <= 1:
            hist["1"] += 1
        elif n <= 2:
            hist["2"] += 1
        elif n <= 5:
            hist["3-5"] += 1
        elif n <= 10:
            hist["6-10"] += 1
        elif n <= 50:
            hist["11-50"] += 1
        else:
            hist["> 50"] += 1
    return hist


# === Report Generators ========================================================


def generate_corpus_report(
    manifest_path: Path,
    structured_path: Path,
    segments_path: Path,
    output_path: Path,
    cleaned_path: Path | None = None,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> Path:
    """Generiert corpus_report.md aus Phase-1/3/4-Outputs."""
    input_paths = [manifest_path, structured_path, segments_path]
    if cleaned_path and cleaned_path.exists():
        input_paths.append(cleaned_path)
    input_hash = _combined_hash(input_paths)
    meta_path = _meta_path_for(output_path)

    if not force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_10_corpus_cached")
        return output_path

    t0 = time.monotonic()
    docs = _load_manifest(manifest_path)
    structured = _load_structured(structured_path)
    seg_count = _load_segment_counts(segments_path)

    total_words = sum(d.word_count for d in docs)
    total_chars = sum(d.char_count for d in docs)
    total_bytes = sum(d.size_bytes for d in docs)

    size_bins: dict[str, int] = {
        "< 100": 0,
        "100-500": 0,
        "500-2000": 0,
        "2000-10000": 0,
        "> 10000": 0,
    }
    for d in docs:
        w = d.word_count
        if w < 100:
            size_bins["< 100"] += 1
        elif w < 500:
            size_bins["100-500"] += 1
        elif w < 2000:
            size_bins["500-2000"] += 1
        elif w <= 10000:
            size_bins["2000-10000"] += 1
        else:
            size_bins["> 10000"] += 1

    type_counts: Counter[str] = Counter()
    for d in docs:
        rec = structured.get(d.doc_id)
        label = rec.doc_type_guess.label if rec else "unklar"
        type_counts[label] += 1

    if cleaned_path and cleaned_path.exists():
        lang_map = _load_language_map(cleaned_path)
        lang_counts: Counter[str] = Counter(lang_map.values())
        lang_rows = "\n".join(f"| {lang} | {cnt} |" for lang, cnt in lang_counts.most_common())
        lang_section = f"| Sprache | Anzahl |\n|---|---|\n{lang_rows}"
    else:
        lang_section = "_Nicht analysiert (cleaned_documents.jsonl nicht verfügbar)_"

    sorted_docs = sorted(docs, key=lambda d: d.word_count, reverse=True)
    top_long = sorted_docs[:10]
    non_empty = [d for d in docs if d.word_count > 0]
    top_short = sorted(non_empty, key=lambda d: d.word_count)[:10]

    type_rows = "\n".join(
        f"| {t} | {cnt} | {cnt / len(docs) * 100:.1f}% |" for t, cnt in type_counts.most_common()
    )
    long_rows = "\n".join(f"| {d.filename} | {d.word_count:,} |" for d in top_long)
    short_rows = "\n".join(f"| {d.filename} | {d.word_count:,} |" for d in top_short)

    content = f"""---
title: Korpus-Bericht
slug: corpus-report
status: stable
generated: {_iso_date()}
pipeline_version: {pipeline_version}
---

# Korpus-Bericht

## Übersicht
- Files gesamt: {len(docs):,}
- Dateigröße gesamt: {total_bytes / 1_048_576:.1f} MB
- Wörter gesamt: {total_words:,}
- Zeichen gesamt: {total_chars:,}
- Segmente gesamt: {seg_count:,}

## Doc-Typ-Verteilung (heuristisch)
| Typ | Anzahl | Anteil |
|---|---|---|
{type_rows}

## Sprach-Verteilung (heuristisch, Stoppwort-Analyse)
{lang_section}

## Größen-Verteilung
| Bereich | Anzahl |
|---|---|
| < 100 Wörter | {size_bins["< 100"]} |
| 100-500 | {size_bins["100-500"]} |
| 500-2000 | {size_bins["500-2000"]} |
| 2000-10000 | {size_bins["2000-10000"]} |
| > 10000 | {size_bins["> 10000"]} |

## Top-10 längste Files
| Datei | Wörter |
|---|---|
{long_rows}

## Top-10 kürzeste Files
| Datei | Wörter |
|---|---|
{short_rows}
"""
    output_path.write_text(content.strip() + "\n", encoding="utf-8")
    _write_meta(
        meta_path,
        input_hash,
        output_path,
        "phase_10_corpus_report",
        pipeline_version,
        time.monotonic() - t0,
    )
    log.info("phase_10_corpus_done", docs=len(docs), segments=seg_count)
    return output_path


def generate_duplicate_report(
    exact_path: Path,
    edges_path: Path,
    output_path: Path,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> Path:
    """Generiert duplicate_report.md aus Phase-5-Outputs."""
    input_hash = _combined_hash([exact_path, edges_path])
    meta_path = _meta_path_for(output_path)

    if not force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_10_duplicate_cached")
        return output_path

    t0 = time.monotonic()
    exact_groups = _load_exact_duplicates(exact_path)
    edges = _load_edges(edges_path)
    sims = [e.similarity for e in edges]

    affected_docs = sum(len(g.doc_ids) for g in exact_groups)

    bins: dict[str, int] = {"0.72-0.80": 0, "0.80-0.90": 0, "0.90-0.99": 0, "1.00": 0}
    for s in sims:
        if s >= 1.0:
            bins["1.00"] += 1
        elif s >= 0.90:
            bins["0.90-0.99"] += 1
        elif s >= 0.80:
            bins["0.80-0.90"] += 1
        else:
            bins["0.72-0.80"] += 1

    exact_rows = (
        "\n".join(f"| {i + 1} | {', '.join(g.doc_ids)} |" for i, g in enumerate(exact_groups))
        or "| — | keine exakten Duplikate gefunden |"
    )
    exact_header = f"""| Gruppe | Files |
|---|---|
{exact_rows}"""

    top10_edges = sorted(edges, key=lambda e: e.similarity, reverse=True)[:10]
    edge_rows = (
        "\n".join(
            f"| {e.segment_id_a} | {e.segment_id_b} | {e.similarity:.3f} |" for e in top10_edges
        )
        or "| — | — | — |"
    )

    content = f"""---
title: Duplikat-Bericht
slug: duplicate-report
status: stable
generated: {_iso_date()}
pipeline_version: {pipeline_version}
---

# Duplikat-Bericht

## Exakte Duplikate (SHA-256)
- Anzahl Gruppen: {len(exact_groups)}
- Betroffene Files: {affected_docs}

{exact_header}

## Nahe Duplikate (TF-IDF Cosine ≥ 0.72)
- Anzahl Kanten: {len(edges)}

### Top-10 nach Similarity
| Segment A | Segment B | Similarity |
|---|---|---|
{edge_rows}

## Verteilung
| Bereich | Kanten |
|---|---|
| 0.72-0.80 | {bins["0.72-0.80"]} |
| 0.80-0.90 | {bins["0.80-0.90"]} |
| 0.90-0.99 | {bins["0.90-0.99"]} |
| 1.00 (identisch auf Segment-Ebene) | {bins["1.00"]} |
"""
    output_path.write_text(content.strip() + "\n", encoding="utf-8")
    _write_meta(
        meta_path,
        input_hash,
        output_path,
        "phase_10_duplicate_report",
        pipeline_version,
        time.monotonic() - t0,
    )
    log.info("phase_10_duplicate_done", groups=len(exact_groups), edges=len(edges))
    return output_path


def generate_cluster_report(
    clusters_path: Path,
    batches_dir: Path,
    edges_path: Path,
    output_path: Path,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> Path:
    """Generiert cluster_report.md (Gate-1-Input) aus Phase-6/7-Outputs."""
    input_paths = [clusters_path, edges_path, *sorted(batches_dir.glob("batch_*.md"))]
    input_hash = _combined_hash(input_paths)
    meta_path = _meta_path_for(output_path)

    if not force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_10_cluster_cached")
        return output_path

    t0 = time.monotonic()
    clusters = _load_clusters(clusters_path)
    edges = _load_edges(edges_path)
    batch_infos = _load_batch_infos(batches_dir)

    named = [c for c in clusters if c.cluster_id != _UNSORTED_ID]
    unsorted_cluster = next((c for c in clusters if c.cluster_id == _UNSORTED_ID), None)
    unsorted_segs = len(unsorted_cluster.segment_ids) if unsorted_cluster else 0

    doc_counts: dict[str, int] = {}
    for c in named:
        unique_docs = {_doc_id_from_segment_id(s) for s in c.segment_ids}
        doc_counts[c.cluster_id] = len(unique_docs)

    micro = [c for c in named if doc_counts.get(c.cluster_id, 0) < 3]
    large = [c for c in named if doc_counts.get(c.cluster_id, 0) >= 3]
    hist = _cluster_size_histogram(clusters, doc_counts)

    top20 = sorted(named, key=lambda c: doc_counts.get(c.cluster_id, 0), reverse=True)[:20]

    # Summe Token-Estimates pro Cluster aus Batch-Files
    cluster_tokens: dict[str, int] = {}
    for b in batch_infos:
        cid = str(b.get("cluster_id", ""))
        cluster_tokens[cid] = cluster_tokens.get(cid, 0) + int(b.get("token_estimate", 0))

    seg_cluster = _build_seg_cluster_map(clusters)
    intra, inter = _count_intra_inter(edges, seg_cluster)

    top20_rows = "\n".join(
        f"| {c.cluster_id} | {c.label_guess[:40]} | {doc_counts.get(c.cluster_id, 0)} "
        f"| {len(c.segment_ids)} | {cluster_tokens.get(c.cluster_id, 0):,} |"
        for c in top20
    )
    micro_rows = (
        "\n".join(
            f"| {c.cluster_id} | {c.label_guess[:40]} | {doc_counts.get(c.cluster_id, 0)} |"
            for c in micro
        )
        or "| — | keine Mikrocluster | — |"
    )

    smoke_candidate = _smoke_test_candidate(batch_infos)

    batch_token_estimates = [int(b.get("token_estimate", 0)) for b in batch_infos]
    mean_tokens = (
        int(sum(batch_token_estimates) / len(batch_token_estimates)) if batch_token_estimates else 0
    )
    max_batch = max(batch_infos, key=lambda b: int(b.get("token_estimate", 0)), default=None)
    min_batch = min(batch_infos, key=lambda b: int(b.get("token_estimate", 0)), default=None)

    content = f"""---
title: Cluster-Bericht (Gate-1-Input)
slug: cluster-report
status: stable
generated: {_iso_date()}
pipeline_version: {pipeline_version}
---

# Cluster-Bericht — Review-Gate 1

## Übersicht
- Cluster gesamt: {len(named)}
- davon mit ≥ 3 Docs: {len(large)}
- Mikrocluster (< 3 Docs): {len(micro)}
- Unsortiert (`C_unsortiert`): {unsorted_segs} Segmente

## Cluster-Größen-Histogramm (Docs, ohne C_unsortiert)
| Docs/Cluster | Anzahl Cluster |
|---|---|
| 1 | {hist["1"]} |
| 2 | {hist["2"]} |
| 3-5 | {hist["3-5"]} |
| 6-10 | {hist["6-10"]} |
| 11-50 | {hist["11-50"]} |
| > 50 | {hist["> 50"]} |

## Top-20 Cluster nach Doc-Count
| Cluster-ID | Label-Guess | Docs | Segmente | Token-Estimate |
|---|---|---|---|---|
{top20_rows}

## Mikrocluster-Liste
| Cluster-ID | Label-Guess | Docs |
|---|---|---|
{micro_rows}

## Batch-Übersicht
- Batches gesamt: {len(batch_infos)}
- Batch mit größtem Token-Estimate: {max_batch.get("batch_id", "—") if max_batch else "—"} ({max(batch_token_estimates, default=0)} Tokens)
- Batch mit kleinstem Token-Estimate: {min_batch.get("batch_id", "—") if min_batch else "—"}
- Mittlere Token-Estimate: {mean_tokens}
- Empfehlung Smoke-Test: `{smoke_candidate}`

## Nahe-Duplikat-Verteilung
- Kanten innerhalb gleicher Cluster: {intra}
- Kanten zwischen verschiedenen Clustern: {inter} (potenziell falsche Cluster-Zuordnung)

## Re-Run-Befehl
```bash
python -m pipeline run --from-phase 6 --force
```
"""
    output_path.write_text(content.strip() + "\n", encoding="utf-8")
    _write_meta(
        meta_path,
        input_hash,
        output_path,
        "phase_10_cluster_report",
        pipeline_version,
        time.monotonic() - t0,
    )
    log.info(
        "phase_10_cluster_done", clusters=len(named), micro=len(micro), batches=len(batch_infos)
    )
    return output_path


def _smoke_test_candidate(batch_infos: list[dict[str, Any]]) -> str:
    """Wählt kleinsten Batch mit 5-10 Segmenten als Smoke-Test-Kandidat."""
    candidates = [b for b in batch_infos if 5 <= int(b.get("segment_count", 0)) <= 10]
    if candidates:
        best = min(candidates, key=lambda b: int(b.get("token_estimate", 999999)))
        return str(best.get("batch_id", "—"))
    # Fallback: kleinster Batch
    if batch_infos:
        fallback = min(batch_infos, key=lambda b: int(b.get("segment_count", 999999)))
        return str(fallback.get("batch_id", "—"))
    return "—"


# === Orchestrator =============================================================


def run_phase_10(
    manifest_path: Path,
    structured_path: Path,
    segments_path: Path,
    exact_path: Path,
    edges_path: Path,
    clusters_path: Path,
    batches_dir: Path,
    output_dir: Path,
    cleaned_path: Path | None = None,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> dict[str, Any]:
    """Orchestriert alle drei Report-Generatoren.

    Args:
        manifest_path: files_manifest.jsonl (Phase 1)
        structured_path: documents_structured.jsonl (Phase 3)
        segments_path: segments.jsonl (Phase 4)
        exact_path: exact_duplicates.json (Phase 5)
        edges_path: near_duplicate_edges.jsonl (Phase 5)
        clusters_path: cluster_proposals.json (Phase 6)
        batches_dir: Verzeichnis mit batch_*.md (Phase 7)
        output_dir: Zielverzeichnis für Reports
        cleaned_path: cleaned_documents.jsonl (optional, für Sprach-Heuristik)
        force: Cache ignorieren
        pipeline_version: Version-String

    Returns:
        Summary-Dict mit reports_generated, report_paths, duration_seconds.
    """
    t0 = time.monotonic()

    corpus_out = output_dir / "corpus_report.md"
    dup_out = output_dir / "duplicate_report.md"
    cluster_out = output_dir / "cluster_report.md"

    generate_corpus_report(
        manifest_path=manifest_path,
        structured_path=structured_path,
        segments_path=segments_path,
        output_path=corpus_out,
        cleaned_path=cleaned_path,
        force=force,
        pipeline_version=pipeline_version,
    )
    generate_duplicate_report(
        exact_path=exact_path,
        edges_path=edges_path,
        output_path=dup_out,
        force=force,
        pipeline_version=pipeline_version,
    )
    generate_cluster_report(
        clusters_path=clusters_path,
        batches_dir=batches_dir,
        edges_path=edges_path,
        output_path=cluster_out,
        force=force,
        pipeline_version=pipeline_version,
    )

    return {
        "reports_generated": 3,
        "report_paths": [str(corpus_out), str(dup_out), str(cluster_out)],
        "duration_seconds": round(time.monotonic() - t0, 2),
    }
