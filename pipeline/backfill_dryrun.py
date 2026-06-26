"""WP-A1a — Deterministischer Backfill-Dry-Run für ``keyphrases`` (read-only).

Berechnet für jede Bestands-Note die ``keyphrases`` (N2-Extraktor, identische Config)
und klassifiziert, **was** ein späterer D4-Write (A1b) täte — **ohne** zu schreiben.
Reines Vorschau-Artefakt; kein Vault-Write, kein Qwen, keine Mutation.

Wiederverwendung: :func:`pipeline.keyphrase.extract_keyphrases` (N2-Extraktor) +
:func:`pipeline.vault_audit.build_index` (vorhandene Note-Discovery). **Kein** zweiter
Extraktor, **keine** neue Glob-Logik.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.keyphrase import extract_keyphrases
from pipeline.vault_audit import build_index, split_frontmatter

#: Klassifikations-Bänder einer Note im Dry-Run.
KLASS_ADD = "would-add"
KLASS_UNCHANGED = "unchanged"
KLASS_CHANGE = "would-change"
KLASS_SKIP_EMPTY = "skip-empty"

Extractor = Callable[[str], list[str]]


@dataclass(frozen=True)
class NoteResult:
    """Dry-Run-Befund für eine einzelne Note."""

    relpath: str
    klass: str
    new: list[str]
    old: list[str]


def _existing_keyphrases(fm: dict[str, Any] | None) -> list[str]:
    """Liest vorhandene ``keyphrases`` aus dem Frontmatter (robust gegen Typen)."""
    if not fm:
        return []
    raw = fm.get("keyphrases")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def classify(existing: list[str], computed: list[str]) -> str:
    """Ordnet eine Note einem Dry-Run-Band zu (idempotenz-bewusst)."""
    if not computed:
        return KLASS_SKIP_EMPTY
    if not existing:
        return KLASS_ADD
    if existing == computed:
        return KLASS_UNCHANGED
    return KLASS_CHANGE


def run_keyphrase_dryrun(
    vault_dir: Path,
    *,
    top_n: int = 8,
    extractor: Extractor | None = None,
) -> list[NoteResult]:
    """Berechnet den Dry-Run über alle Content-Notes (read-only).

    Args:
        vault_dir: Wurzel des produktiven Vaults.
        top_n: Keyphrase-Top-N (identisch zur N2-Config ``keyphrase_top_n``).
        extractor: Injizierbarer Extraktor (Tests); ``None`` → N2-KeyBERT-Extraktor.

    Returns:
        Pro Note ein :class:`NoteResult` (sortiert nach Pfad).
    """
    extract = extractor or (lambda body: extract_keyphrases(body, top_n=top_n))
    index = build_index(vault_dir)
    out: list[NoteResult] = []
    for rel in sorted(index.audit_files):
        text = index.audit_files[rel]
        _, body, _ = split_frontmatter(text)
        computed = extract(body)
        existing = _existing_keyphrases(index.frontmatter.get(rel))
        out.append(NoteResult(rel, classify(existing, computed), computed, existing))
    return out


def summarize(results: list[NoteResult]) -> dict[str, int]:
    """Zählt Notes je Klasse."""
    counts = {KLASS_ADD: 0, KLASS_UNCHANGED: 0, KLASS_CHANGE: 0, KLASS_SKIP_EMPTY: 0}
    for r in results:
        counts[r.klass] = counts.get(r.klass, 0) + 1
    return counts


def render_report(
    results: list[NoteResult],
    *,
    today: str,
    fx1_commit: str,
    roundtrip: str,
    top_n: int,
) -> str:
    """Rendert das Preview-Artefakt im Soll-Format (Markdown)."""
    counts = summarize(results)
    total = len(results)
    lines = [
        f"# Backfill Dry-Run — keyphrases ({today})",
        "",
        "> Read-only Vorschau (WP-A1a). **Kein Vault-Write.** Entscheidungsgrundlage für A1b (D4).",
        "",
        "## Vorbedingung",
        f"- FX1 gemergt: {fx1_commit} · Roundtrip: {roundtrip}",
        "",
        "## Zusammenfassung",
        f"- Notes gesamt: {total}",
        f"- would-add: {counts[KLASS_ADD]} · unchanged: {counts[KLASS_UNCHANGED]} · "
        f"would-change: {counts[KLASS_CHANGE]} · skip-empty: {counts[KLASS_SKIP_EMPTY]}",
        f"- Extraktor-Config: keyphrase_top_n={top_n}, Modell=mpnet (deterministisch, kein Qwen)",
        "",
        "## Detail (pro Note)",
        "| Note | Klasse | keyphrases (neu) | (alt, falls would-change) |",
        "|------|--------|------------------|---------------------------|",
    ]
    for r in results:
        new = ", ".join(r.new) if r.new else "—"
        old = ", ".join(r.old) if r.klass == KLASS_CHANGE else ""
        lines.append(f"| {r.relpath} | {r.klass} | {new} | {old} |")
    skip = [r.relpath for r in results if r.klass == KLASS_SKIP_EMPTY]
    change = [r.relpath for r in results if r.klass == KLASS_CHANGE]
    lines += [
        "",
        "## Auffälligkeiten",
        f"- skip-empty (Body zu kurz → kein Write): {len(skip)}"
        + (f" — {', '.join(skip)}" if skip else ""),
        f"- would-change (Owner prüfen): {len(change)}"
        + (f" — {', '.join(change)}" if change else ""),
    ]
    return "\n".join(lines) + "\n"
