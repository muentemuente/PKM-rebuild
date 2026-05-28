"""Phase 3 — Strukturextraktion: Headings, Code-Blöcke, Tabellen, Links, Typ-Guess.

Input:  data/02_pipeline_output/cleaned_documents.jsonl  (Phase 2 Output)
Output: data/02_pipeline_output/documents_structured.jsonl
        data/02_pipeline_output/documents_structured.jsonl.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 3):
  - H1 für jedes Dokument (Fallback: Dateiname aus doc_id)
  - Confidence-Wert + mind. 1 Signal pro doc_type_guess
  - Alle Code-Blöcke mit Sprach-Tag (unknown wenn nicht erkennbar)
  - Idempotenz: zweimaliger Lauf → identische Outputs
"""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pipeline.schemas import CleanedDocument, DocTypeGuess, StructuredDocumentRecord

log = structlog.get_logger()

_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_TABLE_SEP_RE = re.compile(r"^\|[-:\s|]+\|$")
_NUMBERED_STEP_RE = re.compile(r"\bschritt\s*\d+|\bstep\s*\d+", re.IGNORECASE)


def _partition_body(body: str) -> tuple[str, list[dict]]:
    """Teilt body in non-code-Text und extrahierte Code-Blöcke.

    Im non-code-Text werden Code-Block-Zeilen (inkl. Fence-Marker) durch
    Leerzeilen ersetzt, damit alle anderen Extraktionen Code ignorieren.

    Returns:
        (non_code_text, code_blocks)
        code_blocks: [{"lang": str, "content": str}]
    """
    lines = body.splitlines()
    non_code: list[str] = []
    code_blocks: list[dict] = []

    in_code = False
    fence_char = ""
    lang = ""
    content_lines: list[str] = []

    for line in lines:
        if in_code:
            stripped = line.strip()
            m = _FENCE_OPEN_RE.match(stripped)
            if m and m.group(0)[0] == fence_char and stripped == m.group(0):
                code_blocks.append({"lang": lang or "unknown", "content": "\n".join(content_lines)})
                in_code = False
                fence_char = ""
                lang = ""
                content_lines = []
            else:
                content_lines.append(line)
            non_code.append("")
        else:
            stripped = line.strip()
            m = _FENCE_OPEN_RE.match(stripped)
            if m:
                fence_char = m.group(0)[0]
                in_code = True
                rest = stripped[len(m.group(0)) :].strip()
                lang = rest.split()[0] if rest.strip() else ""
                content_lines = []
                non_code.append("")
            else:
                non_code.append(line)

    if in_code and content_lines:
        code_blocks.append({"lang": lang or "unknown", "content": "\n".join(content_lines)})

    return "\n".join(non_code), code_blocks


def _extract_headings(non_code_text: str) -> list[dict]:
    """Extrahiert H1-H6-Überschriften als [{"level": int, "text": str}]."""
    return [
        {"level": len(m.group(1)), "text": m.group(2).strip()}
        for m in _HEADING_RE.finditer(non_code_text)
    ]


def _count_tables(non_code_text: str) -> int:
    """Zählt Markdown-Tabellen (Gruppen von Tabellenzeilen mit Separator-Zeile)."""
    in_table = False
    has_sep = False
    count = 0

    for line in non_code_text.splitlines():
        stripped = line.strip()
        is_row = stripped.startswith("|") and len(stripped) > 2
        is_sep = bool(_TABLE_SEP_RE.match(stripped))

        if is_row:
            if not in_table:
                in_table = True
                has_sep = False
            if is_sep:
                has_sep = True
        else:
            if in_table and has_sep:
                count += 1
            in_table = False
            has_sep = False

    if in_table and has_sep:
        count += 1

    return count


def _extract_links(non_code_text: str) -> list[str]:
    """Extrahiert alle Links: reguläre Markdown-Links + Wikilinks (keine Bilder)."""
    links: list[str] = []
    for m in _LINK_RE.finditer(non_code_text):
        url = m.group(2).strip()
        if url:
            links.append(url)
    for m in _WIKILINK_RE.finditer(non_code_text):
        target = m.group(1).strip()
        if target:
            links.append(target)
    return links


def _extract_images(non_code_text: str) -> list[str]:
    """Extrahiert alle Bild-URLs aus ![alt](url)-Syntax."""
    return [m.group(2).strip() for m in _IMAGE_RE.finditer(non_code_text) if m.group(2).strip()]


def _get_title(headings: list[dict], frontmatter: dict, doc_id: str) -> str:
    """Liefert den Dokumenttitel: H1 → Frontmatter-title → Slug aus doc_id."""
    for h in headings:
        if h["level"] == 1:
            return h["text"]
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    slug = doc_id[2:] if doc_id.startswith("D_") else doc_id
    return slug.replace("-", " ").replace("_", " ").title()


def _build_type_rules(
    title_l: str,
    heading_flat: str,
    body_lower: str,
    n_code: int,
    named_langs: list[str],
    tables_count: int,
    word_count: int,
    n_headings: int,
) -> list[tuple[str, float, str]]:
    """Liefert gefeuerte Rules als (label, weight, signal)-Tupel.

    Jede Zeile ist eine unabhaengige Heuristik. Die Bedingungen werden
    hier als boolesche Ausdrücke ausgewertet — kein if-Baum, dadurch
    bleibt die aufrufende Funktion unter dem Complexity-Limit.
    """

    def _t(*kws: str) -> bool:
        return any(kw in title_l for kw in kws)

    def _h(*kws: str) -> bool:
        return any(kw in heading_flat for kw in kws)

    def _b(*kws: str) -> bool:
        return any(kw in body_lower for kw in kws)

    fired: list[tuple[str, float, str]] = []
    rules: list[tuple[str, float, str, bool]] = [
        # cheat_sheet
        (
            "cheat_sheet",
            0.5,
            f"compact_table_{word_count}w",
            tables_count >= 1 and word_count < 300,
        ),
        ("cheat_sheet", 0.3, f"tables={tables_count}", tables_count >= 2),
        ("cheat_sheet", 0.3, f"code_blocks={n_code}", n_code >= 3),
        ("cheat_sheet", 0.4, "title_kw:cheat/befehle", _t("cheat", "befehle", "commands", "quick")),
        # reference
        ("reference", 0.2, f"named_langs:{named_langs[:2]}", bool(named_langs)),
        ("reference", 0.5, "title_kw:api/referenz", _t("api", "referenz", "reference", "spec")),
        ("reference", 0.2, "table_and_code", tables_count >= 1 and n_code >= 1),
        # tutorial
        (
            "tutorial",
            0.5,
            "title_kw:tutorial/anleitung",
            _t("tutorial", "anleitung", "einführung", "guide", "intro"),
        ),
        (
            "tutorial",
            0.3,
            "heading_kw:schritt/step",
            _h("schritt", "step", "einführung", "einleitung"),
        ),
        ("tutorial", 0.1, "has_code_and_prose", n_code >= 1 and word_count > 150),
        # how-to
        ("how-to", 0.5, "numbered_steps_in_headings", bool(_NUMBERED_STEP_RE.search(heading_flat))),
        ("how-to", 0.4, "title_kw:howto", _t("how to", "howto", "wie man", "wie du")),
        # projektidee
        ("projektidee", 0.6, "title:projektnotiz", "projektnotiz" in title_l),
        ("projektidee", 0.3, "title_kw:projekt", "projektnotiz" not in title_l and _t("projekt")),
        (
            "projektidee",
            0.3,
            "heading_kw:idee/technologie",
            _h("idee", "technologie", "offene fragen"),
        ),
        ("projektidee", 0.2, "status_section_compact", _h("status") and word_count < 600),
        # projektplanung
        (
            "projektplanung",
            0.5,
            "heading_kw:phase/meilenstein",
            _h("phase", "meilenstein", "milestone", "planung"),
        ),
        ("projektplanung", 0.4, "title_kw:planung", _t("planung", "plan", "roadmap")),
        # gedanke
        (
            "gedanke",
            0.3,
            f"prose_only_short_{word_count}w",
            n_code == 0 and tables_count == 0 and word_count < 350 and "projekt" not in title_l,
        ),
        (
            "gedanke",
            0.4,
            "title_kw:gedanke/notiz",
            _t("gedanke", "notiz", "note") and "projekt" not in title_l,
        ),
        ("gedanke", 0.3, "personal_voice", _b("ich denke", "meine meinung", "ich glaube")),
        # explanation
        (
            "explanation",
            0.4,
            f"long_prose_{word_count}w",
            word_count > 500 and n_code <= 2 and tables_count == 0,
        ),
        (
            "explanation",
            0.4,
            "title_kw:grundlagen",
            _t("erklärung", "explanation", "was ist", "einleitung", "grundlagen"),
        ),
        # wiki
        (
            "wiki",
            0.5,
            "title_kw:wiki/glossar",
            _t("wiki", "glossar", "begriffe", "überblick", "overview"),
        ),
        ("wiki", 0.3, f"many_headings={n_headings}", n_headings > 5 and word_count > 350),
        # manual
        (
            "manual",
            0.4,
            "heading_kw:installation",
            _h("installation", "konfiguration", "configuration", "requirements", "voraussetzungen"),
        ),
        ("manual", 0.4, "title_kw:manual", _t("manual", "handbuch", "dokumentation")),
    ]
    for label, weight, signal, condition in rules:
        if condition:
            fired.append((label, weight, signal))
    return fired


def _detect_book(headings: list[dict], word_count: int, threshold: int) -> bool:
    """True für Buch-artige Files: sehr lang + viele H1/H2-Überschriften."""
    h1_h2_count = sum(1 for h in headings if h["level"] in (1, 2))
    return word_count > threshold and h1_h2_count >= 5


def _guess_doc_type(
    title: str,
    headings: list[dict],
    code_blocks: list[dict],
    tables_count: int,
    word_count: int,
    body_lower: str,
    book_word_threshold: int = 8000,
) -> DocTypeGuess:
    """Heuristische Dokumenttyp-Vermutung mit Confidence und Signalen.

    Book-Erkennung hat höchste Priorität: wenn erfüllt, wird sofort zurückgegeben.
    """
    if _detect_book(headings, word_count, book_word_threshold):
        h1_h2_count = sum(1 for h in headings if h["level"] in (1, 2))
        return DocTypeGuess(
            label="book",
            confidence=0.9,
            signals=[
                f"word_count={word_count}>{book_word_threshold}",
                f"h1_h2_count={h1_h2_count}>=5",
            ],
        )

    title_l = title.lower()
    heading_flat = " ".join(h["text"].lower() for h in headings)
    n_code = len(code_blocks)
    named_langs = [b["lang"] for b in code_blocks if b["lang"] != "unknown"]

    fired = _build_type_rules(
        title_l,
        heading_flat,
        body_lower,
        n_code,
        named_langs,
        tables_count,
        word_count,
        len(headings),
    )

    scores: dict[str, float] = {}
    signals_map: dict[str, list[str]] = {}
    for label, weight, signal in fired:
        scores[label] = scores.get(label, 0.0) + weight
        signals_map.setdefault(label, []).append(signal)

    best_label = "unklar"
    best_score = 0.2
    best_signals: list[str] = ["no_dominant_signal"]
    for label, score in scores.items():
        if score > best_score and signals_map.get(label):
            best_label = label
            best_score = score
            best_signals = signals_map[label]

    confidence = round(min(0.95, max(0.3, best_score)), 2)
    return DocTypeGuess(label=best_label, confidence=confidence, signals=best_signals[:3])


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_cleaned(cleaned_path: Path) -> list[CleanedDocument]:
    """Lädt CleanedDocuments aus einer JSONL-Datei."""
    records = []
    for line in cleaned_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(CleanedDocument.model_validate_json(line))
    return records


def _load_records(output_path: Path) -> list[StructuredDocumentRecord]:
    """Lädt bestehende StructuredDocumentRecords aus einer JSONL-Datei."""
    records = []
    for line in output_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(StructuredDocumentRecord.model_validate_json(line))
    return records


def _write_jsonl(output_path: Path, records: list[StructuredDocumentRecord]) -> None:
    """Schreibt StructuredDocumentRecords in eine JSONL-Datei."""
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
) -> None:
    """Schreibt das Meta-File für Idempotenz-Tracking."""
    meta: dict[str, Any] = {
        "phase": "phase_3_structure",
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": {},
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


def run_phase_3(
    cleaned_path: Path,
    output_path: Path,
    *,
    force: bool = False,
    pipeline_version: str = "0.1.0",
    book_word_threshold: int = 8000,
) -> list[StructuredDocumentRecord]:
    """Phase 3 ausführen: Dokumente strukturell analysieren.

    Args:
        cleaned_path: Pfad zur cleaned_documents.jsonl (Phase 2 Output).
        output_path: Ziel-Pfad für documents_structured.jsonl.
        force: Wenn True, Cache ignorieren und neu berechnen.
        pipeline_version: Version für Meta-File.

    Returns:
        Liste aller StructuredDocumentRecord-Einträge.

    Raises:
        FileNotFoundError: Wenn cleaned_path nicht existiert.
    """
    if not cleaned_path.exists():
        raise FileNotFoundError(f"cleaned_documents nicht gefunden: {cleaned_path}")

    input_hash = f"sha256:{_sha256_file(cleaned_path)}"
    meta_path = Path(str(output_path) + ".meta.json")

    if not force and output_path.exists() and _meta_matches(meta_path, input_hash):
        log.info(
            "phase_3_skipped",
            phase="phase_3_structure",
            reason="same_input_hash",
            output=str(output_path),
        )
        return _load_records(output_path)

    cleaned_records = _load_cleaned(cleaned_path)

    log.info(
        "phase_3_start",
        phase="phase_3_structure",
        doc_count=len(cleaned_records),
        force=force,
    )

    t_start = time.monotonic()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    structured: list[StructuredDocumentRecord] = []

    for rec in cleaned_records:
        non_code_text, code_blocks = _partition_body(rec.body)
        headings = _extract_headings(non_code_text)
        tables_count = _count_tables(non_code_text)
        links = _extract_links(non_code_text)
        images = _extract_images(non_code_text)
        title = _get_title(headings, rec.frontmatter, rec.doc_id)
        word_count = len(rec.body.split())

        doc_type = _guess_doc_type(
            title=title,
            headings=headings,
            code_blocks=code_blocks,
            tables_count=tables_count,
            word_count=word_count,
            body_lower=rec.body.lower(),
            book_word_threshold=book_word_threshold,
        )

        structured.append(
            StructuredDocumentRecord(
                doc_id=rec.doc_id,
                title=title,
                headings=headings,
                code_blocks=code_blocks,
                tables_count=tables_count,
                links=links,
                images=images,
                doc_type_guess=doc_type,
            )
        )

    _write_jsonl(output_path, structured)
    output_hash = f"sha256:{_sha256_file(output_path)}"
    duration = time.monotonic() - t_start

    _write_meta(meta_path, input_hash, output_hash, duration, pipeline_version)

    log.info(
        "phase_3_done",
        phase="phase_3_structure",
        record_count=len(structured),
        output=str(output_path),
        duration_seconds=round(duration, 2),
    )

    return structured
