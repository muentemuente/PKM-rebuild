"""Regeneriert per-Ordner ``_index.md`` im Live-Vault (``BRAIN_VAULT``).

Ersatz für das deprecatete ``scripts/rebuild_indices.py`` (D-WP4-2). Nutzt den
phase_9-Generator (:func:`pipeline.phase_9_vault_build._render_index`) → das Format
ist byte-identisch zum Build und idempotent (kein Wall-Clock im Body).

Semantik bewusst konservativ: es werden **nur bereits existierende** Indizes
aufgefrischt — kein neuer ``_index.md`` in Schutzbereichen (``_attic``,
``15_Gedanken``) oder in ``00_Meta``. Bei Änderung wird archive-before gesichert.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pipeline.phase_9_vault_build import (
    _INDEX_EXCLUDED_FOLDERS,
    _Article,
    _render_index,
)

_FM = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)

# Schutzbereiche ohne Auto-Index (zusätzlich zu ``00_Meta`` aus phase_9).
PROTECTED_FOLDERS: frozenset[str] = frozenset({"_attic", "15_Gedanken"})


@dataclass
class IndexChange:
    """Ergebnis-Record pro Ordner."""

    folder: str
    status: str  # "unchanged" | "regenerated"
    article_count: int


def _read_frontmatter(path: Path) -> dict[str, Any]:
    """Liest das YAML-Frontmatter einer Markdown-Datei (leeres dict ohne/bei Fehler)."""
    m = _FM.match(path.read_text(encoding="utf-8"))
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def collect_articles(vault_dir: Path) -> dict[str, list[_Article]]:
    """Gruppiert alle Vault-Artikel (ohne ``_index.md``) nach Top-Level-Ordner."""
    by_folder: dict[str, list[_Article]] = {}
    for p in sorted(vault_dir.rglob("*.md")):
        if p.name == "_index.md":
            continue
        folder = p.relative_to(vault_dir).parts[0]
        data = _read_frontmatter(p)
        art = _Article(
            stem=p.stem,
            data=data,
            body="",
            folder=folder,
            final_slug=str(data.get("slug", p.stem)),
        )
        by_folder.setdefault(folder, []).append(art)
    return by_folder


def regenerate_indices(
    vault_dir: Path,
    *,
    dry_run: bool = True,
    archive_root: Path | None = None,
) -> list[IndexChange]:
    """Regeneriert existierende ``_index.md`` aus dem aktuellen Vault-Stand.

    Args:
        vault_dir: Wurzel des Vaults (z. B. ``BRAIN_VAULT``).
        dry_run: Wenn ``True`` wird nichts geschrieben, nur die Änderungen ermittelt.
        archive_root: Ziel für archive-before-Kopien (nur bei ``dry_run=False``).

    Returns:
        Liste von :class:`IndexChange` für jeden Ordner mit existierendem Index.
    """
    excluded = set(_INDEX_EXCLUDED_FOLDERS) | PROTECTED_FOLDERS
    changes: list[IndexChange] = []
    by_folder = collect_articles(vault_dir)
    for folder in sorted(by_folder):
        if folder in excluded:
            continue
        idx_path = vault_dir / folder / "_index.md"
        if not idx_path.exists():
            # Nur existierende Indizes auffrischen, keine neuen anlegen.
            continue
        content = _render_index(folder, by_folder[folder])
        count = len(by_folder[folder])
        if idx_path.read_text(encoding="utf-8") == content:
            changes.append(IndexChange(folder, "unchanged", count))
            continue
        if not dry_run:
            if archive_root is not None:
                dest = archive_root / folder / "_index.md"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(idx_path, dest)
            idx_path.write_text(content, encoding="utf-8")
        changes.append(IndexChange(folder, "regenerated", count))
    return changes
