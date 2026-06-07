"""Phase 4 — Segmentierung: Dokumente in Segmente aufteilen.

Input:  work/cleaned_documents.jsonl  (Phase 2 Output)
        work/files_manifest.jsonl     (Phase 1 Output, source_path)
Output: work/segments.jsonl
        work/segments.jsonl.meta.json

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


def _is_heading_only(text: str) -> bool:
    """True wenn das Segment ausschließlich aus Heading-Zeilen besteht (kein Body-Text)."""
    non_blank = [line for line in text.splitlines() if line.strip()]
    return bool(non_blank) and all(_HEADING_LINE_RE.match(line.strip()) for line in non_blank)


def _same_h1_section(path_a: list[str], path_b: list[str]) -> bool:
    """True wenn beide Segmente im selben H1-Abschnitt liegen.

    Zwei leere Pfade (pre-heading Inhalt) gelten als gleicher Abschnitt.
    Ein leerer und ein nichtleerer Pfad gelten als unterschiedliche Abschnitte.
    """
    if not path_a and not path_b:
        return True
    if not path_a or not path_b:
        return False
    return path_a[0] == path_b[0]


def _combine_segments(
    a: SegmentRecord,
    b: SegmentRecord,
    *,
    heading_path_override: list[str] | None = None,
) -> SegmentRecord:
    """Kombiniert zwei Segmente zu einem (temporäre ID, wird in _merge_undersized_segments neu vergeben).

    Heading-Pfad: override hat Vorrang; sonst Segment mit mehr Wörtern; bei Gleichstand: a (erstes).
    contains_code / contains_table: OR-Kombination.
    """
    text = (a.text + "\n\n" + b.text).strip()
    if heading_path_override is not None:
        heading_path = heading_path_override
    elif a.word_count > b.word_count:
        heading_path = a.heading_path
    elif b.word_count > a.word_count:
        heading_path = b.heading_path
    else:
        heading_path = a.heading_path
    return SegmentRecord(
        segment_id=a.segment_id,  # temporär, wird re-indiziert
        doc_id=a.doc_id,
        source_path=a.source_path,
        heading_path=heading_path,
        segment_index=a.segment_index,  # temporär
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        contains_code=a.contains_code or b.contains_code,
        contains_table=a.contains_table or b.contains_table,
    )


def _merge_step_heading_only(
    seg: SegmentRecord,
    prov: list[str],
    i: int,
    segments: list[SegmentRecord],
    provenance: list[list[str]],
    new_segs: list[SegmentRecord],
    new_prov: list[list[str]],
) -> tuple[int, bool]:
    """Heading-only: NEXT (kein H1-Check); fallback PREVIOUS. Returns (new_i, changed)."""
    if i + 1 < len(segments):
        new_segs.append(
            _combine_segments(seg, segments[i + 1], heading_path_override=seg.heading_path)
        )
        new_prov.append(prov + provenance[i + 1])
        return i + 2, True
    if new_segs:
        prev = new_segs.pop()
        prev_prov = new_prov.pop()
        new_segs.append(_combine_segments(prev, seg))
        new_prov.append(prev_prov + prov)
        return i + 1, True
    # Einziges Segment — kein Merge möglich
    new_segs.append(seg)
    new_prov.append(prov)
    return i + 1, False


def _merge_step_undersized(
    seg: SegmentRecord,
    prov: list[str],
    i: int,
    segments: list[SegmentRecord],
    provenance: list[list[str]],
    new_segs: list[SegmentRecord],
    new_prov: list[list[str]],
) -> tuple[int, bool]:
    """Undersized: NEXT in gleicher H1; PREVIOUS in gleicher H1; letztes → PREVIOUS. Returns (new_i, changed)."""
    is_last = i == len(segments) - 1
    if is_last and new_segs:
        # Letztes Segment: mit PREVIOUS, H1-Grenze ignoriert
        prev = new_segs.pop()
        prev_prov = new_prov.pop()
        new_segs.append(_combine_segments(prev, seg))
        new_prov.append(prev_prov + prov)
        return i + 1, True
    next_in_h1 = i + 1 < len(segments) and _same_h1_section(
        seg.heading_path, segments[i + 1].heading_path
    )
    if next_in_h1:
        new_segs.append(_combine_segments(seg, segments[i + 1]))
        new_prov.append(prov + provenance[i + 1])
        return i + 2, True
    prev_in_h1 = bool(new_segs) and _same_h1_section(new_segs[-1].heading_path, seg.heading_path)
    if prev_in_h1:
        prev = new_segs.pop()
        prev_prov = new_prov.pop()
        new_segs.append(_combine_segments(prev, seg))
        new_prov.append(prev_prov + prov)
        return i + 1, True
    # Keine Merge-Option (H1-Grenzen auf beiden Seiten)
    new_segs.append(seg)
    new_prov.append(prov)
    return i + 1, False


def _merge_undersized_segments(
    segments: list[SegmentRecord],
    min_words: int,
    max_words: int,
    doc_id: str,
) -> tuple[list[SegmentRecord], dict[str, list[str]]]:
    """Mergt heading-only und undersized Segmente iterativ bis kein weiterer Merge möglich ist.

    Regeln:
    - Heading-only → immer mit NEXT mergen, kein H1-Check; kein NEXT → mit PREVIOUS
    - Undersized → mit NEXT in gleichem H1; kein NEXT → mit PREVIOUS in gleichem H1
    - Letztes Segment (undersized) → mit PREVIOUS, H1-Grenze ignoriert
    - Einzelnes Segment → unverändert
    - Nach Merge > max_words: akzeptieren + loggen (kein Re-Split)
    - Re-Indizierung: S0000, S0001 … ohne Lücken

    Returns:
        (final_segments, provenance) wobei provenance neue segment_id →
        Liste originaler segment_ids aus denen dieses Segment gemergt wurde mappt.
    """
    if not segments:
        return [], {}

    # provenance[i]: originale segment_ids für segments[i]
    provenance: list[list[str]] = [[seg.segment_id] for seg in segments]

    changed = True
    while changed:
        changed = False
        new_segs: list[SegmentRecord] = []
        new_prov: list[list[str]] = []
        i = 0
        while i < len(segments):
            seg = segments[i]
            prov = provenance[i]
            if _is_heading_only(seg.text):
                i, step_changed = _merge_step_heading_only(
                    seg, prov, i, segments, provenance, new_segs, new_prov
                )
            elif seg.word_count < min_words:
                i, step_changed = _merge_step_undersized(
                    seg, prov, i, segments, provenance, new_segs, new_prov
                )
            else:
                new_segs.append(seg)
                new_prov.append(prov)
                i += 1
                step_changed = False
            changed = changed or step_changed
        segments = new_segs
        provenance = new_prov

    # Re-Indizierung: fortlaufend S0000, S0001 … ohne Lücken
    final: list[SegmentRecord] = []
    final_provenance: dict[str, list[str]] = {}
    for new_idx, (seg, prov) in enumerate(zip(segments, provenance, strict=True)):
        new_id = f"{doc_id}-S{new_idx:04d}"
        final_provenance[new_id] = prov
        final.append(
            SegmentRecord(
                segment_id=new_id,
                doc_id=seg.doc_id,
                source_path=seg.source_path,
                heading_path=seg.heading_path,
                segment_index=new_idx,
                text=seg.text,
                word_count=seg.word_count,
                char_count=seg.char_count,
                contains_code=seg.contains_code,
                contains_table=seg.contains_table,
            )
        )
        if seg.word_count > max_words:
            log.info(
                "phase_4_oversized_after_merge",
                segment_id=new_id,
                word_count=seg.word_count,
                max_words=max_words,
            )

    # Provenance als Debug-Log (Mapping alte→neue IDs)
    merged_map = {k: v for k, v in final_provenance.items() if len(v) > 1}
    if merged_map:
        log.debug(
            "phase_4_merge_provenance",
            doc_id=doc_id,
            merged_segments=len(merged_map),
            mapping=merged_map,
        )

    return final, final_provenance


def _segment_document_book(
    doc_id: str,
    body: str,
    source_path: str,
    book_max_words: int,
) -> list[SegmentRecord]:
    """Book-Pfad: segmentiert nur an H1+H2-Grenzen, kein min_words-Merge.

    Sektionen mit gleichem path[:2] werden zusammengeführt, sodass H3+ Headings
    nicht als eigenständige Splits gelten. Ergebnis: ein Segment pro H2-Abschnitt
    (oder H1 wenn kein H2 vorhanden).
    """
    raw_sections = _parse_raw_sections(body)

    # Aggregiere Sektionen nach H1+H2-Pfadpräfix (path[:2])
    book_secs: list[tuple[list[str], list[str]]] = []
    for path, lines in raw_sections:
        book_path = path[:2]
        if book_secs and book_secs[-1][0] == book_path:
            prev_path, prev_lines = book_secs.pop()
            book_secs.append((prev_path, [*prev_lines, "", *lines]))
        else:
            book_secs.append((book_path, lines))

    # Split bei Überschreitung book_max_words
    split_secs: list[tuple[list[str], list[str]]] = []
    for path, lines in book_secs:
        for chunk in _split_section_lines(lines, book_max_words):
            split_secs.append((path, chunk))

    records: list[SegmentRecord] = []
    seg_idx = 0
    for path, lines in split_secs:
        text = "\n".join(lines).strip()
        if not text:
            continue
        records.append(
            SegmentRecord(
                segment_id=f"{doc_id}-S{seg_idx:04d}",
                doc_id=doc_id,
                source_path=source_path,
                heading_path=path,
                segment_index=seg_idx,
                text=text,
                word_count=len(text.split()),
                char_count=len(text),
                contains_code=_has_code_block(text),
                contains_table=_has_table(text),
            )
        )
        seg_idx += 1

    log.info("phase_4_book_segmented", doc_id=doc_id, segment_count=seg_idx)
    return records


def _segment_document(
    doc_id: str,
    body: str,
    source_path: str,
    min_words: int,
    max_words: int,
    *,
    is_book: bool = False,
    book_max_words: int = 5000,
) -> list[SegmentRecord]:
    """Segmentiert ein Dokument in eine Liste von SegmentRecords.

    Bei is_book=True: Book-Pfad (H1+H2-Split, kein min_words-Merge).
    Sonst: Standard-Pfad mit Merge-Logik.
    """
    if is_book:
        return _segment_document_book(doc_id, body, source_path, book_max_words)

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

    merged, _ = _merge_undersized_segments(records, min_words, max_words, doc_id)
    return merged


def _segment_whole_doc(doc_id: str, body: str, source_path: str) -> list[SegmentRecord]:
    """Token-Cap-Fallback: gibt das Dokument als EIN Segment zurück (kein Heading-Split).

    Genutzt im go-forward-Flow (`pipeline/run_flow.py`), wenn ein Doc unter dem
    Token-Cap liegt — dann wird es nicht segmentiert, sondern 1:1 an Phase 8 gereicht.
    """
    text = body.strip()
    if not text:
        return []
    return [
        SegmentRecord(
            segment_id=f"{doc_id}-S0000",
            doc_id=doc_id,
            source_path=source_path,
            heading_path=[],
            segment_index=0,
            text=text,
            word_count=len(text.split()),
            char_count=len(text),
            contains_code=_has_code_block(text),
            contains_table=_has_table(text),
        )
    ]


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


def _load_doc_types(structured_path: Path) -> dict[str, str]:
    """Lädt doc_id → doc_type_guess.label Mapping aus documents_structured.jsonl."""
    lookup: dict[str, str] = {}
    for line in structured_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            data: dict[str, Any] = json.loads(line)
            doc_id = data.get("doc_id", "")
            label = data.get("doc_type_guess", {}).get("label", "unklar")
            if doc_id:
                lookup[doc_id] = label
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
    book_max_words: int = 5000,
    structured_path: Path | None = None,
    token_cap_words: int | None = None,
    pipeline_version: str = "0.1.0",
) -> list[SegmentRecord]:
    """Phase 4 ausführen: Dokumente in Segmente aufteilen.

    Args:
        cleaned_path: Pfad zur cleaned_documents.jsonl (Phase 2 Output).
        manifest_path: Pfad zur files_manifest.jsonl (Phase 1 Output, source_path).
        output_path: Ziel-Pfad für segments.jsonl.
        force: Wenn True, Cache ignorieren und neu berechnen.
        min_words: Mindest-Wortanzahl pro Segment (best effort).
        max_words: Maximale Wortanzahl pro Segment (Standard-Pfad).
        book_max_words: Maximale Wortanzahl pro Segment im Book-Pfad.
        structured_path: Pfad zu documents_structured.jsonl (Phase 3 Output).
                         Wenn angegeben, wird doc_type_guess.label für Book-Erkennung genutzt.
        token_cap_words: go-forward-Modus (Option B). Wenn gesetzt, wird ein Doc NUR
                         segmentiert, wenn seine Wortzahl diesen Cap überschreitet —
                         sonst als EIN Segment 1:1 durchgereicht. None = klassischer
                         Heading-Split (Korpus-Erstlauf-Verhalten, unverändert).
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
    doc_types = (
        _load_doc_types(structured_path) if structured_path and structured_path.exists() else {}
    )

    log.info(
        "phase_4_start",
        phase="phase_4_segment",
        doc_count=len(cleaned_records),
        force=force,
        book_detection=bool(doc_types),
    )

    t_start = time.monotonic()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_segments: list[SegmentRecord] = []

    for rec in cleaned_records:
        source_path = path_lookup.get(rec.doc_id, "")
        is_book = doc_types.get(rec.doc_id) == "book"
        # go-forward Token-Cap-Modus: kleine Docs als 1 Segment durchreichen,
        # nur bei Cap-Überschreitung den klassischen Heading-Split nutzen.
        if token_cap_words is not None and not is_book and len(rec.body.split()) <= token_cap_words:
            segments = _segment_whole_doc(rec.doc_id, rec.body, source_path)
        else:
            segments = _segment_document(
                doc_id=rec.doc_id,
                body=rec.body,
                source_path=source_path,
                min_words=min_words,
                max_words=max_words,
                is_book=is_book,
                book_max_words=book_max_words,
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
        {
            "min_words": min_words,
            "max_words": max_words,
            "book_max_words": book_max_words,
            "token_cap_words": token_cap_words,
        },
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
