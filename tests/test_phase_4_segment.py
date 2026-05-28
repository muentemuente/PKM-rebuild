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
    _is_heading_only,
    _merge_undersized_segments,
    _parse_raw_sections,
    _same_h1_section,
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


# === _is_heading_only ============================================================


def test_is_heading_only_single_heading() -> None:
    assert _is_heading_only("## Tag-Sammlung") is True


def test_is_heading_only_multiple_headings() -> None:
    assert _is_heading_only("# Top\n\n## Sub") is True


def test_is_heading_only_with_content() -> None:
    assert _is_heading_only("## Section\n\nSome content here") is False


def test_is_heading_only_empty() -> None:
    assert _is_heading_only("") is False


def test_is_heading_only_plain_text() -> None:
    assert _is_heading_only("Just some text without headings") is False


# === _same_h1_section ============================================================


def test_same_h1_both_empty() -> None:
    assert _same_h1_section([], []) is True


def test_same_h1_one_empty() -> None:
    assert _same_h1_section([], ["Section"]) is False


def test_same_h1_same_first_element() -> None:
    assert _same_h1_section(["Top", "Sub1"], ["Top", "Sub2"]) is True


def test_same_h1_different_first_element() -> None:
    assert _same_h1_section(["A", "Sub"], ["B", "Sub"]) is False


def test_same_h1_single_element_match() -> None:
    assert _same_h1_section(["Top"], ["Top"]) is True


# === _merge_undersized_segments ==================================================


def _make_seg(
    doc_id: str,
    idx: int,
    text: str,
    heading_path: list[str] | None = None,
) -> SegmentRecord:
    """Hilfsfunktion: SegmentRecord für Tests bauen."""
    return SegmentRecord(
        segment_id=f"{doc_id}-S{idx:04d}",
        doc_id=doc_id,
        source_path="/test.md",
        heading_path=heading_path or [],
        segment_index=idx,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        contains_code=False,
        contains_table=False,
    )


def test_merge_heading_only_merges_with_next() -> None:
    """Heading-only-Segment wird mit NEXT gemergt."""
    seg0 = _make_seg("D_t", 0, "## Sub", heading_path=["Top", "Sub"])
    seg1 = _make_seg(
        "D_t", 1, "## Sub\n\nEcht Inhalt hier, viele Wörter.", heading_path=["Top", "Sub"]
    )
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=10, max_words=1500, doc_id="D_t")
    assert len(result) == 1
    assert "## Sub" in result[0].text
    assert "Echt Inhalt hier" in result[0].text


def test_merge_heading_only_inherits_path() -> None:
    """Heading-only gibt seinen heading_path ans gemergte Segment weiter."""
    seg0 = _make_seg("D_t", 0, "## SubA", heading_path=["Top", "SubA"])
    body1 = "## SubB\n\n" + "wort " * 20
    seg1 = _make_seg("D_t", 1, body1, heading_path=["Top", "SubB"])
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=10, max_words=1500, doc_id="D_t")
    assert len(result) == 1
    # heading_path vom heading-only-Segment (seg0)
    assert result[0].heading_path == ["Top", "SubA"]


def test_merge_undersized_segment_into_next() -> None:
    """Undersized-Segment wird mit NEXT im gleichen H1 gemergt."""
    seg0 = _make_seg("D_t", 0, "## A\n\nkurz", heading_path=["Top", "A"])
    body1 = "## B\n\n" + "wort " * 30
    seg1 = _make_seg("D_t", 1, body1, heading_path=["Top", "B"])
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=20, max_words=1500, doc_id="D_t")
    assert len(result) == 1
    assert "kurz" in result[0].text


def test_merge_respects_h1_boundary() -> None:
    """Undersized-Segment wird NICHT über H1-Grenzen gemergt."""
    # seg0 unter H1-A (undersized), seg1 unter H1-B (gleicher H1-Check schlägt fehl)
    seg0 = _make_seg("D_t", 0, "## Sub\n\nkurz", heading_path=["H1-A", "Sub"])
    body1 = "## Sub\n\n" + "wort " * 30
    seg1 = _make_seg("D_t", 1, body1, heading_path=["H1-B", "Sub"])
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=20, max_words=1500, doc_id="D_t")
    # seg0 kann nicht mit seg1 mergen (unterschiedlicher H1), kein PREVIOUS → bleibt
    # seg1 ist groß genug
    assert len(result) == 2


def test_merge_last_segment_to_previous() -> None:
    """Letztes undersized Segment mergt mit PREVIOUS, H1-Grenze ignoriert."""
    body0 = "# H1-A\n\n" + "wort " * 30
    seg0 = _make_seg("D_t", 0, body0, heading_path=["H1-A"])
    seg1 = _make_seg("D_t", 1, "# H1-B\n\nkurz", heading_path=["H1-B"])
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=20, max_words=1500, doc_id="D_t")
    assert len(result) == 1
    assert "kurz" in result[0].text


def test_merge_reindexes_segments() -> None:
    """Nach Merge: IDs sind S0000, S0001 … ohne Lücken."""
    seg0 = _make_seg("D_t", 0, "## Only Heading", heading_path=["Top"])
    body1 = "## Content\n\n" + "wort " * 30
    seg1 = _make_seg("D_t", 1, body1, heading_path=["Top"])
    body2 = "## More\n\n" + "inhalt " * 30
    seg2 = _make_seg("D_t", 2, body2, heading_path=["Top"])
    result, _ = _merge_undersized_segments(
        [seg0, seg1, seg2], min_words=10, max_words=1500, doc_id="D_t"
    )
    for i, seg in enumerate(result):
        assert seg.segment_id == f"D_t-S{i:04d}"
        assert seg.segment_index == i


def test_merge_chain_of_undersized_segments() -> None:
    """Kette von undersized Segmenten wird iterativ gemergt."""
    segs = [
        _make_seg("D_t", i, f"## H{i}\n\nkurz", heading_path=["Top", f"H{i}"]) for i in range(4)
    ]
    result, _ = _merge_undersized_segments(segs, min_words=20, max_words=1500, doc_id="D_t")
    assert len(result) < 4
    # Alle Original-Texte im Merge enthalten
    combined = " ".join(r.text for r in result)
    for i in range(4):
        assert f"H{i}" in combined


def test_merge_preserves_code_blocks_after_merge() -> None:
    """Code-Block-Flag bleibt nach Merge erhalten (OR-Kombination)."""
    seg0 = _make_seg("D_t", 0, "## Head", heading_path=["Top"])
    seg1 = SegmentRecord(
        segment_id="D_t-S0001",
        doc_id="D_t",
        source_path="/t.md",
        heading_path=["Top"],
        segment_index=1,
        text="## Section\n\n```python\nx = 1\n```",
        word_count=5,
        char_count=30,
        contains_code=True,
        contains_table=False,
    )
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=10, max_words=1500, doc_id="D_t")
    assert len(result) == 1
    assert result[0].contains_code is True


def test_oversized_after_merge_segment_is_returned() -> None:
    """Segment das nach Merge > max_words ist, wird trotzdem zurückgegeben."""
    body0 = "## A\n\nkurz"
    body1 = "## B\n\n" + "wort " * 100
    seg0 = _make_seg("D_t", 0, body0, heading_path=["Top", "A"])
    seg1 = _make_seg("D_t", 1, body1, heading_path=["Top", "B"])
    result, _ = _merge_undersized_segments([seg0, seg1], min_words=20, max_words=50, doc_id="D_t")
    # Merge findet statt (seg0 < min_words), Ergebnis > max_words aber wird behalten
    assert len(result) == 1
    assert result[0].word_count > 50


# === _segment_document mit Merge-Logik ==========================================


def test_phase_4_merges_heading_only_segment() -> None:
    """Heading-only-Segment in _segment_document wird mit Nachfolger gemergt."""
    body = "# Top\n\n## Sub\n\n" + "inhalt " * 20
    result = _segment_document("D_t", body, "/t.md", min_words=10, max_words=1500)
    # "## Sub" allein ist heading-only → muss mit dem Inhalt-Segment gemergt werden
    assert all(not _is_heading_only(r.text) for r in result)


def test_phase_4_no_merge_when_above_min_words() -> None:
    """Segmente über min_words bleiben unverändert (kein unnötiger Merge)."""
    body_a = "# A\n\n" + "wort " * 60
    body_b = "# B\n\n" + "wort " * 60
    body = body_a + "\n\n" + body_b
    result = _segment_document("D_t", body, "/t.md", min_words=50, max_words=1500)
    # Zwei separate H1 mit ausreichend Inhalt → keine Merge-Reduktion
    assert len(result) == 2
