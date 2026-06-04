"""Tests für Phase 1 — Inventar.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 1:
  - Alle .md aus corpus_input erfasst (Count-Check)
  - Keine doppelten doc_ids (Slug-Kollisionen → Suffix _2, _3, ...)
  - SHA-256 für jedes File berechnet
  - Idempotenz: zweimaliger Lauf → identische Outputs
"""

import unicodedata
from pathlib import Path

import pytest
from pipeline.phase_1_inventory import (
    _assign_doc_ids,
    _filename_to_slug,
    run_phase_1,
)
from pipeline.schemas import DocumentRecord

# === _filename_to_slug =========================================================


def test_slug_basic() -> None:
    assert _filename_to_slug("rest-api") == "rest-api"


def test_slug_underscores_become_hyphens() -> None:
    assert _filename_to_slug("rest_api") == "rest-api"


def test_slug_spaces_become_hyphens() -> None:
    assert _filename_to_slug("my notes") == "my-notes"


def test_slug_uppercase() -> None:
    assert _filename_to_slug("HTTP-Protokoll") == "http-protokoll"


def test_slug_umlauts() -> None:
    assert _filename_to_slug("Übersicht") == "uebersicht"
    assert _filename_to_slug("Größe") == "groesse"
    assert _filename_to_slug("Straße") == "strasse"


def test_slug_umlauts_nfd_decomposed() -> None:
    # macOS-Dateisystem liefert NFD-zerlegte Umlaute (o + combining ¨).
    # Ohne NFC-Komposition vorab würde ä→a statt ä→ae (E2-Naming-Bug).
    for nfc in ("Lösung", "Übersicht", "Größe", "Straße", "Ärzte-Maße"):
        nfd = unicodedata.normalize("NFD", nfc)
        assert nfd != nfc or "ß" in nfc  # ß hat keine NFD-Zerlegung
        assert _filename_to_slug(nfd) == _filename_to_slug(nfc)
    assert _filename_to_slug(unicodedata.normalize("NFD", "Lösung")) == "loesung"


def test_slug_mixed_special_chars() -> None:
    # Mehrere Sonderzeichen in Folge → einzelner Bindestrich
    assert _filename_to_slug("foo!@#bar") == "foo-bar"


def test_slug_leading_trailing_hyphens_stripped() -> None:
    assert _filename_to_slug("-leading") == "leading"
    assert _filename_to_slug("trailing-") == "trailing"


# === _assign_doc_ids ===========================================================


def test_no_collision(tmp_path: Path) -> None:
    files = [tmp_path / "alpha.md", tmp_path / "beta.md"]
    for f in files:
        f.touch()
    ids = _assign_doc_ids(files)
    assert ids[files[0]] == "D_alpha"
    assert ids[files[1]] == "D_beta"


def test_slug_collision_gets_suffix(tmp_path: Path) -> None:
    """rest-api.md und rest_api.md ergeben denselben Slug → Suffix _2."""
    f1 = tmp_path / "rest-api.md"
    f2 = tmp_path / "rest_api.md"
    f1.touch()
    f2.touch()
    # Sortierte Reihenfolge: rest-api.md < rest_api.md (weil '-' < '_')
    ids = _assign_doc_ids(sorted([f1, f2]))
    assert ids[f1] == "D_rest-api"
    assert ids[f2] == "D_rest-api_2"


def test_three_way_collision_gets_incrementing_suffix(tmp_path: Path) -> None:
    files = [tmp_path / "foo-bar.md", tmp_path / "foo_bar.md", tmp_path / "foo bar.md"]
    for f in files:
        f.write_text("x")
    ids = _assign_doc_ids(sorted(files))
    suffixes = sorted(ids.values())
    assert "D_foo-bar" in suffixes
    assert "D_foo-bar_2" in suffixes
    assert "D_foo-bar_3" in suffixes


# === run_phase_1 ===============================================================


def test_corpus_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_phase_1(corpus_input=tmp_path / "nonexistent", output_path=tmp_path / "out.jsonl")


def test_all_files_captured(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """Alle 10 .md aus sample_corpus werden erfasst."""
    records = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "manifest.jsonl",
    )
    assert len(records) == 10


def test_no_duplicate_doc_ids(sample_corpus_dir: Path, tmp_path: Path) -> None:
    records = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "manifest.jsonl",
    )
    doc_ids = [r.doc_id for r in records]
    assert len(doc_ids) == len(set(doc_ids)), "Doppelte doc_ids gefunden"


def test_slug_collision_in_corpus(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """rest-api.md und rest_api.md → D_rest-api und D_rest-api_2."""
    records = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "manifest.jsonl",
    )
    doc_ids = {r.doc_id for r in records}
    assert "D_rest-api" in doc_ids
    assert "D_rest-api_2" in doc_ids


def test_sha256_present_and_nonempty(sample_corpus_dir: Path, tmp_path: Path) -> None:
    records = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "manifest.jsonl",
    )
    for r in records:
        assert r.sha256, f"sha256 fehlt für {r.doc_id}"
        assert len(r.sha256) == 64, "sha256 muss 64 Hex-Zeichen haben"


def test_all_fields_populated(sample_corpus_dir: Path, tmp_path: Path) -> None:
    records = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "manifest.jsonl",
    )
    for r in records:
        assert r.doc_id.startswith("D_")
        assert r.filename.endswith(".md")
        assert r.size_bytes > 0
        assert r.word_count > 0
        assert r.line_count > 0
        assert r.char_count > 0


def test_output_is_valid_jsonl(sample_corpus_dir: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "manifest.jsonl"
    run_phase_1(corpus_input=sample_corpus_dir, output_path=output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    # Jede Zeile muss als DocumentRecord validierbar sein
    for line in lines:
        rec = DocumentRecord.model_validate_json(line)
        assert rec.doc_id.startswith("D_")


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "manifest.jsonl"
    run_phase_1(corpus_input=sample_corpus_dir, output_path=output_path)

    meta_path = Path(str(output_path) + ".meta.json")
    assert meta_path.exists()

    import json

    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_1_inventory"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["output_hash"].startswith("sha256:")


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """Zweimaliger Lauf ohne Änderungen am Korpus → zweiter Lauf überspringt."""
    output_path = tmp_path / "manifest.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")

    run_phase_1(corpus_input=sample_corpus_dir, output_path=output_path)
    mtime_after_first = meta_path.stat().st_mtime_ns

    run_phase_1(corpus_input=sample_corpus_dir, output_path=output_path)
    mtime_after_second = meta_path.stat().st_mtime_ns

    assert mtime_after_first == mtime_after_second, (
        "Meta-File wurde beim zweiten Lauf neu geschrieben — Idempotenz verletzt"
    )


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """--force schreibt auch dann neu, wenn Input unverändert ist."""
    output_path = tmp_path / "manifest.jsonl"
    meta_path = Path(str(output_path) + ".meta.json")

    run_phase_1(corpus_input=sample_corpus_dir, output_path=output_path)
    mtime_first = meta_path.stat().st_mtime_ns

    # Kurze Pause um mtime-Änderung sicher zu machen (1 ns Auflösung auf macOS)
    import time

    time.sleep(0.01)
    run_phase_1(corpus_input=sample_corpus_dir, output_path=output_path, force=True)
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first, "--force hätte Meta-File neu schreiben sollen"


def test_sample_mode(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """sample=5 verarbeitet nur 5 der 10 Dateien."""
    records = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "manifest.jsonl",
        sample=5,
    )
    assert len(records) == 5


def test_sample_is_deterministic(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """Zwei Sample-Läufe mit gleicher N-Zahl liefern identische doc_ids."""
    r1 = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "run1.jsonl",
        sample=5,
    )
    r2 = run_phase_1(
        corpus_input=sample_corpus_dir,
        output_path=tmp_path / "run2.jsonl",
        sample=5,
        force=True,
    )
    assert [r.doc_id for r in r1] == [r.doc_id for r in r2]


def test_excludes_hidden_files(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "visible.md").write_text("sichtbar")
    (corpus / ".hidden.md").write_text("versteckt")

    records = run_phase_1(corpus_input=corpus, output_path=tmp_path / "out.jsonl")
    assert len(records) == 1
    assert records[0].filename == "visible.md"


def test_excludes_underscore_files(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "normal.md").write_text("normal")
    (corpus / "_index.md").write_text("index")

    records = run_phase_1(corpus_input=corpus, output_path=tmp_path / "out.jsonl")
    assert len(records) == 1
    assert records[0].filename == "normal.md"
