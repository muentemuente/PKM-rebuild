"""Tests für Phase 2 — Normalisierung.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 2:
  - CRLF → LF
  - Tabs → Spaces (außer in Code-Blöcken)
  - Trailing Whitespace entfernt (außer in Code-Blöcken)
  - Max. 3 aufeinanderfolgende Leerzeilen
  - YAML-Frontmatter extrahiert (oder leeres Dict)
  - Idempotenz: zweimaliger Lauf → identische Outputs
"""

import json
import time
from pathlib import Path

import pytest
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import (
    _extract_frontmatter,
    _normalize_body,
    run_phase_2,
)
from pipeline.schemas import CleanedDocument

# === _extract_frontmatter =====================================================


def test_no_frontmatter() -> None:
    text = "# Hello\n\nBody text."
    fm, body = _extract_frontmatter(text)
    assert fm == {}
    assert body == text


def test_valid_frontmatter() -> None:
    text = "---\ntitle: Test\nstatus: draft\n---\n# Hello\n\nBody."
    fm, body = _extract_frontmatter(text)
    assert fm == {"title": "Test", "status": "draft"}
    assert body == "# Hello\n\nBody."


def test_frontmatter_body_stripped_of_leading_newlines() -> None:
    # \s* in der Regex konsumiert auch den Blank-Separator nach ---
    text = "---\ntitle: Test\n---\n\n# Hello"
    fm, body = _extract_frontmatter(text)
    assert fm == {"title": "Test"}
    assert body == "# Hello"


def test_unclosed_frontmatter_returns_empty() -> None:
    text = "---\ntitle: Test\n# Hello"
    fm, body = _extract_frontmatter(text)
    assert fm == {}
    assert body == text


def test_invalid_yaml_frontmatter_returns_empty() -> None:
    text = "---\ntitle: {broken: [unclosed\n---\n# Hello"
    fm, body = _extract_frontmatter(text)
    assert fm == {}
    assert body == text


def test_frontmatter_with_list_values() -> None:
    text = "---\ntags:\n  - python\n  - cli\n---\nbody"
    fm, body = _extract_frontmatter(text)
    assert fm == {"tags": ["python", "cli"]}
    assert body == "body"


# === _normalize_body ==========================================================


def test_tab_outside_code_block_replaced() -> None:
    text = "line\twith\ttabs"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == "line    with    tabs"


def test_tab_inside_code_block_preserved() -> None:
    text = "```\ncode\twith\ttabs\n```"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == text


def test_tilde_fence_code_block_protected() -> None:
    text = "~~~\ncode\twith\ttabs\n~~~"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == text


def test_trailing_whitespace_outside_code_block_stripped() -> None:
    text = "line with trailing   "
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == "line with trailing"


def test_trailing_whitespace_inside_code_block_preserved() -> None:
    text = "```\ncode line   \n```"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == text


def test_max_blank_lines_reduced() -> None:
    # 5 Leerzeilen → 3
    text = "line1\n\n\n\n\n\nline2"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == "line1\n\n\n\nline2"


def test_blank_lines_within_limit_kept() -> None:
    text = "line1\n\n\nline2"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == "line1\n\n\nline2"


def test_blank_lines_inside_code_block_not_counted() -> None:
    # Viele Leerzeilen innerhalb eines Code-Blocks bleiben erhalten
    text = "```\nline1\n\n\n\n\nline2\n```"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    assert result == text


def test_multiple_code_blocks_protected() -> None:
    text = "before\n```\ntab\there\n```\nmiddle\t\n```\nanother\t\n```\nafter"
    result = _normalize_body(
        text, tab_replacement="    ", max_blank_lines=3, strip_trailing_whitespace=True
    )
    # "middle\t" → "middle    " (trailing whitespace stripped → "middle")
    assert "tab\there" in result
    assert "another\t" in result
    assert result.startswith("before")


# === run_phase_2 ==============================================================


def _make_manifest(corpus: Path, manifest_path: Path) -> None:
    """Hilfsfunktion: Phase 1 auf corpus ausführen → manifest schreiben."""
    run_phase_1(corpus_input=corpus, output_path=manifest_path)


def test_manifest_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_phase_2(
            manifest_path=tmp_path / "nonexistent.jsonl",
            output_path=tmp_path / "out.jsonl",
        )


def test_all_docs_processed(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    _make_manifest(sample_corpus_dir, manifest_path)

    records = run_phase_2(
        manifest_path=manifest_path,
        output_path=tmp_path / "cleaned.jsonl",
    )
    assert len(records) == 10


def test_output_is_valid_jsonl(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    output_path = tmp_path / "cleaned.jsonl"
    _make_manifest(sample_corpus_dir, manifest_path)
    run_phase_2(manifest_path=manifest_path, output_path=output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    for line in lines:
        rec = CleanedDocument.model_validate_json(line)
        assert rec.doc_id.startswith("D_")
        assert len(rec.normalized_sha256) == 64


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    output_path = tmp_path / "cleaned.jsonl"
    _make_manifest(sample_corpus_dir, manifest_path)
    run_phase_2(manifest_path=manifest_path, output_path=output_path)

    meta_path = Path(str(output_path) + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_2_normalize"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["output_hash"].startswith("sha256:")


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    output_path = tmp_path / "cleaned.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")
    _make_manifest(sample_corpus_dir, manifest_path)

    run_phase_2(manifest_path=manifest_path, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns

    run_phase_2(manifest_path=manifest_path, output_path=output_path)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_first == mtime_second, (
        "Meta-File beim zweiten Lauf neu geschrieben — Idempotenz verletzt"
    )


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.jsonl"
    output_path = tmp_path / "cleaned.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")
    _make_manifest(sample_corpus_dir, manifest_path)

    run_phase_2(manifest_path=manifest_path, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns

    time.sleep(0.01)
    run_phase_2(manifest_path=manifest_path, output_path=output_path, force=True)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first, "--force hätte Meta-File neu schreiben sollen"


def test_crlf_normalized(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "crlf.md").write_bytes(b"# Title\r\n\r\nBody line.\r\n")

    manifest_path = tmp_path / "manifest.jsonl"
    _make_manifest(corpus, manifest_path)

    records = run_phase_2(
        manifest_path=manifest_path,
        output_path=tmp_path / "cleaned.jsonl",
    )
    assert len(records) == 1
    assert "\r" not in records[0].body


def test_frontmatter_extracted(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "with-fm.md").write_text(
        "---\ntitle: Mein Artikel\nstatus: draft\n---\n# Body\n\nText.",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "manifest.jsonl"
    _make_manifest(corpus, manifest_path)

    records = run_phase_2(
        manifest_path=manifest_path,
        output_path=tmp_path / "cleaned.jsonl",
    )
    assert len(records) == 1
    r = records[0]
    assert r.frontmatter == {"title": "Mein Artikel", "status": "draft"}
    assert "---" not in r.body


def test_no_frontmatter_gives_empty_dict(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "no-fm.md").write_text("# Only body\n\nNo frontmatter.", encoding="utf-8")

    manifest_path = tmp_path / "manifest.jsonl"
    _make_manifest(corpus, manifest_path)

    records = run_phase_2(
        manifest_path=manifest_path,
        output_path=tmp_path / "cleaned.jsonl",
    )
    assert records[0].frontmatter == {}


def test_normalized_sha256_is_deterministic(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.md").write_text("# Hello\n\nWorld.", encoding="utf-8")

    manifest_path = tmp_path / "manifest.jsonl"
    _make_manifest(corpus, manifest_path)

    r1 = run_phase_2(
        manifest_path=manifest_path,
        output_path=tmp_path / "run1.jsonl",
    )
    r2 = run_phase_2(
        manifest_path=manifest_path,
        output_path=tmp_path / "run2.jsonl",
        force=True,
    )
    assert r1[0].normalized_sha256 == r2[0].normalized_sha256
