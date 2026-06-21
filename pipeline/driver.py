"""Chain-Driver (S5) + D4-``--apply``-Driver (S6) für den Composability-Kern.

Baut auf dem Transform-Protokoll (S4, :mod:`pipeline.transforms`) auf:

* **S5 — :func:`run_chain`** (non-mutating): wendet eine konfigurierbare Folge von
  Transforms auf einen Body an (Output→Input verkettet, Reports gemerged). Default
  :data:`pipeline.transforms.DEFAULT_CHAIN` (Entscheidung 2A).
* **S6 — :func:`apply_to_vault`** (mutating-fähig, Entscheidung 1A): wendet eine Chain
  auf alle Content-Files eines Vault-Verzeichnisses an. **Default = dry-run** (Diff +
  Audit-Vorschau, **kein** Write). Erst ``execute=True`` schreibt — und nur mit
  vollständigem **D4**: auto-Snapshot → Canary (1 Write + Verify) → bei grün Mass-Write
  → Verify (Audit-Pass). **tier-Gate:** nur safe-Transforms sind auto-write-fähig;
  enthält die Chain einen review/audit-mutierenden Transform, wird **nicht** geschrieben
  (nur Diff). Rollback über :func:`restore_snapshot`.

Frontmatter bleibt **byte-stabil**: Transforms wirken nur auf den Body; der
Frontmatter-Block (inkl. Delimiter) wird unverändert vorangestellt.
"""

from __future__ import annotations

import difflib
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

from pipeline.transforms import (
    DEFAULT_CHAIN,
    TIER_SAFE,
    TransformResult,
    get,
)
from pipeline.vault_audit import audit_build_output, is_content_md, split_frontmatter

log = structlog.get_logger()


# === S5: Chain-Driver (non-mutating) ==========================================


@dataclass(frozen=True)
class ChainResult:
    """Ergebnis einer Transform-Chain auf einem Body.

    Args:
        text: Resultierender Body (verkettetes Ergebnis aller Transforms).
        changed: ``True`` wenn ``text`` vom Input abweicht.
        report: Gemergte Aktions-/Befund-Zeilen, je mit ``"<transform>: "`` prefixt.
        per_transform: Detail je Schritt ``(name, TransformResult)`` in Chain-Reihenfolge.
    """

    text: str
    changed: bool
    report: list[str]
    per_transform: list[tuple[str, TransformResult]]


def run_chain(text: str, chain: Sequence[str] = DEFAULT_CHAIN) -> ChainResult:
    """Wendet die Transforms ``chain`` der Reihe nach auf ``text`` an (Output→Input).

    Rein funktional (text → text), **kein** IO. ``audit``-Transforms in der Chain lassen
    den Text unverändert und tragen nur zum Report bei (read-only).

    Args:
        text: Eingangs-Body.
        chain: Transform-Namen in Anwendungs-Reihenfolge (Default 2A).

    Returns:
        :class:`ChainResult`.
    """
    body = text
    report: list[str] = []
    detail: list[tuple[str, TransformResult]] = []
    for name in chain:
        res = get(name).apply(body)
        body = res.text
        report.extend(f"{name}: {line}" for line in res.report)
        detail.append((name, res))
    return ChainResult(text=body, changed=body != text, report=report, per_transform=detail)


# === S6: D4-``--apply``-Driver ================================================


@dataclass(frozen=True)
class FilePlan:
    """Plan für eine einzelne Datei (Diff-Vorschau + Ziel-Inhalt)."""

    relpath: str
    changed: bool
    new_text: str
    diff: str
    report: list[str]


@dataclass
class ApplyReport:
    """Ergebnis/Plan eines :func:`apply_to_vault`-Laufs."""

    target: Path
    chain: tuple[str, ...]
    executed: bool = False
    writable: bool = True
    reason: str = ""
    files_total: int = 0
    files_changed: int = 0
    files_written: int = 0
    snapshot: Path | None = None
    canary: str | None = None
    canary_ok: bool | None = None
    audit_counts: dict[str, int] | None = None
    rolled_back: bool = False
    plans: list[FilePlan] = field(default_factory=list)


def _split_for_body(text: str) -> tuple[str, str]:
    """Trennt ``(frontmatter_prefix, body)`` byte-exakt.

    ``frontmatter_prefix`` enthält den kompletten Frontmatter-Block inkl. Delimitern
    **und der Leerzeilen-Trennung** zum Body (oder ``""`` ohne Frontmatter). ``prefix +
    body == text`` gilt byte-genau, sodass Frontmatter und Separator unverändert bleiben.

    Die Separator-Leerzeile gehört in den Prefix, damit ein Format-Transform sie nicht
    als führende Body-Leerzeile strippt (sonst würde jeder Build-konforme File
    `---\\n…---\\n\\n<body>` beim Apply churnen — idempotenz-brechend).
    """
    fm, body, _line = split_frontmatter(text)
    if fm is None:
        return "", text
    prefix = text[: len(text) - len(body)]
    stripped = body.lstrip("\n")
    prefix += body[: len(body) - len(stripped)]
    return prefix, stripped


def _apply_chain_to_file(text: str, chain: Sequence[str]) -> tuple[str, bool, list[str]]:
    """Wendet die Chain auf den **Body** an, Frontmatter bleibt byte-stabil."""
    prefix, body = _split_for_body(text)
    res = run_chain(body, chain)
    new_text = prefix + res.text
    return new_text, new_text != text, res.report


def _file_diff(relpath: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
        )
    )


def _content_files(target: Path) -> list[Path]:
    return sorted(p for p in target.rglob("*.md") if is_content_md(p, target))


def plan_vault(target: Path, chain: Sequence[str]) -> list[FilePlan]:
    """Berechnet den Datei-Plan (read-only): pro Content-File Diff + Ziel-Inhalt."""
    plans: list[FilePlan] = []
    for p in _content_files(target):
        rel = str(p.relative_to(target))
        text = p.read_text(encoding="utf-8")
        new_text, changed, report = _apply_chain_to_file(text, chain)
        diff = _file_diff(rel, text, new_text) if changed else ""
        plans.append(FilePlan(rel, changed, new_text, diff, report))
    return plans


def _chain_writable(chain: Sequence[str]) -> tuple[bool, str]:
    """tier-Gate: nur safe-Transforms dürfen auto-schreiben.

    review/audit-mutierende Transforms (tier != safe) blockieren den auto-Write — sie
    werden im dry-run als Diff ausgewiesen, aber nie automatisch angewandt.
    """
    for name in chain:
        t = get(name)
        if t.mutating and t.tier != TIER_SAFE:
            return False, f"Transform '{name}' (tier={t.tier}) ist nicht safe-auto-anwendbar"
    return True, ""


def snapshot_vault(target: Path, backups_dir: Path | None = None) -> Path:
    """D4-Snapshot: vollständige Kopie von ``target`` in ein Zeitstempel-Verzeichnis.

    Default-Ziel liegt **außerhalb** von ``target`` (``<target>.parent/_apply_backups``),
    damit der Snapshot nicht rekursiv sich selbst erfasst.
    """
    base = backups_dir if backups_dir is not None else (target.parent / "_apply_backups")
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S_%f")
    snap = base / f"apply_{target.name}_{ts}"
    shutil.copytree(target, snap)
    log.info("apply_snapshot_created", target=str(target), snapshot=str(snap))
    return snap


def restore_snapshot(snapshot: Path, target: Path) -> None:
    """Rollback: ersetzt ``target`` vollständig durch den ``snapshot``-Stand."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(snapshot, target)
    log.info("apply_rolled_back", target=str(target), snapshot=str(snapshot))


def _write_plan(target: Path, plan: FilePlan) -> None:
    (target / plan.relpath).write_text(plan.new_text, encoding="utf-8")


def _verify_idempotent(target: Path, relpath: str, chain: Sequence[str]) -> bool:
    """Canary-Verify: nach dem Write muss ein erneuter Chain-Lauf stabil sein (idempotent)."""
    text = (target / relpath).read_text(encoding="utf-8")
    _new, changed, _report = _apply_chain_to_file(text, chain)
    return not changed


def _execute_d4(
    target: Path,
    changed: list[FilePlan],
    chain: Sequence[str],
    backups_dir: Path | None,
    report: ApplyReport,
) -> ApplyReport:
    """D4-Mutation: Snapshot → Canary (1 Write + Verify) → Mass-Write → Verify (Audit)."""
    report.snapshot = snapshot_vault(target, backups_dir)

    # Canary: erste geänderte Datei schreiben + idempotent verifizieren.
    canary = changed[0]
    _write_plan(target, canary)
    report.canary = canary.relpath
    report.canary_ok = _verify_idempotent(target, canary.relpath, chain)
    if not report.canary_ok:
        report.reason = "canary-verify rot → Mass-Write gestoppt; Rollback via restore_snapshot()"
        report.files_written = 1
        log.warning("apply_canary_failed", file=canary.relpath, snapshot=str(report.snapshot))
        return report

    # Mass-Write der restlichen Änderungen.
    for plan in changed[1:]:
        _write_plan(target, plan)
    report.files_written = len(changed)
    report.executed = True

    # Verify: Audit-Pass über den frisch geschriebenen Vault.
    report.audit_counts = audit_build_output(target)
    log.info(
        "apply_executed",
        target=str(target),
        files_written=report.files_written,
        audit=report.audit_counts,
    )
    return report


def apply_to_vault(
    target_dir: Path | str,
    chain: Sequence[str] = DEFAULT_CHAIN,
    *,
    execute: bool = False,
    backups_dir: Path | None = None,
) -> ApplyReport:
    """Wendet ``chain`` auf alle Content-Files von ``target_dir`` an (S6, D4).

    **Default ``execute=False`` (dry-run):** berechnet Diffs + Audit-Vorschau, schreibt
    **nichts**. ``execute=True`` löst die D4-Mutation aus (Snapshot → Canary → Mass-Write
    → Verify) — aber nur, wenn die Chain auto-write-fähig ist (tier-Gate: alle mutierenden
    Transforms ``safe``). Sonst bleibt es beim Diff (``writable=False``, kein Write).

    Args:
        target_dir: Vault-Verzeichnis (im Bau-/Test-Kontext: Test-Vault/``tmp_path``).
        chain: Transform-Namen in Reihenfolge (Default 2A).
        execute: ``True`` = echte Mutation mit D4. ``False`` (Default) = dry-run.
        backups_dir: Ziel für den D4-Snapshot (Default ``<target>.parent/_apply_backups``).

    Returns:
        :class:`ApplyReport`.
    """
    target = Path(target_dir)
    plans = plan_vault(target, chain)
    changed = [p for p in plans if p.changed]
    writable, reason = _chain_writable(chain)
    report = ApplyReport(
        target=target,
        chain=tuple(chain),
        writable=writable,
        reason=reason,
        files_total=len(plans),
        files_changed=len(changed),
        plans=plans,
    )

    # dry-run ODER nicht auto-write-fähig → kein Write, nur Audit-Vorschau.
    if not execute or not writable:
        if execute and not writable:
            report.reason = reason or "Chain nicht auto-write-fähig → kein Write (nur Diff)"
        report.audit_counts = audit_build_output(target)
        return report

    # execute + writable, aber keine Änderung → No-op-Erfolg.
    if not changed:
        report.executed = True
        report.audit_counts = audit_build_output(target)
        return report

    return _execute_d4(target, changed, chain, backups_dir, report)
