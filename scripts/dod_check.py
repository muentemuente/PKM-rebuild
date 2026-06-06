#!/usr/bin/env python3
"""dod_check.py — Maschinen-prüfbarer DoD-Gesamtcheck (docs/01_strategy.md §3).

Prüft die automatisierbaren Definition-of-Done-Kriterien gegen Ground Truth
(gebauter Vault, Reports, Repo) und schreibt `docs/DOD_CHECK.md` mit
✅ / ⚠️ / offen pro Kriterium. Nicht-automatisierbare Kriterien werden als
Status gemeldet, nicht bewertet.

Aufruf:
  python3 scripts/dod_check.py            # prüfen + DOD_CHECK.md schreiben
  python3 scripts/dod_check.py --no-subprocess   # ohne pytest/sample-Shellout

Exit-Code: 0 immer (Report ist das Ergebnis, kein harter Fail).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.config import load_config  # noqa: E402
from pipeline.phase_9_vault_build import _INDEX_EXCLUDED_FOLDERS, _build_plan  # noqa: E402
from pipeline.schemas import FrontmatterDraft  # noqa: E402

OK = "✅"
WARN = "⚠️"
OPEN = "offen"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        return ""


def check_vault(vault: Path, drafts: Path) -> list[tuple[str, str, str]]:
    """Vault-bezogene Checks via Build-Plan (Ground Truth der 180 Artikel)."""
    rows: list[tuple[str, str, str]] = []
    plan = _build_plan(drafts)
    expected = [(a.folder, a.final_slug) for a in plan.articles]
    paths = [vault / f / f"{s}.md" for f, s in expected]
    present = [p for p in paths if p.exists()]

    # 1. strukturierter Vault vorhanden
    folders = {a.folder for a in plan.articles}
    rows.append(
        (
            "`output/` strukturierter Vault (Ordner + Files)",
            OK if present and folders else OPEN,
            f"{len(present)} Artikel in {len(folders)} Ordnern",
        )
    )

    # 2. valides Frontmatter (Pydantic) über alle 180 Build-Artikel
    fm_fails = []
    for p in present:
        text = p.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        try:
            FrontmatterDraft.model_validate(yaml.safe_load(parts[1]))
        except Exception as exc:
            fm_fails.append(f"{p.name}: {str(exc)[:40]}")
    rows.append(
        (
            "jede Vault-Artikel-`.md` valides Frontmatter (Pydantic)",
            OK if not fm_fails else WARN,
            f"{len(present)} geprüft, {len(fm_fails)} Fails"
            + (f" ({fm_fails[:3]})" if fm_fails else ""),
        )
    )

    # 3. keine SHA-256-Duplikate
    hashes = [_sha(p) for p in present]
    dups = [h for h, n in Counter(hashes).items() if n > 1]
    rows.append(
        ("keine SHA-256-Duplikate im Vault", OK if not dups else WARN, f"{len(dups)} Doppel")
    )

    # 4. genutzte Cluster < 3 Artikel (Ausnahmen auflisten, kein Fail)
    counts = Counter(a.folder for a in plan.articles)
    small = {f: n for f, n in counts.items() if n < 3}
    rows.append(
        (
            "genutzte Cluster ≥ 3 Artikel (Ausnahmen dokumentiert)",
            WARN if small else OK,
            f"kleine Ordner (dokumentierte Ausnahme): {small}" if small else "alle ≥ 3",
        )
    )

    # 5. _index.md pro genutztem Cluster (außer ausgeschlossene)
    indexed_expected = {f for f in folders if f not in _INDEX_EXCLUDED_FOLDERS}
    indexed_present = {f for f in indexed_expected if (vault / f / "_index.md").exists()}
    missing_idx = indexed_expected - indexed_present
    rows.append(
        (
            f"`_index.md` pro genutztem Cluster (außer {sorted(_INDEX_EXCLUDED_FOLDERS)})",
            OK if not missing_idx else WARN,
            f"{len(indexed_present)}/{len(indexed_expected)} vorhanden"
            + (f", fehlt: {sorted(missing_idx)}" if missing_idx else ""),
        )
    )
    return rows


def check_reports(out_dir: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    names = ["corpus_report.md", "duplicate_report.md", "cluster_report.md"]
    present = [n for n in names if (out_dir / n).exists()]
    rows.append(("3x `*_report.md` vorhanden", OK if len(present) == 3 else OPEN, f"{present}"))
    return rows


def check_subprocess(out_dir: Path) -> list[tuple[str, str, str]]:
    """Idempotenz (Reports 2x), pytest, Sample-Smoke, Prompts-Tracking."""
    rows: list[tuple[str, str, str]] = []

    before = {p.name: _sha(p) for p in out_dir.glob("*_report.md")}
    subprocess.run(
        [sys.executable, "-m", "pipeline", "reports", "--force"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    after = {p.name: _sha(p) for p in out_dir.glob("*_report.md")}
    rows.append(
        (
            "Reports idempotent (2x -> identisch)",
            OK if before == after and before else WARN,
            "byte-identisch" if before == after else "Abweichung",
        )
    )

    sample = subprocess.run(
        [sys.executable, "-m", "pipeline", "run", "--sample", "10", "--dry-run"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    rows.append(
        (
            "`--sample 10` läuft (Dry-Run-Smoke)",
            OK if sample.returncode == 0 else WARN,
            "dry-run rc=0; volle Kette braucht LM-Studio (Phase 8)"
            if sample.returncode == 0
            else f"rc={sample.returncode}",
        )
    )

    tracked = _git("ls-files", "prompts/v1")
    n_tracked = len([ln for ln in tracked.splitlines() if ln.strip()])
    rows.append(
        (
            "Prompts in `prompts/v1/` git-getrackt",
            OK if n_tracked > 0 else OPEN,
            f"{n_tracked} Dateien getrackt",
        )
    )

    pytest_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    last_line = pytest_run.stdout.strip().splitlines()[-1] if pytest_run.stdout.strip() else ""
    rows.append(
        (
            "pytest grün",
            OK if pytest_run.returncode == 0 else WARN,
            last_line[:60],
        )
    )
    return rows


def check_manual() -> list[tuple[str, str, str]]:
    """Nicht autonom erfüllbare Kriterien — nur Status melden."""
    learnings = sorted((REPO / "docs" / "learnings").glob("PHASE_*.md"))
    phases = {p.name.split("_")[1] for p in learnings}
    expected = {f"{i:02d}" for i in range(11)}
    missing = sorted(expected - phases)
    return [
        ("Backup: 2. Medium + Recovery-Drill", OPEN, "Backlog (nicht autonom prüfbar)"),
        ("alle Vault-Files ≥ Qualitätsstufe 2", OPEN, "menschliche Bewertung (Review-Gate 3)"),
        (
            "Reflexions-Doku pro Phase (`docs/learnings/`)",
            OK if not missing else WARN,
            f"{len(phases & expected)}/11 Phasen" + (f", fehlt: {missing}" if missing else ""),
        ),
    ]


def render(auto: list[tuple[str, str, str]], manual: list[tuple[str, str, str]]) -> str:
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    commit = _git("rev-parse", "--short", "HEAD")
    n_ok = sum(1 for _, s, _ in auto if s == OK)
    n_warn = sum(1 for _, s, _ in auto if s == WARN)
    n_open = sum(1 for _, s, _ in auto if s == OPEN)

    def block(rows: list[tuple[str, str, str]]) -> str:
        return "\n".join(f"| {k} | {s} | {d} |" for k, s, d in rows)

    return f"""---
title: DoD-Gesamtcheck Phase 10
slug: dod-check
type: report
status: stable
generated: {now}
commit: {commit}
---

# DoD-Gesamtcheck (`docs/01_strategy.md` §3)

Automatisch geprüft via `scripts/dod_check.py`. Zähl-Werte aus Ground Truth
(gebauter Vault, Reports, Repo), nicht aus anderen Reports.

**Automatisch: {n_ok} {OK} · {n_warn} {WARN} · {n_open} {OPEN}**

## Automatisch prüfbar
| Kriterium | Status | Detail |
|---|:---:|---|
{block(auto)}

## Nur Status (nicht autonom erfüllbar)
| Kriterium | Status | Detail |
|---|:---:|---|
{block(manual)}

> {WARN} bei „kleine Ordner" und „Frontmatter-Fails" sind dokumentierte
> Option-B-/Sonderfälle, kein harter Fail (s. Detail-Spalte).
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--no-subprocess", action="store_true", help="ohne pytest/sample/reports-Shellout"
    )
    ap.add_argument("--config", default="pipeline/pipeline.config.yaml")
    args = ap.parse_args()

    cfg = load_config(REPO / args.config)
    auto = check_vault(cfg.paths.vault, cfg.paths.drafts)
    auto += check_reports(cfg.paths.pipeline_output)
    if not args.no_subprocess:
        auto += check_subprocess(cfg.paths.pipeline_output)
    manual = check_manual()

    out = REPO / "docs" / "DOD_CHECK.md"
    out.write_text(render(auto, manual), encoding="utf-8")
    print(f"DOD_CHECK.md geschrieben: {out}")
    for k, s, d in auto + manual:
        print(f"  {s:>3} {k} — {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
