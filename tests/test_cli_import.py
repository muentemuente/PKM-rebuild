"""Regressionstest für H2/R-1: die ``pkm``-CLI darf ohne ``mdformat`` im
Environment importieren und laufen.

Hintergrund: ``mdformat`` ist bewusst nicht als harte Dependency gesetzt
(Wikilink-Schaden, ratifiziert abgelehnt). Ein Top-Level-Import in
``pipeline.format_vault`` würde jeden ``pkm …``-Aufruf über alle Subcommands
mit ``ModuleNotFoundError`` crashen. Der Import ist lazy (innerhalb
``format_markdown``); diese Tests fixieren das gegen Regression.
"""

from __future__ import annotations

import builtins
import importlib

import pytest
from click.testing import CliRunner


def test_cli_help_runs_without_mdformat(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pkm --help` läuft, auch wenn ``import mdformat`` hart fehlschlägt."""
    real_import = builtins.__import__

    def _no_mdformat(name: str, *args: object, **kwargs: object) -> object:
        if name == "mdformat" or name.startswith("mdformat."):
            raise ImportError("mdformat blocked for test")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _no_mdformat)

    # Frisch importieren, damit ein etwaiger Top-Level-mdformat-Import triggern würde.
    import pipeline.__main__ as main
    import pipeline.format_vault as fv

    importlib.reload(fv)
    importlib.reload(main)

    res = CliRunner().invoke(main.cli, ["--help"])
    assert res.exit_code == 0, res.output
    # Alle Subcommands sind sichtbar (kein Import-Crash beim Modul-Load).
    for cmd in ("quality-score", "vault-audit", "format-vault"):
        assert cmd in res.output


def test_format_markdown_raises_clear_error_without_mdformat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Der tatsächliche Format-Pfad meldet den fehlenden ``mdformat`` klar,
    statt mit rohem ImportError zu sterben."""
    from pipeline import format_vault as fv

    real_import = builtins.__import__

    def _no_mdformat(name: str, *args: object, **kwargs: object) -> object:
        if name == "mdformat" or name.startswith("mdformat."):
            raise ImportError("mdformat blocked for test")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _no_mdformat)

    with pytest.raises(RuntimeError, match="mdformat ist nicht installiert"):
        fv.format_markdown("# Titel\n\nText.\n")
