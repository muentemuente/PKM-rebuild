"""Tests für die CLI-Exposure von ``apply_to_vault`` (``pkm vault-apply``).

Alle Tests laufen auf ``tmp_path``-Test-Vaults mit explizitem ``--vault-dir`` /
``--backup-dir`` — der Live-BRAIN_VAULT wird **nie** berührt. Default-Pfade aus
``_paths`` werden in keinem Test ausgelöst (immer überschrieben).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner
from pipeline import transforms as tf
from pipeline.__main__ import cli

# Frontmatter + Body mit Safe-Tier-Defekt (entboldbar) + nicht-kanonischen Bullets.
_FM = "---\ntitle: Test\nslug: test\n---\n\n"
_BODY = "## **Wichtig**\n\n*  eins\n*  zwei\n"


def _make_vault(root: Path, n: int = 2) -> Path:
    vault = root / "vault"
    (vault / "01_Grundlagen").mkdir(parents=True)
    for i in range(n):
        (vault / "01_Grundlagen" / f"art{i}.md").write_text(_FM + _BODY, encoding="utf-8")
    return vault


def _snapshot(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def _backup_present(root: Path) -> Path:
    """Legt ein nicht-leeres O4-Backup-Verzeichnis an (Präsenz-Check besteht)."""
    b = root / "backups"
    b.mkdir()
    (b / "vault_20260101.tar").write_text("x", encoding="utf-8")
    return b


# === dry-run (Default) ========================================================


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    work = tmp_path / "work"
    res = CliRunner().invoke(
        cli, ["vault-apply", "--vault-dir", str(vault), "--work-dir", str(work)]
    )
    assert res.exit_code == 0, res.output
    assert _snapshot(vault) == before  # Byte-Snapshot stabil → kein Write
    assert (work / "apply_diff.diff").is_file()
    assert "Files changed" in res.output


def test_unknown_chain_name_aborts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    res = CliRunner().invoke(
        cli, ["vault-apply", "--vault-dir", str(vault), "--chain", "does-not-exist"]
    )
    assert res.exit_code == 2
    assert _snapshot(vault) == before


# === --execute Owner-Gate =====================================================


def test_execute_without_confirm_aborts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    backups = _backup_present(tmp_path)
    # Kein --confirm, kein Input → click.confirm bricht ab, bevor irgendetwas schreibt.
    res = CliRunner().invoke(
        cli,
        ["vault-apply", "--vault-dir", str(vault), "--backup-dir", str(backups), "--execute"],
    )
    assert res.exit_code != 0
    assert _snapshot(vault) == before


def test_execute_confirm_declined_aborts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    backups = _backup_present(tmp_path)
    res = CliRunner().invoke(
        cli,
        ["vault-apply", "--vault-dir", str(vault), "--backup-dir", str(backups), "--execute"],
        input="n\n",
    )
    assert res.exit_code != 0
    assert _snapshot(vault) == before


def test_execute_missing_backup_aborts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    missing = tmp_path / "no_backups"  # existiert nicht
    res = CliRunner().invoke(
        cli,
        [
            "vault-apply",
            "--vault-dir",
            str(vault),
            "--backup-dir",
            str(missing),
            "--execute",
            "--confirm",
        ],
    )
    assert res.exit_code == 2
    assert "O4-Backup" in res.output
    assert _snapshot(vault) == before  # kein Write trotz --confirm


def test_execute_empty_backup_dir_aborts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    empty = tmp_path / "empty_backups"
    empty.mkdir()  # existiert, aber leer
    res = CliRunner().invoke(
        cli,
        [
            "vault-apply",
            "--vault-dir",
            str(vault),
            "--backup-dir",
            str(empty),
            "--execute",
            "--confirm",
        ],
    )
    assert res.exit_code == 2
    assert _snapshot(vault) == before


# === --execute --confirm: D4-Pfad =============================================


def test_execute_confirm_writes_and_verifies(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    backups = _backup_present(tmp_path)
    res = CliRunner().invoke(
        cli,
        [
            "vault-apply",
            "--vault-dir",
            str(vault),
            "--backup-dir",
            str(backups),
            "--execute",
            "--confirm",
        ],
    )
    assert res.exit_code == 0, res.output
    text = (vault / "01_Grundlagen" / "art0.md").read_text(encoding="utf-8")
    assert "## Wichtig" in text  # repair (entboldet)
    assert "**Wichtig**" not in text
    assert "- eins" in text  # format (kanonische Bullets)
    # Frontmatter byte-stabil:
    assert text.startswith(_FM[: _FM.index("\n---\n") + len("\n---\n")])
    assert "Files written" in res.output


def test_execute_confirm_idempotent(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    backups = _backup_present(tmp_path)
    args = [
        "vault-apply",
        "--vault-dir",
        str(vault),
        "--backup-dir",
        str(backups),
        "--execute",
        "--confirm",
    ]
    first = CliRunner().invoke(cli, args)
    assert first.exit_code == 0, first.output
    after_first = _snapshot(vault)
    second = CliRunner().invoke(cli, args)
    assert second.exit_code == 0, second.output
    assert _snapshot(vault) == after_first  # 2. Lauf mutiert nichts → idempotent


# === tier-Gate über die CLI ===================================================


@pytest.fixture
def review_transform() -> Iterator[str]:
    name = "xcli-review"
    tf.register(
        tf.FunctionTransform(
            name, tf.TIER_REVIEW, True, lambda t: (t + "\nREVIEW\n", ["review-edit"])
        )
    )
    try:
        yield name
    finally:
        tf.unregister(name)


def test_review_chain_not_auto_written(tmp_path: Path, review_transform: str) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(vault)
    backups = _backup_present(tmp_path)
    res = CliRunner().invoke(
        cli,
        [
            "vault-apply",
            "--vault-dir",
            str(vault),
            "--backup-dir",
            str(backups),
            "--chain",
            review_transform,
            "--execute",
            "--confirm",
        ],
    )
    assert res.exit_code == 1
    assert "tier-Gate" in res.output
    assert _snapshot(vault) == before  # review-Transform nie auto-geschrieben
