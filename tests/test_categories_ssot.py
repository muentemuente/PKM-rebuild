"""Lock-in-Tests für G5: ``config/categories.yaml`` ist die alleinige Single Source.

Der SSoT-Kern existiert bereits (``pipeline.taxonomy`` lädt die YAML und leitet
``CATEGORY_TO_FOLDER`` / ``ALLOWED_CATEGORIES`` daraus ab). Diese Tests *verriegeln*
diesen Zustand: sie fangen künftige YAML-Drift gegen den Vault-Standard §4.3 und die
Wiedereinführung eines hartcodierten Code-Literals (das die Single Source aushebeln würde).
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline import taxonomy

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Soll-Liste der 18 kanonischen Kategorien → Vault-Ordner aus docs/03_vault_standard.md
# §4.3 ("Kanonische category-Werte"). Bewusst hier eingefroren (unabhängig von der YAML),
# damit eine YAML-Änderung, die vom dokumentierten Standard abweicht, rot wird.
_VAULT_STANDARD_4_3: dict[str, str] = {
    "meta": "00_Meta",
    "grundlagen": "01_Grundlagen",
    "webentwicklung": "02_Webentwicklung",
    "betriebssysteme": "03_Betriebssysteme",
    "protokolle-und-standards": "04_Protokolle-und-Standards",
    "dateitypen-und-konfiguration": "05_Dateitypen-und-Konfiguration",
    "methoden-und-prozesse": "06_Methoden-und-Prozesse",
    "best-practices": "07_Best-Practices",
    "cheatsheets": "08_Cheatsheets",
    "ki-und-semantische-systeme": "09_KI-und-Semantische-Systeme",
    "datenarchitektur-und-datenbanken": "10_Datenarchitektur-und-Datenbanken",
    "dokumentenverarbeitung-und-extraktion": "11_Dokumentenverarbeitung-und-Extraktion",
    "wissensmodellierung-und-knowledge-graphs": "12_Wissensmodellierung-und-Knowledge-Graphs",
    "visualisierung-reporting-und-design-systeme": "13_Visualisierung-Reporting-und-Design-Systeme",
    "automatisierung-scripting-und-pipelines": "14_Automatisierung-Scripting-und-Pipelines",
    "gedanken": "15_Gedanken",
    "kunst-kultur": "16_Kunst-Kultur",
    "unsortiert": "17_unsortiert",
}


def test_loader_matches_vault_standard() -> None:
    """``load_category_to_folder()`` liefert exakt die §4.3-Soll-Liste (fängt YAML-Drift)."""
    assert taxonomy.load_category_to_folder() == _VAULT_STANDARD_4_3


def test_allowed_categories_derived_from_loader() -> None:
    """``ALLOWED_CATEGORIES`` ist exakt die Key-Menge der geladenen YAML — keine Eigenliste."""
    assert set(taxonomy.load_category_to_folder()) == taxonomy.ALLOWED_CATEGORIES


def test_category_to_folder_is_bijective() -> None:
    """Jede ``category`` → genau ein ``folder`` und kein Ordner wird doppelt belegt."""
    mapping = taxonomy.load_category_to_folder()
    folders = list(mapping.values())
    assert len(folders) == len(set(folders))  # injektiv: keine Ordner-Kollision
    assert len(mapping) == 18


def test_no_hardcoded_category_literal_in_source() -> None:
    """Guard: kein Modul reintroduziert ein literales ``CATEGORY_TO_FOLDER = {…}``.

    Erlaubt bleibt allein das leere Platzhalter-Dict in ``pipeline/taxonomy.py`` (wird per
    ``reload()`` aus der YAML befüllt) und der bewusst eingefrorene
    ``_EXPECTED_CATEGORY_TO_FOLDER``-Snapshot in ``tests/test_config.py`` (anderer Name,
    matcht das Muster ohnehin nicht). Ein populiertes Literal hier wäre eine zweite Quelle.
    """
    # Populiertes Dict-Literal direkt an CATEGORY_TO_FOLDER gebunden (mit String-Key).
    pattern = re.compile(r"CATEGORY_TO_FOLDER\b\s*(?::[^=\n]+)?=\s*\{\s*[\"']")
    offenders: list[str] = []
    for base in ("pipeline", "scripts"):
        for py in (_REPO_ROOT / base).rglob("*.py"):
            if pattern.search(py.read_text(encoding="utf-8")):
                offenders.append(str(py.relative_to(_REPO_ROOT)))
    assert offenders == [], f"hartcodiertes CATEGORY_TO_FOLDER-Literal gefunden: {offenders}"
