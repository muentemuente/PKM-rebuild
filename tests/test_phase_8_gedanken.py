"""Tests fuer den Gedanken-Sonderpfad in Phase 8 (Block 0G.6).

Akzeptanzkriterien:
  - Gedanken-Files werden korrekt erkannt (doc_type_guess.label == "gedanke")
  - Stage 3 wird fuer Gedanken uebersprungen (Body = Original-Text)
  - Stage 4 verwendet den Gedanken-Prompt (stage4_frontmatter_gedanken.md)
  - FrontmatterDraft-Validation erzwingt type="gedanke", category="gedanken"
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.phase_8_synthesis import (
    _build_gedanken_body,
    _load_gedanken_doc_ids,
    _QwenStageConfig,
    _run_stage4_gedanken,
)
from pipeline.schemas import (
    DocTypeGuess,
    FrontmatterDraft,
    SegmentRecord,
    StructuredDocumentRecord,
)

# === Fixtures =================================================================


def _make_segment(doc_id: str, idx: int = 0, text: str = "Test-Text.") -> SegmentRecord:
    return SegmentRecord(
        segment_id=f"{doc_id}-S{idx:04d}",
        doc_id=doc_id,
        source_path=f"corpus/{doc_id}.md",
        heading_path=["Test-Heading"],
        segment_index=idx,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        contains_code=False,
        contains_table=False,
    )


def _make_structured_doc(doc_id: str, label: str) -> StructuredDocumentRecord:
    return StructuredDocumentRecord(
        doc_id=doc_id,
        title="Test",
        headings=[],
        code_blocks=[],
        tables_count=0,
        links=[],
        images=[],
        doc_type_guess=DocTypeGuess(label=label, confidence=0.9, signals=["test"]),
    )


def _write_structured_jsonl(path: Path, records: list[StructuredDocumentRecord]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(rec.model_dump_json() + "\n")


# === Test: _load_gedanken_doc_ids =============================================


def test_load_gedanken_doc_ids_detects_gedanke(tmp_path: Path) -> None:
    """Gedanken-Docs werden korrekt erkannt und zurueckgegeben."""
    records = [
        _make_structured_doc("D_gedanke-1", "gedanke"),
        _make_structured_doc("D_gedanke-2", "gedanke"),
        _make_structured_doc("D_normal-doc", "tutorial"),
    ]
    jsonl = tmp_path / "documents_structured.jsonl"
    _write_structured_jsonl(jsonl, records)

    result = _load_gedanken_doc_ids(jsonl)

    assert "D_gedanke-1" in result
    assert "D_gedanke-2" in result
    assert "D_normal-doc" not in result


def test_load_gedanken_doc_ids_missing_file(tmp_path: Path) -> None:
    """Fehlende Datei gibt leeres Set zurueck (kein Absturz)."""
    result = _load_gedanken_doc_ids(tmp_path / "nonexistent.jsonl")
    assert result == set()


def test_load_gedanken_doc_ids_no_gedanken(tmp_path: Path) -> None:
    """Wenn keine Gedanken vorhanden: leeres Set."""
    records = [
        _make_structured_doc("D_doc-a", "tutorial"),
        _make_structured_doc("D_doc-b", "wiki"),
    ]
    jsonl = tmp_path / "documents_structured.jsonl"
    _write_structured_jsonl(jsonl, records)

    result = _load_gedanken_doc_ids(jsonl)
    assert result == set()


# === Test: _build_gedanken_body ===============================================


def test_build_gedanken_body_joins_segments() -> None:
    """Original-Segmenttexte werden unveraendert zusammengefuehrt."""
    segments = [
        _make_segment("D_test", 0, "Erster Gedanke."),
        _make_segment("D_test", 1, "Zweiter Gedanke."),
    ]
    body = _build_gedanken_body(segments)
    assert "Erster Gedanke." in body
    assert "Zweiter Gedanke." in body


def test_build_gedanken_body_skips_empty_segments() -> None:
    """Leere Segmente werden uebersprungen."""
    segments = [
        _make_segment("D_test", 0, "Echter Inhalt."),
        _make_segment("D_test", 1, "   "),  # nur Whitespace
    ]
    body = _build_gedanken_body(segments)
    assert "Echter Inhalt." in body
    assert body.strip() == "Echter Inhalt."


# === Test: Stage-4-Gedanken-Pflichtfelder =====================================


def test_stage4_gedanken_forces_required_fields(tmp_path: Path) -> None:
    """_run_stage4_gedanken erzwingt type=gedanke, category=gedanken, doc_role=[wiki]."""
    # Qwen liefert falschen type/category (wird ueberschrieben)
    fake_fm_response = {
        "title": "Mein Gedanke",
        "slug": "mein-gedanke",
        "summary": "Ein kurzer Gedanke.",
        "type": "knowledge-article",  # wird auf "gedanke" erzwungen
        "category": "webentwicklung",  # wird auf "gedanken" erzwungen
        "doc_role": ["explanation"],  # wird auf ["wiki"] erzwungen
        "tags": ["design"],
        "sources_docs": ["D_mein-gedanke"],
        "source_chunks": ["D_mein-gedanke-S0001"],
        "confidence": "medium",
        "doc_version": "0.1.0",
        "created": "2026-05-30",
        "updated": "2026-05-30",
        "last_synthesized": "2026-05-30",
        "prompt_version": "v1",
    }

    # Mock: Prompt laden + API-Aufruf
    with (
        patch("pipeline.phase_8_synthesis._load_prompt", return_value="SYSTEM PROMPT"),
        patch(
            "pipeline.phase_8_synthesis._run_json_stage",
            return_value=fake_fm_response.copy(),
        ),
    ):
        cfg = _QwenStageConfig(
            client=MagicMock(),
            model="test-model",
            context_window=50000,
            max_retries=1,
            backoff_seconds=0,
            prompts_dir=tmp_path / "prompts",
            prompt_version="v1",
            needs_human_path=tmp_path / "needs_human.jsonl",
            pipeline_version="0.1.0",
            force=False,
            today_str="2026-05-30",
            temp_stage1=0.3,
            temp_stage2=0.2,
            temp_stage3=0.4,
            temp_stage4=0.1,
            max_tokens_stage1=20000,
            max_tokens_stage2=14000,
            max_tokens_stage3=24000,
            max_tokens_stage4=10000,
        )
        concept = {
            "ck_id": "CK_mein-gedanke",
            "title": "Mein Gedanke",
            "type": "gedanke",
            "doc_role": ["wiki"],
            "category": "gedanken",
            "sources_docs": ["D_mein-gedanke"],
            "source_chunks": ["D_mein-gedanke-S0001"],
            "merged_from": [],
        }
        fm = _run_stage4_gedanken(concept, "Gedanken-Body.", tmp_path, "mein-gedanke", "D_mein-gedanke", cfg)

    assert fm is not None
    assert fm.type == "gedanke"
    assert fm.category == "gedanken"
    assert fm.doc_role == ["wiki"]
    assert fm.merged_from == []
    assert fm.status == "draft"
    assert fm.review_status == "ai_drafted"


# === Test: FrontmatterDraft validiert "gedanke" als type =====================


def test_frontmatter_draft_accepts_gedanke_type() -> None:
    """FrontmatterDraft.type akzeptiert den neuen Wert 'gedanke'."""
    fm = FrontmatterDraft(
        title="Gedanke Test",
        slug="gedanke-test",
        summary="Ein Test-Gedanke.",
        type="gedanke",
        doc_role=["wiki"],
        category="gedanken",
        tags=[],
        sources_docs=["D_test"],
        source_chunks=[],
        confidence="low",
        created="2026-05-30",
        updated="2026-05-30",
        last_synthesized="2026-05-30",
        prompt_version="v1",
    )
    assert fm.type == "gedanke"
    assert fm.category == "gedanken"
