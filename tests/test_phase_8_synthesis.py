"""Tests fuer Phase 8 — Qwen-Veredelung (Option B: Pro-Doc-Veredelung).

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 8:
  - sources_docs belegt; merged_from leer ([])
  - confidence-Feld gesetzt
  - prompt_version gesetzt
  - last_synthesized gesetzt
  - Validation gegen Pydantic-Schema gruen
  - Idempotenz: zweimaliger Lauf identische Outputs
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pipeline.config import load_config
from pipeline.phase_8_synthesis import (
    _build_doc_concept,
    _build_stage3_user_message,
    _build_stage4_user_message,
    _extract_json,
    _extract_markdown_body,
    _group_segments_by_doc,
    _is_cached,
    _QwenStageConfig,
    _run_stage2,
    _sha256_str,
    _slugify_ck,
    _unique_slug,
    _write_stage_meta,
    run_phase_8,
)
from pipeline.schemas import FrontmatterDraft, SegmentRecord

# === Fixtures ==================================================================

# Stage-1+2-Konstanten: deprecated (Option A), behalten fuer _run_stage2-Test
STAGE1_JSON = {
    "cluster_id": "C_test",
    "main_topics": [
        {"topic": "Test-Thema", "segment_ids": ["D_test-S0000"], "confidence": "medium"}
    ],
    "redundancies": [],
    "contradictions": [],
    "structure_proposal": {
        "concept_candidates": [
            {
                "tentative_slug": "test-konzept",
                "tentative_title": "Test Konzept",
                "covers_segments": ["D_test-S0000"],
                "type_guess": "knowledge-article",
            }
        ]
    },
    "overall_confidence": "medium",
}

STAGE2_JSON = {
    "cluster_id": "C_test",
    "proposed_concepts": [
        {
            "ck_id": "CK_test-konzept",
            "title": "Test Konzept",
            "slug": "test-konzept",
            "type": "knowledge-article",
            "doc_role": ["explanation"],
            "category": "grundlagen",
            "subcategory": None,
            "sources_docs": ["D_test"],
            "source_chunks": ["D_test-S0000"],
            "merged_from": [],
            "aliases_suggested": [],
            "parent_concept_suggestion": None,
            "child_concepts_suggestions": [],
            "rationale": "Klares Thema.",
        }
    ],
    "discarded_segments": [],
    "overall_confidence": "medium",
}

STAGE3_BODY = "# Test Konzept\n\nEin Test-Artikel mit ausreichend Inhalt."

STAGE4_FM = {
    "title": "Test Konzept",
    "slug": "test",
    "aliases": [],
    "summary": "Ein Test-Konzept fuer die Pipeline.",
    "type": "knowledge-article",
    "doc_role": ["explanation"],
    "category": "grundlagen",
    "subcategory": None,
    "tags": ["test"],
    "related": [],
    "used_in": [],
    "parent_concept": None,
    "child_concepts": [],
    "sources_docs": ["D_test"],
    "source_chunks": ["D_test-S0000"],
    "merged_from": [],
    "status": "draft",
    "review_status": "ai_drafted",
    "confidence": "medium",
    "doc_version": "0.1.0",
    "created": "2026-05-27",
    "updated": "2026-05-27",
    "last_synthesized": "2026-05-27",
    "prompt_version": "v1",
}


def _make_mock_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_segment(seg_id: str, doc_id: str = "D_test", text: str = "Test Inhalt") -> SegmentRecord:
    return SegmentRecord(
        segment_id=seg_id,
        doc_id=doc_id,
        source_path="/test.md",
        heading_path=["Test"],
        segment_index=0,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        contains_code=False,
        contains_table=False,
    )


def _make_segments_file(tmp_path: Path, doc_id: str = "D_test") -> Path:
    segs_path = tmp_path / "segments.jsonl"
    seg = _make_segment(f"{doc_id}-S0000", doc_id=doc_id, text="Test Inhalt fuer Stage 3.")
    segs_path.write_text(seg.model_dump_json() + "\n", encoding="utf-8")
    return segs_path


def _make_prompts_dir(tmp_path: Path) -> Path:
    """Erstellt minimale Prompt-Stubs fuer Tests."""
    v1 = tmp_path / "prompts" / "v1"
    v1.mkdir(parents=True)
    for name in [
        "stage1_cluster_analysis.md",
        "stage2_merge_proposal.md",
        "stage3_synthesis.md",
        "stage4_frontmatter_json.md",
    ]:
        (v1 / name).write_text(f"# System-Prompt\nTest-Prompt: {name}\n", encoding="utf-8")
    return tmp_path / "prompts"


@pytest.fixture
def mock_openai(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mockt openai.OpenAI mit Stage-3+4-Antworten (Option B)."""
    responses = [
        _make_mock_response(f"```markdown\n{STAGE3_BODY}\n```"),
        _make_mock_response(f"```json\n{json.dumps(STAGE4_FM)}\n```"),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = responses

    import pipeline.phase_8_synthesis as m8

    monkeypatch.setattr(m8, "openai", MagicMock(OpenAI=lambda **_: mock_client))
    return mock_client


@pytest.fixture
def mock_openai_infinite(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mockt openai.OpenAI mit unbegrenzt gleichen Stage-3+4-Antworten."""

    def _make_response(_messages: list, **_kwargs: object) -> MagicMock:
        content = str(_messages)
        if "stage4_frontmatter" in content or "Artikel-Body" in content:
            return _make_mock_response(f"```json\n{json.dumps(STAGE4_FM)}\n```")
        return _make_mock_response(f"```markdown\n{STAGE3_BODY}\n```")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = lambda **kw: _make_response(
        kw.get("messages", [])
    )

    import pipeline.phase_8_synthesis as m8

    monkeypatch.setattr(m8, "openai", MagicMock(OpenAI=lambda **_: mock_client))
    return mock_client


# === _extract_json =============================================================


def test_extract_json_from_code_block() -> None:
    text = '```json\n{"key": "value"}\n```'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_strips_thinking() -> None:
    text = '<think>Denke nach...</think>\n```json\n{"x": 1}\n```'
    assert _extract_json(text) == {"x": 1}


def test_extract_json_fallback_bare_object() -> None:
    text = '{"key": "value"}'
    assert _extract_json(text) == {"key": "value"}


def test_extract_json_raises_on_no_json() -> None:
    with pytest.raises(ValueError, match="Kein JSON"):
        _extract_json("kein json hier")


def test_extract_json_nested_object() -> None:
    text = '```json\n{"a": {"b": [1, 2, 3]}}\n```'
    result = _extract_json(text)
    assert result["a"]["b"] == [1, 2, 3]


# === _extract_markdown_body ====================================================


def test_extract_markdown_from_code_block() -> None:
    text = "```markdown\n# Titel\n\nBody.\n```"
    assert _extract_markdown_body(text) == "# Titel\n\nBody."


def test_extract_markdown_strips_thinking() -> None:
    text = "<think>...</think>\n```markdown\n# Test\n```"
    assert _extract_markdown_body(text) == "# Test"


def test_extract_markdown_fallback() -> None:
    body = _extract_markdown_body("# Direkt als Body")
    assert "# Direkt" in body


# === _slugify_ck ===============================================================


def test_slugify_ck_umlauts() -> None:
    assert _slugify_ck("Übersicht über Änderungen") == "uebersicht-ueber-aenderungen"


def test_slugify_ck_lowercase() -> None:
    assert _slugify_ck("REST API") == "rest-api"


def test_slugify_ck_max_length() -> None:
    result = _slugify_ck("a" * 100)
    assert len(result) <= 60


def test_slugify_ck_empty_fallback() -> None:
    assert _slugify_ck("!!!") == "concept"


# === _unique_slug ==============================================================


def test_unique_slug_no_collision() -> None:
    used: set[str] = set()
    assert _unique_slug("rest", used) == "rest"
    assert "rest" in used


def test_unique_slug_collision() -> None:
    used: set[str] = {"rest"}
    assert _unique_slug("rest", used) == "rest_2"
    assert "rest_2" in used


def test_unique_slug_multiple_collisions() -> None:
    used: set[str] = {"api", "api_2"}
    assert _unique_slug("api", used) == "api_3"


# === _is_cached ================================================================


def test_is_cached_missing_files(tmp_path: Path) -> None:
    assert not _is_cached(tmp_path / "out.json", tmp_path / "meta.json", "abc")


def test_is_cached_hash_matches(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    meta = tmp_path / "meta.json"
    out.write_text("{}", encoding="utf-8")
    _write_stage_meta(meta, "deadbeef", "stage1")
    assert _is_cached(out, meta, "deadbeef")


def test_is_cached_hash_mismatch(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    meta = tmp_path / "meta.json"
    out.write_text("{}", encoding="utf-8")
    _write_stage_meta(meta, "aaa", "stage1")
    assert not _is_cached(out, meta, "bbb")


# === _group_segments_by_doc ====================================================


def test_group_segments_by_doc_basic() -> None:
    seg_a = _make_segment("D_alpha-S0000", doc_id="D_alpha", text="Alpha text.")
    seg_b = _make_segment("D_beta-S0000", doc_id="D_beta", text="Beta text.")
    seg_map = {seg_a.segment_id: seg_a, seg_b.segment_id: seg_b}
    docs = _group_segments_by_doc(seg_map)
    assert set(docs.keys()) == {"D_alpha", "D_beta"}
    assert len(docs["D_alpha"]) == 1
    assert len(docs["D_beta"]) == 1


def test_group_segments_by_doc_sorted_by_index() -> None:
    seg0 = SegmentRecord(
        segment_id="D_x-S0000",
        doc_id="D_x",
        source_path="/x.md",
        heading_path=[],
        segment_index=0,
        text="first",
        word_count=1,
        char_count=5,
        contains_code=False,
        contains_table=False,
    )
    seg1 = SegmentRecord(
        segment_id="D_x-S0001",
        doc_id="D_x",
        source_path="/x.md",
        heading_path=[],
        segment_index=1,
        text="second",
        word_count=1,
        char_count=6,
        contains_code=False,
        contains_table=False,
    )
    seg_map = {seg1.segment_id: seg1, seg0.segment_id: seg0}
    docs = _group_segments_by_doc(seg_map)
    assert docs["D_x"][0].segment_index == 0
    assert docs["D_x"][1].segment_index == 1


# === _build_doc_concept ========================================================


def test_build_doc_concept_structure() -> None:
    seg = _make_segment("D_yaml-frontmatter-S0000", doc_id="D_yaml-frontmatter", text="Inhalt.")
    concept = _build_doc_concept("D_yaml-frontmatter", [seg])
    assert concept["ck_id"] == "CK_yaml-frontmatter"
    assert concept["sources_docs"] == ["D_yaml-frontmatter"]
    assert concept["source_chunks"] == ["D_yaml-frontmatter-S0000"]
    assert concept["merged_from"] == []


def test_build_doc_concept_title_from_heading() -> None:
    seg = SegmentRecord(
        segment_id="D_test-S0000",
        doc_id="D_test",
        source_path="/test.md",
        heading_path=["YAML Grundlagen"],
        segment_index=0,
        text="Inhalt.",
        word_count=1,
        char_count=7,
        contains_code=False,
        contains_table=False,
    )
    concept = _build_doc_concept("D_test", [seg])
    assert concept["title"] == "YAML Grundlagen"


def test_build_doc_concept_title_fallback_no_heading() -> None:
    seg = SegmentRecord(
        segment_id="D_yaml-frontmatter-S0000",
        doc_id="D_yaml-frontmatter",
        source_path="/x.md",
        heading_path=[],
        segment_index=0,
        text="Inhalt.",
        word_count=1,
        char_count=7,
        contains_code=False,
        contains_table=False,
    )
    concept = _build_doc_concept("D_yaml-frontmatter", [seg])
    # Fallback: doc_id ohne D_-Prefix, humanisiert
    assert "yaml" in concept["title"].lower() or "Yaml" in concept["title"]


# === _build_stage3_user_message ================================================


def test_build_stage3_user_message_includes_segments() -> None:
    concept = {
        "ck_id": "CK_test",
        "title": "Test",
        "type": "knowledge-article",
        "doc_role": ["explanation"],
        "category": "grundlagen",
        "source_chunks": ["D_test-S0000"],
    }
    seg_map = {"D_test-S0000": _make_segment("D_test-S0000", text="Segment-Text hier.")}
    msg, resolved, missing = _build_stage3_user_message(concept, seg_map)
    assert "D_test-S0000" in msg
    assert "Segment-Text hier." in msg
    assert "CK_test" in msg
    assert resolved == 1
    assert missing == 0


def test_build_stage3_skips_missing_segments() -> None:
    concept = {
        "ck_id": "CK_x",
        "title": "X",
        "type": "knowledge-article",
        "doc_role": [],
        "category": "grundlagen",
        "source_chunks": ["D_missing-S0000"],
    }
    msg, resolved, missing = _build_stage3_user_message(concept, {})
    assert "D_missing-S0000" not in msg
    assert resolved == 0
    assert missing == 1


def test_stage3_logs_missing_segment_ids(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Fehlende Segment-IDs werden als warning geloggt, aufgeloeste nicht."""
    concept = {
        "ck_id": "CK_test",
        "title": "Test",
        "type": "knowledge-article",
        "doc_role": [],
        "category": "grundlagen",
        "source_chunks": ["D_real-S0000", "D_halluziniert-S0099"],
    }
    seg_map = {"D_real-S0000": _make_segment("D_real-S0000", text="Echter Text.")}
    import logging

    with caplog.at_level(logging.WARNING):
        msg, resolved, missing = _build_stage3_user_message(concept, seg_map)

    assert resolved == 1
    assert missing == 1
    assert "D_real-S0000" in msg
    assert "D_halluziniert-S0099" not in msg


# === _build_stage4_user_message ================================================


def test_build_stage4_user_message_contains_body() -> None:
    concept = {"ck_id": "CK_test", "slug": "test"}
    msg = _build_stage4_user_message(concept, "# Test\n\nBody.", "2026-05-27")
    assert "# Test" in msg
    assert "2026-05-27" in msg
    assert "CK_test" in msg


# === run_phase_8 ===============================================================


def test_missing_segments_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_phase_8(
            segments_path=tmp_path / "nonexistent.jsonl",
            qwen_output_dir=tmp_path / "qwen",
            drafts_dir=tmp_path / "drafts",
            endpoint="http://localhost:1234/v1",
            model="test",
            context_window=49152,
            prompt_version="v1",
            prompts_dir=tmp_path / "prompts",
            temperature_stage3=0.4,
            temperature_stage4=0.1,
            max_retries=0,
            retry_backoff_seconds=0,
            timeout_seconds=30,
        )


def test_run_phase_8_empty_segments(tmp_path: Path, mock_openai: MagicMock) -> None:
    segs_path = tmp_path / "segments.jsonl"
    segs_path.write_text("", encoding="utf-8")
    prompts_dir = _make_prompts_dir(tmp_path)

    result = run_phase_8(
        segments_path=segs_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    assert result["docs_processed"] == 0
    assert result["concepts_drafted"] == 0
    mock_openai.chat.completions.create.assert_not_called()


def test_run_phase_8_produces_outputs(tmp_path: Path, mock_openai: MagicMock) -> None:
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    result = run_phase_8(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="qwen/qwen3.6-27b",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )

    assert result["docs_processed"] == 1
    assert result["concepts_drafted"] == 1
    assert result["errors"] == 0


def test_run_phase_8_combined_draft_written(tmp_path: Path, mock_openai: MagicMock) -> None:
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)
    drafts_dir = tmp_path / "drafts"

    run_phase_8(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=drafts_dir,
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    # D_test → slug "test" → CK_test.md
    combined = drafts_dir / "CK_test.md"
    assert combined.exists()
    content = combined.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "title:" in content
    assert "# Test Konzept" in content


def test_run_phase_8_frontmatter_pydantic_valid(tmp_path: Path, mock_openai: MagicMock) -> None:
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    run_phase_8(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    fm_path = tmp_path / "drafts" / "CK_test.frontmatter.json"
    assert fm_path.exists()
    fm_data = json.loads(fm_path.read_text())
    fm = FrontmatterDraft.model_validate(fm_data)
    assert fm.confidence in ("low", "medium", "high")
    assert fm.prompt_version == "v1"
    assert fm.status == "draft"
    assert fm.review_status == "ai_drafted"
    assert fm.last_synthesized != ""


def test_run_phase_8_merged_from_always_empty(tmp_path: Path, mock_openai: MagicMock) -> None:
    """Option B: merged_from ist in jedem generierten Frontmatter leer."""
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    run_phase_8(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    fm_path = tmp_path / "drafts" / "CK_test.frontmatter.json"
    fm_data = json.loads(fm_path.read_text())
    assert fm_data["merged_from"] == []


def test_run_phase_8_sources_docs_contains_doc_id(tmp_path: Path, mock_openai: MagicMock) -> None:
    """sources_docs enthaelt die Source-Doc-ID des veredelten Dokuments."""
    segments_path = _make_segments_file(tmp_path, doc_id="D_test")
    prompts_dir = _make_prompts_dir(tmp_path)

    run_phase_8(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    fm_path = tmp_path / "drafts" / "CK_test.frontmatter.json"
    fm_data = json.loads(fm_path.read_text())
    assert "D_test" in fm_data["sources_docs"]


def test_run_phase_8_idempotency(tmp_path: Path, mock_openai_infinite: MagicMock) -> None:
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    kwargs = dict(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )

    run_phase_8(**kwargs)
    calls_after_first = mock_openai_infinite.chat.completions.create.call_count

    run_phase_8(**kwargs)
    calls_after_second = mock_openai_infinite.chat.completions.create.call_count

    assert calls_after_second == calls_after_first


def test_run_phase_8_force_reruns(tmp_path: Path, mock_openai_infinite: MagicMock) -> None:
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    kwargs = dict(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )

    run_phase_8(**kwargs)
    calls_after_first = mock_openai_infinite.chat.completions.create.call_count

    run_phase_8(**kwargs, force=True)
    calls_after_force = mock_openai_infinite.chat.completions.create.call_count

    assert calls_after_force > calls_after_first


def test_run_phase_8_stage3_error_lands_in_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage-3-Fehler (leere Antwort) wird behandelt: Doc landet in errors, kein Crash."""
    bad_response = _make_mock_response("")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = bad_response

    import pipeline.phase_8_synthesis as m8

    monkeypatch.setattr(m8, "openai", MagicMock(OpenAI=lambda **_: mock_client))

    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    result = run_phase_8(
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    assert result["errors"] >= 1
    assert result["concepts_drafted"] == 0


# === Bug-B2: merge_decisions-Vorrang vor Cache (deprecated _run_stage2) =========


def test_merge_decisions_override_wins_over_cache(tmp_path: Path) -> None:
    """merge_decisions.json ueberschreibt Stage-2-Cache (Option-A-Referenztest)."""
    batch_path = tmp_path / "batch_001_test.md"
    batch_path.write_text("batch content", encoding="utf-8")
    output_dir = tmp_path / "qwen" / "batch_001_test"
    output_dir.mkdir(parents=True)

    stage1_data: dict[str, object] = {"some": "stage1_data"}
    input_hash = _sha256_str(json.dumps(stage1_data, ensure_ascii=False))

    cached_content = {"proposed_concepts": [{"ck_id": "CK_from-cache", "title": "From Cache"}]}
    (output_dir / "stage2_merges.json").write_text(json.dumps(cached_content), encoding="utf-8")
    (output_dir / ".stage2.meta.json").write_text(
        json.dumps({"input_hash": input_hash}), encoding="utf-8"
    )

    decisions_content = {
        "proposed_concepts": [{"ck_id": "CK_from-decisions", "title": "From Decisions"}]
    }
    (output_dir / "merge_decisions.json").write_text(
        json.dumps(decisions_content), encoding="utf-8"
    )

    cfg = _QwenStageConfig(
        client=MagicMock(),
        model="test",
        context_window=49152,
        max_retries=0,
        backoff_seconds=0,
        prompts_dir=tmp_path / "prompts",
        prompt_version="v1",
        needs_human_path=tmp_path / "needs_human.jsonl",
        pipeline_version="0.1.0",
        force=False,
        today_str="2026-05-28",
        temp_stage1=0.3,
        temp_stage2=0.2,
        temp_stage3=0.4,
        temp_stage4=0.1,
        max_tokens_stage1=20000,
        max_tokens_stage2=14000,
        max_tokens_stage3=24000,
        max_tokens_stage4=10000,
    )

    result = _run_stage2(batch_path, stage1_data, output_dir, cfg)

    assert result is not None
    assert result["proposed_concepts"][0]["ck_id"] == "CK_from-decisions"


# === Bug-B5: used_slugs aus bestehenden Drafts laden ============================


def test_used_slugs_loaded_from_existing_drafts(
    tmp_path: Path, mock_openai_infinite: MagicMock
) -> None:
    """Bestehende CK_* Slugs aus drafts_dir werden in used_slugs geladen (Kollisionsschutz)."""
    segs_path = _make_segments_file(tmp_path)  # D_test → slug "test"
    prompts_dir = _make_prompts_dir(tmp_path)
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()

    # slug "test" ist bereits vergeben
    (drafts_dir / "CK_test.md").write_text("", encoding="utf-8")
    (drafts_dir / "CK_test.body.md").write_text("", encoding="utf-8")
    (drafts_dir / "CK_test.frontmatter.json").write_text("{}", encoding="utf-8")

    run_phase_8(
        segments_path=segs_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=drafts_dir,
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    # "test" war belegt → neuer Draft muss CK_test_2.md heissen
    assert (drafts_dir / "CK_test_2.md").exists()
    assert not (drafts_dir / "CK_test.md").read_text()  # Placeholder leer geblieben


def test_max_tokens_loaded_from_config() -> None:
    """pipeline.config.yaml max_tokens-Sektion wird korrekt ins Pydantic-Modell geladen."""
    repo_root = Path(__file__).parent.parent
    cfg = load_config(repo_root / "pipeline" / "pipeline.config.yaml")
    assert cfg.qwen.max_tokens.stage1 == 20000
    assert cfg.qwen.max_tokens.stage2 == 14000
    assert cfg.qwen.max_tokens.stage3 == 24000
    assert cfg.qwen.max_tokens.stage4 == 10000
