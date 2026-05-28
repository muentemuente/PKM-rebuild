"""Tests fuer Phase 8 — Qwen-Synthese.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 8:
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
from pipeline.phase_8_synthesis import (
    _build_stage3_user_message,
    _build_stage4_user_message,
    _extract_json,
    _extract_markdown_body,
    _is_cached,
    _slugify_ck,
    _unique_slug,
    _write_stage_meta,
    run_phase_8,
)
from pipeline.schemas import FrontmatterDraft, SegmentRecord

# === Fixtures ==================================================================


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
    "slug": "test-konzept",
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


def _make_segment(seg_id: str, text: str = "Test Inhalt") -> SegmentRecord:
    return SegmentRecord(
        segment_id=seg_id,
        doc_id="D_test",
        source_path="/test.md",
        heading_path=["Test"],
        segment_index=0,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        contains_code=False,
        contains_table=False,
    )


def _make_batch_file(tmp_path: Path) -> Path:
    """Erstellt ein minimales Batch-File fuer Tests."""
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    batch = batch_dir / "batch_001_test.md"
    batch.write_text(
        "---\n"
        "batch_id: batch_001_test\n"
        "cluster_id: C_test\n"
        "label_guess: Test Cluster\n"
        "segment_count: 1\n"
        "doc_count: 1\n"
        "token_estimate: 50\n"
        "sub_batch: 1/1\n"
        "created_at: 2026-05-27T00:00:00+00:00\n"
        "pipeline_version: 0.1.0\n"
        "---\n\n"
        "## Cluster: Test Cluster\n\n"
        "### Segmente\n\n"
        "---\n\n"
        "**[D_test-S0000]** | Heading: `Test` | Woerter: 5\n\n"
        "Test Inhalt fuer Stage 1.\n",
        encoding="utf-8",
    )
    return batch_dir


def _make_segments_file(tmp_path: Path) -> Path:
    segs_path = tmp_path / "segments.jsonl"
    seg = _make_segment("D_test-S0000", "Test Inhalt fuer Stage 1.")
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
    """Mockt openai.OpenAI mit vordefinierten Stage-Antworten."""
    responses = [
        _make_mock_response(f"```json\n{json.dumps(STAGE1_JSON)}\n```"),
        _make_mock_response(f"```json\n{json.dumps(STAGE2_JSON)}\n```"),
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
    """Mockt openai.OpenAI mit unbegrenzt gleichen Stage-Antworten (fuer Idempotenz-Tests)."""

    def _make_response(_messages: list, **_kwargs: object) -> MagicMock:
        # Bestimme Stage anhand von Nachrichten-Inhalt
        content = str(_messages)
        if "stage4_frontmatter" in content or "Artikel-Body" in content:
            return _make_mock_response(f"```json\n{json.dumps(STAGE4_FM)}\n```")
        if "stage3_synthesis" in content or "Quell-Segmente" in content:
            return _make_mock_response(f"```markdown\n{STAGE3_BODY}\n```")
        if (
            "stage2_merge" in content
            or "Stage-1-Analyse" in content
            or "proposed_concepts" in content
        ):
            return _make_mock_response(f"```json\n{json.dumps(STAGE2_JSON)}\n```")
        return _make_mock_response(f"```json\n{json.dumps(STAGE1_JSON)}\n```")

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
    seg_map = {"D_test-S0000": _make_segment("D_test-S0000", "Segment-Text hier.")}
    msg = _build_stage3_user_message(concept, seg_map)
    assert "D_test-S0000" in msg
    assert "Segment-Text hier." in msg
    assert "CK_test" in msg


def test_build_stage3_skips_missing_segments() -> None:
    concept = {
        "ck_id": "CK_x",
        "title": "X",
        "type": "knowledge-article",
        "doc_role": [],
        "category": "grundlagen",
        "source_chunks": ["D_missing-S0000"],
    }
    msg = _build_stage3_user_message(concept, {})
    assert "D_missing-S0000" not in msg


# === _build_stage4_user_message ================================================


def test_build_stage4_user_message_contains_body() -> None:
    concept = {"ck_id": "CK_test", "slug": "test"}
    msg = _build_stage4_user_message(concept, "# Test\n\nBody.", "2026-05-27")
    assert "# Test" in msg
    assert "2026-05-27" in msg
    assert "CK_test" in msg


# === run_phase_8 ===============================================================


def test_missing_batches_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_phase_8(
            batches_dir=tmp_path / "nonexistent",
            segments_path=tmp_path / "segments.jsonl",
            qwen_output_dir=tmp_path / "qwen",
            drafts_dir=tmp_path / "drafts",
            endpoint="http://localhost:1234/v1",
            model="test",
            context_window=49152,
            prompt_version="v1",
            prompts_dir=tmp_path / "prompts",
            temperature_stage1=0.3,
            temperature_stage2=0.2,
            temperature_stage3=0.4,
            temperature_stage4=0.1,
            max_retries=0,
            retry_backoff_seconds=0,
            timeout_seconds=30,
        )


def test_missing_segments_raises(tmp_path: Path) -> None:
    batches = tmp_path / "batches"
    batches.mkdir()
    with pytest.raises(FileNotFoundError):
        run_phase_8(
            batches_dir=batches,
            segments_path=tmp_path / "nonexistent.jsonl",
            qwen_output_dir=tmp_path / "qwen",
            drafts_dir=tmp_path / "drafts",
            endpoint="http://localhost:1234/v1",
            model="test",
            context_window=49152,
            prompt_version="v1",
            prompts_dir=tmp_path / "prompts",
            temperature_stage1=0.3,
            temperature_stage2=0.2,
            temperature_stage3=0.4,
            temperature_stage4=0.1,
            max_retries=0,
            retry_backoff_seconds=0,
            timeout_seconds=30,
        )


def test_run_phase_8_produces_outputs(tmp_path: Path, mock_openai: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)
    qwen_dir = tmp_path / "qwen"
    drafts_dir = tmp_path / "drafts"

    result = run_phase_8(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=qwen_dir,
        drafts_dir=drafts_dir,
        endpoint="http://localhost:1234/v1",
        model="qwen/qwen3.6-27b",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )

    assert result["batches_processed"] == 1
    assert result["concepts_drafted"] == 1
    assert result["errors"] == 0


def test_run_phase_8_stage1_output(tmp_path: Path, mock_openai: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    run_phase_8(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    stage1_path = tmp_path / "qwen" / "batch_001_test" / "stage1_analysis.json"
    assert stage1_path.exists()
    data = json.loads(stage1_path.read_text())
    assert "cluster_id" in data
    assert "structure_proposal" in data


def test_run_phase_8_stage2_output(tmp_path: Path, mock_openai: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    run_phase_8(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    stage2_path = tmp_path / "qwen" / "batch_001_test" / "stage2_merges.json"
    assert stage2_path.exists()
    data = json.loads(stage2_path.read_text())
    assert "proposed_concepts" in data


def test_run_phase_8_combined_draft_written(tmp_path: Path, mock_openai: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)
    drafts_dir = tmp_path / "drafts"

    run_phase_8(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=drafts_dir,
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    combined = drafts_dir / "CK_test-konzept.md"
    assert combined.exists()
    content = combined.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "title:" in content
    assert "# Test Konzept" in content


def test_run_phase_8_frontmatter_pydantic_valid(tmp_path: Path, mock_openai: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    run_phase_8(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    fm_path = tmp_path / "drafts" / "CK_test-konzept.frontmatter.json"
    assert fm_path.exists()
    fm_data = json.loads(fm_path.read_text())
    fm = FrontmatterDraft.model_validate(fm_data)
    assert fm.confidence in ("low", "medium", "high")
    assert fm.prompt_version == "v1"
    assert fm.status == "draft"
    assert fm.review_status == "ai_drafted"
    assert fm.last_synthesized != ""


def test_run_phase_8_idempotency(tmp_path: Path, mock_openai_infinite: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    kwargs = dict(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
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

    # Zweiter Lauf darf keine neuen API-Calls machen (Cache greift)
    assert calls_after_second == calls_after_first


def test_run_phase_8_force_reruns(tmp_path: Path, mock_openai_infinite: MagicMock) -> None:
    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    kwargs = dict(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
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


def test_run_phase_8_json_retry_on_bad_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage-1-Fehler wird behandelt: Batch landet in errors, nicht crash."""
    bad_response = _make_mock_response("Das ist kein JSON.")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = bad_response

    import pipeline.phase_8_synthesis as m8

    monkeypatch.setattr(m8, "openai", MagicMock(OpenAI=lambda **_: mock_client))

    batches_dir = _make_batch_file(tmp_path)
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    result = run_phase_8(
        batches_dir=batches_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    assert result["errors"] >= 1
    assert result["concepts_drafted"] == 0


def test_run_phase_8_empty_batches_dir(tmp_path: Path, mock_openai: MagicMock) -> None:
    empty_dir = tmp_path / "batches"
    empty_dir.mkdir()
    segments_path = _make_segments_file(tmp_path)
    prompts_dir = _make_prompts_dir(tmp_path)

    result = run_phase_8(
        batches_dir=empty_dir,
        segments_path=segments_path,
        qwen_output_dir=tmp_path / "qwen",
        drafts_dir=tmp_path / "drafts",
        endpoint="http://localhost:1234/v1",
        model="test",
        context_window=49152,
        prompt_version="v1",
        prompts_dir=prompts_dir,
        temperature_stage1=0.3,
        temperature_stage2=0.2,
        temperature_stage3=0.4,
        temperature_stage4=0.1,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=30,
    )
    assert result["batches_processed"] == 0
    assert result["concepts_drafted"] == 0
