#!/usr/bin/env python3
"""
phase8_runner.py — Robuster Phase-8-Batch-Runner.

Verarbeitet RERUN_LM- oder FRESH_RUN-Batches aus pkm_triage.py-Output mit:
  - subprocess statt zsh-eval (kein Quoting-Problem bei Leerzeichen)
  - File-Log statt Pipe (kein SIGPIPE wenn Reader bricht)
  - State-File pro Batch (Resume nach Crash)
  - Per-Slug-Verifikation (nicht nur Pipeline-Exit-Code)
  - Crash-Toleranz (Einzel-Slug-Fehler blockiert nicht den Rest)
  - Konstante Backup-Pfad-Konvention

Aufrufe:
  python3 scripts/phase8_runner.py --source rerun           # alle rerun_batches
  python3 scripts/phase8_runner.py --source fresh           # alle fresh_run_batches
  python3 scripts/phase8_runner.py --source rerun --single 3   # nur batch_003
  python3 scripts/phase8_runner.py --source rerun --from 2 --to 5
  python3 scripts/phase8_runner.py --source rerun --dry-run    # nur parsen + listen

Output:
  data/02_pipeline_output/phase8_logs/
    state_batch_NNN.json     pro Batch: done/failed-Listen
    batch_NNN/<slug>.log     pro Slug: kompletter Pipeline-Stdout/Stderr

Resume:
  Wiederholter Aufruf überspringt bereits in state als 'done' markierte Slugs.

Stop-Bedingungen (automatisch):
  - >5 consecutive failures in einem Batch → Abbruch des Batchs (rest skipped)
  - SIGINT (Ctrl-C) → state speichern, sauberer Exit
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# === Pfade ===
PROJECT_ROOT = Path.home() / "projects" / "aktiv" / "PKM-rebuild"
DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
DRAFTS_DIR = DATA_ROOT / "03_drafts"
TRIAGE_DIR = DATA_ROOT / "02_pipeline_output" / "triage"
LOG_BASE = DATA_ROOT / "02_pipeline_output" / "phase8_logs"
BACKUP_BASE = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "backups"

# === Pipeline-Aufruf ===
PIPELINE_CMD = [sys.executable, "-m", "pipeline", "run", "--phase", "8"]
TIMEOUT_PER_SLUG = 30 * 60  # 30 min Maximum pro Slug

# === Stop-Bedingungen ===
MAX_CONSECUTIVE_FAILURES = 5

# Slug-Werkzeuge (normalize_slug, canonical_ck_slug) → scripts/_pkm_common.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._pkm_common import (  # noqa: E402
    canonical_ck_slug,
    normalize_slug,
)

# Re-Export für test_phase8_runner.py (importiert runner.canonical_ck_slug)
__all__ = ["canonical_ck_slug", "normalize_slug"]


# === Batch-File parsen ===

def parse_batch(batch_file: Path) -> list[tuple[str, Path]]:
    """Extrahiert (slug, corpus_path) aus einem Batch-Markdown-File.

    Format:
        ## `<slug>`
        - Korpus: `<absoluter-pfad>`
    """
    items: list[tuple[str, Path]] = []
    current_slug: str | None = None
    for line in batch_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+`([^`]+)`", line)
        if m:
            current_slug = m.group(1)
            continue
        m = re.match(r"^-\s+Korpus:\s*`([^`]+)`", line)
        if m and current_slug:
            items.append((current_slug, Path(m.group(1))))
            current_slug = None
    return items


# === State-Persistence ===

def state_path(batch_name: str) -> Path:
    LOG_BASE.mkdir(parents=True, exist_ok=True)
    return LOG_BASE / f"state_{batch_name}.json"


def load_state(batch_name: str) -> dict:
    p = state_path(batch_name)
    if not p.exists():
        return {"done": [], "failed": [], "started_at": None,
                "last_update": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"done": [], "failed": [], "started_at": None,
                "last_update": None}


def save_state(batch_name: str, state: dict) -> None:
    state["last_update"] = datetime.now().isoformat(timespec="seconds")
    state_path(batch_name).write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# === Backup ===

def backup_existing_drafts(slug: str, backup_dir: Path) -> int:
    """Verschiebt vorhandene CK_<slug>.* (sichtbar + hidden) nach backup_dir."""
    visible = f"CK_{slug}"
    hidden = f".CK_{slug}"
    count = 0
    for p in DRAFTS_DIR.iterdir():
        if not p.is_file():
            continue
        # Beide Familien: CK_foo.* und .CK_foo.*
        if (p.name.startswith(visible + ".")
                or p.name.startswith(hidden + ".")):
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(backup_dir / p.name))
            count += 1
    return count


# === Verifikation ===

def verify_outputs(slug: str) -> dict[str, bool]:
    return {
        "md": (DRAFTS_DIR / f"CK_{slug}.md").exists(),
        "body_md": (DRAFTS_DIR / f"CK_{slug}.body.md").exists(),
        "frontmatter": (DRAFTS_DIR / f"CK_{slug}.frontmatter.json").exists(),
    }


def is_complete(outputs: dict[str, bool]) -> bool:
    """Triple ist vollständig wenn .md UND .frontmatter.json existieren.
    body.md ist optional (passthrough-Routing erzeugt es nicht)."""
    return outputs["md"] and outputs["frontmatter"]


# === Pipeline-Call ===

def run_pipeline(corpus_path: Path, log_file: Path) -> int:
    """Single Pipeline-Aufruf für ein Korpus-File. Stdout+Stderr in log_file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("wb") as logf:
        result = subprocess.run(
            PIPELINE_CMD + ["--file", str(corpus_path)],
            cwd=str(PROJECT_ROOT),
            stdout=logf,
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT_PER_SLUG,
            check=False,
        )
    return result.returncode


# === Batch-Verarbeitung ===

def process_batch(batch_file: Path, dry_run: bool = False) -> dict:
    batch_name = batch_file.stem
    items = parse_batch(batch_file)
    state = load_state(batch_name)
    if state["started_at"] is None:
        state["started_at"] = datetime.now().isoformat(timespec="seconds")

    done = set(state.get("done", []))
    failed = set(state.get("failed", []))

    backup_dir = (BACKUP_BASE
                  / f"phase8_{batch_name}_"
                  f"{datetime.now().strftime('%Y%m%d_%H%M')}")

    stats = {
        "batch": batch_name,
        "total": len(items),
        "done_new": 0,
        "skipped_already_done": 0,
        "failed": 0,
        "aborted": False,
    }

    print(f"\n=== {batch_name} ({len(items)} Slugs) ===", flush=True)
    if dry_run:
        for slug, corpus in items:
            print(f"  DRY: {slug:50} ← {corpus}", flush=True)
        return stats

    consecutive_failures = 0

    for i, (batch_slug, corpus) in enumerate(items, 1):
        # Kanonischer Slug aus dem Korpus-Dateinamen — exakt die Ableitung, unter
        # der die Pipeline CK_<slug>.* schreibt. Behebt den false-FAIL, bei dem
        # verify_outputs unter dem (divergenten) Batch-Slug suchte (E2/Runner-Bug).
        slug = canonical_ck_slug(corpus.stem)
        prefix = f"  [{i:2}/{len(items)}] {slug}"

        if slug in done:
            print(f"{prefix:60} SKIP (done)", flush=True)
            stats["skipped_already_done"] += 1
            continue

        if not corpus.exists():
            print(f"{prefix:60} FAIL (corpus missing: {corpus})", flush=True)
            failed.add(slug)
            stats["failed"] += 1
            consecutive_failures += 1
            state["done"] = sorted(done)
            state["failed"] = sorted(failed)
            save_state(batch_name, state)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"  ABORT: {consecutive_failures} consecutive failures",
                      flush=True)
                stats["aborted"] = True
                break
            continue

        t0 = time.time()
        n_backed = backup_existing_drafts(slug, backup_dir / slug)
        log_file = LOG_BASE / batch_name / f"{slug}.log"

        try:
            rc = run_pipeline(corpus, log_file)
        except subprocess.TimeoutExpired:
            rc = -1
            print(f"{prefix:60} TIMEOUT after {TIMEOUT_PER_SLUG}s",
                  flush=True)
        except Exception as e:
            rc = -2
            print(f"{prefix:60} EXCEPTION: {type(e).__name__}: {e}",
                  flush=True)

        outputs = verify_outputs(slug)
        complete = is_complete(outputs)
        elapsed = time.time() - t0

        # verify_outputs ist autoritativ: existieren die Draft-Files, gilt der
        # Slug als erfolgreich — auch wenn der Pipeline-Aufruf an der Timeout-
        # Boundary rc!=0 meldete (Draft kann vor dem Timeout geschrieben sein).
        if complete:
            done.add(slug)
            failed.discard(slug)
            stats["done_new"] += 1
            consecutive_failures = 0
            note = "" if rc == 0 else f"  (rc={rc}, outputs vollständig)"
            print(f"{prefix:60} OK   {elapsed:5.0f}s  backed_up={n_backed}{note}",
                  flush=True)
        else:
            failed.add(slug)
            done.discard(slug)
            stats["failed"] += 1
            consecutive_failures += 1
            short_out = "".join(
                "1" if outputs[k] else "0"
                for k in ("md", "body_md", "frontmatter"))
            print(f"{prefix:60} FAIL rc={rc} files={short_out} "
                  f"{elapsed:5.0f}s log={log_file.name}", flush=True)

        # State nach jedem Slug persistieren (Crash-Sicherheit)
        state["done"] = sorted(done)
        state["failed"] = sorted(failed)
        save_state(batch_name, state)

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            print(f"  ABORT: {consecutive_failures} consecutive failures",
                  flush=True)
            stats["aborted"] = True
            break

    return stats


# === Main ===

def install_signal_handlers():
    def handler(signum, frame):
        print(f"\nSIGNAL {signum} empfangen — state ist persistiert, beende.",
              flush=True)
        sys.exit(130)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main() -> int:
    install_signal_handlers()

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["rerun", "fresh"], required=True)
    ap.add_argument("--from", dest="from_batch", type=int, default=1)
    ap.add_argument("--to", dest="to_batch", type=int, default=999)
    ap.add_argument("--single", type=int, help="Nur diesen einen Batch")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.single is not None:
        args.from_batch = args.single
        args.to_batch = args.single

    src_dir = TRIAGE_DIR / (
        "rerun_batches" if args.source == "rerun" else "fresh_run_batches")
    if not src_dir.exists():
        print(f"FEHLER: {src_dir} fehlt. Erst pkm_triage.py laufen lassen.",
              file=sys.stderr)
        return 2

    batches = sorted(src_dir.glob("batch_*.md"))
    selected = []
    for b in batches:
        try:
            n = int(b.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if args.from_batch <= n <= args.to_batch:
            selected.append(b)

    if not selected:
        print(f"Keine Batches im Bereich {args.from_batch}-{args.to_batch} "
              f"in {src_dir}", file=sys.stderr)
        return 2

    print(f"Source: {args.source}  Verzeichnis: {src_dir}")
    print(f"Batches: {[b.stem for b in selected]}  Dry-Run: {args.dry_run}")

    all_stats = []
    for bf in selected:
        s = process_batch(bf, dry_run=args.dry_run)
        all_stats.append(s)
        if s.get("aborted"):
            print(f"\nBatch {s['batch']} abgebrochen — Loop stoppt.",
                  flush=True)
            break

    print("\n=== SUMMARY ===")
    print(f"{'Batch':22} {'Total':>5} {'Done':>5} {'Skip':>5} {'Fail':>5} "
          f"{'Aborted':>7}")
    for s in all_stats:
        print(f"{s['batch']:22} {s['total']:5} {s['done_new']:5} "
              f"{s['skipped_already_done']:5} {s['failed']:5} "
              f"{'yes' if s.get('aborted') else 'no':>7}")

    total_failed = sum(s["failed"] for s in all_stats)
    aborted = any(s.get("aborted") for s in all_stats)
    return 1 if (total_failed or aborted) else 0


if __name__ == "__main__":
    sys.exit(main())
