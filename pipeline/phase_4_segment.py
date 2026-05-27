"""Phase 4 — Segmentierung: Dokumente in Segmente aufteilen.

Input:  data/02_pipeline_output/cleaned_documents.jsonl  (Phase 2 Output)
        data/02_pipeline_output/files_manifest.jsonl     (Phase 1 Output, source_path)
Output: data/02_pipeline_output/segments.jsonl
        data/02_pipeline_output/segments.jsonl.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 4):
  - Jedes Segment zwischen min_words und max_words (best effort)
  - Code-Blöcke nicht zerrissen (Anzahl Fence-Marker pro Segment ist gerade)
  - Heading-Pfad für jedes Segment vorhanden (kann leer sein bei Intro-Abschnitten)
  - Idempotenz: zweimaliger Lauf -> identische Outputs
"""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pipeline.schemas import CleanedDocument, DocumentRecord, SegmentRecord

log = structlog.get_logger()

_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")
_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+)")


def _classify_lines(lines: list[str]) -> list[str]:
    """Klassifiziert jede Zeile: 'code', 'table', 'text', 'blank'."""
    result: list[str] = []
    in_code = False
    fence_char = ""

    for line in lines:
        stripped = line.strip()
        if in_code:
            result.append("code")
            m = _FENCE_OPEN_RE.match(stripped)
            if m and m.group(0)[0] == fence_char and stripped == m.group(0):
                in_code = False
        elif _FENCE_OPEN_RE.match(stripped):
            m = _FENCE_OPEN_RE.match(stripped)
            assert m is not None
            fence_char = m.group(0)[0]
            in_code = True
            result.append("code")
        elif stripped.startswith("|") and len(stripped) > 2:
            result.append("table")
        elif not stripped:
            result.append("blank")
        else:
            result.append("text")

    return result


def _group_into_blocks(lines: list[str], types: list[str]) -> list[list[str]]:
    """Gruppiert Zeilen anhand ihrer Typen in atomare Blöcke."""
    blocks: list[list[str]] = []
    current: list[str] = []
    prev_type = "blank"

    for line, ltype in zip(lines, types, strict=True):
        if ltype == "blank":
            if current:
                blocks.append(current)
                current = []
            prev_type = "blank"
        elif ltype != prev_type and ltype in ("code", "table") and current:
            blocks.append(current)
            current = [line]
            prev_type = ltype
        elif prev_type in ("code", "table") and ltype == "text" and current:
            blocks.append(current)
            current = [line]
            prev_type = "text"
        else:
            current.append(line)
            prev_type = ltype

    if current:
        blocks.append(current)

    return blocks


def _build_blocks(lines: list[str]) -> list[list[str]]:
    """Zerlegt Zeilen in atomare Blöcke (Paragraphen, Code-Blöcke, Tabellen)."""
    return _group_into_blocks(lines, _classify_lines(lines))


def _parse_raw_sections(body: str) -> list[tuple[list[str], list[str]]]:
    """Teilt body in (heading_path, lines) Sektionen an Überschriften.

    Überschriften innerhalb von Code-Blöcken werden ignoriert.
    Der Heading-Pfad ist leer für Inhalt vor der ersten Überschrift.
    Die Heading-Zeile ist Teil der jeweiligen Sektion.
    """
    lines = body.split("\n")
    sections: list[tuple[list[str], list[str]]] = []
    current_path: list[str] = []
    current_lines: list[str] = []
    in_code = False
    fence_char = ""

    for line in lines:
        stripped = line.strip()
        if in_code:
            current_lines.append(line)
            m = _FENCE_OPEN_RE.match(stripped)
            if m and m.group(0)[0] == fence_char and stripped == m.group(0):
                in_code = False
            continue

        m = _FENCE_OPEN_RE.match(stripped)
        if m:
            fence_char = m.group(0)[0]
            in_code = True
            current_lines.append(line)
            continue

        m_head = _HEADING_LINE_RE.match(line)
        if m_head:
            if current_lines:
                sections.append((list(current_path), current_lines))
            level = len(m_head.group(1))
            current_path = [*current_path[: level - 1], m_head.group(2).strip()]
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((list(current_path), current_lines))

    return sections


def _split_section_lines(lines: list[str], max_words: int) -> list[list[str]]:
    """Teilt eine Sektion bei Absatz-/Block-Grenzen wenn sie max_words überschreitet.

    Code-Blöcke und Tabellen werden nie zerrissen.
    """
    if len(" ".join(lines).split()) <= max_words:
        return [lines]

    blocks = _build_blocks(lines)
    chunks: list[list[str]] = []
    current: list[str] = []
    current_words = 0

    for block in blocks:
        bw = len(" ".join(block).split())
        if current_words + bw > max_words and current:
            chunks.append(current)
            current = list(block)
            current_words = bw
        else:
            if current:
                current.append("")
            current.extend(block)
            current_words += bw

    if current:
        chunks.append(current)

    return chunks if chunks else [lines]


def _has_code_block(text: str) -> bool:
    """True wenn der Text einen Fenced-Code-Block enthält."""
    return "```" in text or "~~~" in text


def _has_table(text: str) -> bool:
    """True wenn der Text eine Markdown-Tabellen-Zeile enthält."""
    return any(line.strip().startswith("|") and len(line.strip()) > 2 for line in text.splitlines())


def _segment_document(
    doc_id: str,
    body: str,
    source_path: str,
    min_words: int,
    max_words: int,
) -> list[SegmentRecord]:
    """Segmentiert ein Dokument in eine Liste von SegmentRecords."""
    raw_sections = _parse_raw_sections(body)

    # Split long sections at block boundaries
    split_sections: list[tuple[list[str], list[str]]] = []
    for path, lines in raw_sections:
        for chunk in _split_section_lines(lines, max_words):
            split_sections.append((path, chunk))

    # Build SegmentRecords (skip empty text)
    records: list[SegmentRecord] = []
    seg_index = 0
    for path, lines in split_sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        records.append(
            SegmentRecord(
                segment_id=f"{doc_id}-S{seg_index:04d}",
                doc_id=doc_id,
                source_path=source_path,
                heading_path=path,
                segment_index=seg_index,
                text=text,
                word_count=len(text.split()),
                char_count=len(text),
                contains_code=_has_code_block(text),
                contains_table=_has_table(text),
            )
        )
        seg_index += 1

    return records


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(manifest_path: Path) -> dict[str, str]:
    """Lädt doc_id → source_path Mapping aus der files_manifest.jsonl."""
    lookup: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = DocumentRecord.model_validate_json(line)
            lookup[rec.doc_id] = rec.path
    return lookup


def _load_cleaned(cleaned_path: Path) -> list[CleanedDocument]:
    """Lädt CleanedDocuments aus einer JSONL-Datei."""
    records = []
    for line in cleaned_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(CleanedDocument.model_validate_json(line))
    return records


def _load_records(output_path: Path) -> list[SegmentRecord]:
    """Lädt bestehende SegmentRecords aus einer JSONL-Datei."""
    records = []
    for line in output_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(SegmentRecord.model_validate_json(line))
    return records


def _write_jsonl(output_path: Path, records: list[SegmentRecord]) -> None:
    """Schreibt SegmentRecords in eine JSONL-Datei."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(r.model_dump_json() + "\n")


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
        "phase": "phase_4_segment",
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


def run_phase_4(
    cleaned_path: Path,
    manifest_path: Path,
    output_path: Path,
    *,
    force: bool = False,
    min_words: int = 50,
    max_words: int = 1500,
    pipeline_version: str = "0.1.0",
) -> list[SegmentRecord]:
    """Phase 4 ausführen: Dokumente in Segmente aufteilen.

    Args:
        cleaned_path: Pfad zur cleaned_documents.jsonl (Phase 2 Output).
        manifest_path: Pfad zur files_manifest.jsonl (Phase 1 Output, source_path).
        output_path: Ziel-Pfad für segments.jsonl.
        force: Wenn True, Cache ignorieren und neu berechnen.
        min_words: Mindest-Wortanzahl pro Segment (best effort).
        max_words: Maximale Wortanzahl pro Segment.
        pipeline_version: Version für Meta-File.

    Returns:
        Liste aller SegmentRecord-Einträge.

    Raises:
        FileNotFoundError: Wenn cleaned_path oder manifest_path nicht existiert.
    """
    for p in (cleaned_path, manifest_path):
        if not p.exists():
            raise FileNotFoundError(f"Input nicht gefunden: {p}")

    input_hash = f"sha256:{_sha256_file(cleaned_path)}"
    meta_path = Path(str(output_path) + ".meta.json")

    if not force and output_path.exists() and _meta_matches(meta_path, input_hash):
        log.info(
            "phase_4_skipped",
            phase="phase_4_segment",
            reason="same_input_hash",
            output=str(output_path),
        )
        return _load_records(output_path)

    path_lookup = _load_manifest(manifest_path)
    cleaned_records = _load_cleaned(cleaned_path)

    log.info(
        "phase_4_start",
        phase="phase_4_segment",
        doc_count=len(cleaned_records),
        force=force,
    )

    t_start = time.monotonic()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_segments: list[SegmentRecord] = []

    for rec in cleaned_records:
        source_path = path_lookup.get(rec.doc_id, "")
        segments = _segment_document(
            doc_id=rec.doc_id,
            body=rec.body,
            source_path=source_path,
            min_words=min_words,
            max_words=max_words,
        )
        all_segments.extend(segments)

    _write_jsonl(output_path, all_segments)
    output_hash = f"sha256:{_sha256_file(output_path)}"
    duration = time.monotonic() - t_start

    _write_meta(
        meta_path,
        input_hash,
        output_hash,
        duration,
        pipeline_version,
        {"min_words": min_words, "max_words": max_words},
    )

    log.info(
        "phase_4_done",
        phase="phase_4_segment",
        segment_count=len(all_segments),
        doc_count=len(cleaned_records),
        output=str(output_path),
        duration_seconds=round(duration, 2),
    )

    return all_segments
