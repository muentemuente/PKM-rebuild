"""Tests fuer Phase 6 - Embeddings + Cluster-Vorbereitung.

Akzeptanzkriterien aus docs/02_pipeline_spec.md, Phase 6:
  - Embeddings als Parquet (kompakt, schnell lesbar)
  - Cluster-Vorschlaege mit Label-Vermutung pro Cluster
  - Mikrocluster (< min_cluster_size) gehen in 'unsortiert'
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import json
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_6_embeddings import (
    _build_cluster_proposals,
    _find_component_labels,
    _internal_mean_similarity,
    _make_label_guess,
    _write_parquet,
    run_phase_6,
)
from pipeline.schemas import ClusterProposal, SegmentRecord

# === Hilfsfunktionen ===========================================================


def _make_segment(
    seg_id: str, doc_id: str = "D_test", heading_path: list[str] | None = None
) -> SegmentRecord:
    text = f"content of segment {seg_id} with enough words"
    return SegmentRecord(
        segment_id=seg_id,
        doc_id=doc_id,
        source_path="/test.md",
        heading_path=heading_path or [],
        segment_index=0,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        contains_code=False,
        contains_table=False,
    )


def _random_unit_vectors(n: int, dim: int = 32, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vecs = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


def _identical_unit_vectors(n: int, dim: int = 32) -> np.ndarray:
    base = np.ones((1, dim), dtype=np.float32)
    base /= np.linalg.norm(base)
    return np.tile(base, (n, 1))


@pytest.fixture
def mock_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ersetzt _embed_segments durch eine Funktion die Zufallsvektoren liefert."""
    import pipeline.phase_6_embeddings as m6

    def fake_embed(
        segments: list[SegmentRecord], model_name: str, batch_size: int, device: str
    ) -> np.ndarray:
        return _random_unit_vectors(len(segments), dim=32)

    monkeypatch.setattr(m6, "_embed_segments", fake_embed)


# === _find_component_labels ====================================================


def test_all_identical_form_one_component() -> None:
    vecs = _identical_unit_vectors(5)
    labels = _find_component_labels(vecs, threshold=0.99)
    assert len(set(labels.tolist())) == 1


def test_orthogonal_vectors_all_separate() -> None:
    n = 4
    vecs = np.eye(n, dtype=np.float32)
    labels = _find_component_labels(vecs, threshold=0.5)
    assert len(set(labels.tolist())) == n


def test_labels_length_matches_input() -> None:
    vecs = _random_unit_vectors(10)
    labels = _find_component_labels(vecs, threshold=0.9)
    assert len(labels) == 10


# === _internal_mean_similarity =================================================


def test_single_element_returns_zero() -> None:
    sim = np.array([[1.0]], dtype=np.float32)
    assert _internal_mean_similarity([0], sim) == 0.0


def test_identical_vectors_similarity_one() -> None:
    vecs = _identical_unit_vectors(3)
    sim = vecs @ vecs.T
    result = _internal_mean_similarity([0, 1, 2], sim)
    assert abs(result - 1.0) < 1e-4


def test_orthogonal_vectors_similarity_zero() -> None:
    vecs = np.eye(3, dtype=np.float32)
    sim = vecs @ vecs.T
    result = _internal_mean_similarity([0, 1, 2], sim)
    assert result == 0.0


# === _make_label_guess =========================================================


def test_label_from_heading_path() -> None:
    segs = [
        _make_segment("D_a-S0000", heading_path=["Python"]),
        _make_segment("D_b-S0000", heading_path=["Python"]),
        _make_segment("D_c-S0000", heading_path=["JavaScript"]),
    ]
    label = _make_label_guess([0, 1, 2], segs)
    assert label == "Python"


def test_label_from_doc_id_when_no_heading() -> None:
    segs = [_make_segment("D_my-topic-S0000", doc_id="D_my-topic", heading_path=[])]
    label = _make_label_guess([0], segs)
    assert "my" in label.lower() or "topic" in label.lower()


def test_label_max_length() -> None:
    long_heading = "A" * 200
    segs = [_make_segment("D_a-S0000", heading_path=[long_heading])]
    label = _make_label_guess([0], segs)
    assert len(label) <= 80


# === _build_cluster_proposals ==================================================


def test_large_components_become_named_clusters() -> None:
    n = 9
    vecs = _identical_unit_vectors(n)
    segs = [_make_segment(f"D_test-S{i:04d}") for i in range(n)]
    proposals = _build_cluster_proposals(segs, vecs, threshold=0.99, min_cluster_size=3)
    named = [p for p in proposals if p.cluster_id != "C_unsortiert"]
    assert len(named) >= 1
    assert all(len(p.segment_ids) >= 3 for p in named)


def test_small_components_land_in_unsortiert() -> None:
    # 4 orthogonal vectors -> 4 separate components -> all < min_cluster_size=3
    vecs = np.eye(4, dtype=np.float32)
    segs = [_make_segment(f"D_test-S{i:04d}") for i in range(4)]
    proposals = _build_cluster_proposals(segs, vecs, threshold=0.5, min_cluster_size=3)
    unsorted = next((p for p in proposals if p.cluster_id == "C_unsortiert"), None)
    assert unsorted is not None
    assert len(unsorted.segment_ids) == 4


def test_no_unsortiert_when_all_large() -> None:
    vecs = _identical_unit_vectors(6)
    segs = [_make_segment(f"D_test-S{i:04d}") for i in range(6)]
    proposals = _build_cluster_proposals(segs, vecs, threshold=0.99, min_cluster_size=3)
    unsorted = [p for p in proposals if p.cluster_id == "C_unsortiert"]
    assert unsorted == []


def test_cluster_ids_unique() -> None:
    vecs = _random_unit_vectors(20, dim=32, seed=0)
    segs = [_make_segment(f"D_test-S{i:04d}") for i in range(20)]
    proposals = _build_cluster_proposals(segs, vecs, threshold=0.99, min_cluster_size=2)
    ids = [p.cluster_id for p in proposals]
    assert len(ids) == len(set(ids))


def test_all_segment_ids_covered() -> None:
    vecs = _random_unit_vectors(15)
    segs = [_make_segment(f"D_test-S{i:04d}") for i in range(15)]
    proposals = _build_cluster_proposals(segs, vecs, threshold=0.9, min_cluster_size=3)
    covered = {sid for p in proposals for sid in p.segment_ids}
    expected = {s.segment_id for s in segs}
    assert covered == expected


# === _write_parquet + _load_parquet ============================================


def test_parquet_round_trip(tmp_path: Path) -> None:
    segs = [_make_segment(f"D_a-S{i:04d}") for i in range(5)]
    vecs = _random_unit_vectors(5, dim=32)
    path = tmp_path / "emb.parquet"
    _write_parquet(path, segs, vecs, "test-model")
    assert path.exists()
    table = pq.read_table(path)
    assert len(table) == 5
    assert "segment_id" in table.schema.names
    assert "embedding" in table.schema.names


# === run_phase_6 ===============================================================


def _build_pipeline_inputs(corpus: Path, tmp_path: Path) -> Path:
    """Phase 1 + 2 + 4 auf corpus -> segments_path."""
    manifest = tmp_path / "manifest.jsonl"
    cleaned = tmp_path / "cleaned.jsonl"
    segments = tmp_path / "segments.jsonl"
    run_phase_1(corpus_input=corpus, output_path=manifest)
    run_phase_2(manifest_path=manifest, output_path=cleaned)
    run_phase_4(cleaned_path=cleaned, manifest_path=manifest, output_path=segments)
    return segments


def test_missing_segments_raises(tmp_path: Path, mock_embed: None) -> None:
    with pytest.raises(FileNotFoundError):
        run_phase_6(
            segments_path=tmp_path / "nonexistent.jsonl",
            embeddings_path=tmp_path / "emb.parquet",
            clusters_path=tmp_path / "clusters.json",
        )


def test_outputs_written(sample_corpus_dir: Path, tmp_path: Path, mock_embed: None) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    emb_path = tmp_path / "emb.parquet"
    clusters_path = tmp_path / "clusters.json"
    run_phase_6(
        segments_path=segments,
        embeddings_path=emb_path,
        clusters_path=clusters_path,
    )
    assert emb_path.exists()
    assert clusters_path.exists()


def test_cluster_proposals_valid_json(
    sample_corpus_dir: Path, tmp_path: Path, mock_embed: None
) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    clusters_path = tmp_path / "clusters.json"
    run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
    )
    data = json.loads(clusters_path.read_text())
    assert isinstance(data, list)
    for item in data:
        p = ClusterProposal.model_validate(item)
        assert p.cluster_id.startswith("C_")
        assert isinstance(p.segment_ids, list)
        assert -1.0 <= p.internal_similarity_mean <= 1.0


def test_all_segments_covered(sample_corpus_dir: Path, tmp_path: Path, mock_embed: None) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    clusters_path = tmp_path / "clusters.json"
    n_segments, proposals = run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
    )
    covered_ids = {sid for p in proposals for sid in p.segment_ids}
    assert len(covered_ids) == n_segments


def test_named_clusters_min_size(sample_corpus_dir: Path, tmp_path: Path, mock_embed: None) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    _, proposals = run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=tmp_path / "clusters.json",
        min_cluster_size=3,
    )
    for p in proposals:
        if p.cluster_id != "C_unsortiert":
            assert len(p.segment_ids) >= 3


def test_meta_file_written(sample_corpus_dir: Path, tmp_path: Path, mock_embed: None) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    clusters_path = tmp_path / "clusters.json"
    run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
    )
    meta_path = Path(str(clusters_path) + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["phase"] == "phase_6_embeddings"
    assert meta["input_hash"].startswith("sha256:")
    assert meta["output_hash"].startswith("sha256:")


def test_idempotency(sample_corpus_dir: Path, tmp_path: Path, mock_embed: None) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    clusters_path = tmp_path / "clusters.json"
    meta_path = Path(str(clusters_path) + ".meta.json")

    run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
    )
    mtime_first = meta_path.stat().st_mtime_ns

    run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
    )
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_first == mtime_second, "Idempotenz verletzt"


def test_force_reruns(sample_corpus_dir: Path, tmp_path: Path, mock_embed: None) -> None:
    segments = _build_pipeline_inputs(sample_corpus_dir, tmp_path)
    clusters_path = tmp_path / "clusters.json"
    meta_path = Path(str(clusters_path) + ".meta.json")

    run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
    )
    mtime_first = meta_path.stat().st_mtime_ns
    time.sleep(0.01)
    run_phase_6(
        segments_path=segments,
        embeddings_path=tmp_path / "emb.parquet",
        clusters_path=clusters_path,
        force=True,
    )
    mtime_second = meta_path.stat().st_mtime_ns

    assert mtime_second > mtime_first
