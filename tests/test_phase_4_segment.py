"""Tests für Phase 4 — Segmentierung.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 4:
  - Jedes Segment zwischen min_words und max_words (best effort)
  - Code-Blöcke nicht zerrissen (Anzahl Fence-Marker pro Segment ist gerade)
  - Heading-Pfad für jedes Segment vorhanden (kann leer sein bei Intro-Abschnitten)
  - Idempotenz: zweimaliger Lauf → identische Outputs
"""

import json
import time
from pathlib import Path

import pytest
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_4_segment import (
    _classify_lines,
    _group_into_blocks,
    _parse_raw_sections,
    _segment_document,
    _split_section_lines,
    run_phase_4,
)
from pipeline.schemas import SegmentRecord

# === _classify_lines ===========================================================


def test_classify_text_and_blank() -> None:
    lines = ["hello world", "", "another line"]
    result = _classify_lines(lines)
    assert result == ["text", "blank", "text"]


def test_classify_code_block() -> None:
    lines = ["```python", "x = 1", "```"]
    result = _classify_lines(lines)
    assert result == ["code", "code", "code"]


def test_classify_tilde_fence() -> None:
    lines = ["~~~bash", "cmd", "~~~"]
    result = _classify_lines(lines)
    assert result == ["code", "code", "code"]


def test_classify_table_line() -> None:
    lines = ["| A | B |", "|---|---|", "| 1 | 2 |"]
    result = _classify_lines(lines)
    assert result == ["table", "table", "table"]


def test_heading_inside_code_block_is_code() -> None:
    lines = ["```", "# not a heading", "```"]
    result = _classify_lines(lines)
    assert result == ["code", "code", "code"]


# === _group_into_blocks =========================================================


def test_group_separates_code_from_text() -> None:
    lines = ["text line", "```python", "x = 1", "```", "more text"]
    types = ["text", "code", "code", "code", "text"]
    blocks = _group_into_blocks(lines, types)
    assert len(blocks) == 3
    assert blocks[0] == ["text line"]
    assert "```python" in blocks[1]
    assert blocks[2] == ["more text"]


def test_group_blank_splits_text_blocks() -> None:
    lines = ["a", "", "b"]
    types = ["text", "blank", "text"]
    blocks = _group_into_blocks(lines, types)
    assert len(blocks) == 2
    assert blocks[0] == ["a"]
    assert blocks[1] == ["b"]


def test_group_table_is_atomic() -> None:
    lines = ["| A |", "|---|", "| 1 |"]
    types = ["table", "table", "table"]
    blocks = _group_into_blocks(lines, types)
    assert len(blocks) == 1
    assert len(blocks[0]) == 3


# === _parse_raw_sections ========================================================


def test_parse_single_section_no_heading() -> None:
    body = "Intro text\nmore intro"
    sections = _parse_raw_sections(body)
    assert len(sections) == 1
    path, lines = sections[0]
    assert path == []
    assert "Intro text" in lines


def test_parse_heading_splits_sections() -> None:
    body = "Intro\n\n# Section One\n\nContent"
    sections = _parse_raw_sections(body)
    assert len(sections) == 2
    assert sections[1][0] == ["Section One"]


def test_parse_heading_path_nested() -> None:
    body = "# Top\n\ntext\n\n## Sub\n\nsub text"
    sections = _parse_raw_sections(body)
    assert sections[0][0] == ["Top"]
    assert sections[1][0] == ["Top", "Sub"]


def test_parse_heading_path_resets_at_higher_level() -> None:
    body = "## A\n\ntext\n\n# Top\n\ncontent"
    sections = _parse_raw_sections(body)
    assert sections[1][0] == ["Top"]


def test_parse_heading_inside_code_block_ignored() -> None:
    body = "```\n# Not a heading\n```\n\n# Real\n\ncontent"
    sections = _parse_raw_sections(body)
    assert len(sections) == 2
    assert sections[1][0] == ["Real"]


def test_parse_heading_line_included_in_section() -> None:
    body = "# My Section\n\nSome content"
    sections = _parse_raw_sections(body)
    assert sections[0][1][0] == "# My Section"


# === _split_section_lines ========================================================


def test_split_short_section_unchanged() -> None:
    lines = ["This is a short text."]
    result = _split_section_lines(lines, max_words=100)
    assert result == [lines]


def test_split_long_section_at_block_boundary() -> None:
    words = "word " * 60
    lines = [words.strip(), "", words.strip()]
    result = _split_section_lines(lines, max_words=50)
    assert len(result) >= 2


def test_split_never_breaks_code_block() -> None:
    code_lines = ["```python"] + ["x = 1"] * 80 + ["```"]
    result = _split_section_lines(code_lines, max_words=10)
    # Code block must not be split across multiple chunks
    for chunk in result:
        text = "\n".join(chunk)
        count = text.count("```")
        assert count % 2 == 0, f"Zerrissener Code-Block: {count} Fence-Marker"


def test_split_returns_lines_if_no_chunks() -> None:
    lines = ["only a few words here"]
    result = _split_section_lines(lines, max_words=1000)
    assert result == [lines]


# === _segment_document ===========================================================


def test_segment_empty_body_returns_empty() -> None:
    result = _segment_document("D_test", "", "/path/test.md", 50, 1500)
    assert result == []


def test_segment_ids_sequential() -> None:
    body = "# A\n\nContent A\n\n# B\n\nContent B"
    result = _segment_document("D_test", body, "/path/test.md", 1, 1500)
    ids = [r.segment_id for r in result]
    assert ids == [f"D_test-S{i:04d}" for i in range(len(ids))]


def test_segment_heading_path_populated() -> None:
    body = "# Top\n\ntext here\n\n## Sub\n\nsub content"
    result = _segment_document("D_test", body, "/path/test.md", 1, 1500)
    paths = [r.heading_path for r in result]
    assert any(p == ["Top"] for p in paths)
    assert any(p == ["Top", "Sub"] for p in paths)


def test_segment_code_blocks_not_split() -> None:
    code = "```python\n" + "x = 1\n" * 200 + "```"
    body = f"# Section\n\n{code}"
    result = _segment_document("D_test", body, "/path/test.md", 1, 100)
    for seg in result:
        count = seg.text.count("```") + seg.text.count("~~~")
        assert count % 2 == 0, f"Zerrissener Code-Block in {seg.segment_id}"


def test_segment_contains_code_flag() -> None:
    body = "# A\n\n```bash\necho hi\n```"
    result = _segment_document("D_test", body, "/path/test.md", 1, 1500)
    assert any(r.contains_code for r in result)


def test_segment_contains_table_flag() -> None:
    body = "# A\n\n| X | Y |\n|---|---|\n| 1 | 2 |"
    result = _segment_document("D_test", body, "/path/test.md", 1, 1500)
    assert any(r.contains_table for r in result)


def test_segment_word_count_matches_text() -> None:
    body = "# A\n\nThis is five words here."
    result = _segment_document("D_test", body, "/path/test.md", 1, 1500)
    for seg in result:
        assert seg.word_count == len(seg.text.split())
        assert seg.char_count == len(seg.text)


# === run_phase_4 ==================================================================


def _build_phase12_outputs(corpus: Path, tmp_path: Path) -> tuple[Path, Path]:
    """Phase 1 + 2 auf corpus → (manifest_path, cleaned_path)."""
    manifest = tmp_path / "manifest.jsonl"
    cleaned = tmp_path / "cleaned.jsonl"
    run_phase_1(corpus_input=corpus, output_path=manifest)
    run_phase_2(manifest_path=manifest, output_path=cleaned)
    return manifest, cleaned


def test_missing_cleaned_raises(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("")
    with pytest.raises(FileNotFoundError):
        run_phase_4(
            cleaned_path=tmp_path / "nonexistent.jsonl",
            manifest_path=manifest,
            output_path=tmp_path / "out.jsonl",
        )


def test_missing_manifest_raises(tmp_path: Path) -> None:
    cleaned = tmp_path / "cleaned.jsonl"
    cleaned.write_text("")
    with pytest.raises(FileNotFoundError):
        run_phase_4(
            cleaned_path=cleaned,
            manifest_path=tmp_path / "nonexistent.jsonl",
            output_path=tmp_path / "out.jsonl",
        )


def test_all_docs_produce_segments(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    records = run_phase_4(
        cleaned_path=cleaned,
        manifest_path=manifest,
        output_path=tmp_path / "segments.jsonl",
    )
    assert len(records) > 0


def test_output_is_valid_jsonl(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "segments.jsonl"
    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 0
    for line in lines:
        rec = SegmentRecord.model_validate_json(line)
        assert rec.segment_id.startswith("D_")
        assert rec.doc_id.startswith("D_")


def test_no_torn_code_blocks_in_corpus(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    records = run_phase_4(
        cleaned_path=cleaned,
        manifest_path=manifest,
        output_path=tmp_path / "segments.jsonl",
    )
    for seg in records:
        count = seg.text.count("```") + seg.text.count("~~~")
        assert count % 2 == 0, f"Zerrissener Code-Block: {seg.segment_id}"


def test_all_segments_have_heading_path_field(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    records = run_phase_4(
        cleaned_path=cleaned,
        manifest_path=manifest,
        output_path=tmp_path / "segments.jsonl",
    )
    for seg in records:
        assert isinstance(seg.heading_path, list)


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "segments.jsonl"
    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=output_path)

    meta_path = Path(str(output_path) + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_4_segment"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["output_hash"].startswith("sha256:")


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "segments.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")

    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns

    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=output_path)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_first == mtime_second, (
        "Idempotenz verletzt: Meta-File beim zweiten Lauf neu geschrieben"
    )


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest, cleaned = _build_phase12_outputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "segments.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")

    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns
    time.sleep(0.01)
    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=output_path, force=True)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first
