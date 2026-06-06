"""Phase 7 — LLM-Batch-Bildung: Cluster zu Qwen-Input-Batches aufbereiten.

Input:  work/segments.jsonl            (Phase 4 Output)
        work/cluster_proposals.json    (Phase 6 Output)
        work/near_duplicate_edges.jsonl (Phase 5 Output)
Output: work/batches/batch_NNN_<slug>.md

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 7):
  - Jeder Batch ist ein valides Markdown
  - Jeder Batch enthaelt Anweisungs-Header fuer Qwen
  - Token-Schaetzung pro Batch geloggt
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pipeline.schemas import ClusterProposal, NearDuplicateEdge, SegmentRecord

log = structlog.get_logger()

_UNSORTED_CLUSTER_ID = "C_unsortiert"


# === Hilfsfunktionen ===========================================================


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binaer, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _combined_hash(paths: list[Path]) -> str:
    """Kombinierter SHA-256 aus mehreren Dateien."""
    h = hashlib.sha256()
    for p in paths:
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _estimate_tokens(text: str) -> int:
    """Schaetzt Token-Anzahl via Zeichen-Heuristik (4 Zeichen ~ 1 Token)."""
    return max(1, len(text) // 4)


def _slugify(text: str) -> str:
    """Wandelt Text in URL-sicheren Slug um (max 50 Zeichen)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:50].strip("-") or "batch"


def _format_heading_path(path: list[str]) -> str:
    """Gibt Heading-Pfad als 'A > B > C' zurück; leer wenn kein Pfad."""
    return " > ".join(path) if path else "(kein Heading)"


# === Loader ====================================================================


def _load_segments(path: Path) -> dict[str, SegmentRecord]:
    """Laedt SegmentRecords als {segment_id: record}."""
    records: dict[str, SegmentRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = SegmentRecord.model_validate_json(line)
            records[rec.segment_id] = rec
    return records


def _load_cluster_proposals(path: Path) -> list[ClusterProposal]:
    """Laedt ClusterProposals aus JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ClusterProposal.model_validate(item) for item in data]


def _load_edges(path: Path) -> list[NearDuplicateEdge]:
    """Laedt NearDuplicateEdges aus JSONL."""
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(NearDuplicateEdge.model_validate_json(line))
    return records


# === Batch-Content-Generierung =================================================


def _edges_for_cluster(
    segment_ids: set[str], all_edges: list[NearDuplicateEdge]
) -> list[NearDuplicateEdge]:
    """Filtert Kanten, bei denen beide Segment-IDs im Cluster liegen."""
    return [e for e in all_edges if e.segment_id_a in segment_ids and e.segment_id_b in segment_ids]


def _doc_segment_counts(segments: list[SegmentRecord]) -> dict[str, int]:
    """Zaehlt Segmente pro doc_id."""
    counts: dict[str, int] = defaultdict(int)
    for seg in segments:
        counts[seg.doc_id] += 1
    return dict(counts)


def _build_batch_markdown(
    batch_id: str,
    cluster_id: str,
    label_guess: str,
    segments: list[SegmentRecord],
    edges: list[NearDuplicateEdge],
    sub_label: str,
    pipeline_version: str,
) -> str:
    """Erstellt den vollstaendigen Markdown-Inhalt eines Batch-Files."""
    doc_counts = _doc_segment_counts(segments)
    token_estimate = _estimate_tokens(" ".join(seg.text for seg in segments))
    created_at = datetime.now(tz=UTC).isoformat()

    lines: list[str] = [
        "---",
        f"batch_id: {batch_id}",
        f"cluster_id: {cluster_id}",
        f"label_guess: {label_guess}",
        f"segment_count: {len(segments)}",
        f"doc_count: {len(doc_counts)}",
        f"token_estimate: {token_estimate}",
        f"sub_batch: {sub_label}",
        f"created_at: {created_at}",
        f"pipeline_version: {pipeline_version}",
        "---",
        "",
        "<!-- QWEN-ANWEISUNG",
        "Dieser Batch enthaelt Cluster-Daten fuer die Qwen-Synthese (Phase 8).",
        "Stage 1 Prompt: prompts/v1/stage1_cluster_analysis.md",
        "Stage 2 Prompt: prompts/v1/stage2_merge_proposal.md",
        "Stage 3 Prompt: prompts/v1/stage3_synthesis.md",
        "Stage 4 Prompt: prompts/v1/stage4_frontmatter_json.md",
        "-->",
        "",
        f"## Cluster: {label_guess}",
        "",
        f"**Cluster-ID:** {cluster_id} | "
        f"**Segmente:** {len(segments)} | "
        f"**Dokumente:** {len(doc_counts)} | "
        f"**Token-Schaetzung:** ~{token_estimate}",
        "",
        "### Enthaltene Dokumente",
        "",
    ]

    for doc_id, count in sorted(doc_counts.items()):
        lines.append(f"- `{doc_id}` ({count} Segment{'e' if count != 1 else ''})")

    lines.append("")

    if edges:
        lines += [
            "### Nahe Duplikate (TF-IDF, Cosine >= 0.72)",
            "",
            "| Segment A | Segment B | Similarity |",
            "|---|---|---|",
        ]
        for edge in edges[:50]:
            lines.append(
                f"| `{edge.segment_id_a}` | `{edge.segment_id_b}` | {edge.similarity:.4f} |"
            )
        if len(edges) > 50:
            lines.append(f"| *(weitere {len(edges) - 50} Kanten ausgelassen)* | | |")
        lines.append("")

    lines += ["### Segmente", ""]

    for seg in segments:
        heading = _format_heading_path(seg.heading_path)
        lines += [
            "---",
            "",
            f"**[{seg.segment_id}]** | Heading: `{heading}` | "
            f"Woerter: {seg.word_count}"
            + (" | :code:" if seg.contains_code else "")
            + (" | :table:" if seg.contains_table else ""),
            "",
            seg.text,
            "",
        ]

    return "\n".join(lines)


# === Sub-Batch-Splitting =======================================================


def _split_into_sub_batches(
    segments: list[SegmentRecord],
    max_tokens: int,
    overhead_tokens: int = 500,
) -> list[list[SegmentRecord]]:
    """Teilt Segmente in Token-begrenzte Sub-Batches auf.

    Args:
        segments: Alle Segmente des Clusters.
        max_tokens: Maximale Token-Anzahl pro Batch.
        overhead_tokens: Reserve fuer Metadaten und Header.
    """
    effective_limit = max(1, max_tokens - overhead_tokens)
    sub_batches: list[list[SegmentRecord]] = []
    current: list[SegmentRecord] = []
    current_tokens = 0

    for seg in segments:
        seg_tokens = _estimate_tokens(seg.text)
        if current and current_tokens + seg_tokens > effective_limit:
            sub_batches.append(current)
            current = [seg]
            current_tokens = seg_tokens
        else:
            current.append(seg)
            current_tokens += seg_tokens

    if current:
        sub_batches.append(current)

    return sub_batches if sub_batches else [segments]


# === Meta-File =================================================================


def _write_meta(
    meta_path: Path,
    input_hash: str,
    batch_paths: list[Path],
    duration_seconds: float,
    pipeline_version: str,
    config_snapshot: dict[str, Any],
) -> None:
    """Schreibt das Meta-File fuer Idempotenz-Tracking."""
    meta: dict[str, Any] = {
        "phase": "phase_7_batches",
        "input_hash": input_hash,
        "batch_count": len(batch_paths),
        "batch_files": [str(p) for p in batch_paths],
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": config_snapshot,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
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


def _load_meta_batch_paths(meta_path: Path) -> list[Path]:
    """Liest batch_files-Liste aus dem Meta-File."""
    meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
    return [Path(p) for p in meta.get("batch_files", [])]


# === run_phase_7 ===============================================================


def run_phase_7(
    segments_path: Path,
    clusters_path: Path,
    edges_path: Path,
    output_dir: Path,
    *,
    force: bool = False,
    max_input_tokens: int = 35000,
    split_oversized_clusters: bool = True,
    skip_unsorted: bool = True,
    pipeline_version: str = "0.1.0",
) -> list[Path]:
    """Phase 7 ausfuehren: Cluster-Batches fuer Qwen-Synthese erstellen.

    Args:
        segments_path: Pfad zur segments.jsonl (Phase 4 Output).
        clusters_path: Pfad zur cluster_proposals.json (Phase 6 Output).
        edges_path: Pfad zur near_duplicate_edges.jsonl (Phase 5 Output).
        output_dir: Ziel-Verzeichnis fuer batch_NNN_<slug>.md Files.
        force: Cache ignorieren und neu berechnen.
        max_input_tokens: Maximale Token-Anzahl pro Batch.
        split_oversized_clusters: Grosse Cluster in Sub-Batches teilen.
        skip_unsorted: C_unsortiert-Cluster ueberspringen.
        pipeline_version: Version fuer Meta-File.

    Returns:
        Liste der erstellten Batch-File-Paths.

    Raises:
        FileNotFoundError: Wenn ein Eingabe-File nicht existiert.
    """
    for p in (segments_path, clusters_path, edges_path):
        if not p.exists():
            raise FileNotFoundError(f"Input nicht gefunden: {p}")

    input_hash = _combined_hash([segments_path, clusters_path, edges_path])
    meta_path = output_dir / ".meta.json"

    if not force and _meta_matches(meta_path, input_hash):
        existing = _load_meta_batch_paths(meta_path)
        log.info(
            "phase_7_skipped",
            phase="phase_7_batches",
            reason="same_input_hash",
            batch_count=len(existing),
        )
        return existing

    seg_map = _load_segments(segments_path)
    clusters = _load_cluster_proposals(clusters_path)
    all_edges = _load_edges(edges_path)

    log.info(
        "phase_7_start",
        phase="phase_7_batches",
        cluster_count=len(clusters),
        segment_count=len(seg_map),
        force=force,
    )

    t_start = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)

    # vorherige Batch-Files loeschen (force oder neuer Hash)
    for old_file in output_dir.glob("batch_*.md"):
        old_file.unlink()

    batch_paths: list[Path] = []
    batch_counter = 1
    skipped_unsorted = 0

    for cluster in clusters:
        if skip_unsorted and cluster.cluster_id == _UNSORTED_CLUSTER_ID:
            skipped_unsorted = len(cluster.segment_ids)
            log.info(
                "phase_7_unsorted_skipped",
                phase="phase_7_batches",
                segment_count=skipped_unsorted,
            )
            continue

        cluster_segments = [seg_map[sid] for sid in cluster.segment_ids if sid in seg_map]
        if not cluster_segments:
            continue

        cluster_seg_ids = {seg.segment_id for seg in cluster_segments}
        cluster_edges = _edges_for_cluster(cluster_seg_ids, all_edges)

        full_text = " ".join(seg.text for seg in cluster_segments)
        needs_split = split_oversized_clusters and _estimate_tokens(full_text) > max_input_tokens

        sub_batches = (
            _split_into_sub_batches(cluster_segments, max_input_tokens)
            if needs_split
            else [cluster_segments]
        )
        total_parts = len(sub_batches)
        slug = _slugify(cluster.label_guess)

        for part_idx, sub_segs in enumerate(sub_batches, start=1):
            batch_id = f"batch_{batch_counter:03d}_{slug}"
            sub_label = f"{part_idx}/{total_parts}"
            sub_seg_ids = {seg.segment_id for seg in sub_segs}
            sub_edges = [
                e
                for e in cluster_edges
                if e.segment_id_a in sub_seg_ids and e.segment_id_b in sub_seg_ids
            ]
            token_est = _estimate_tokens(" ".join(seg.text for seg in sub_segs))

            content = _build_batch_markdown(
                batch_id=batch_id,
                cluster_id=cluster.cluster_id,
                label_guess=cluster.label_guess,
                segments=sub_segs,
                edges=sub_edges,
                sub_label=sub_label,
                pipeline_version=pipeline_version,
            )

            file_path = output_dir / f"{batch_id}.md"
            file_path.write_text(content, encoding="utf-8")
            batch_paths.append(file_path)

            log.info(
                "phase_7_batch_written",
                phase="phase_7_batches",
                batch_id=batch_id,
                cluster_id=cluster.cluster_id,
                segment_count=len(sub_segs),
                token_estimate=token_est,
                sub_batch=sub_label,
            )

            batch_counter += 1

    duration = time.monotonic() - t_start
    _write_meta(
        meta_path,
        input_hash,
        batch_paths,
        duration,
        pipeline_version,
        {
            "max_input_tokens": max_input_tokens,
            "split_oversized_clusters": split_oversized_clusters,
            "skip_unsorted": skip_unsorted,
        },
    )

    log.info(
        "phase_7_done",
        phase="phase_7_batches",
        batch_count=len(batch_paths),
        skipped_unsorted_segments=skipped_unsorted,
        duration_seconds=round(duration, 2),
    )

    return batch_paths
