"""Tests fuer Phase 10 — Kontroll-Berichte.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 10:
  - corpus_report.md, duplicate_report.md, cluster_report.md werden generiert
  - Frontmatter valide (YAML-parseable)
  - Idempotenz: zweiter Lauf erzeugt identische Outputs (Hash-Vergleich)
  - CLI-Commands funktionieren: --phase 10 und reports
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner
from pipeline.__main__ import cli
from pipeline.phase_10_reports import (
    _detect_language,
    _doc_id_from_segment_id,
    _smoke_test_candidate,
    generate_cluster_report,
    generate_corpus_report,
    generate_duplicate_report,
    run_phase_10,
)

# === Fixtures =================================================================


def _write_manifest(path: Path, docs: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")


def _write_structured(path: Path, docs: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")


def _write_segments(path: Path, segs: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(s) for s in segs) + "\n", encoding="utf-8")


def _sample_manifest_records() -> list[dict[str, Any]]:
    return [
        {
            "doc_id": "D_alpha",
            "path": "/data/alpha.md",
            "filename": "alpha.md",
            "size_bytes": 1024,
            "modified_at": "2026-05-27T19:25:00+00:00",
            "sha256": "abc123",
            "line_count": 50,
            "word_count": 300,
            "char_count": 1800,
        },
        {
            "doc_id": "D_beta",
            "path": "/data/beta.md",
            "filename": "beta.md",
            "size_bytes": 512,
            "modified_at": "2026-05-27T19:25:00+00:00",
            "sha256": "def456",
            "line_count": 20,
            "word_count": 80,
            "char_count": 480,
        },
    ]


def _sample_structured_records() -> list[dict[str, Any]]:
    return [
        {
            "doc_id": "D_alpha",
            "title": "Alpha",
            "headings": [],
            "code_blocks": [],
            "tables_count": 0,
            "links": [],
            "images": [],
            "doc_type_guess": {"label": "wiki", "confidence": 0.8, "signals": []},
        },
        {
            "doc_id": "D_beta",
            "title": "Beta",
            "headings": [],
            "code_blocks": [],
            "tables_count": 0,
            "links": [],
            "images": [],
            "doc_type_guess": {"label": "cheat_sheet", "confidence": 0.7, "signals": []},
        },
    ]


def _sample_segments() -> list[dict[str, Any]]:
    return [
        {
            "segment_id": "D_alpha-S0000",
            "doc_id": "D_alpha",
            "source_path": "/data/alpha.md",
            "heading_path": [],
            "segment_index": 0,
            "text": "Alpha text",
            "word_count": 2,
            "char_count": 10,
            "contains_code": False,
            "contains_table": False,
        },
        {
            "segment_id": "D_beta-S0000",
            "doc_id": "D_beta",
            "source_path": "/data/beta.md",
            "heading_path": [],
            "segment_index": 0,
            "text": "Beta text",
            "word_count": 2,
            "char_count": 9,
            "contains_code": False,
            "contains_table": False,
        },
    ]


def _make_corpus_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "files_manifest.jsonl"
    structured = tmp_path / "documents_structured.jsonl"
    segments = tmp_path / "segments.jsonl"
    _write_manifest(manifest, _sample_manifest_records())
    _write_structured(structured, _sample_structured_records())
    _write_segments(segments, _sample_segments())
    return manifest, structured, segments


def _make_duplicate_inputs(tmp_path: Path) -> tuple[Path, Path]:
    exact = tmp_path / "exact_duplicates.json"
    edges = tmp_path / "near_duplicate_edges.jsonl"
    exact.write_text("[]", encoding="utf-8")
    edges.write_text(
        json.dumps(
            {"segment_id_a": "D_alpha-S0000", "segment_id_b": "D_beta-S0000", "similarity": 0.85}
        )
        + "\n",
        encoding="utf-8",
    )
    return exact, edges


def _make_cluster_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    clusters = tmp_path / "cluster_proposals.json"
    edges = tmp_path / "near_duplicate_edges.jsonl"
    batches_dir = tmp_path / "batches"
    batches_dir.mkdir()

    cluster_data = [
        {
            "cluster_id": "C_cluster-0001",
            "label_guess": "Test Cluster",
            "segment_ids": ["D_alpha-S0000", "D_alpha-S0001", "D_alpha-S0002", "D_beta-S0000"],
            "internal_similarity_mean": 0.8,
        },
        {
            "cluster_id": "C_unsortiert",
            "label_guess": "Unsortiert",
            "segment_ids": ["D_gamma-S0000"],
            "internal_similarity_mean": 0.0,
        },
    ]
    clusters.write_text(json.dumps(cluster_data), encoding="utf-8")
    edges.write_text(
        json.dumps(
            {"segment_id_a": "D_alpha-S0000", "segment_id_b": "D_alpha-S0001", "similarity": 0.9}
        )
        + "\n",
        encoding="utf-8",
    )

    batch_content = """---
batch_id: batch_001_test-cluster
cluster_id: C_cluster-0001
label_guess: Test Cluster
segment_count: 7
doc_count: 2
token_estimate: 500
sub_batch: 1/1
created_at: 2026-05-27T19:26:48.992266+00:00
pipeline_version: 0.1.0
---

Batch content here.
"""
    (batches_dir / "batch_001_test-cluster.md").write_text(batch_content, encoding="utf-8")
    return clusters, edges, batches_dir


# === Unit Tests ===============================================================


def test_doc_id_from_segment_id() -> None:
    """Segment-ID-Suffix wird korrekt entfernt."""
    assert _doc_id_from_segment_id("D_some-slug-S0003") == "D_some-slug"
    assert _doc_id_from_segment_id("D_short-S0000") == "D_short"


def test_detect_language_german() -> None:
    """Deutscher Text wird als 'de' erkannt."""
    german = "Das ist ein Text und der die das auch mit von zu für eine"
    result = _detect_language(german)
    assert result == "de"


def test_detect_language_english() -> None:
    """Englischer Text wird als 'en' erkannt."""
    english = "The quick brown fox and the lazy dog is with the other fox"
    result = _detect_language(english)
    assert result == "en"


def test_smoke_test_candidate_prefers_5_to_10_segs() -> None:
    """Smoke-Test-Kandidat bevorzugt Batches mit 5-10 Segmenten."""
    infos = [
        {"batch_id": "big", "segment_count": "50", "token_estimate": "1000"},
        {"batch_id": "small", "segment_count": "7", "token_estimate": "200"},
        {"batch_id": "tiny", "segment_count": "2", "token_estimate": "50"},
    ]
    assert _smoke_test_candidate(infos) == "small"


# === Integration Tests ========================================================


def test_corpus_report_generates(tmp_path: Path) -> None:
    """corpus_report.md wird erstellt und hat gültiges Frontmatter."""
    manifest, structured, segments = _make_corpus_inputs(tmp_path)
    output = tmp_path / "corpus_report.md"

    result = generate_corpus_report(manifest, structured, segments, output)

    assert result.exists()
    content = result.read_text(encoding="utf-8")
    assert content.startswith("---")
    fm_end = content.find("---", 3)
    fm = yaml.safe_load(content[3:fm_end])
    assert fm["slug"] == "corpus-report"
    assert fm["status"] == "stable"
    assert "2" in content  # doc count
    assert "2" in content  # segment count


def test_duplicate_report_generates(tmp_path: Path) -> None:
    """duplicate_report.md wird erstellt und hat gültiges Frontmatter."""
    exact, edges = _make_duplicate_inputs(tmp_path)
    output = tmp_path / "duplicate_report.md"

    result = generate_duplicate_report(exact, edges, output)

    assert result.exists()
    content = result.read_text(encoding="utf-8")
    fm_end = content.find("---", 3)
    fm = yaml.safe_load(content[3:fm_end])
    assert fm["slug"] == "duplicate-report"
    assert "0.85" in content  # edge similarity


def test_cluster_report_generates(tmp_path: Path) -> None:
    """cluster_report.md wird erstellt und hat gültiges Frontmatter."""
    clusters, edges, batches_dir = _make_cluster_inputs(tmp_path)
    output = tmp_path / "cluster_report.md"

    result = generate_cluster_report(clusters, batches_dir, edges, output)

    assert result.exists()
    content = result.read_text(encoding="utf-8")
    fm_end = content.find("---", 3)
    fm = yaml.safe_load(content[3:fm_end])
    assert fm["slug"] == "cluster-report"
    assert "C_cluster-0001" in content
    assert "C_unsortiert" in content


def test_reports_idempotent(tmp_path: Path) -> None:
    """Zweiter Lauf erzeugt identische Outputs (Hash-Vergleich)."""
    manifest, structured, segments = _make_corpus_inputs(tmp_path)
    output = tmp_path / "corpus_report.md"

    generate_corpus_report(manifest, structured, segments, output)
    hash1 = hashlib.sha256(output.read_bytes()).hexdigest()

    generate_corpus_report(manifest, structured, segments, output)
    hash2 = hashlib.sha256(output.read_bytes()).hexdigest()

    assert hash1 == hash2, "Zweiter Lauf erzeugte anderen Hash — nicht idempotent"


def test_reports_force_regenerates(tmp_path: Path) -> None:
    """Mit force=True wird der Report auch bei Cache-Hit neu generiert."""
    exact, edges = _make_duplicate_inputs(tmp_path)
    output = tmp_path / "duplicate_report.md"

    generate_duplicate_report(exact, edges, output)
    mtime1 = output.stat().st_mtime

    # Kurze Pause nötig damit mtime sich unterscheidet
    import time

    time.sleep(0.05)
    generate_duplicate_report(exact, edges, output, force=True)
    mtime2 = output.stat().st_mtime

    assert mtime2 >= mtime1


def test_run_phase_10_returns_summary(tmp_path: Path) -> None:
    """run_phase_10 gibt Summary-Dict mit 3 reports_generated zurück."""
    manifest, structured, segments = _make_corpus_inputs(tmp_path)
    exact, edges = _make_duplicate_inputs(tmp_path)
    clusters, _, batches_dir = _make_cluster_inputs(tmp_path)

    summary = run_phase_10(
        manifest_path=manifest,
        structured_path=structured,
        segments_path=segments,
        exact_path=exact,
        edges_path=edges,
        clusters_path=clusters,
        batches_dir=batches_dir,
        output_dir=tmp_path,
    )

    assert summary["reports_generated"] == 3
    assert len(summary["report_paths"]) == 3
    for p in summary["report_paths"]:
        assert Path(p).exists()


def test_reports_command_runs(tmp_path: Path) -> None:
    """CLI-Command 'reports' läuft durch ohne Exception (auf echten Outputs)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["reports", "--help"])
    assert result.exit_code == 0
    assert "Kontroll-Berichte" in result.output
