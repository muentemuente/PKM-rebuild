"""Tests für WP3c-5 — Draft → Vault-Promotion (D4).

Alle Tests laufen auf einem tmp-Vault; der Live-Brain-Vault wird nie berührt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pipeline.promotion import (
    PromotionError,
    execute_promotion,
    plan_promotion,
)

_TODAY = "2026-06-22"


def _complete_fm(
    slug: str = "test-artikel", review: str = "human_reviewed", **over: Any
) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "title": "Test Artikel",
        "slug": slug,
        "summary": "Eine Zusammenfassung des Artikels.",
        "type": "knowledge-article",
        "doc_role": ["explanation"],
        "category": "grundlagen",
        "tags": ["test"],
        "sources_docs": ["D_x"],
        "source_chunks": ["D_x-S0000"],
        "status": "draft",
        "review_status": review,
        "confidence": "high",
        "doc_version": "0.1.0",
        "created": "2026-06-01",
        "updated": "2026-06-01",
        "last_synthesized": "2026-06-01",
        "prompt_version": "v2",
        "type_source": "frontmatter",
        "restructure_action": "rewrite",
        "provenance": {
            "source": slug,
            "model": "qwen/qwen3.6-27b",
            "prompt_version": "v2",
            "type_source": "frontmatter",
            "generated_at": "2026-06-20T00:00:00+00:00",
        },
    }
    fm.update(over)
    return fm


def _write_md(path: Path, fm: dict[str, Any], body: str = "# Titel\n\nInhalt.") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{dumped}---\n\n{body}\n", encoding="utf-8")
    return path


def _vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


def _parse(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    fm = text.split("---\n", 2)[1]
    return yaml.safe_load(fm)


# === Gate =====================================================================


def test_gate_ai_drafted_aborts_no_write(tmp_path: Path) -> None:
    """ai_drafted → PromotionError, kein Write."""
    vault = _vault(tmp_path)
    draft = _write_md(tmp_path / "drafts" / "d.md", _complete_fm(review="ai_drafted"))
    with pytest.raises(PromotionError, match="review_status"):
        plan_promotion(draft, vault, today=_TODAY)
    assert list(vault.rglob("*.md")) == []  # nichts geschrieben


# === doc_type-Override (MOC → 00_Maps, status bleibt draft) ===================


def test_moc_doc_type_routes_to_maps_and_keeps_draft(tmp_path: Path) -> None:
    """doc_type: moc → 00_Maps (Override vor category), status bleibt draft."""
    vault = _vault(tmp_path)
    fm = _complete_fm(
        slug="moc-test",
        doc_type="moc",
        category="grundlagen",  # würde sonst nach 01_Grundlagen routen
        moc_members=["a", "b", "c"],
    )
    draft = _write_md(tmp_path / "drafts" / "moc-test.md", fm)
    plan = plan_promotion(draft, vault, today=_TODAY)

    # Override greift VOR dem category-Mapping
    assert plan.folder == "00_Maps"
    assert plan.target_path == vault / "00_Maps" / "moc-test.md"
    assert plan.collision is False
    assert plan.is_update is False

    report = execute_promotion(plan, vault, archive_dir=tmp_path / "archive")
    out = _parse(report.target_path)
    assert out["status"] == "draft"  # NICHT auf review gehoben (PRESERVE_STATUS_DOC_TYPES)
    assert out["doc_type"] == "moc"
    assert out["category"] == "grundlagen"  # category bleibt Metadatum
    assert report.folder == "00_Maps"


# === Neu-Anlage + Finalisierung ===============================================


def test_human_reviewed_target_folder_ssot_and_finalize(tmp_path: Path) -> None:
    """human_reviewed → Ziel-Ordner aus category-SSoT, Frontmatter finalisiert."""
    vault = _vault(tmp_path)
    draft = _write_md(tmp_path / "drafts" / "test-artikel.md", _complete_fm())
    plan = plan_promotion(draft, vault, today=_TODAY)

    assert plan.folder == "01_Grundlagen"  # grundlagen → 01_Grundlagen (SSoT)
    assert plan.target_path == vault / "01_Grundlagen" / "test-artikel.md"
    assert plan.collision is False
    assert plan.is_update is False
    assert plan.doc_count_delta == 1

    report = execute_promotion(plan, vault, archive_dir=tmp_path / "archive")
    assert report.target_path.exists()
    fm = _parse(report.target_path)
    assert fm["status"] == "review"  # nie auto-stable
    assert fm["updated"] == _TODAY
    assert fm["review_status"] == "human_reviewed"
    # WP3c-4-Felder erhalten
    assert fm["type_source"] == "frontmatter"
    assert fm["restructure_action"] == "rewrite"
    assert fm["provenance"]["model"] == "qwen/qwen3.6-27b"


def test_archive_and_index_regen(tmp_path: Path) -> None:
    """Nach Promote: Index regeneriert (Ordner) + Draft archiviert."""
    vault = _vault(tmp_path)
    # Bestehender Artikel im Zielordner → Index muss beide zählen.
    _write_md(vault / "01_Grundlagen" / "bestand.md", _complete_fm(slug="bestand"))
    draft = _write_md(tmp_path / "drafts" / "neu.md", _complete_fm(slug="neu"))
    plan = plan_promotion(draft, vault, today=_TODAY)
    report = execute_promotion(plan, vault, archive_dir=tmp_path / "archive")

    idx = vault / "01_Grundlagen" / "_index.md"
    assert idx.exists()
    assert report.index_article_count == 2  # bestand + neu
    assert not draft.exists()  # Draft verschoben
    assert report.archived_draft.exists()
    assert (tmp_path / "archive" / "promoted_drafts" / "neu.md").exists()


# === Kollision ================================================================


def test_collision_abort_blocks_write(tmp_path: Path) -> None:
    """Ziel existiert + on_collision=abort → collision, execute schreibt nicht."""
    vault = _vault(tmp_path)
    existing = _write_md(
        vault / "01_Grundlagen" / "test-artikel.md", _complete_fm(), body="# Alt\n\nAlt."
    )
    before = existing.read_bytes()
    draft = _write_md(tmp_path / "drafts" / "test-artikel.md", _complete_fm(), body="# Neu\n\nNeu.")

    plan = plan_promotion(draft, vault, on_collision="abort", today=_TODAY)
    assert plan.collision is True
    assert plan.is_update is True
    assert plan.diff  # Diff Bestand→promotet vorhanden

    with pytest.raises(PromotionError, match="Kollision"):
        execute_promotion(plan, vault, archive_dir=tmp_path / "archive")
    assert existing.read_bytes() == before  # kein Blind-Overwrite


def test_collision_replace_updates_preserving_existing_taxonomy(tmp_path: Path) -> None:
    """on_collision=replace → Update: Content aus Draft, Taxonomie aus Bestand."""
    vault = _vault(tmp_path)
    existing_fm = _complete_fm(
        slug="test-artikel",
        review="ai_drafted",
        tags=["alt-tag-a", "alt-tag-b"],
        doc_role=["reference"],
        aliases=["Alias-1"],
    )
    _write_md(vault / "01_Grundlagen" / "test-artikel.md", existing_fm, body="# Alt\n\nAlt.")
    draft = _write_md(
        tmp_path / "drafts" / "test-artikel.md",
        _complete_fm(title="Neuer Titel", type_source="reclassified"),
        body="# Neuer Titel\n\nNeuer Body.",
    )

    plan = plan_promotion(draft, vault, on_collision="replace", today=_TODAY)
    assert plan.collision is False
    assert plan.is_update is True
    report = execute_promotion(plan, vault, archive_dir=tmp_path / "archive")

    fm = _parse(report.target_path)
    assert fm["title"] == "Neuer Titel"  # Content-Feld aus Draft
    assert fm["type_source"] == "reclassified"  # Restructure-Feld aus Draft
    assert fm["tags"] == ["alt-tag-a", "alt-tag-b"]  # Taxonomie aus Bestand erhalten
    assert fm["aliases"] == ["Alias-1"]  # Verlinkung aus Bestand erhalten
    assert "Neuer Body." in report.target_path.read_text(encoding="utf-8")


def test_collision_suffix_writes_new_slug(tmp_path: Path) -> None:
    """on_collision=suffix → neuer Slug `_2`, Bestand unberührt."""
    vault = _vault(tmp_path)
    existing = _write_md(vault / "01_Grundlagen" / "test-artikel.md", _complete_fm())
    before = existing.read_bytes()
    draft = _write_md(tmp_path / "drafts" / "test-artikel.md", _complete_fm())

    plan = plan_promotion(draft, vault, on_collision="suffix", today=_TODAY)
    assert plan.target_path.name == "test-artikel_2.md"
    assert plan.collision is False
    execute_promotion(plan, vault, archive_dir=tmp_path / "archive")
    assert (vault / "01_Grundlagen" / "test-artikel_2.md").exists()
    assert existing.read_bytes() == before


# === Dry-run ==================================================================


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """plan_promotion (ohne execute) schreibt nichts; Draft bleibt liegen."""
    vault = _vault(tmp_path)
    draft = _write_md(tmp_path / "drafts" / "test-artikel.md", _complete_fm())
    plan_promotion(draft, vault, today=_TODAY)
    assert list(vault.rglob("*.md")) == []  # kein Write
    assert draft.exists()  # Draft unberührt


def test_incomplete_draft_rejected(tmp_path: Path) -> None:
    """Unvollständiges Frontmatter (Neu-Anlage) → PromotionError (kein Write)."""
    vault = _vault(tmp_path)
    incomplete = _complete_fm()
    del incomplete["doc_role"]  # Pflichtfeld entfernen
    draft = _write_md(tmp_path / "drafts" / "test-artikel.md", incomplete)
    with pytest.raises(PromotionError, match="unvollständig"):
        plan_promotion(draft, vault, today=_TODAY)
    assert list(vault.rglob("*.md")) == []
