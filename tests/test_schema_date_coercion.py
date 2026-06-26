"""Tests für WP-FX1 — Date-Coercion in FrontmatterDraft (created/updated/last_synthesized).

YAML parst unquotierte Datumswerte zu ``date``-Objekten; das Schema erwartet ``str``.
Der ``mode="before"``-Validator coerct date/datetime → kanonisches ``YYYY-MM-DD`` und
lässt korrekte Strings + ``None`` unverändert. Der 166er-Roundtrip belegt, dass der
spätere D4-Backfill (A1) nicht mehr an den 5 betroffenen Notes scheitert.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.schemas import FrontmatterDraft

_FM_BASE = {
    "title": "Test",
    "slug": "test",
    "summary": "Ein Test-Konzept.",
    "type": "knowledge-article",
    "doc_role": ["explanation"],
    "category": "grundlagen",
    "tags": ["test"],
    "sources_docs": ["D_test"],
    "source_chunks": ["D_test-S0000"],
    "status": "draft",
    "review_status": "ai_drafted",
    "confidence": "medium",
    "doc_version": "0.1.0",
    "created": "2026-05-27",
    "updated": "2026-05-27",
    "last_synthesized": "2026-05-27",
    "prompt_version": "v1",
}


def _fm(**overrides: object) -> FrontmatterDraft:
    return FrontmatterDraft.model_validate({**_FM_BASE, **overrides})


def test_date_object_coerced_to_iso_string() -> None:
    fm = _fm(created=date(2026, 6, 26))
    assert fm.created == "2026-06-26"
    assert isinstance(fm.created, str)


def test_datetime_object_coerced_to_date_only_string() -> None:
    fm = _fm(updated=datetime(2026, 6, 26, 14, 30, 0))
    assert fm.updated == "2026-06-26"


def test_correct_string_passes_through_unchanged() -> None:
    fm = _fm(created="2024-01-15")
    assert fm.created == "2024-01-15"  # kein Reparse/Reformat


def test_all_three_date_fields_coerced() -> None:
    fm = _fm(
        created=date(2024, 1, 1),
        updated=date(2025, 2, 2),
        last_synthesized=datetime(2026, 3, 3, 9, 0),
    )
    assert (fm.created, fm.updated, fm.last_synthesized) == (
        "2024-01-01",
        "2025-02-02",
        "2026-03-03",
    )


def test_empty_string_unchanged() -> None:
    fm = _fm(created="")
    assert fm.created == ""


# === 166er-Roundtrip über den realen Bestand (read-only) ======================


def test_full_vault_roundtrip_validates() -> None:
    """Alle Content-Notes des Brain-Vaults validieren nach der Coercion (166/166)."""
    from pipeline import _paths
    from pipeline.vault_audit import parse_frontmatter, split_frontmatter

    vault = _paths.BRAIN_VAULT
    if not vault.is_dir():
        pytest.skip(f"Brain-Vault nicht verfügbar: {vault}")
    notes = [
        p
        for p in vault.rglob("*.md")
        if p.name != "_index.md"
        and not any(x in p.parts for x in ("_attic", "_assets", "00_Meta"))
    ]
    if not notes:
        pytest.skip("Brain-Vault enthält keine Content-Notes")
    failures: list[tuple[str, str]] = []
    for p in notes:
        fm_text, _, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        if not fm_text:
            continue
        data, _ = parse_frontmatter(fm_text)
        if data is None:
            continue
        try:
            FrontmatterDraft.model_validate(data)
        except Exception as exc:  # Befund sammeln, nicht abbrechen
            failures.append((p.name, str(exc)[:120]))
    assert not failures, f"{len(failures)}/{len(notes)} Notes scheitern: {failures[:5]}"
