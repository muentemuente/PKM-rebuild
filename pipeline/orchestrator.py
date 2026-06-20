"""Go-forward-Orchestrierung `pkm run`: input/ → (Review-Gates) → output/.

Ein Befehl fährt den schlanken Option-B-Flow von der Inbox bis zum Staging-Vault
und hält an den Review-Gates an. Idempotent (SHA-Skip in den Phasen) und
resume-fähig über `work/state.json`.

State-Maschine pro Doc (`state.json` → `docs`)::

    ingested → normalized → drafted → needs_review → approved → published

`ingested`/`normalized` sind Sub-Schritte der Synthese; persistiert werden
`drafted`, `needs_review`, `approved` (Gate D publish), `published` (gebaut).

Ablauf je `pkm run`:
 1. Synthese: neue `input/*.md` (max. 1-10) → `drafts/` (run_synthesis_flow).
 2. Review-Decisions aus den Drafts bauen (approved/published übersprungen).
 3. Offene Punkte → STOPP mit Hinweis auf `pkm review`.
 4. Keine offenen Punkte → approved Drafts nach `output/` bauen (Phase 9) →
    `published`; verarbeitete Inputs nach `archive/` verschieben.

Quarantäne: Drafts mit Validierungsfehler/Hang werden über Gate A
(`nachbessern`/`quarantaene`) aus dem aktiven Set genommen; der `max_tokens`-Cap
in der Qwen-Config begrenzt Reasoning-Hangs pro Doc.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.phase_9_vault_build import run_phase_9
from pipeline.review import render_review
from pipeline.run_flow import run_synthesis_flow

log = structlog.get_logger()

_STATE_FILE = "state.json"
_DONE_STATES = {"approved", "published"}
_BUILDABLE_STATES = {"drafted", "needs_review", "approved"}
_DEFAULT_MAX_FILES = 10


def _state_path(cfg: PipelineConfig) -> Path:
    return cfg.paths.work / _STATE_FILE


def load_state(cfg: PipelineConfig) -> dict[str, Any]:
    """Lädt work/state.json (oder ein leeres Gerüst)."""
    path = _state_path(cfg)
    if path.exists():
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("docs", {})
        return data
    return {"docs": {}}


def save_state(cfg: PipelineConfig, state: dict[str, Any]) -> None:
    """Schreibt work/state.json (mit Zeitstempel)."""
    state["updated"] = datetime.now(tz=UTC).isoformat(timespec="seconds")
    path = _state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _input_files(cfg: PipelineConfig) -> list[Path]:
    """Roh-`.md` direkt in input/ (ohne Hidden-/Underscore-Files), sortiert."""
    src = cfg.paths.input
    if not src.exists():
        return []
    return sorted(p for p in src.glob("*.md") if p.is_file() and not p.name.startswith((".", "_")))


def _archive_inputs(cfg: PipelineConfig, files: list[Path]) -> int:
    """Verschiebt verarbeitete Input-Files (+ input/_assets/) nach archive/processed_<ts>/.

    Die zum Build kopierten Assets (jetzt in output/_assets/) werden zusammen mit ihren
    Quell-`.md` mit-archiviert und input/_assets/ geleert — keine Akkumulation, konsistent
    mit der Input-Archivierung. Gibt die Zahl archivierter `.md`-Inputs zurück.
    """
    if not files:
        return 0
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    dest = cfg.paths.archive / f"processed_{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in files:
        if f.exists():
            f.rename(dest / f.name)
            n += 1
    _archive_input_assets(cfg, dest)
    return n


def _archive_input_assets(cfg: PipelineConfig, dest: Path) -> int:
    """Verschiebt input/_assets/* nach dest/_assets/ und leert input/_assets/ (idempotent).

    Wird nach erfolgreichem Build aufgerufen, wenn die referenzierten Assets bereits in
    output/_assets/ liegen. Auch nicht-referenzierte (orphan) Assets wandern mit ins
    Archiv, sodass input/_assets/ vollständig geleert wird. Gibt die Zahl der bewegten
    Asset-Dateien zurück.
    """
    assets_dir = cfg.paths.input / "_assets"
    if not assets_dir.is_dir():
        return 0
    assets = [p for p in assets_dir.iterdir() if p.is_file()]
    if not assets:
        return 0
    assets_dest = dest / "_assets"
    assets_dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for a in assets:
        a.rename(assets_dest / a.name)
        n += 1
    return n


def run_pipeline(
    cfg: PipelineConfig,
    *,
    force: bool = False,
    prompts_dir: Path = Path("prompts"),
    max_files: int = _DEFAULT_MAX_FILES,
) -> dict[str, Any]:
    """Fährt `pkm run`: input/ → Drafts → (Gates) → output/. Resume-fähig.

    Returns:
        Summary-Dict. ``status`` ∈ {"idle", "review_pending", "published"}.
        - review_pending: offene Gate-Punkte → Mensch via `pkm review`.
        - published: Build nach output/ erfolgt, Inputs archiviert.
        - idle: nichts zu tun (keine Inputs, keine Drafts, keine offenen Punkte).
    """
    state = load_state(cfg)
    docs: dict[str, str] = state["docs"]
    inputs = _input_files(cfg)

    # 1. Synthese (neue Inputs → Drafts). SHA-Skip macht Re-Runs idempotent.
    synth: dict[str, Any] = {"new_stems": [], "dropped_duplicates": []}
    if inputs:
        synth = run_synthesis_flow(cfg, force=force, prompts_dir=prompts_dir, max_files=max_files)
        for stem in synth["new_stems"]:
            docs[stem] = "drafted"

    # 2. Review-Decisions (approved/published auslassen)
    done = {s for s, st in docs.items() if st in _DONE_STATES}
    review = render_review(cfg, rebuild=True, skip_doc_ids=done)
    for stem in review["open_doc_ids"]:
        if docs.get(stem) not in _DONE_STATES:
            docs[stem] = "needs_review"

    # 3. Offene Punkte → STOPP
    if review["total"] > 0:
        save_state(cfg, state)
        log.info("run_review_pending", open=review["total"])
        return {
            "status": "review_pending",
            "new_drafts": len(synth["new_stems"]),
            "dropped_duplicates": len(synth["dropped_duplicates"]),
            "open": review["total"],
            "per_gate": review["per_gate"],
            "decisions_md": review["decisions_md"],
        }

    # 4. Keine offenen Punkte → Build nach output/
    has_drafts = any(st in _BUILDABLE_STATES for st in docs.values())
    if not has_drafts:
        save_state(cfg, state)
        return {"status": "idle", "new_drafts": 0}

    summary9 = run_phase_9(
        drafts_dir=cfg.paths.drafts,
        vault_dir=cfg.paths.output,
        pipeline_output=cfg.paths.work,
        backups_dir=cfg.paths.backups,
        assets_src=cfg.paths.input / "_assets",
        assets_dst=cfg.paths.output / "_assets",
        force=force,
        dry_run=False,
        repair_on_build=cfg.vault.repair_on_build,
        pipeline_version=cfg.pipeline.version,
    )
    for stem, st in list(docs.items()):
        if st in _BUILDABLE_STATES:
            docs[stem] = "published"
    archived = _archive_inputs(cfg, inputs)
    save_state(cfg, state)
    log.info("run_published", articles=summary9.get("articles", 0), archived_inputs=archived)
    return {
        "status": "published",
        "new_drafts": len(synth["new_stems"]),
        "articles": summary9.get("articles", 0),
        "folders_used": summary9.get("folders_used", 0),
        "archived_inputs": archived,
    }
