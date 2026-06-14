"""Tests für Phase 3 — Strukturextraktion.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 3:
  - H1 für jedes Dokument (Fallback: Dateiname aus doc_id)
  - Confidence-Wert + mind. 1 Signal pro doc_type_guess
  - Alle Code-Blöcke mit Sprach-Tag (unknown wenn nicht erkennbar)
  - Idempotenz: zweimaliger Lauf → identische Outputs
"""

import json
import time
from pathlib import Path

import pytest
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_3_structure import (
    _count_tables,
    _detect_book,
    _extract_embeds,
    _extract_headings,
    _extract_images,
    _extract_links,
    _get_title,
    _guess_doc_type,
    _partition_body,
    run_phase_3,
)
from pipeline.schemas import StructuredDocumentRecord

# === _partition_body ===========================================================


def test_partition_code_block_with_lang() -> None:
    body = "before\n```python\nx = 1\n```\nafter"
    non_code, blocks = _partition_body(body)
    assert blocks == [{"lang": "python", "content": "x = 1"}]
    assert "x = 1" not in non_code
    assert "before" in non_code
    assert "after" in non_code


def test_partition_code_block_without_lang() -> None:
    body = "```\nno lang\n```"
    _, blocks = _partition_body(body)
    assert blocks[0]["lang"] == "unknown"


def test_partition_tilde_fence() -> None:
    body = "~~~bash\ncmd\n~~~"
    _, blocks = _partition_body(body)
    assert blocks[0]["lang"] == "bash"
    assert blocks[0]["content"] == "cmd"


def test_partition_multiple_code_blocks() -> None:
    body = "```python\na=1\n```\ntext\n```bash\ncmd\n```"
    _, blocks = _partition_body(body)
    assert len(blocks) == 2
    assert blocks[0]["lang"] == "python"
    assert blocks[1]["lang"] == "bash"


def test_partition_no_code_blocks() -> None:
    body = "# Title\n\nJust text."
    non_code, blocks = _partition_body(body)
    assert blocks == []
    assert non_code == body


# === _extract_headings =========================================================


def test_extract_h1_to_h6() -> None:
    text = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
    headings = _extract_headings(text)
    assert len(headings) == 6
    assert headings[0] == {"level": 1, "text": "H1"}
    assert headings[5] == {"level": 6, "text": "H6"}


def test_headings_skipped_in_code_block() -> None:
    body = "# Real Heading\n```\n# Not a heading\n```"
    non_code, _ = _partition_body(body)
    headings = _extract_headings(non_code)
    assert len(headings) == 1
    assert headings[0]["text"] == "Real Heading"


def test_no_headings_returns_empty_list() -> None:
    assert _extract_headings("Just text, no headings.") == []


# === _count_tables =============================================================


def test_count_single_table() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |"
    assert _count_tables(text) == 1


def test_count_two_tables() -> None:
    text = "| A |\n|---|\n| 1 |\n\ntext\n\n| B |\n|---|\n| 2 |"
    assert _count_tables(text) == 2


def test_table_without_separator_not_counted() -> None:
    text = "| A | B |\n| 1 | 2 |"
    assert _count_tables(text) == 0


def test_table_in_code_block_not_counted() -> None:
    body = "```\n| A | B |\n|---|---|\n| 1 | 2 |\n```"
    non_code, _ = _partition_body(body)
    assert _count_tables(non_code) == 0


# === _extract_links + images ===================================================


def test_extract_regular_link() -> None:
    text = "[Python](https://python.org)"
    links = _extract_links(text)
    assert "https://python.org" in links


def test_extract_wikilink() -> None:
    text = "Siehe auch [[yaml-frontmatter]]"
    links = _extract_links(text)
    assert "yaml-frontmatter" in links


def test_extract_wikilink_with_display_text() -> None:
    text = "[[slug|Display Text]]"
    links = _extract_links(text)
    assert "slug" in links
    assert "Display Text" not in links


def test_image_not_in_links() -> None:
    text = "![Alt](img.png)"
    links = _extract_links(text)
    assert "img.png" not in links


# === _extract_embeds (WP3) ====================================================


def test_extract_embed_target() -> None:
    text = "Vorher ![[slug__bild.png]] nachher"
    assert _extract_embeds(text) == ["slug__bild.png"]


def test_extract_embed_with_alias() -> None:
    assert _extract_embeds("![[slug__bild.png|Diagramm]]") == ["slug__bild.png"]


def test_embed_not_counted_as_link() -> None:
    """![[…]] ist ein Embed, kein Wikilink — darf nicht in links landen."""
    text = "![[slug__bild.png]]"
    assert _extract_embeds(text) == ["slug__bild.png"]
    assert _extract_links(text) == []


def test_plain_wikilink_not_an_embed() -> None:
    text = "[[eine-note]]"
    assert _extract_embeds(text) == []
    assert "eine-note" in _extract_links(text)


def test_extract_image() -> None:
    text = "![Screenshot](img.png)"
    images = _extract_images(text)
    assert "img.png" in images


def test_no_images_returns_empty_list() -> None:
    assert _extract_images("No images here.") == []


# === _get_title ================================================================


def test_title_from_h1() -> None:
    headings = [{"level": 1, "text": "Mein Titel"}]
    assert _get_title(headings, {}, "D_slug") == "Mein Titel"


def test_title_from_frontmatter_when_no_h1() -> None:
    headings = [{"level": 2, "text": "Section"}]
    assert _get_title(headings, {"title": "FM Titel"}, "D_slug") == "FM Titel"


def test_title_fallback_to_doc_id_slug() -> None:
    title = _get_title([], {}, "D_rest-api")
    assert title == "Rest Api"


def test_title_uses_first_h1_only() -> None:
    headings = [{"level": 2, "text": "Sub"}, {"level": 1, "text": "First H1"}]
    assert _get_title(headings, {}, "D_slug") == "First H1"


# === _guess_doc_type ===========================================================


def test_guess_doc_type_returns_valid_label() -> None:
    from pipeline.schemas import DocTypeGuess

    valid_labels = {
        "cheat_sheet",
        "tutorial",
        "wiki",
        "manual",
        "how-to",
        "explanation",
        "reference",
        "gedanke",
        "projektidee",
        "projektplanung",
        "book",
        "unklar",
    }
    result = _guess_doc_type("Test", [], [], 0, 100, "test body")
    assert isinstance(result, DocTypeGuess)
    assert result.label in valid_labels


def test_guess_doc_type_has_signal() -> None:
    result = _guess_doc_type("Test", [], [], 0, 100, "test body")
    assert len(result.signals) >= 1


def test_guess_doc_type_confidence_in_range() -> None:
    result = _guess_doc_type("Test", [], [], 0, 100, "test body")
    assert 0.0 <= result.confidence <= 1.0


def test_cheat_sheet_from_table_with_short_doc() -> None:
    headings = [{"level": 1, "text": "Linux-Befehle"}]
    result = _guess_doc_type(
        "Linux-Befehle", headings, [], tables_count=1, word_count=80, body_lower=""
    )
    assert result.label == "cheat_sheet"


def test_projektidee_from_title() -> None:
    headings = [
        {"level": 1, "text": "Projektnotiz: KI-Agent"},
        {"level": 2, "text": "Idee"},
        {"level": 2, "text": "Offene Fragen"},
        {"level": 2, "text": "Status"},
    ]
    result = _guess_doc_type("Projektnotiz: KI-Agent für PKM", headings, [], 0, 150, "")
    assert result.label == "projektidee"


# === _detect_book ==============================================================


def _make_headings(h1: int = 0, h2: int = 0, h3: int = 0) -> list[dict]:
    """Hilfsfunktion: Heading-Liste mit gewünschter Anzahl pro Level."""
    return (
        [{"level": 1, "text": f"Kapitel {i}"} for i in range(h1)]
        + [{"level": 2, "text": f"Abschnitt {i}"} for i in range(h2)]
        + [{"level": 3, "text": f"Unterabschnitt {i}"} for i in range(h3)]
    )


def test_detect_book_true_when_large_and_many_h1_h2() -> None:
    headings = _make_headings(h1=3, h2=4)  # 7 H1/H2
    assert _detect_book(headings, word_count=9000, threshold=8000) is True


def test_detect_book_false_when_too_short() -> None:
    headings = _make_headings(h1=3, h2=4)
    assert _detect_book(headings, word_count=5000, threshold=8000) is False


def test_detect_book_false_when_too_few_h1_h2() -> None:
    headings = _make_headings(h1=1, h2=2)  # nur 3 H1/H2 < 5
    assert _detect_book(headings, word_count=10000, threshold=8000) is False


def test_detect_book_counts_only_h1_and_h2() -> None:
    # Viele H3, aber wenige H1/H2 → kein book
    headings = _make_headings(h1=1, h2=2, h3=20)
    assert _detect_book(headings, word_count=10000, threshold=8000) is False


def test_guess_doc_type_book_has_priority() -> None:
    """book wird zurückgegeben, auch wenn andere Heuristiken feuern würden."""
    headings = _make_headings(h1=3, h2=4)
    result = _guess_doc_type(
        title="Denkschulen Überblick",
        headings=headings,
        code_blocks=[],
        tables_count=0,
        word_count=9000,
        body_lower="",
        book_word_threshold=8000,
    )
    assert result.label == "book"
    assert result.confidence >= 0.8
    assert any("word_count" in s for s in result.signals)


def test_guess_doc_type_book_not_triggered_below_threshold() -> None:
    """Unter dem Schwellwert: normaler Pfad, kein book-Label."""
    headings = _make_headings(h1=3, h2=4)
    result = _guess_doc_type(
        title="Kurzes Dokument",
        headings=headings,
        code_blocks=[],
        tables_count=0,
        word_count=5000,
        body_lower="",
        book_word_threshold=8000,
    )
    assert result.label != "book"


# === run_phase_3 ===============================================================


def _build_pipeline_inputs(corpus: Path, tmp_path: Path) -> tuple[Path, Path]:
    """Phase 1 + Phase 2 auf corpus ausführen → (manifest_path, cleaned_path)."""
    manifest = tmp_path / "manifest.jsonl"
    cleaned = tmp_path / "cleaned.jsonl"
    run_phase_1(corpus_input=corpus, output_path=manifest)
    run_phase_2(manifest_path=manifest, output_path=cleaned)
    return manifest, cleaned


def test_cleaned_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_phase_3(
            cleaned_path=tmp_path / "nonexistent.jsonl",
            output_path=tmp_path / "out.jsonl",
        )


def test_all_docs_processed(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    records = run_phase_3(cleaned_path=cleaned, output_path=tmp_path / "structured.jsonl")
    assert len(records) == 10


def test_output_is_valid_jsonl(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "structured.jsonl"
    run_phase_3(cleaned_path=cleaned, output_path=output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    for line in lines:
        rec = StructuredDocumentRecord.model_validate_json(line)
        assert rec.doc_id.startswith("D_")
        assert rec.title


def test_all_docs_have_title(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    records = run_phase_3(cleaned_path=cleaned, output_path=tmp_path / "structured.jsonl")
    for r in records:
        assert r.title, f"Kein Titel für {r.doc_id}"


def test_all_code_blocks_have_lang_tag(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    records = run_phase_3(cleaned_path=cleaned, output_path=tmp_path / "structured.jsonl")
    for r in records:
        for cb in r.code_blocks:
            assert cb["lang"], f"Leerer lang-Tag in {r.doc_id}"
            assert cb["lang"] != "", f"Leerer lang-Tag in {r.doc_id}"


def test_all_docs_have_doc_type_signal(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    records = run_phase_3(cleaned_path=cleaned, output_path=tmp_path / "structured.jsonl")
    for r in records:
        assert len(r.doc_type_guess.signals) >= 1, f"Kein Signal für {r.doc_id}"
        assert 0.0 <= r.doc_type_guess.confidence <= 1.0


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "structured.jsonl"
    run_phase_3(cleaned_path=cleaned, output_path=output_path)

    meta_path = Path(str(output_path) + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_3_structure"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["output_hash"].startswith("sha256:")


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "structured.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")

    run_phase_3(cleaned_path=cleaned, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns

    run_phase_3(cleaned_path=cleaned, output_path=output_path)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_first == mtime_second, (
        "Idempotenz verletzt: Meta-File beim zweiten Lauf neu geschrieben"
    )


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path) -> None:
    _, cleaned = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    output_path = tmp_path / "structured.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")

    run_phase_3(cleaned_path=cleaned, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns
    time.sleep(0.01)
    run_phase_3(cleaned_path=cleaned, output_path=output_path, force=True)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first
