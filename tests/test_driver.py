"""Tests für den Chain-Driver (S5) + D4-``--apply``-Driver (S6).

Alle Tests laufen auf ``tmp_path`` / Test-Vault — der Live-BRAIN_VAULT wird nie berührt.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pipeline import transforms as tf
from pipeline.driver import (
    apply_to_vault,
    restore_snapshot,
    run_chain,
)
from pipeline.format_vault import format_body_safe
from pipeline.vault_audit import repair_text

# Body mit Safe-Tier-Defekt (entboldbar) + nicht-kanonischen Bullets (format).
_BODY = "## **Wichtig**\n\n*  eins\n*  zwei\n"
_FM = "---\ntitle: Test\nslug: test\n---\n\n"


def _snapshot(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def _make_vault(root: Path, n: int = 2) -> Path:
    """Legt einen Test-Vault mit n Content-Files (Frontmatter + Defekt-Body) an."""
    vault = root / "vault"
    (vault / "01_Grundlagen").mkdir(parents=True)
    for i in range(n):
        (vault / "01_Grundlagen" / f"art{i}.md").write_text(_FM + _BODY, encoding="utf-8")
    return vault


# === S5: run_chain ============================================================


def test_run_chain_equals_manual_composition() -> None:
    res = run_chain(_BODY)  # Default-Chain repair → format
    manual = repair_text(_BODY)[0]
    manual = format_body_safe(manual)[0]
    assert res.text == manual
    assert res.changed is True


def test_run_chain_custom_order() -> None:
    res = run_chain(_BODY, chain=("format-safe", "repair-safe"))
    manual = format_body_safe(_BODY)[0]
    manual = repair_text(manual)[0]
    assert res.text == manual


def test_run_chain_idempotent() -> None:
    once = run_chain(_BODY).text
    twice = run_chain(once).text
    assert twice == once


def test_run_chain_audit_is_readonly() -> None:
    res = run_chain(_BODY, chain=("audit-readonly",))
    assert res.text == _BODY  # audit verändert nichts
    assert res.changed is False
    assert res.report  # meldet aber Befunde (Heading-bold etc.)


def test_run_chain_reports_are_prefixed() -> None:
    res = run_chain(_BODY)
    assert all(":" in line for line in res.report)
    assert any(line.startswith("repair-safe:") for line in res.report)


# === S6: apply_to_vault — dry-run (Default) ===================================


def test_apply_dry_run_writes_nothing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    report = apply_to_vault(vault)  # execute=False default
    after = _snapshot(vault)
    assert before == after  # kein Write
    assert report.executed is False
    assert report.files_changed == 2
    assert report.snapshot is None
    assert all(p.diff for p in report.plans if p.changed)


# === S6: apply_to_vault — execute (D4) ========================================


def test_apply_execute_writes_and_verifies(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    report = apply_to_vault(vault, execute=True)
    assert report.executed is True
    assert report.files_written == 2
    assert report.canary is not None
    assert report.canary_ok is True
    # Snapshot wurde angelegt:
    assert report.snapshot is not None
    assert report.snapshot.is_dir()
    # Body repariert (entboldet) + formatiert (Bullets):
    text = (vault / "01_Grundlagen" / "art0.md").read_text(encoding="utf-8")
    assert "## Wichtig" in text
    assert "**Wichtig**" not in text
    assert "- eins" in text
    # Verify-Audit sauber (0 Safe-Tier-Rest):
    assert report.audit_counts is not None
    assert report.audit_counts["safe_tier_rest"] == 0


def test_apply_execute_preserves_frontmatter_bytes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, n=1)
    apply_to_vault(vault, execute=True)
    text = (vault / "01_Grundlagen" / "art0.md").read_text(encoding="utf-8")
    fm_block = text.split("\n---\n", 1)[0] + "\n---\n"
    assert fm_block == "---\ntitle: Test\nslug: test\n---\n"  # byte-stabil


def test_apply_execute_idempotent(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    apply_to_vault(vault, execute=True)
    # 2. Lauf als dry-run: nichts mehr zu ändern.
    second = apply_to_vault(vault)
    assert second.files_changed == 0


def test_apply_execute_clean_vault_noop(tmp_path: Path) -> None:
    """Bereits sauberer Vault → execute schreibt nichts, executed True."""
    vault = tmp_path / "clean"
    (vault / "01_Grundlagen").mkdir(parents=True)
    (vault / "01_Grundlagen" / "ok.md").write_text(
        _FM + "## Wichtig\n\n- eins\n- zwei\n", encoding="utf-8"
    )
    before = _snapshot(vault)
    report = apply_to_vault(vault, execute=True)
    assert report.executed is True
    assert report.files_changed == 0
    assert _snapshot(vault) == before


# === S6: tier-Gate (review nie auto-write) ====================================


@pytest.fixture
def review_transform() -> Iterator[str]:
    """Registriert temporär einen mutierenden review-Transform, räumt danach auf."""
    name = "xtest-review"
    tf.register(
        tf.FunctionTransform(
            name, tf.TIER_REVIEW, True, lambda t: (t + "\nREVIEW\n", ["review-edit"])
        )
    )
    try:
        yield name
    finally:
        tf.unregister(name)


def test_review_transform_not_auto_applied(tmp_path: Path, review_transform: str) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    report = apply_to_vault(vault, chain=(review_transform,), execute=True)
    assert report.writable is False
    assert report.executed is False
    assert report.files_written == 0
    assert _snapshot(vault) == before  # tier-Gate: kein Write
    assert report.reason


# === S6: Rollback =============================================================


def test_restore_snapshot_rolls_back(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, n=1)
    report = apply_to_vault(vault, execute=True)
    assert report.snapshot is not None
    changed_text = (vault / "01_Grundlagen" / "art0.md").read_text(encoding="utf-8")
    assert "**Wichtig**" not in changed_text  # wurde verändert
    # Rollback:
    restore_snapshot(report.snapshot, vault)
    restored = (vault / "01_Grundlagen" / "art0.md").read_text(encoding="utf-8")
    assert restored == _FM + _BODY  # Originalzustand wiederhergestellt
