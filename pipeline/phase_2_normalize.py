"""Phase 2 — Normalisierung: Text bereinigen, Frontmatter extrahieren.

Input:  data/02_pipeline_output/files_manifest.jsonl  (Phase 1 Output)
        data/01_corpus_input/**/*.md                   (read-only)
Output: data/02_pipeline_output/cleaned_documents.jsonl
        data/02_pipeline_output/cleaned_documents.jsonl.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 2):
  - Alle docs aus manifest verarbeitet
  - CRLF → LF, Tabs → 4 Spaces (außer in Code-Blöcken)
  - Trailing Whitespace entfernt (außer in Code-Blöcken)
  - Max. 3 aufeinanderfolgende Leerzeilen
  - YAML-Frontmatter extrahiert (oder leeres Dict)
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
import yaml

from pipeline.schemas import CleanedDocument, DocumentRecord

log = structlog.get_logger()

_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")
_FRONTMATTER_RE = re.compile(
    r"^---\r?\n(.*?)^(---|\.\.\.)\s*\r?\n",
    re.MULTILINE | re.DOTALL,
)


def _extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extrahiert YAML-Frontmatter aus einem Markdown-Text.

    Gibt (frontmatter_dict, body) zurück. Bei fehlendem oder
    ungültigem Frontmatter: ({}, vollständiger Text als body).
    """
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return {}, text
    yaml_text = m.group(1)
    body = text[m.end() :]
    try:
        fm = yaml.safe_load(yaml_text) or {}
        return (fm if isinstance(fm, dict) else {}), body
    except yaml.YAMLError:
        return {}, text


def _normalize_body(
    text: str,
    tab_replacement: str,
    max_blank_lines: int,
    strip_trailing_whitespace: bool,
) -> str:
    """Normalisiert den Body-Text: Tabs, Trailing-Whitespace, Leerzeilen.

    Code-Blöcke (``` oder ~~~) werden unverändert übernommen.
    """
    lines = text.split("\n")
    result: list[str] = []
    in_code = False
    fence_char = ""
    consecutive_blanks = 0

    for line in lines:
        if in_code:
            result.append(line)
            stripped = line.strip()
            m = _FENCE_OPEN_RE.match(stripped)
            if m and m.group(0)[0] == fence_char and stripped == m.group(0):
                in_code = False
                fence_char = ""
            continue

        stripped = line.strip()
        m = _FENCE_OPEN_RE.match(stripped)
        if m:
            fence_char = m.group(0)[0]
            in_code = True
            result.append(line)
            consecutive_blanks = 0
            continue

        processed = line.replace("\t", tab_replacement)
        if strip_trailing_whitespace:
            processed = processed.rstrip()

        if processed.strip() == "":
            consecutive_blanks += 1
            if consecutive_blanks <= max_blank_lines:
                result.append(processed)
        else:
            consecutive_blanks = 0
            result.append(processed)

    return "\n".join(result)


def _sha256_text(text: str) -> str:
    """SHA-256 eines UTF-8-Strings."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(manifest_path: Path) -> list[DocumentRecord]:
    """Lädt DocumentRecords aus einer JSONL-Datei."""
    records = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(DocumentRecord.model_validate_json(line))
    return records


def _load_records(output_path: Path) -> list[CleanedDocument]:
    """Lädt bestehende CleanedDocuments aus einer JSONL-Datei."""
    records = []
    for line in output_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(CleanedDocument.model_validate_json(line))
    return records


def _write_jsonl(output_path: Path, records: list[CleanedDocument]) -> None:
    """Schreibt CleanedDocuments in eine JSONL-Datei."""
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
        "phase": "phase_2_normalize",
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


def run_phase_2(
    manifest_path: Path,
    output_path: Path,
    *,
    force: bool = False,
    max_blank_lines: int = 3,
    tab_replacement: str = "    ",
    strip_trailing_whitespace: bool = True,
    parse_frontmatter: bool = True,
    pipeline_version: str = "0.1.0",
) -> list[CleanedDocument]:
    """Phase 2 ausführen: Dokumente normalisieren.

    Args:
        manifest_path: Pfad zur files_manifest.jsonl (Phase 1 Output).
        output_path: Ziel-Pfad für cleaned_documents.jsonl.
        force: Wenn True, Cache ignorieren und neu berechnen.
        max_blank_lines: Max. aufeinanderfolgende Leerzeilen.
        tab_replacement: Ersatz für Tab-Zeichen (außer in Code-Blöcken).
        strip_trailing_whitespace: Trailing-Whitespace entfernen.
        parse_frontmatter: YAML-Frontmatter extrahieren.
        pipeline_version: Version für Meta-File.

    Returns:
        Liste aller CleanedDocument-Einträge.

    Raises:
        FileNotFoundError: Wenn manifest_path nicht existiert.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest nicht gefunden: {manifest_path}")

    input_hash = f"sha256:{_sha256_file(manifest_path)}"
    meta_path = Path(str(output_path) + ".meta.json")

    if not force and output_path.exists() and _meta_matches(meta_path, input_hash):
        log.info(
            "phase_2_skipped",
            phase="phase_2_normalize",
            reason="same_input_hash",
            output=str(output_path),
        )
        return _load_records(output_path)

    manifest_records = _load_manifest(manifest_path)

    log.info(
        "phase_2_start",
        phase="phase_2_normalize",
        doc_count=len(manifest_records),
        force=force,
    )

    t_start = time.monotonic()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path = output_path.parent / "errors.jsonl"
    cleaned: list[CleanedDocument] = []
    error_count = 0

    for rec in manifest_records:
        file_path = Path(rec.path)
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            error_count += 1
            log.error(
                "phase_2_file_error",
                phase="phase_2_normalize",
                doc_id=rec.doc_id,
                path=rec.path,
                error=str(exc),
            )
            with errors_path.open("a", encoding="utf-8") as ef:
                ef.write(
                    json.dumps(
                        {
                            "phase": "phase_2_normalize",
                            "doc_id": rec.doc_id,
                            "path": rec.path,
                            "error": str(exc),
                        }
                    )
                    + "\n"
                )
            continue

        # Schritt 1: CRLF → LF
        text = raw.replace("\r\n", "\n").replace("\r", "\n")

        # Schritt 2: Frontmatter extrahieren
        if parse_frontmatter:
            frontmatter, body = _extract_frontmatter(text)
        else:
            frontmatter, body = {}, text

        # Schritt 3: Body normalisieren
        normalized_body = _normalize_body(
            body,
            tab_replacement=tab_replacement,
            max_blank_lines=max_blank_lines,
            strip_trailing_whitespace=strip_trailing_whitespace,
        )

        cleaned.append(
            CleanedDocument(
                doc_id=rec.doc_id,
                body=normalized_body,
                frontmatter=frontmatter,
                normalized_sha256=_sha256_text(normalized_body),
            )
        )

    _write_jsonl(output_path, cleaned)
    output_hash = f"sha256:{_sha256_file(output_path)}"
    duration = time.monotonic() - t_start

    _write_meta(
        meta_path,
        input_hash,
        output_hash,
        duration,
        pipeline_version,
        {
            "max_blank_lines": max_blank_lines,
            "tab_replacement": tab_replacement,
            "strip_trailing_whitespace": strip_trailing_whitespace,
            "parse_frontmatter": parse_frontmatter,
        },
    )

    log.info(
        "phase_2_done",
        phase="phase_2_normalize",
        record_count=len(cleaned),
        error_count=error_count,
        output=str(output_path),
        duration_seconds=round(duration, 2),
    )

    return cleaned
