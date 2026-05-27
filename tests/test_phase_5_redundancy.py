"""Tests für Phase 5 — Redundanz-Erkennung.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 5:
  - Exakte Duplikate: SHA-256 auf normalisiertem Text
  - TF-IDF Cosine-Similarity >= Threshold -> Kanten
  - Symmetrische Kanten (nur upper-triangle gespeichert, a < b per Listenordnung)
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import json
import time
from pathlib import Path

import pytest
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_5_redundancy import (
    _find_exact_duplicates,
    _find_near_duplicates,
    run_phase_5,
)
from pipeline.schemas import CleanedDocument, ExactDuplicateGroup, NearDuplicateEdge, SegmentRecord

# === _find_exact_duplicates ====================================================


def test_no_duplicates_returns_empty() -> None:
    docs = [
        CleanedDocument(doc_id="D_a", body="text a", frontmatter={}, normalized_sha256="aaa"),
        CleanedDocument(doc_id="D_b", body="text b", frontmatter={}, normalized_sha256="bbb"),
    ]
    result = _find_exact_duplicates(docs)
    assert result == []


def test_exact_duplicates_grouped() -> None:
    docs = [
        CleanedDocument(doc_id="D_a", body="same", frontmatter={}, normalized_sha256="xyz"),
        CleanedDocument(doc_id="D_b", body="same", frontmatter={}, normalized_sha256="xyz"),
        CleanedDocument(doc_id="D_c", body="other", frontmatter={}, normalized_sha256="abc"),
    ]
    result = _find_exact_duplicates(docs)
    assert len(result) == 1
    assert set(result[0].doc_ids) == {"D_a", "D_b"}
    assert result[0].sha256 == "xyz"


def test_three_way_duplicate() -> None:
    docs = [
        CleanedDocument(doc_id=f"D_{i}", body="same", frontmatter={}, normalized_sha256="dup")
        for i in range(3)
    ]
    result = _find_exact_duplicates(docs)
    assert len(result) == 1
    assert len(result[0].doc_ids) == 3


def test_multiple_duplicate_groups() -> None:
    docs = [
        CleanedDocument(doc_id="D_a1", body="x", frontmatter={}, normalized_sha256="h1"),
        CleanedDocument(doc_id="D_a2", body="x", frontmatter={}, normalized_sha256="h1"),
        CleanedDocument(doc_id="D_b1", body="y", frontmatter={}, normalized_sha256="h2"),
        CleanedDocument(doc_id="D_b2", body="y", frontmatter={}, normalized_sha256="h2"),
    ]
    result = _find_exact_duplicates(docs)
    assert len(result) == 2


# === _find_near_duplicates ====================================================


def _make_segments(texts: list[str]) -> list[SegmentRecord]:
    return [
        SegmentRecord(
            segment_id=f"D_test-S{i:04d}",
            doc_id="D_test",
            source_path="/test.md",
            heading_path=[],
            segment_index=i,
            text=text,
            word_count=len(text.split()),
            char_count=len(text),
            contains_code=False,
            contains_table=False,
        )
        for i, text in enumerate(texts)
    ]


def test_empty_segments_returns_empty() -> None:
    result = _find_near_duplicates(
        [], threshold=0.5, ngram_range=(1, 2), max_features=100, min_df=1
    )
    assert result == []


def test_identical_texts_produce_edge() -> None:
    text = "This is a test sentence with enough words to form a TF-IDF vector"
    segs = _make_segments([text, text])
    result = _find_near_duplicates(
        segs, threshold=0.99, ngram_range=(1, 1), max_features=100, min_df=1
    )
    assert len(result) == 1
    edge = result[0]
    assert edge.segment_id_a == "D_test-S0000"
    assert edge.segment_id_b == "D_test-S0001"
    assert edge.similarity >= 0.99


def test_dissimilar_texts_no_edge() -> None:
    segs = _make_segments(
        [
            "Python programming language functions classes modules",
            "Kochen Rezept Zutaten Mehl Butter Zucker Eier backen",
        ]
    )
    result = _find_near_duplicates(
        segs, threshold=0.5, ngram_range=(1, 1), max_features=100, min_df=1
    )
    assert result == []


def test_only_upper_triangle_stored() -> None:
    text = "same text same content same words repeated repeated"
    segs = _make_segments([text, text, text])
    result = _find_near_duplicates(
        segs, threshold=0.5, ngram_range=(1, 1), max_features=100, min_df=1
    )
    # For 3 identical segments: pairs (0,1), (0,2), (1,2) — exactly 3
    assert len(result) == 3
    for edge in result:
        idx_a = int(edge.segment_id_a.split("-S")[1])
        idx_b = int(edge.segment_id_b.split("-S")[1])
        assert idx_a < idx_b, f"Nicht upper-triangle: {edge.segment_id_a} vs {edge.segment_id_b}"


def test_similarity_is_float_in_range() -> None:
    text = "machine learning neural networks deep learning"
    segs = _make_segments([text, text])
    result = _find_near_duplicates(
        segs, threshold=0.5, ngram_range=(1, 1), max_features=100, min_df=1
    )
    assert len(result) == 1
    assert 0.0 <= result[0].similarity <= 1.0


# === run_phase_5 ==============================================================


def _build_pipeline_inputs(corpus: Path, tmp_path: Path) -> tuple[Path, Path]:
    """Phase 1 + 2 + 4 auf corpus -> (cleaned_path, segments_path)."""
    manifest = tmp_path / "manifest.jsonl"
    cleaned = tmp_path / "cleaned.jsonl"
    segments = tmp_path / "segments.jsonl"
    run_phase_1(corpus_input=corpus, output_path=manifest)
    run_phase_2(manifest_path=manifest, output_path=cleaned)
    run_phase_4(
        cleaned_path=cleaned,
        manifest_path=manifest,
        output_path=segments,
    )
    return cleaned, segments


def test_missing_cleaned_raises(tmp_path: Path) -> None:
    segments = tmp_path / "segments.jsonl"
    segments.write_text("")
    with pytest.raises(FileNotFoundError):
        run_phase_5(
            cleaned_path=tmp_path / "nonexistent.jsonl",
            segments_path=segments,
            exact_output_path=tmp_path / "exact.json",
            edges_output_path=tmp_path / "edges.jsonl",
        )


def test_missing_segments_raises(tmp_path: Path) -> None:
    cleaned = tmp_path / "cleaned.jsonl"
    cleaned.write_text("")
    with pytest.raises(FileNotFoundError):
        run_phase_5(
            cleaned_path=cleaned,
            segments_path=tmp_path / "nonexistent.jsonl",
            exact_output_path=tmp_path / "exact.json",
            edges_output_path=tmp_path / "edges.jsonl",
        )


def test_outputs_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    exact_path = tmp_path / "exact.json"
    edges_path = tmp_path / "edges.jsonl"
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=exact_path,
        edges_output_path=edges_path,
    )
    assert exact_path.exists()
    assert edges_path.exists()


def test_exact_output_is_valid_json(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    exact_path = tmp_path / "exact.json"
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=exact_path,
        edges_output_path=tmp_path / "edges.jsonl",
    )
    data = json.loads(exact_path.read_text())
    assert isinstance(data, list)
    for item in data:
        g = ExactDuplicateGroup.model_validate(item)
        assert len(g.doc_ids) >= 2


def test_edges_output_is_valid_jsonl(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    edges_path = tmp_path / "edges.jsonl"
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
        tfidf_threshold=0.5,
    )
    for line in edges_path.read_text().splitlines():
        if line.strip():
            edge = NearDuplicateEdge.model_validate_json(line)
            assert 0.0 <= edge.similarity <= 1.0


def test_edges_are_upper_triangle(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    edges_path = tmp_path / "edges.jsonl"
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
        tfidf_threshold=0.5,
    )
    seen_pairs: set[tuple[str, str]] = set()
    for line in edges_path.read_text().splitlines():
        if not line.strip():
            continue
        edge = NearDuplicateEdge.model_validate_json(line)
        pair = (edge.segment_id_a, edge.segment_id_b)
        reverse = (edge.segment_id_b, edge.segment_id_a)
        assert pair not in seen_pairs, f"Doppelte Kante: {pair}"
        assert reverse not in seen_pairs, f"Symmetrische Kante gespeichert: {pair}"
        seen_pairs.add(pair)


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    edges_path = tmp_path / "edges.jsonl"
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
    )
    meta_path = Path(str(edges_path) + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_5_redundancy"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["output_hash"].startswith("sha256:")


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    edges_path = tmp_path / "edges.jsonl"
    meta_path = Path(str(edges_path) + ".meta.json")

    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
    )
    mtime_first = meta_path.stat().st_mtime_ns

    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
    )
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_first == mtime_second, "Idempotenz verletzt"


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    edges_path = tmp_path / "edges.jsonl"
    meta_path = Path(str(edges_path) + ".meta.json")

    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
    )
    mtime_first = meta_path.stat().st_mtime_ns
    time.sleep(0.01)
    run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
        force=True,
    )
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first


def test_tfidf_disabled_produces_empty_edges(sample_corpus_dir: Path, tmp_path: Path) -> None:
    cleaned, segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    edges_path = tmp_path / "edges.jsonl"
    _groups, edges = run_phase_5(
        cleaned_path=cleaned,
        segments_path=segments,
        exact_output_path=tmp_path / "exact.json",
        edges_output_path=edges_path,
        tfidf_enabled=False,
    )
    assert edges == []
    assert edges_path.read_text() == ""
