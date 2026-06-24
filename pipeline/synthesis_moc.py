"""WP3b — additive MOC-Generierung aus freigegebenen Synthese-Clustern (D6, RV13).

Erzeugt pro freigegebenem Cluster **ein neues** MOC-Dokument (Map of Content) in
**Staging** (`drafts/`). Strikt **additiv**: Quell-Artikel werden nie gelesen-und-kopiert
(nur ihr **Frontmatter** — Titel + `summary` — als Descriptor, RV13), nie verändert,
``merged_from`` bleibt leer. Kein Body-Transfer, kein Auto-Promotion.

Generierung ist überwiegend **deterministisch** (Anti-Halluzination): Link-Descriptoren
kommen 1:1 aus dem realen ``summary``-Frontmatter des Ziel-Docs. Nur die 2-3-Satz-Rahmung
(„was verbindet die Docs") wird per Qwen formuliert (injizierbarer ``FramingFn``,
Reasoning aus via ``/no_think`` + Strip, max_tokens-Cap). Schlägt das fehl, greift eine
deterministische Fallback-Rahmung und das MOC wird ``needs_human`` markiert.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()

_FM_DELIM = "---\n"
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Rahmung: (title, members) -> Prosa | None (None = Qwen-Fehler/Timeout → Fallback).
FramingFn = Callable[[str, list["Member"]], str | None]


@dataclass
class Member:
    """Ein Cluster-Mitglied — ausschließlich aus dem realen Ziel-Frontmatter (RV13)."""

    slug: str
    title: str
    summary: str
    category: str = ""
    found: bool = True


@dataclass
class ApprovedCluster:
    """Eine vom Owner (Gate A) freigegebene Cluster-Definition."""

    title: str  # kanonischer MOC-Titel (Owner-Adjudikation)
    candidate_id: str  # SC_xxx aus dem Re-Scan-Report
    member_slugs: list[str]
    mean_similarity: float
    redundancy_note: str = ""  # optionaler „→ WP4"-Hinweis


@dataclass
class MocResult:
    """Ergebnis einer MOC-Generierung (für Report + Datei-Write)."""

    title: str
    slug: str
    text: str
    confidence: str
    review_status: str
    framing_source: str  # "qwen" | "deterministic"
    missing_members: list[str] = field(default_factory=list)


# === Frontmatter-Lesen (read-only) ============================================


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith(_FM_DELIM):
        return {}, text
    m = re.search(r"\n---\s*\n", text[4:])
    if not m:
        return {}, text
    import yaml

    fm = yaml.safe_load(text[4 : 4 + m.start()])
    return (fm if isinstance(fm, dict) else {}), text[4 + m.end() :]


def load_member(vault_dir: Path, slug: str) -> Member:
    """Liest Titel + ``summary`` + ``category`` eines Vault-Docs (read-only, kein Body-Kopieren).

    Sucht die Datei per Frontmatter-``slug`` bzw. Dateinamen. Nicht gefunden →
    ``found=False`` (das MOC wird dann ``needs_human``).
    """
    for p in sorted(vault_dir.rglob(f"{slug}.md")):
        if "_attic" in p.parts:
            continue
        fm, _ = _split_frontmatter(p.read_text(encoding="utf-8"))
        return Member(
            slug=str(fm.get("slug") or slug),
            title=str(fm.get("title") or slug),
            summary=str(fm.get("summary") or "").strip(),
            category=str(fm.get("category") or ""),
        )
    log.warning("moc_member_not_found", slug=slug)
    return Member(slug=slug, title=slug, summary="", found=False)


# === Rahmung ==================================================================


def strip_reasoning(text: str) -> str:
    """Entfernt ``<think>…</think>``-Blöcke (Reasoning-Modell) + trimmt."""
    return _THINK_RE.sub("", text).strip()


def deterministic_framing(title: str, members: list[Member]) -> str:
    """Faktische Fallback-Rahmung ohne LLM (keine erfundenen Aussagen)."""
    n = len(members)
    return (
        f"Diese Übersicht bündelt {n} thematisch verwandte Artikel zum Thema „{title}“, "
        "die über semantische Nähe als zusammengehörig erkannt wurden. Sie ersetzt keinen "
        "der Quell-Artikel — jeder bleibt eigenständig; diese Seite verlinkt sie nur und "
        "ordnet sie ein."
    )


_FRAMING_PROMPT = """/no_think
Du formulierst die kurze Einleitung einer thematischen Übersichtsseite (MOC) in einem
deutschsprachigen Wissens-Vault. Schreibe 2-3 Sätze, die erklären, was die folgenden
Artikel thematisch verbindet. NUR auf Basis der gegebenen Titel und Zusammenfassungen —
erfinde keine Fakten, nenne keine Inhalte, die nicht unten stehen. Fließtext, keine
Aufzählung, kein Markdown, keine Überschrift.

Thema: {title}

Artikel:
{members}
"""


def make_qwen_framer(
    *,
    endpoint: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 600,
    timeout: int = 600,
    summary_cap: int = 600,
) -> FramingFn:
    """Baut einen Qwen-Rahmer (LM-Studio/OpenAI-kompatibel). Fehler/Timeout → ``None``."""
    import openai

    client = openai.OpenAI(base_url=endpoint, api_key="not-needed", timeout=timeout)

    def _frame(title: str, members: list[Member]) -> str | None:
        block = "\n".join(f"- {m.title}: {m.summary[:summary_cap]}" for m in members if m.found)
        prompt = _FRAMING_PROMPT.format(title=title, members=block)
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover - Netzwerk/Endpoint
            log.warning("moc_framing_failed", title=title, error=str(exc)[:200])
            return None
        prose = strip_reasoning(raw)
        return prose or None

    return _frame


# === MOC-Bau (pure) ===========================================================


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"moc-{s}"


def _confidence_and_status(
    mean_similarity: float, framing_source: str, missing: list[str]
) -> tuple[str, str]:
    """Confidence + review_status aus Cluster-Güte + Rahmungs-Quelle ableiten."""
    if missing or framing_source == "deterministic":
        # Unsichere Rahmung oder fehlendes Mitglied → menschliche Prüfung Pflicht.
        confidence = "medium" if mean_similarity >= 0.70 else "low"
        return confidence, "needs_human"
    confidence = "high" if mean_similarity >= 0.70 else "medium"
    return confidence, "ai_drafted"


def build_moc(
    cluster: ApprovedCluster, members: list[Member], framing: str | None, *, today: str
) -> MocResult:
    """Rendert ein vollständiges MOC-Dokument (Frontmatter + Rahmung + Wikilinks)."""
    missing = [m.slug for m in members if not m.found]
    framing_source = "qwen" if framing else "deterministic"
    prose = framing or deterministic_framing(cluster.title, members)
    confidence, review_status = _confidence_and_status(
        cluster.mean_similarity, framing_source, missing
    )
    slug = _slugify(cluster.title)
    # dominante category der Mitglieder (Mehrheit), nur informativ
    cats = [m.category for m in members if m.category]
    category = max(set(cats), key=cats.count) if cats else ""
    n_found = sum(1 for m in members if m.found)
    # Deterministische MOC-Summary (Metadaten, kein LLM): beschreibt die Map, nicht den Inhalt.
    summary = (
        f"Themen-Übersicht (MOC) zu {cluster.title}: verlinkt {n_found} "
        "thematisch verwandte Artikel."
    )

    fm = [
        "---",
        f"title: {cluster.title}",
        f"slug: {slug}",
        f"summary: {summary}",
        "doc_type: moc",
        "type: knowledge-article",
        "doc_role:",
        "  - index",
        "status: draft",
        f"review_status: {review_status}",
        f"confidence: {confidence}",
        f"category: {category}",
        "tags: []",
        f"synthesis_candidate: {cluster.candidate_id}",
        f"mean_similarity: {cluster.mean_similarity}",
        "moc_members:",
        *[f"  - {m.slug}" for m in members],
        # MOC referenziert via moc_members/Wikilinks, nicht via Korpus-Quellen → leer.
        "sources_docs: []",
        "source_chunks: []",
        "merged_from: []",
        f"created: '{today}'",
        f"updated: '{today}'",
        "prompt_version: moc-v1",
        f"framing_source: {framing_source}",
        "---",
    ]
    body = [
        "",
        prose,
        "",
        "## Artikel in dieser Übersicht",
        "",
    ]
    for m in members:
        if m.found:
            desc = m.summary or "_(keine Zusammenfassung im Frontmatter)_"
            body.append(f"- [[{m.slug}|{m.title}]] — {desc}")
        else:
            body.append(f"- `{m.slug}` — ⚠️ Ziel-Doc nicht gefunden (Review)")
    if cluster.redundancy_note:
        body += ["", "## Hinweise", "", f"- {cluster.redundancy_note}"]
    body.append("")

    text = "\n".join(fm) + "\n" + "\n".join(body)
    return MocResult(
        title=cluster.title,
        slug=slug,
        text=text,
        confidence=confidence,
        review_status=review_status,
        framing_source=framing_source,
        missing_members=missing,
    )


def generate_mocs(
    clusters: list[ApprovedCluster],
    vault_dir: Path,
    out_dir: Path,
    *,
    framer: FramingFn | None,
    today: str,
) -> list[MocResult]:
    """Erzeugt für jeden freigegebenen Cluster ein MOC in ``out_dir`` (Staging)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[MocResult] = []
    for cl in clusters:
        members = [load_member(vault_dir, s) for s in cl.member_slugs]
        framing = framer(cl.title, members) if framer else None
        result = build_moc(cl, members, framing, today=today)
        (out_dir / f"{result.slug}.md").write_text(result.text, encoding="utf-8")
        log.info(
            "moc_written",
            slug=result.slug,
            confidence=result.confidence,
            review_status=result.review_status,
            framing=result.framing_source,
        )
        results.append(result)
    return results
