"""Phase 6 — Embeddings + Cluster-Vorbereitung.

Input:  data/02_pipeline_output/segments.jsonl            (Phase 4 Output)
Output: data/02_pipeline_output/embeddings.parquet
        data/02_pipeline_output/cluster_proposals.json
        data/02_pipeline_output/cluster_proposals.json.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 6):
  - Embeddings als Parquet (kompakt, schnell lesbar)
  - Cluster-Vorschlaege mit Label-Vermutung pro Cluster
  - Mikrocluster (< min_cluster_size) gehen in 'unsortiert'
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components as _scipy_connected_components

from pipeline.schemas import ClusterProposal, SegmentRecord

log = structlog.get_logger()


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _input_hash(segments_path: Path, model_name: str) -> str:
    """Kombinierter Hash aus Segments-Datei und Modell-Name."""
    h = hashlib.sha256()
    with segments_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    h.update(model_name.encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


def _resolve_device(device: str) -> str:
    """Gibt verfuegbares Device zurueck; faellt auf cpu zurueck wenn mps nicht verfuegbar."""
    if device == "mps":
        try:
            import torch

            return "mps" if torch.backends.mps.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return device


def _load_segments(segments_path: Path) -> list[SegmentRecord]:
    """Laedt SegmentRecords aus JSONL."""
    records = []
    for line in segments_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(SegmentRecord.model_validate_json(line))
    return records


def _embed_segments(
    segments: list[SegmentRecord],
    model_name: str,
    batch_size: int,
    device: str,
) -> np.ndarray:
    """Berechnet L2-normalisierte Embeddings fuer alle Segmente.

    Returns:
        float32-Array der Form (n_segments, embedding_dim), L2-normalisiert.
    """
    from sentence_transformers import SentenceTransformer

    effective_device = _resolve_device(device)
    log.info(
        "phase_6_loading_model",
        phase="phase_6_embeddings",
        model=model_name,
        device=effective_device,
    )
    model = SentenceTransformer(model_name, device=effective_device)
    texts = [seg.text for seg in segments]
    embeddings: np.ndarray = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype(np.float32)


def _write_parquet(
    path: Path,
    segments: list[SegmentRecord],
    embeddings: np.ndarray,
    model_name: str,
) -> None:
    """Schreibt Embeddings als Parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "segment_id": pa.array([s.segment_id for s in segments], type=pa.string()),
            "doc_id": pa.array([s.doc_id for s in segments], type=pa.string()),
            "model": pa.array([model_name] * len(segments), type=pa.string()),
            "embedding": pa.array(
                [row.tolist() for row in embeddings],
                type=pa.list_(pa.float32()),
            ),
        }
    )
    pq.write_table(table, path, compression="snappy")  # type: ignore[no-untyped-call]  # pyarrow untyped


def _load_parquet(path: Path) -> tuple[list[str], np.ndarray]:
    """Laedt segment_ids und Embedding-Matrix aus Parquet.

    Returns:
        (segment_ids, embeddings) wobei embeddings shape (n, dim) hat.
    """
    table = pq.read_table(path, columns=["segment_id", "embedding"])  # type: ignore[no-untyped-call]  # pyarrow untyped
    segment_ids = table["segment_id"].to_pylist()
    embeddings = np.array(table["embedding"].to_pylist(), dtype=np.float32)
    return segment_ids, embeddings


def _find_component_labels(embeddings: np.ndarray, threshold: float) -> np.ndarray:
    """Findet Connected-Components im Aehnlichkeitsgraph.

    Args:
        embeddings: L2-normalisierte Embeddings (n, dim).
        threshold: Cosine-Similarity-Schwellwert fuer eine Kante.

    Returns:
        int-Array der Laenge n; gleiche Werte = gleiche Komponente.
    """
    sim = embeddings @ embeddings.T
    adj = (sim >= threshold).astype(np.uint8)
    np.fill_diagonal(adj, 0)
    _, labels = _scipy_connected_components(csr_matrix(adj), directed=False)
    return np.asarray(labels)


def _internal_mean_similarity(indices: list[int], sim_matrix: np.ndarray) -> float:
    """Mittlere paarweise Cosine-Similarity innerhalb eines Clusters."""
    if len(indices) < 2:
        return 0.0
    idx = np.array(indices)
    sub = sim_matrix[np.ix_(idx, idx)]
    n = len(indices)
    upper_sum = float((sub.sum() - float(np.trace(sub))) / 2)
    count = n * (n - 1) / 2
    return round(upper_sum / count, 4) if count > 0 else 0.0


def _make_label_guess(indices: list[int], segments: list[SegmentRecord]) -> str:
    """Leitet Label-Vermutung aus haeufigstem Top-Level-Heading ab."""
    top_headings: list[str] = []
    for i in indices:
        seg = segments[i]
        if seg.heading_path:
            top_headings.append(seg.heading_path[0])
        else:
            top_headings.append(seg.doc_id.removeprefix("D_").replace("-", " "))
    if not top_headings:
        return "unbekannt"
    most_common: str = Counter(top_headings).most_common(1)[0][0]
    return most_common[:80].strip()


def _build_cluster_proposals(
    segments: list[SegmentRecord],
    embeddings: np.ndarray,
    threshold: float,
    min_cluster_size: int,
) -> list[ClusterProposal]:
    """Erstellt Cluster-Vorschlaege via Connected-Components.

    Komponenten < min_cluster_size landen in einem gemeinsamen 'C_unsortiert'-Cluster.
    """
    labels = _find_component_labels(embeddings, threshold)
    sim_matrix = embeddings @ embeddings.T

    component_to_indices: dict[int, list[int]] = {}
    for i, label in enumerate(labels.tolist()):
        component_to_indices.setdefault(label, []).append(i)

    proposals: list[ClusterProposal] = []
    unsorted_indices: list[int] = []
    cluster_idx = 0

    for indices in sorted(component_to_indices.values(), key=len, reverse=True):
        if len(indices) < min_cluster_size:
            unsorted_indices.extend(indices)
            continue
        proposals.append(
            ClusterProposal(
                cluster_id=f"C_cluster-{cluster_idx:04d}",
                label_guess=_make_label_guess(indices, segments),
                segment_ids=[segments[i].segment_id for i in indices],
                internal_similarity_mean=_internal_mean_similarity(indices, sim_matrix),
            )
        )
        cluster_idx += 1

    if unsorted_indices:
        proposals.append(
            ClusterProposal(
                cluster_id="C_unsortiert",
                label_guess="unsortiert",
                segment_ids=[segments[i].segment_id for i in unsorted_indices],
                internal_similarity_mean=_internal_mean_similarity(unsorted_indices, sim_matrix),
            )
        )

    return proposals


def _write_cluster_proposals(path: Path, proposals: list[ClusterProposal]) -> None:
    """Schreibt ClusterProposals als JSON-Array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [p.model_dump() for p in proposals]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_cluster_proposals(path: Path) -> list[ClusterProposal]:
    """Laedt ClusterProposals aus JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ClusterProposal.model_validate(item) for item in data]


def _write_meta(
    meta_path: Path,
    input_hash: str,
    output_hash: str,
    duration_seconds: float,
    pipeline_version: str,
    config_snapshot: dict[str, Any],
) -> None:
    """Schreibt das Meta-File fuer Idempotenz-Tracking."""
    meta: dict[str, Any] = {
        "phase": "phase_6_embeddings",
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": config_snapshot,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _meta_matches(meta_path: Path, input_hash: str) -> bool:
    """Prueft ob das bestehende Meta-File den selben Input-Hash enthaelt."""
    if not meta_path.exists():
        return False
    try:
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(meta.get("input_hash") == input_hash)
    except (json.JSONDecodeError, OSError):
        return False


def run_phase_6(
    segments_path: Path,
    embeddings_path: Path,
    clusters_path: Path,
    *,
    force: bool = False,
    model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    batch_size: int = 32,
    device: str = "mps",
    similarity_threshold: float = 0.85,
    min_cluster_size: int = 3,
    pipeline_version: str = "0.1.0",
) -> tuple[int, list[ClusterProposal]]:
    """Phase 6 ausfuehren: Embeddings berechnen und Cluster-Vorschlaege erstellen.

    Args:
        segments_path: Pfad zur segments.jsonl (Phase 4 Output).
        embeddings_path: Ziel fuer embeddings.parquet.
        clusters_path: Ziel fuer cluster_proposals.json.
        force: Cache ignorieren und neu berechnen.
        model_name: sentence-transformers Modell-Name.
        batch_size: Batch-Groesse fuer Inference.
        device: Ziel-Device ('mps', 'cuda', 'cpu').
        similarity_threshold: Cosine-Similarity-Schwellwert fuer Cluster-Kanten.
        min_cluster_size: Minimale Cluster-Groesse (kleinere -> 'unsortiert').
        pipeline_version: Version fuer Meta-File.

    Returns:
        Tupel (n_embeddings, cluster_proposals).

    Raises:
        FileNotFoundError: Wenn segments_path nicht existiert.
    """
    if not segments_path.exists():
        raise FileNotFoundError(f"Input nicht gefunden: {segments_path}")

    ih = _input_hash(segments_path, model_name)
    meta_path = Path(str(clusters_path) + ".meta.json")

    if (
        not force
        and embeddings_path.exists()
        and clusters_path.exists()
        and _meta_matches(meta_path, ih)
    ):
        log.info(
            "phase_6_skipped",
            phase="phase_6_embeddings",
            reason="same_input_hash",
            output=str(clusters_path),
        )
        proposals = _load_cluster_proposals(clusters_path)
        _, cached_embeddings = _load_parquet(embeddings_path)
        return len(cached_embeddings), proposals

    segments = _load_segments(segments_path)
    log.info(
        "phase_6_start",
        phase="phase_6_embeddings",
        segment_count=len(segments),
        model=model_name,
        force=force,
    )

    t_start = time.monotonic()
    embeddings = _embed_segments(segments, model_name, batch_size, device)
    log.info(
        "phase_6_embeddings_done",
        phase="phase_6_embeddings",
        segment_count=len(segments),
        embedding_dim=embeddings.shape[1] if len(embeddings) > 0 else 0,
    )

    _write_parquet(embeddings_path, segments, embeddings, model_name)

    proposals = _build_cluster_proposals(
        segments, embeddings, similarity_threshold, min_cluster_size
    )

    named_clusters = [p for p in proposals if p.cluster_id != "C_unsortiert"]
    unsorted = next((p for p in proposals if p.cluster_id == "C_unsortiert"), None)
    log.info(
        "phase_6_clustering_done",
        phase="phase_6_embeddings",
        named_cluster_count=len(named_clusters),
        unsorted_segment_count=len(unsorted.segment_ids) if unsorted else 0,
        threshold=similarity_threshold,
    )

    _write_cluster_proposals(clusters_path, proposals)
    output_hash = f"sha256:{_sha256_file(clusters_path)}"
    duration = time.monotonic() - t_start

    _write_meta(
        meta_path,
        ih,
        output_hash,
        duration,
        pipeline_version,
        {
            "model_name": model_name,
            "similarity_threshold": similarity_threshold,
            "min_cluster_size": min_cluster_size,
        },
    )

    log.info(
        "phase_6_done",
        phase="phase_6_embeddings",
        n_embeddings=len(segments),
        named_clusters=len(named_clusters),
        duration_seconds=round(duration, 2),
    )

    return len(segments), proposals
