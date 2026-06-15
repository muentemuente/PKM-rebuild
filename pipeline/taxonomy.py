"""Taxonomie-Facade — die *einzige* Import-Quelle für das kontrollierte Vokabular.

Bündelt die drei deklarativen Single-Source-Dateien unter ``config/`` zu einer
einheitlichen Loader-Facade. Alle Konsumenten (``pipeline.schemas``,
``scripts/_pkm_common``, ``pipeline.phase_9_vault_build`` u. a.) importieren
Kategorien, Ordner-Mapping, Tags, Synonyme und Wert-Enums **ausschließlich von
hier** — kein Modul definiert ein Enum selbst (0 Dup-Enum, Drift strukturell
ausgeschlossen).

Physische Quellen (bleiben bestehen, werden von ``manage_vocab`` / Gate B/C gepflegt):

* ``config/categories.yaml``     — ``category`` → ``NN_Ordnername``
* ``config/tag_vocabulary.yaml``  — kanonische Tags (Sektionen) + Synonym-Map
* ``config/enums.yaml``           — ``type``/``status``/``review_status``/
  ``confidence``/``doc_role`` (governed growth)

Die Modul-Konstanten werden beim Import einmal geladen. Nach einer Mutation der
YAML-Dateien (CLI ``pkm taxonomy``, Migrationen, Tests) ruft man :func:`reload`,
um sie neu einzulesen.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline import _paths
from pipeline.vocab import load_tag_vocabulary_yaml

# === Loader (reine Funktionen, Pfad-parametrisiert für Tests) =================


def load_category_to_folder(path: Path | None = None) -> dict[str, str]:
    """Lädt das ``category`` → Vault-Ordner-Mapping aus ``config/categories.yaml``."""
    path = path or _paths.CATEGORIES_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(data.get("categories") or {})


def load_enums(path: Path | None = None) -> dict[str, set[str]]:
    """Lädt die Wert-Enums aus ``config/enums.yaml`` als ``{feld: {werte}}``."""
    path = path or _paths.ENUMS_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {key: set(values or []) for key, values in data.items()}


def load_tags(path: Path | None = None) -> tuple[set[str], dict[str, str | None]]:
    """Lädt ``(kanonische Tags, Synonym-Map)`` aus ``config/tag_vocabulary.yaml``."""
    path = path or _paths.TAG_VOCABULARY_FILE
    return load_tag_vocabulary_yaml(path)


# === Modul-Konstanten (beim Import geladen; via reload() aktualisierbar) =======

CATEGORY_TO_FOLDER: dict[str, str]
ALLOWED_CATEGORIES: set[str]
ALLOWED_TAGS: set[str]
TAG_SYNONYMS: dict[str, str | None]
ALLOWED_TYPE: set[str]
ALLOWED_STATUS: set[str]
ALLOWED_REVIEW: set[str]
ALLOWED_CONFIDENCE: set[str]
ALLOWED_DOC_ROLE: set[str]

# Feldname → Live-Enum-Lookup, von schemas.FrontmatterDraft genutzt. Wird in
# reload() neu verdrahtet, damit der Pydantic-Validator nach einer Vokabular-
# Erweiterung den aktuellen Stand sieht.
_FIELD_ENUMS: dict[str, set[str]]


def reload() -> None:
    """Lädt alle Taxonomie-Konstanten aus den ``config/``-YAMLs neu (idempotent)."""
    global CATEGORY_TO_FOLDER, ALLOWED_CATEGORIES, ALLOWED_TAGS, TAG_SYNONYMS
    global ALLOWED_TYPE, ALLOWED_STATUS, ALLOWED_REVIEW, ALLOWED_CONFIDENCE
    global ALLOWED_DOC_ROLE, _FIELD_ENUMS

    CATEGORY_TO_FOLDER = load_category_to_folder()
    ALLOWED_CATEGORIES = set(CATEGORY_TO_FOLDER)
    ALLOWED_TAGS, TAG_SYNONYMS = load_tags()

    enums = load_enums()
    ALLOWED_TYPE = enums.get("type", set())
    ALLOWED_STATUS = enums.get("status", set())
    ALLOWED_REVIEW = enums.get("review_status", set())
    ALLOWED_CONFIDENCE = enums.get("confidence", set())
    ALLOWED_DOC_ROLE = enums.get("doc_role", set())

    _FIELD_ENUMS = {
        "type": ALLOWED_TYPE,
        "status": ALLOWED_STATUS,
        "review_status": ALLOWED_REVIEW,
        "confidence": ALLOWED_CONFIDENCE,
        "category": ALLOWED_CATEGORIES,
    }


def allowed_values(field_name: str) -> set[str]:
    """Live-Enum-Set für ein vom Schema validiertes Feld (nutzt aktuellen Stand)."""
    return _FIELD_ENUMS.get(field_name, set())


def folder_for_category(category: str) -> str | None:
    """Vault-Ordner (``NN_Name``) zu einer ``category`` — ``None`` wenn unbekannt."""
    return CATEGORY_TO_FOLDER.get(category)


def resolve_tag_synonym(tag: str) -> str | None:
    """Kanonischer Tag für ein Alias. Kanonisch→selbst, verworfen/unbekannt→None."""
    if tag in ALLOWED_TAGS:
        return tag
    return TAG_SYNONYMS.get(tag)


# Initialer Load beim Import.
reload()
