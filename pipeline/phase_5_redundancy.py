"""Phase 5 — Redundanz-Erkennung: exakte und nahe Duplikate finden.

Input:  data/02_pipeline_output/cleaned_documents.jsonl  (Phase 2 Output)
        data/02_pipeline_output/segments.jsonl            (Phase 4 Output)
Output: data/02_pipeline_output/exact_duplicates.json
        data/02_pipeline_output/near_duplicate_edges.jsonl
        data/02_pipeline_output/near_duplicate_edges.jsonl.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 5):
  - Performance: TF-IDF < 5 min auf 200 Docs / 3000 Segmenten
  - Threshold konfigurierbar
  - Symmetrische Kanten (a->b == b->a, nur upper-triangle gespeichert)
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from pipeline.schemas import (
    CleanedDocument,
    ExactDuplicateGroup,
    NearDuplicateEdge,
    SegmentRecord,
)

log = structlog.get_logger()


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _combined_input_hash(cleaned_path: Path, segments_path: Path) -> str:
    """Kombinierter SHA-256 aus zwei Input-Dateien."""
    h = hashlib.sha256()
    for path in (cleaned_path, segments_path):
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _load_cleaned(cleaned_path: Path) -> list[CleanedDocument]:
    """Lädt CleanedDocuments aus JSONL."""
    records = []
    for line in cleaned_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(CleanedDocument.model_validate_json(line))
    return records


def _load_segments(segments_path: Path) -> list[SegmentRecord]:
    """Lädt SegmentRecords aus JSONL."""
    records = []
    for line in segments_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(SegmentRecord.model_validate_json(line))
    return records


def _find_exact_duplicates(cleaned: list[CleanedDocument]) -> list[ExactDuplicateGroup]:
    """Grupiert Dokumente mit identischem normalisierten SHA-256."""
    by_hash: dict[str, list[str]] = defaultdict(list)
    for doc in cleaned:
        by_hash[doc.normalized_sha256].append(doc.doc_id)
    return [
        ExactDuplicateGroup(sha256=sha, doc_ids=ids)
        for sha, ids in by_hash.items()
        if len(ids) >= 2
    ]


def _find_near_duplicates(
    segments: list[SegmentRecord],
    threshold: float,
    ngram_range: tuple[int, int],
    max_features: int,
    min_df: int,
    batch_size: int = 500,
) -> list[NearDuplicateEdge]:
    """TF-IDF Cosine-Similarity auf Segment-Texten; gibt Kanten >= threshold zurück.

    Nur upper-triangle: segment_id_a < segment_id_b (nach Listensortierung).
    """
    if not segments:
        return []

    texts = [seg.text for seg in segments]
    ids = [seg.segment_id for seg in segments]
    n = len(segments)

    effective_min_df = min(min_df, max(1, n // 10))

    vec = TfidfVectorizer(
        ngram_range=ngram_range,
        max_features=max_features,
        min_df=effective_min_df,
        sublinear_tf=True,
    )
    tfidf_matrix = vec.fit_transform(texts)
    tfidf_matrix = normalize(tfidf_matrix, norm="l2", copy=False)

    edges: list[NearDuplicateEdge] = []

    for i_start in range(0, n, batch_size):
        i_end = min(i_start + batch_size, n)
        batch = tfidf_matrix[i_start:i_end]
        sim_block: np.ndarray = (batch @ tfidf_matrix.T).toarray()

        local_idxs, j_idxs = np.where(sim_block >= threshold)

        for local_i, j in zip(local_idxs.tolist(), j_idxs.tolist(), strict=True):
            global_i = i_start + local_i
            if j <= global_i:
                continue
            edges.append(
                NearDuplicateEdge(
                    segment_id_a=ids[global_i],
                    segment_id_b=ids[j],
                    similarity=round(float(sim_block[local_i, j]), 6),
                )
            )

    return edges


def _write_exact_duplicates(path: Path, groups: list[ExactDuplicateGroup]) -> None:
    """Schreibt ExactDuplicateGroups als JSON-Array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [g.model_dump() for g in groups]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_near_duplicate_edges(path: Path, edges: list[NearDuplicateEdge]) -> None:
    """Schreibt NearDuplicateEdges als JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for edge in edges:
            fh.write(edge.model_dump_json() + "\n")


def _load_near_duplicate_edges(path: Path) -> list[NearDuplicateEdge]:
    """Lädt NearDuplicateEdges aus JSONL."""
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(NearDuplicateEdge.model_validate_json(line))
    return records


def _load_exact_duplicates(path: Path) -> list[ExactDuplicateGroup]:
    """Lädt ExactDuplicateGroups aus JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ExactDuplicateGroup.model_validate(item) for item in data]


def _write_meta(
    meta_path: Path,
    input_hash: str,
    output_hash: str,
    duration_seconds: float,
    pipeline_version: str,
    config_snapshot: dict[str, Any],
) -> None:
    """Schreibt das Meta-File für Idempotenz-Tracking."""
    meta: dict[str, Any] = {
        "phase": "phase_5_redundancy",
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": config_snapshot,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _meta_matches(meta_path: Path, input_hash: str) -> bool:
    """Prüft ob das bestehende Meta-File den selben Input-Hash enthält."""
    if not meta_path.exists():
        return False
    try:
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(meta.get("input_hash") == input_hash)
    except (json.JSONDecodeError, OSError):
        return False


def run_phase_5(
    cleaned_path: Path,
    segments_path: Path,
    exact_output_path: Path,
    edges_output_path: Path,
    *,
    force: bool = False,
    tfidf_enabled: bool = True,
    tfidf_threshold: float = 0.72,
    ngram_range: tuple[int, int] = (1, 2),
    max_features: int = 20000,
    min_df: int = 2,
    pipeline_version: str = "0.1.0",
) -> tuple[list[ExactDuplicateGroup], list[NearDuplicateEdge]]:
    """Phase 5 ausführen: Exakte und nahe Duplikate erkennen.

    Args:
        cleaned_path: Pfad zur cleaned_documents.jsonl (Phase 2 Output).
        segments_path: Pfad zur segments.jsonl (Phase 4 Output).
        exact_output_path: Ziel für exact_duplicates.json.
        edges_output_path: Ziel für near_duplicate_edges.jsonl.
        force: Cache ignorieren und neu berechnen.
        tfidf_enabled: TF-IDF-Stufe aktivieren.
        tfidf_threshold: Cosine-Similarity-Schwellwert für Kanten.
        ngram_range: N-Gramm-Bereich für TF-IDF.
        max_features: Maximale Feature-Anzahl für TF-IDF.
        min_df: Minimale Dokument-Häufigkeit pro Term.
        pipeline_version: Version für Meta-File.

    Returns:
        Tupel (exact_duplicate_groups, near_duplicate_edges).

    Raises:
        FileNotFoundError: Wenn cleaned_path oder segments_path nicht existiert.
    """
    for p in (cleaned_path, segments_path):
        if not p.exists():
            raise FileNotFoundError(f"Input nicht gefunden: {p}")

    input_hash = _combined_input_hash(cleaned_path, segments_path)
    meta_path = Path(str(edges_output_path) + ".meta.json")

    if (
        not force
        and exact_output_path.exists()
        and edges_output_path.exists()
        and _meta_matches(meta_path, input_hash)
    ):
        log.info(
            "phase_5_skipped",
            phase="phase_5_redundancy",
            reason="same_input_hash",
            output=str(edges_output_path),
        )
        return _load_exact_duplicates(exact_output_path), _load_near_duplicate_edges(
            edges_output_path
        )

    cleaned = _load_cleaned(cleaned_path)
    segments = _load_segments(segments_path)

    log.info(
        "phase_5_start",
        phase="phase_5_redundancy",
        doc_count=len(cleaned),
        segment_count=len(segments),
        force=force,
    )

    t_start = time.monotonic()

    exact_groups = _find_exact_duplicates(cleaned)
    log.info(
        "phase_5_exact_done",
        phase="phase_5_redundancy",
        duplicate_groups=len(exact_groups),
        duplicate_docs=sum(len(g.doc_ids) for g in exact_groups),
    )

    edges: list[NearDuplicateEdge] = []
    if tfidf_enabled:
        edges = _find_near_duplicates(
            segments,
            threshold=tfidf_threshold,
            ngram_range=ngram_range,
            max_features=max_features,
            min_df=min_df,
        )
        log.info(
            "phase_5_tfidf_done",
            phase="phase_5_redundancy",
            edge_count=len(edges),
            threshold=tfidf_threshold,
        )

    _write_exact_duplicates(exact_output_path, exact_groups)
    _write_near_duplicate_edges(edges_output_path, edges)

    output_hash = f"sha256:{_sha256_file(edges_output_path)}"
    duration = time.monotonic() - t_start

    _write_meta(
        meta_path,
        input_hash,
        output_hash,
        duration,
        pipeline_version,
        {
            "tfidf_enabled": tfidf_enabled,
            "tfidf_threshold": tfidf_threshold,
            "ngram_range": list(ngram_range),
            "max_features": max_features,
            "min_df": min_df,
        },
    )

    log.info(
        "phase_5_done",
        phase="phase_5_redundancy",
        exact_groups=len(exact_groups),
        near_duplicate_edges=len(edges),
        duration_seconds=round(duration, 2),
    )

    return exact_groups, edges
