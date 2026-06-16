"""Tests für das passive 17_unsortiert-Surfacing (read-only Count).

Deckt scripts/unsortiert_diagnose.count_unsorted ab — die Zähl-Logik hinter der
build-vault-Schwellwert-Warnung. Kein P4, verschiebt/ändert nichts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import taxonomy
from scripts.unsortiert_diagnose import count_unsorted, unsorted_dir

_FOLDER = taxonomy.CATEGORY_TO_FOLDER["unsortiert"]  # "17_unsortiert"


def _write(p: Path, body: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nslug: {p.stem}\n---\n\n{body}\n", encoding="utf-8")


def test_unsorted_dir_uses_ssot_folder_name(tmp_path: Path) -> None:
    assert unsorted_dir(tmp_path).name == _FOLDER
    assert unsorted_dir(tmp_path) == tmp_path / _FOLDER


def test_count_zero_when_missing(tmp_path: Path) -> None:
    assert count_unsorted(tmp_path) == 0


def test_count_excludes_index_and_counts_articles(tmp_path: Path) -> None:
    folder = tmp_path / _FOLDER
    _write(folder / "a.md")
    _write(folder / "b.md")
    _write(folder / "_index.md")  # zählt NICHT
    assert count_unsorted(tmp_path) == 2


def test_count_only_unsorted_folder(tmp_path: Path) -> None:
    _write(tmp_path / _FOLDER / "a.md")
    _write(tmp_path / "01_Grundlagen" / "other.md")  # anderer Ordner zählt nicht
    assert count_unsorted(tmp_path) == 1
