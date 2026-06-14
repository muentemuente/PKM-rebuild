"""Zentrale Pfad- und Config-Auflösung — Single Source of Truth für ALLE Skripte.

**Alle** Pipeline-Phasen und Standalone-Skripte importieren ihre Pfade von hier,
statt eigene ``DATA_ROOT``-Konstanten zu definieren (löst das duplizierte
Pfad-Backlog aus ``docs/REBUILD_inventory.md``).

Layout (gitignored, außerhalb des Repos)::

    PKM_PIPELINE_ROOT/            (default: ~/projects/aktiv/pkm-pipeline)
    ├── input/                    neue .md (Run-Quelle)
    ├── work/                     ALLE Zwischen-JSONL + state.json + logs
    ├── drafts/                   Qwen-Outputs (body + frontmatter)
    ├── review/                   Gate-Queues
    │   ├── needs_human/          low-confidence / Validierungsfehler
    │   ├── category_open/        unklare/neue Kategorie
    │   ├── tags_open/            Tags außerhalb Vokabular
    │   └── quarantine/           Hangs/Crashes
    ├── output/                   gebauter, getaggter Staging-Vault (Mensch zieht raus)
    └── archive/                  verarbeitete Inputs + alte Runs + Backups

Repo (Git)::

    PKM_REPO_ROOT/                (default: Parent des pipeline/-Pakets)
    └── config/                   categories.yaml, tag_vocabulary.yaml, tag_merge_map.json

Override per Env-Variable: ``PKM_PIPELINE_ROOT`` (Daten), ``PKM_REPO_ROOT`` (Repo).
"""

from __future__ import annotations

import os
from pathlib import Path

# === Basis-Roots ==============================================================

_DEFAULT_PIPELINE_ROOT = Path.home() / "projects" / "aktiv" / "pkm-pipeline"
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent
# Produktiver Obsidian-Vault (#3, außerhalb der Pipeline). Ziel des manuellen
# Asset-Merge (WP3). Überschreibbar per PKM_BRAIN_VAULT.
_DEFAULT_BRAIN_VAULT = Path.home() / "Zentrale" / "09_Brain-Vault"


def _env_path(var: str, default: Path) -> Path:
    """Liest einen Pfad aus der Env-Variable ``var`` (mit ~-Expansion), sonst ``default``."""
    raw = os.environ.get(var)
    return Path(raw).expanduser() if raw else default


PIPELINE_ROOT: Path = _env_path("PKM_PIPELINE_ROOT", _DEFAULT_PIPELINE_ROOT)
REPO_ROOT: Path = _env_path("PKM_REPO_ROOT", _DEFAULT_REPO_ROOT)
BRAIN_VAULT: Path = _env_path("PKM_BRAIN_VAULT", _DEFAULT_BRAIN_VAULT)

# === Arbeits-Ordner (Daten) ===================================================

INPUT: Path = PIPELINE_ROOT / "input"
INPUT_ASSETS: Path = INPUT / "_assets"
INGEST: Path = PIPELINE_ROOT / "_ingest"
INGEST_QUARANTINE: Path = INGEST / "_quarantine"
WORK: Path = PIPELINE_ROOT / "work"
DRAFTS: Path = PIPELINE_ROOT / "drafts"
REVIEW: Path = PIPELINE_ROOT / "review"
OUTPUT: Path = PIPELINE_ROOT / "output"
OUTPUT_ASSETS: Path = OUTPUT / "_assets"
ARCHIVE: Path = PIPELINE_ROOT / "archive"

# Asset-Pool im produktiven Vault (Ziel des add-only Merge, WP3)
BRAIN_VAULT_ASSETS: Path = BRAIN_VAULT / "_assets"

# Review-Queues
REVIEW_NEEDS_HUMAN: Path = REVIEW / "needs_human"
REVIEW_CATEGORY_OPEN: Path = REVIEW / "category_open"
REVIEW_TAGS_OPEN: Path = REVIEW / "tags_open"
REVIEW_QUARANTINE: Path = REVIEW / "quarantine"

# Backups leben unter archive/ (kein eigener Top-Level mehr)
BACKUPS: Path = ARCHIVE / "backups"

# === Config (im Repo) =========================================================

CONFIG: Path = REPO_ROOT / "config"
CATEGORIES_FILE: Path = CONFIG / "categories.yaml"
TAG_VOCABULARY_FILE: Path = CONFIG / "tag_vocabulary.yaml"
TAG_MERGE_MAP_FILE: Path = CONFIG / "tag_merge_map.json"

# === Helfer ===================================================================

_WORK_DIRS = (
    INPUT,
    WORK,
    DRAFTS,
    OUTPUT,
    ARCHIVE,
    REVIEW_NEEDS_HUMAN,
    REVIEW_CATEGORY_OPEN,
    REVIEW_TAGS_OPEN,
    REVIEW_QUARANTINE,
)


def ensure_layout() -> None:
    """Legt alle Arbeits-Ordner an (idempotent). Config-Ordner bleibt unberührt (Git)."""
    for path in _WORK_DIRS:
        path.mkdir(parents=True, exist_ok=True)
