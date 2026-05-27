"""Tests fuer Phase 7 — LLM-Batch-Bildung.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 7:
  - Jeder Batch ist ein valides Markdown (hat Frontmatter + Qwen-Header)
  - Token-Schaetzung pro Batch geloggt
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import json
import time
from pathlib import Path

import pytest
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_5_redundancy import run_phase_5
from pipeline.phase_7_batches import (
    _build_batch_markdown,
    _edges_for_cluster,
    _estimate_tokens,
    _slugify,
    _split_into_sub_batches,
    run_phase_7,
)
from pipeline.schemas import ClusterProposal, NearDuplicateEdge, SegmentRecord

# === Hilfsfunktionen ===========================================================


def _make_segment(seg_id: str, doc_id: str = "D_test", words: int = 100) -> SegmentRecord:
    text = ("wort " * words).strip()
    return SegmentRecord(
        segment_id=seg_id,
        doc_id=doc_id,
        source_path="/test.md",
        heading_path=["Abschnitt"],
        segment_index=0,
        text=text,
        word_count=words,
        char_count=len(text),
        contains_code=False,
        contains_table=False,
    )


def _make_cluster(cluster_id: str, seg_ids: list[str]) -> ClusterProposal:
    return ClusterProposal(
        cluster_id=cluster_id,
        label_guess="Test Cluster",
        segment_ids=seg_ids,
        internal_similarity_mean=0.9,
    )


# === _estimate_tokens ==========================================================


def test_estimate_tokens_basic() -> None:
    assert _estimate_tokens("abcd") == 1
    assert _estimate_tokens("a" * 400) == 100


def test_estimate_tokens_minimum() -> None:
    assert _estimate_tokens("") == 1
    assert _estimate_tokens("x") == 1


# === _slugify ==================================================================


def test_slugify_simple() -> None:
    assert _slugify("Python Grundlagen") == "python-grundlagen"


def test_slugify_special_chars() -> None:
    result = _slugify("Übersicht: API & REST")
    assert " " not in result
    assert ":" not in result
    assert "&" not in result


def test_slugify_max_length() -> None:
    result = _slugify("a" * 200)
    assert len(result) <= 50


def test_slugify_empty_fallback() -> None:
    assert _slugify("!!!") == "batch"


# === _edges_for_cluster ========================================================


def test_edges_for_cluster_filters_correctly() -> None:
    edges = [
        NearDuplicateEdge(segment_id_a="A", segment_id_b="B", similarity=0.9),
        NearDuplicateEdge(segment_id_a="A", segment_id_b="C", similarity=0.8),
        NearDuplicateEdge(segment_id_a="X", segment_id_b="Y", similarity=0.75),
    ]
    result = _edges_for_cluster({"A", "B"}, edges)
    assert len(result) == 1
    assert result[0].segment_id_a == "A"
    assert result[0].segment_id_b == "B"


def test_edges_for_cluster_empty_when_no_match() -> None:
    edges = [NearDuplicateEdge(segment_id_a="X", segment_id_b="Y", similarity=0.9)]
    result = _edges_for_cluster({"A", "B"}, edges)
    assert result == []


# === _split_into_sub_batches ===================================================


def test_split_small_cluster_stays_whole() -> None:
    segs = [_make_segment(f"D_test-S{i:04d}", words=10) for i in range(3)]
    result = _split_into_sub_batches(segs, max_tokens=10000)
    assert len(result) == 1
    assert result[0] == segs


def test_split_large_cluster_into_multiple() -> None:
    # 10 segments each ~5000 tokens -> should be split
    segs = [_make_segment(f"D_test-S{i:04d}", words=5000) for i in range(10)]
    result = _split_into_sub_batches(segs, max_tokens=10000)
    assert len(result) > 1


def test_split_all_segments_covered() -> None:
    segs = [_make_segment(f"D_test-S{i:04d}", words=100) for i in range(20)]
    sub_batches = _split_into_sub_batches(segs, max_tokens=1000)
    covered = [seg for batch in sub_batches for seg in batch]
    assert len(covered) == 20


# === _build_batch_markdown =====================================================


def test_batch_has_yaml_frontmatter() -> None:
    segs = [_make_segment("D_a-S0000")]
    content = _build_batch_markdown(
        batch_id="batch_001_test",
        cluster_id="C_cluster-0000",
        label_guess="Test",
        segments=segs,
        edges=[],
        sub_label="1/1",
        pipeline_version="0.1.0",
    )
    assert content.startswith("---\n")
    assert "\n---\n" in content


def test_batch_has_qwen_instruction_header() -> None:
    segs = [_make_segment("D_a-S0000")]
    content = _build_batch_markdown(
        batch_id="batch_001_test",
        cluster_id="C_cluster-0000",
        label_guess="Test",
        segments=segs,
        edges=[],
        sub_label="1/1",
        pipeline_version="0.1.0",
    )
    assert "QWEN-ANWEISUNG" in content
    assert "prompts/v1/stage1_cluster_analysis.md" in content


def test_batch_contains_segment_text() -> None:
    segs = [_make_segment("D_a-S0000")]
    content = _build_batch_markdown(
        batch_id="batch_001_test",
        cluster_id="C_cluster-0000",
        label_guess="Test",
        segments=segs,
        edges=[],
        sub_label="1/1",
        pipeline_version="0.1.0",
    )
    assert "D_a-S0000" in content
    assert segs[0].text in content


def test_batch_contains_edge_table() -> None:
    segs = [_make_segment(f"D_a-S{i:04d}") for i in range(2)]
    edge = NearDuplicateEdge(segment_id_a="D_a-S0000", segment_id_b="D_a-S0001", similarity=0.9)
    content = _build_batch_markdown(
        batch_id="batch_001_test",
        cluster_id="C_cluster-0000",
        label_guess="Test",
        segments=segs,
        edges=[edge],
        sub_label="1/1",
        pipeline_version="0.1.0",
    )
    assert "Nahe Duplikate" in content
    assert "0.9000" in content


# === run_phase_7 ===============================================================


def _build_p1_p2_p4_p5_outputs(corpus: Path, tmp: Path) -> tuple[Path, Path, Path]:
    """Phase 1+2+4+5 -> (segments_path, edges_path, clusters_path_placeholder)."""
    manifest = tmp / "manifest.jsonl"
    cleaned = tmp / "cleaned.jsonl"
    segments = tmp / "segments.jsonl"
    exact_path = tmp / "exact.json"
    edges_path = tmp / "edges.jsonl"

    run_phase_1(corpus_input=corpus, output_path=manifest)
    run_phase_2(manifest_path=manifest, output_path=cleaned)
    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=segments)
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=exact_path,
        edges_output_path=edges_path,
    )
    return segments, edges_path


def _write_minimal_clusters(tmp: Path, segments_path: Path) -> Path:
    """Erstellt eine minimale cluster_proposals.json mit 2 Named Clustern."""
    import json as _json

    from pipeline.schemas import SegmentRecord

    all_segs = []
    for line in segments_path.read_text().splitlines():
        if line.strip():
            all_segs.append(SegmentRecord.model_validate_json(line))

    half = len(all_segs) // 2
    clusters = [
        {
            "cluster_id": "C_cluster-0000",
            "label_guess": "Gruppe A",
            "segment_ids": [s.segment_id for s in all_segs[:half]],
            "internal_similarity_mean": 0.88,
        },
        {
            "cluster_id": "C_cluster-0001",
            "label_guess": "Gruppe B",
            "segment_ids": [s.segment_id for s in all_segs[half:]],
            "internal_similarity_mean": 0.82,
        },
    ]
    clusters_path = tmp / "clusters.json"
    clusters_path.write_text(_json.dumps(clusters, ensure_ascii=False), encoding="utf-8")
    return clusters_path


def test_missing_segments_raises(tmp_path: Path) -> None:
    edges = tmp_path / "edges.jsonl"
    edges.write_text("")
    clusters = tmp_path / "clusters.json"
    clusters.write_text("[]")
    with pytest.raises(FileNotFoundError):
        run_phase_7(
            segments_path=tmp_path / "nonexistent.jsonl",
            clusters_path=clusters,
            edges_path=edges,
            output_dir=tmp_path / "batches",
        )


def test_missing_clusters_raises(tmp_path: Path) -> None:
    segs = tmp_path / "segs.jsonl"
    segs.write_text("")
    edges = tmp_path / "edges.jsonl"
    edges.write_text("")
    with pytest.raises(FileNotFoundError):
        run_phase_7(
            segments_path=segs,
            clusters_path=tmp_path / "nonexistent.json",
            edges_path=edges,
            output_dir=tmp_path / "batches",
        )


def test_batch_files_created(sample_corpus_dir: Path, tmp_path: Path) -> None:
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)
    clusters = _write_minimal_clusters(tmp_path, segments)
    batch_dir = tmp_path / "batches"

    batch_paths = run_phase_7(
        segments_path=segments,
        clusters_path=clusters,
        edges_path=edges,
        output_dir=batch_dir,
    )
    assert len(batch_paths) > 0
    for p in batch_paths:
        assert p.exists()
        assert p.suffix == ".md"


def test_every_batch_has_frontmatter_and_header(sample_corpus_dir: Path, tmp_path: Path) -> None:
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)
    clusters = _write_minimal_clusters(tmp_path, segments)

    batch_paths = run_phase_7(
        segments_path=segments,
        clusters_path=clusters,
        edges_path=edges,
        output_dir=tmp_path / "batches",
    )
    for p in batch_paths:
        content = p.read_text(encoding="utf-8")
        assert content.startswith("---\n"), f"Kein Frontmatter: {p.name}"
        assert "QWEN-ANWEISUNG" in content, f"Kein Qwen-Header: {p.name}"
        assert "token_estimate:" in content, f"Keine Token-Schaetzung: {p.name}"


def test_batch_filenames_sequential(sample_corpus_dir: Path, tmp_path: Path) -> None:
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)
    clusters = _write_minimal_clusters(tmp_path, segments)

    batch_paths = run_phase_7(
        segments_path=segments,
        clusters_path=clusters,
        edges_path=edges,
        output_dir=tmp_path / "batches",
    )
    names = sorted(p.name for p in batch_paths)
    assert names[0].startswith("batch_001_")
    if len(names) > 1:
        assert names[1].startswith("batch_002_")


def test_unsorted_cluster_skipped(sample_corpus_dir: Path, tmp_path: Path) -> None:
    """C_unsortiert produziert keine Batch-Files wenn skip_unsorted=True."""
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)

    import json as _json

    from pipeline.schemas import SegmentRecord

    all_segs = [
        SegmentRecord.model_validate_json(line)
        for line in segments.read_text().splitlines()
        if line.strip()
    ]
    clusters_data = [
        {
            "cluster_id": "C_unsortiert",
            "label_guess": "unsortiert",
            "segment_ids": [s.segment_id for s in all_segs],
            "internal_similarity_mean": 0.0,
        }
    ]
    clusters_path = tmp_path / "clusters_unsorted.json"
    clusters_path.write_text(_json.dumps(clusters_data), encoding="utf-8")

    batch_paths = run_phase_7(
        segments_path=segments,
        clusters_path=clusters_path,
        edges_path=edges,
        output_dir=tmp_path / "batches_unsorted",
        skip_unsorted=True,
    )
    assert batch_paths == []


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)
    clusters = _write_minimal_clusters(tmp_path, segments)
    batch_dir = tmp_path / "batches"

    run_phase_7(
        segments_path=segments,
        clusters_path=clusters,
        edges_path=edges,
        output_dir=batch_dir,
    )
    meta_path = batch_dir / ".meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_7_batches"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["batch_count"] > 0


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path) -> None:
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)
    clusters = _write_minimal_clusters(tmp_path, segments)
    batch_dir = tmp_path / "batches"

    run_phase_7(
        segments_path=segments, clusters_path=clusters, edges_path=edges, output_dir=batch_dir
    )
    meta_path = batch_dir / ".meta.json"
    mtime_first = meta_path.stat().st_mtime_ns

    run_phase_7(
        segments_path=segments, clusters_path=clusters, edges_path=edges, output_dir=batch_dir
    )
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_first == mtime_second, "Idempotenz verletzt"


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path) -> None:
    segments, edges = _build_p1_p2_p4_p5_outputs(sample_corpus_dir, tmp_path)
    clusters = _write_minimal_clusters(tmp_path, segments)
    batch_dir = tmp_path / "batches"

    run_phase_7(
        segments_path=segments, clusters_path=clusters, edges_path=edges, output_dir=batch_dir
    )
    meta_path = batch_dir / ".meta.json"
    mtime_first = meta_path.stat().st_mtime_ns
    time.sleep(0.01)
    run_phase_7(
        segments_path=segments,
        clusters_path=clusters,
        edges_path=edges,
        output_dir=batch_dir,
        force=True,
    )
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first
