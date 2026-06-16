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


def write_category_mapping(mapping: dict[str, str], path: Path | None = None) -> None:
    """Schreibt ``config/categories.yaml`` (Kommentar-Header bleibt, nur Body neu).

    Single Source des Schreibformats — von ``manage_vocab`` (add) und
    ``taxonomy_migrate`` (rename) genutzt, damit der Header nicht divergiert.
    """
    path = path or _paths.CATEGORIES_FILE
    text = path.read_text(encoding="utf-8")
    header_end = text.find("categories:")
    header = text[:header_end] if header_end != -1 else ""
    body = "categories:\n" + "".join(f"  {k}: {v}\n" for k, v in mapping.items())
    path.write_text(header + body, encoding="utf-8")


def load_enums(path: Path | None = None) -> dict[str, set[str]]:
    """Lädt die Wert-Enums aus ``config/enums.yaml`` als ``{feld: {werte}}``."""
    path = path or _paths.ENUMS_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {key: set(values or []) for key, values in data.items()}


def load_tags(path: Path | None = None) -> tuple[set[str], dict[str, str | None]]:
    """Lädt ``(kanonische Tags, Synonym-Map)`` aus ``config/tag_vocabulary.yaml``."""
    path = path or _paths.TAG_VOCABULARY_FILE
    return load_tag_vocabulary_yaml(path)


# === Modul-Konstanten ==========================================================
# Werden beim Import via reload() befüllt und bei jedem reload() **in-place**
# aktualisiert (clear+update statt Rebind). Dadurch behält jeder Konsument, der
# ein Set/Dict beim Import gebunden hat (scripts/_pkm_common, der Pydantic-
# Validator über _FIELD_ENUMS), nach einer Vokabular-Mutation den Live-Stand —
# keine stale Referenzen, Objekt-Identität bleibt über reload() hinweg stabil.

CATEGORY_TO_FOLDER: dict[str, str] = {}
ALLOWED_CATEGORIES: set[str] = set()
ALLOWED_TAGS: set[str] = set()
TAG_SYNONYMS: dict[str, str | None] = {}
ALLOWED_TYPE: set[str] = set()
ALLOWED_STATUS: set[str] = set()
ALLOWED_REVIEW: set[str] = set()
ALLOWED_CONFIDENCE: set[str] = set()
ALLOWED_DOC_ROLE: set[str] = set()

# Feldname → Live-Enum-Set (dieselben Objekte wie oben), von
# schemas.FrontmatterDraft über allowed_values() genutzt.
_FIELD_ENUMS: dict[str, set[str]] = {
    "type": ALLOWED_TYPE,
    "status": ALLOWED_STATUS,
    "review_status": ALLOWED_REVIEW,
    "confidence": ALLOWED_CONFIDENCE,
    "category": ALLOWED_CATEGORIES,
}


def _refill(target: set[str], values: set[str]) -> None:
    """Set in-place ersetzen (Identität erhalten)."""
    target.clear()
    target.update(values)


def reload() -> None:
    """Lädt alle Taxonomie-Konstanten aus den ``config/``-YAMLs neu (idempotent, in-place)."""
    mapping = load_category_to_folder()
    CATEGORY_TO_FOLDER.clear()
    CATEGORY_TO_FOLDER.update(mapping)
    _refill(ALLOWED_CATEGORIES, set(mapping))

    tags, synonyms = load_tags()
    _refill(ALLOWED_TAGS, tags)
    TAG_SYNONYMS.clear()
    TAG_SYNONYMS.update(synonyms)

    enums = load_enums()
    _refill(ALLOWED_TYPE, enums.get("type", set()))
    _refill(ALLOWED_STATUS, enums.get("status", set()))
    _refill(ALLOWED_REVIEW, enums.get("review_status", set()))
    _refill(ALLOWED_CONFIDENCE, enums.get("confidence", set()))
    _refill(ALLOWED_DOC_ROLE, enums.get("doc_role", set()))


def allowed_values(field_name: str) -> set[str]:
    """Live-Enum-Set für ein vom Schema validiertes Feld (nutzt aktuellen Stand)."""
    return _FIELD_ENUMS.get(field_name, set())


def folder_for_category(category: str) -> str | None:
    """Vault-Ordner (``NN_Name``) zu einer ``category`` — ``None`` wenn unbekannt."""
    return CATEGORY_TO_FOLDER.get(category)


# Kleine Wörter, die im Ordner-Anzeigenamen kleingeschrieben bleiben
# (Stil der Bestands-Ordner, z. B. "04_Protokolle-und-Standards").
_LOWER_TOKENS = {"und", "oder", "der", "die", "das", "von", "zu", "mit", "für", "im", "am"}


def folder_display_name(slug: str) -> str:
    """Category-Slug → Ordner-Anzeigename (Token-Caps, kleine Wörter klein).

    Beispiel: ``protokolle-und-standards`` → ``Protokolle-und-Standards``.
    Single Source dieser Konvention (auch von scripts/manage_vocab genutzt).
    """
    parts = [tok if tok in _LOWER_TOKENS else tok.capitalize() for tok in slug.split("-")]
    return "-".join(parts)


def resolve_tag_synonym(tag: str) -> str | None:
    """Kanonischer Tag für ein Alias. Kanonisch→selbst, verworfen/unbekannt→None."""
    if tag in ALLOWED_TAGS:
        return tag
    return TAG_SYNONYMS.get(tag)


# Initialer Load beim Import.
reload()
