"""Phase 1 — Inventar: Einsammeln aller Markdown-Dateien aus corpus_input.

Input:  input/**/*.md  (read-only, niemals schreiben)
Output: work/files_manifest.jsonl
        work/files_manifest.jsonl.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 1):
  - Alle .md aus corpus_input erfasst (Count-Check im Log)
  - Keine doppelten doc_ids (Slug-Kollisionen → Suffix _2, _3, ...)
  - SHA-256 für jedes File berechnet
  - Idempotenz: zweimaliger Lauf mit gleichem Input → identische Outputs
"""

import fnmatch
import hashlib
import json
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pipeline.schemas import DocumentRecord

log = structlog.get_logger()

_SLUG_SPECIAL_RE = re.compile(r"[^a-z0-9]+")
_UMLAUT_TABLE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)


def _filename_to_slug(stem: str) -> str:
    """Konvertiert einen Dateinamen-Stamm (ohne Endung) in einen URL-sicheren Slug."""
    # NFC zuerst: macOS-Dateinamen sind oft NFD-zerlegt (z.B. "o" + combining ¨).
    # Ohne Komposition matcht die _UMLAUT_TABLE (Composed-Keys) nicht, und das
    # nachfolgende NFKD-Strippen wuerfe ä→a statt ä→ae (E2-Naming-Bug).
    s = unicodedata.normalize("NFC", stem)
    s = s.translate(_UMLAUT_TABLE)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _SLUG_SPECIAL_RE.sub("-", s)
    return s.strip("-")


def _is_excluded(path: Path, base: Path, patterns: list[str]) -> bool:
    """Prüft ob eine Datei durch ein Exclude-Pattern gefiltert wird."""
    name = path.name
    rel = str(path.relative_to(base))
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def _collect_files(
    corpus_input: Path,
    recursive: bool,
    exclude_patterns: list[str],
    include_extensions: list[str],
) -> list[Path]:
    """Sammelt Markdown-Dateien aus corpus_input; gibt sortierte Liste zurück."""
    collected: set[Path] = set()
    for ext in include_extensions:
        pattern = f"**/*{ext}" if recursive else f"*{ext}"
        for f in corpus_input.glob(pattern):
            if f.is_file() and not _is_excluded(f, corpus_input, exclude_patterns):
                collected.add(f)
    return sorted(collected)


def _assign_doc_ids(files: list[Path]) -> dict[Path, str]:
    """Weist eindeutige doc_ids zu; Slug-Kollisionen bekommen Suffix _2, _3, ...

    Die Eingabeliste muss sortiert sein für Determinismus.
    """
    seen: dict[str, int] = {}
    result: dict[Path, str] = {}
    for f in files:
        slug = _filename_to_slug(f.stem)
        count = seen.get(slug, 0) + 1
        seen[slug] = count
        result[f] = f"D_{slug}" if count == 1 else f"D_{slug}_{count}"
    return result


def _sha256_file(path: Path) -> str:
    """Berechnet den SHA-256 Hash einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _text_stats(path: Path) -> tuple[int, int, int]:
    """Gibt (line_count, word_count, char_count) zurück.

    Bei Lesefehlern werden Nullen zurückgegeben (Fehler wird vom Aufrufer geloggt).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0, 0
    return len(text.splitlines()), len(text.split()), len(text)


def _compute_input_hash(files: list[Path], base: Path) -> str:
    """Schneller Input-Hash aus Pfad, Größe und mtime_ns — kein Datei-Lesen nötig."""
    h = hashlib.sha256()
    for f in files:
        stat = f.stat()
        entry = f"{f.relative_to(base)}|{stat.st_size}|{stat.st_mtime_ns}\n"
        h.update(entry.encode())
    return f"sha256:{h.hexdigest()}"


def _meta_matches(meta_path: Path, input_hash: str) -> bool:
    """Prüft ob das bestehende Meta-File den selben Input-Hash enthält."""
    if not meta_path.exists():
        return False
    try:
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(meta.get("input_hash") == input_hash)
    except (json.JSONDecodeError, OSError):
        return False


def _load_records(output_path: Path) -> list[DocumentRecord]:
    """Lädt bestehende DocumentRecords aus einer JSONL-Datei."""
    records = []
    for line in output_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(DocumentRecord.model_validate_json(line))
    return records


def _write_jsonl(output_path: Path, records: list[DocumentRecord]) -> None:
    """Schreibt Records in eine JSONL-Datei (eine JSON-Zeile pro Record)."""
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
        "phase": "phase_1_inventory",
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": config_snapshot,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def run_phase_1(
    corpus_input: Path,
    output_path: Path,
    *,
    force: bool = False,
    sample: int | None = None,
    recursive: bool = True,
    exclude_patterns: list[str] | None = None,
    include_extensions: list[str] | None = None,
    pipeline_version: str = "0.1.0",
) -> list[DocumentRecord]:
    """Phase 1 ausführen: Korpus inventarisieren.

    Args:
        corpus_input: Pfad zu input/ (read-only, niemals schreiben).
        output_path: Ziel-Pfad für files_manifest.jsonl.
        force: Wenn True, Cache ignorieren und neu berechnen.
        sample: Wenn gesetzt, nur die ersten N Dateien verarbeiten (sortiert).
        recursive: Unterverzeichnisse einschließen.
        exclude_patterns: Glob-Muster für auszuschließende Dateien.
        include_extensions: Nur Dateien mit diesen Endungen einschließen.
        pipeline_version: Version für Meta-File.

    Returns:
        Liste aller DocumentRecord-Einträge.

    Raises:
        FileNotFoundError: Wenn corpus_input nicht existiert.
    """
    if not corpus_input.exists():
        raise FileNotFoundError(f"corpus_input nicht gefunden: {corpus_input}")

    _exclude = exclude_patterns if exclude_patterns is not None else [".*", "_*"]
    _include = include_extensions if include_extensions is not None else [".md"]

    t_start = time.monotonic()

    files = _collect_files(corpus_input, recursive, _exclude, _include)
    if sample is not None:
        files = files[:sample]

    input_hash = _compute_input_hash(files, corpus_input)
    meta_path = Path(str(output_path) + ".meta.json")

    if not force and output_path.exists() and _meta_matches(meta_path, input_hash):
        log.info(
            "phase_1_skipped",
            phase="phase_1_inventory",
            reason="same_input_hash",
            output=str(output_path),
        )
        return _load_records(output_path)

    log.info(
        "phase_1_start",
        phase="phase_1_inventory",
        file_count=len(files),
        corpus_input=str(corpus_input),
        force=force,
        sample=sample,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path = output_path.parent / "errors.jsonl"
    doc_ids = _assign_doc_ids(files)
    records: list[DocumentRecord] = []
    error_count = 0

    for f in files:
        try:
            stat = f.stat()
            sha256 = _sha256_file(f)
            line_count, word_count, char_count = _text_stats(f)
            records.append(
                DocumentRecord(
                    doc_id=doc_ids[f],
                    path=str(f),
                    filename=f.name,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    sha256=sha256,
                    line_count=line_count,
                    word_count=word_count,
                    char_count=char_count,
                )
            )
        except OSError as exc:
            error_count += 1
            log.error(
                "phase_1_file_error",
                phase="phase_1_inventory",
                path=str(f),
                error=str(exc),
            )
            with errors_path.open("a", encoding="utf-8") as ef:
                ef.write(
                    json.dumps({"phase": "phase_1_inventory", "path": str(f), "error": str(exc)})
                    + "\n"
                )

    _write_jsonl(output_path, records)
    output_hash = f"sha256:{_sha256_file(output_path)}"
    duration = time.monotonic() - t_start

    _write_meta(
        meta_path,
        input_hash,
        output_hash,
        duration,
        pipeline_version,
        {
            "recursive": recursive,
            "exclude_patterns": _exclude,
            "include_extensions": _include,
            "sample": sample,
        },
    )

    log.info(
        "phase_1_done",
        phase="phase_1_inventory",
        record_count=len(records),
        error_count=error_count,
        output=str(output_path),
        duration_seconds=round(duration, 2),
    )

    return records
