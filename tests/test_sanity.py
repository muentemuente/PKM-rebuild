"""Sanity-Tests — prüfen, dass die Test-Infrastruktur läuft."""

import sys
from pathlib import Path


def test_python_version() -> None:
    """Python 3.12 oder höher."""
    assert sys.version_info >= (3, 12), f"Python 3.12+ erwartet, aber {sys.version_info}"


def test_repo_structure_exists() -> None:
    """Wichtige Repo-Verzeichnisse existieren."""
    repo_root = Path(__file__).parent.parent
    expected = ["docs", "pipeline", "prompts", "tests"]
    for folder in expected:
        path = repo_root / folder
        assert path.is_dir(), f"Erwartetes Verzeichnis fehlt: {path}"


def test_doku_files_exist() -> None:
    """Pflicht-Dokumentation ist vorhanden."""
    repo_root = Path(__file__).parent.parent
    expected_docs = [
        "docs/01_strategy.md",
        "docs/02_pipeline_spec.md",
        "docs/03_vault_standard.md",
        "docs/04_qwen_prompts.md",
        "docs/05_glossary.md",
        "docs/06_claude_code_workflow.md",
        "docs/07_backup_strategy.md",
    ]
    for doc in expected_docs:
        path = repo_root / doc
        assert path.is_file(), f"Pflicht-Dokumentation fehlt: {path}"


def test_claude_md_files_exist() -> None:
    """Alle drei CLAUDE.md-Files sind vorhanden."""
    repo_root = Path(__file__).parent.parent
    expected_claude_md = [
        "CLAUDE.md",
        "pipeline/CLAUDE.md",
        "prompts/CLAUDE.md",
    ]
    for claude_file in expected_claude_md:
        path = repo_root / claude_file
        assert path.is_file(), f"CLAUDE.md fehlt: {path}"


def test_pipeline_config_exists() -> None:
    """pipeline.config.yaml ist vorhanden."""
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "pipeline" / "pipeline.config.yaml"
    assert config_path.is_file(), "pipeline/pipeline.config.yaml fehlt"
