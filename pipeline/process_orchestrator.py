"""Process-1 — universeller Erstverarbeitungs-Orchestrator (`pkm process`).

Der **primäre** Weg, durch den **jedes** md-File — egal welcher Ausgangszustand
(fertig, gescrapt, copy-paste, unformatiert) — **immer** läuft und vault-ready wird.
**Kein Vorab-Filter/Triage:** alle Files durchlaufen alle Stages der Reihe nach.

Eigenständiger Orchestrator (Architektur-Entscheidung Option A) — hängt **nicht** in
`pkm run` (Synthese) ein; eigener State `work/process/state.jsonl`. Synthese ist eine
**nachgelagerte** Phase (läuft auf bereits vault-ready Files), nicht der Ingest.

Stage-Kette (fest verankert)::

    ingested → normalize → restructure → tags → assets → links → review_ready
             → [human_reviewed] → promoted   (Owner-Gates, außerhalb dieses Laufs)

Eigenschaften: **idempotent** (unveränderte Datei per Hash überspringt erledigte
Stages, nicht die Datei), **resumable** (`--resume` setzt am letzten State fort),
**resilient** (Einzelfehler → Datei `needs_human`, Lauf fährt fort). STOPpt bei
`review_ready`; Promotion (WP3c-5 D4) bleibt ein separater Owner-Aufruf.

Reuse statt Neubau: `driver.run_chain` (repair-safe+format-safe), `restructure_file`
(WP3c-4, im Test gemockt), `taxonomy` (Tag-Vokabular-SSoT), `batch_restructure`
(Review-Sheet/Promote-Mode). **Kein realer LLM-Call hier; kein Vault-Write, kein D4.**
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from pipeline import _paths, taxonomy
from pipeline.batch_restructure import (
    BatchResult,
    BatchRow,
    _draft_complete,
    _slug_in_vault,
    write_review_sheet,
)
from pipeline.config import QwenConfig
from pipeline.driver import run_chain
from pipeline.phase_8_synthesis import _slugify_ck
from pipeline.restructure import restructure_file
from pipeline.vault_audit import parse_frontmatter, split_frontmatter

#: Fest verankerte Stage-Reihenfolge bis zum Review-Gate.
STAGES: tuple[str, ...] = (
    "ingested",
    "normalize",
    "restructure",
    "tags",
    "assets",
    "links",
    "review_ready",
)
_TERMINAL = "review_ready"

_EMBED_RE = re.compile(r"!\[\[\s*([^\]]+?)\s*\]\]")
_WIKILINK_RE = re.compile(r"(?<!!)\[\[\s*([^\]]+?)\s*\]\]")


@dataclass
class FileState:
    """Persistenter Zustand einer Datei in der Stage-Kette."""

    source: str
    slug: str
    source_hash: str
    stage: str
    working_path: str
    updated: str
    last_error: str | None = None


@dataclass
class ProcessResult:
    """Ergebnis eines `pkm process`-Laufs."""

    review_ready: list[FileState] = field(default_factory=list)
    failures: list[tuple[Path, str, str]] = field(default_factory=list)  # (src, stage, error)
    sheet_path: Path | None = None


# === State (work/process/state.jsonl) =========================================


def load_state(state_path: Path) -> dict[str, FileState]:
    """Lädt den Per-File-State (JSONL), gekeyed nach Source-Pfad."""
    states: dict[str, FileState] = {}
    if not state_path.exists():
        return states
    for line in state_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        states[d["source"]] = FileState(**d)
    return states


def save_state(state_path: Path, states: dict[str, FileState]) -> None:
    """Schreibt den State atomar als JSONL (eine Zeile pro Datei)."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(s), ensure_ascii=False) for s in states.values()]
    state_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _nfc_slug(path: Path) -> str:
    """NFC-normalisierter, kanonischer Slug aus dem Dateinamen."""
    return _slugify_ck(unicodedata.normalize("NFC", path.stem))


# === Datei-IO der Stages ======================================================


def _parse_working(path: Path) -> tuple[dict[str, Any], str]:
    fm_text, body, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    data, _ = parse_frontmatter(fm_text) if fm_text else (None, None)
    return (data or {}), body


def _write_working(path: Path, fm: dict[str, Any], body: str) -> None:
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{dumped}---\n\n{body.strip()}\n", encoding="utf-8")


@lru_cache(maxsize=1)
def _tag_vocab() -> tuple[frozenset[str], dict[str, str | None]]:
    """(kanonische Tags, Synonym-Map) aus der Taxonomie-SSoT — gecached."""
    canonical, synonyms = taxonomy.load_tags()
    return frozenset(canonical), dict(synonyms)


# === Deterministische Stages ==================================================


def _stage_normalize(st: FileState) -> None:
    """Frontmatter-Gerüst (Slug) + Body-Hygiene (repair-safe + format-safe)."""
    p = Path(st.working_path)
    data, body = _parse_working(p)
    data.setdefault("slug", st.slug)
    new_body = run_chain(body).text
    _write_working(p, data, new_body)


def _stage_restructure(
    st: FileState, client: Any, qwen: QwenConfig, prompts_dir: Path | None, timestamp: str | None
) -> None:
    """Typ-bewusstes restructure (WP3c-4) → Draft (Passthrough wenn gut strukturiert)."""
    p = Path(st.working_path)
    draft = restructure_file(
        p, client=client, qwen=qwen, out_dir=p.parent, prompts_dir=prompts_dir, timestamp=timestamp
    )
    st.working_path = str(draft.draft_path)


def _stage_tags(st: FileState) -> None:
    """Tags gegen das kontrollierte Vokabular mappen (Synonyme auflösen, Freitext droppen)."""
    p = Path(st.working_path)
    data, body = _parse_working(p)
    canonical, synonyms = _tag_vocab()
    raw = data.get("tags")
    mapped: list[str] = []
    if isinstance(raw, list):
        for t in raw:
            tag = str(t).strip().lower()
            resolved = tag if tag in canonical else synonyms.get(tag)
            if resolved and resolved not in mapped:
                mapped.append(resolved)
    data["tags"] = sorted(mapped)
    _write_working(p, data, body)


def _stage_assets(st: FileState) -> None:
    """Asset-Embed-Syntax normalisieren: ``![[ name ]]`` → ``![[name]]`` (idempotent)."""
    p = Path(st.working_path)
    data, body = _parse_working(p)
    _write_working(p, data, _EMBED_RE.sub(r"![[\1]]", body))


def _stage_links(st: FileState) -> None:
    """Wikilink-Syntax normalisieren: ``[[ x ]]`` → ``[[x]]`` (Embeds via assets; idempotent)."""
    p = Path(st.working_path)
    data, body = _parse_working(p)
    _write_working(p, data, _WIKILINK_RE.sub(r"[[\1]]", body))


def _run_stage(
    name: str,
    st: FileState,
    client: Any,
    qwen: QwenConfig,
    prompts_dir: Path | None,
    timestamp: str | None,
) -> None:
    if name == "normalize":
        _stage_normalize(st)
    elif name == "restructure":
        _stage_restructure(st, client, qwen, prompts_dir, timestamp)
    elif name == "tags":
        _stage_tags(st)
    elif name == "assets":
        _stage_assets(st)
    elif name == "links":
        _stage_links(st)
    elif name == "review_ready":
        pass  # terminales Gate — keine Transformation
    else:  # pragma: no cover - Schutz gegen Tippfehler in STAGES
        raise ValueError(f"unbekannte Stage: {name}")


def _advance(
    st: FileState,
    client: Any,
    qwen: QwenConfig,
    prompts_dir: Path | None,
    timestamp: str | None,
) -> None:
    """Führt die noch ausstehenden Stages der Reihe nach aus (bis review_ready)."""
    start = STAGES.index(st.stage)
    for name in STAGES[start + 1 :]:
        _run_stage(name, st, client, qwen, prompts_dir, timestamp)
        st.stage = name
        st.updated = _now()


# === Orchestrator =============================================================


def run_process(
    source_dir: Path,
    *,
    client: Any,
    qwen: QwenConfig,
    vault_dir: Path,
    work_dir: Path | None = None,
    prompts_dir: Path | None = None,
    timestamp: str | None = None,
    resume: bool = False,
) -> ProcessResult:
    """Fährt **alle** Files aus ``source_dir`` durch die Stage-Kette bis ``review_ready``.

    Args:
        source_dir: Quell-Ordner (ALLE ``*.md`` werden erfasst — kein Filter).
        client: injizierter Qwen-Client (nur für die restructure-Stage; im Test gemockt).
        qwen: Qwen-Konfiguration.
        vault_dir: Live-Vault (read-only) — nur für den ``promote_mode``-Check im Sheet.
        work_dir: Arbeits-/State-Wurzel (Default ``_paths.WORK / "process"``).
        resume: setzt am persistierten State fort (idempotent ist Default).
    """
    work = work_dir if work_dir is not None else (_paths.WORK / "process")
    working_dir = work / "working"
    working_dir.mkdir(parents=True, exist_ok=True)
    state_path = work / "state.jsonl"
    states = load_state(state_path)
    result = ProcessResult()

    for src in sorted(source_dir.glob("*.md")):
        key = str(src.resolve())
        digest = _sha256(src)
        st = states.get(key)

        # Neu ODER Quelle geändert → von vorne (ingested). Sonst State behalten.
        if st is None or st.source_hash != digest:
            slug = _nfc_slug(src)
            working = working_dir / f"{slug}.md"
            shutil.copyfile(src, working)
            st = FileState(
                source=key,
                slug=slug,
                source_hash=digest,
                stage="ingested",
                working_path=str(working),
                updated=_now(),
            )
            states[key] = st

        if st.stage == _TERMINAL and st.last_error is None:
            result.review_ready.append(st)  # idempotent: nichts zu tun
            continue

        # Bereits gescheiterte Datei nur mit --resume erneut versuchen; sonst
        # bleibt sie needs_human (kein wiederholtes Anrennen gegen bekannte Fehler).
        if st.last_error is not None and not resume:
            result.failures.append((src, st.stage, st.last_error))
            continue

        try:
            _advance(st, client, qwen, prompts_dir, timestamp)
        except Exception as exc:  # Resilienz: Einzelfehler isolieren
            st.last_error = f"{st.stage}: {type(exc).__name__}: {str(exc)[:160]}"
            st.updated = _now()
            result.failures.append((src, st.stage, st.last_error))
            save_state(state_path, states)
            continue

        st.last_error = None
        st.updated = _now()
        save_state(state_path, states)
        result.review_ready.append(st)

    if result.review_ready:
        result.sheet_path = _build_sheet(result, vault_dir, work, timestamp)
    if result.failures:
        _write_needs_human(work, result.failures)
    return result


def _build_sheet(result: ProcessResult, vault_dir: Path, work: Path, timestamp: str | None) -> Path:
    """Erzeugt das WP3c-6-Review-Sheet aus den review_ready Drafts (Reuse)."""
    rows: list[BatchRow] = []
    for st in result.review_ready:
        draft = Path(st.working_path)
        data, _ = _parse_working(draft)
        promote_mode = "update" if _slug_in_vault(vault_dir, st.slug) else "new"
        action = str(data.get("restructure_action", ""))
        rows.append(
            BatchRow(
                slug=st.slug,
                type=str(data.get("type", "")),
                type_source=str(data.get("type_source", "")),
                restructure_action=action,
                confidence=str(data.get("confidence", "")),
                promote_mode=promote_mode,
                genre_shift_flag=action == "rewrite",
                runtime_s=0.0,
                draft_path=draft,
                new_incomplete=promote_mode == "new" and not _draft_complete(draft),
            )
        )
    ts = timestamp_compact(timestamp)
    return write_review_sheet(BatchResult(rows=rows), work / f"review_sheet_{ts}.xlsx")


def timestamp_compact(timestamp: str | None) -> str:
    """Kompakter Zeitstempel für Dateinamen (deterministisch injizierbar)."""
    if timestamp is not None:
        return re.sub(r"[^0-9]", "", timestamp)[:14] or "run"
    return datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")


def _write_needs_human(work: Path, failures: list[tuple[Path, str, str]]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    lines = [f"{src}\t{stage}\t{err}" for src, stage, err in failures]
    (work / "needs_human.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
