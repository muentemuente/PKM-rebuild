"""Guard: SSoT für geteilte Enums/Konstanten/Helfer der PKM-Skripte.

Sichert die Konsolidierung aus `chore/phase2-prep-pt018-dedup` gegen Re-Drift:
die früher in `validate_vault.py`, `check_frontmatter.py` und `tag_inventory.py`
duplizierten Enum- und Konstanten-Literale (Kategorien, Type/Status/Review/
Confidence, Slug-Regex, Umlaut-Map) dürfen nur noch in der Single Source of
Truth liegen — `pipeline.taxonomy` (Enums, via `scripts._pkm_common` re-exportiert)
bzw. `scripts._pkm_common` selbst (Slug-Regex, Umlaut-Map, Pure-Helfer).

Drei Wächter:
  1. rg-Guard — keine doppelte Definition der konsolidierten Literale in scripts/
  2. eingefrorene Enum-Fixture — Soll-Werte der fixen Enums
  3. Import-Smoke — alle öffentlichen Importpfade weiterhin auflösbar
"""

from __future__ import annotations

from pathlib import Path

from scripts import _pkm_common as common

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

# Dateien, die ein Umlaut-/Slug-Literal behalten DÜRFEN (dokumentierte Ausnahmen):
#  - _pkm_common.py  → die SSoT selbst
#  - r2_diagnose.py  → spiegelt bewusst die Pipeline-Slug-Logik (Diagnose-Zweck,
#                       verifiziert zur Laufzeit gegen die Pipeline-Quelle)
_UMLAUT_LITERAL = '"ä"'
_UMLAUT_ALLOWED = {"_pkm_common.py", "r2_diagnose.py"}

# Enum-Literale, die nur noch aus der Taxonomie-Facade kommen dürfen:
_TYPE_LITERAL = "knowledge-article"
_REVIEW_LITERAL = "ai_drafted"
_SLUG_REGEX_LITERAL = r"^[a-z0-9]+(-[a-z0-9]+)*$"


# === 1. rg-Guard: keine Eigenkopien außerhalb der SSoT ========================


def test_no_duplicate_umlaut_literal_in_scripts() -> None:
    """Umlaut-Map-Literal (`"ä"`) nur in der SSoT bzw. dokumentierten Ausnahmen."""
    offenders = sorted(
        p.name
        for p in _SCRIPTS.glob("*.py")
        if p.name not in _UMLAUT_ALLOWED and _UMLAUT_LITERAL in p.read_text(encoding="utf-8")
    )
    assert offenders == [], (
        f"Umlaut-Literal außerhalb der SSoT (_pkm_common.UMLAUT_MAP): {offenders}. "
        "UMLAUT_MAP importieren statt re-definieren."
    )


def test_validate_vault_has_no_hardcoded_enums() -> None:
    """validate_vault.py nutzt die Enum/Slug-SSoT, keine hartkodierten Literale."""
    src = (_SCRIPTS / "validate_vault.py").read_text(encoding="utf-8")
    assert _TYPE_LITERAL not in src, "type-Enum hartkodiert — ALLOWED_TYPE importieren"
    assert _REVIEW_LITERAL not in src, "review-Enum hartkodiert (war ohnehin tot)"
    assert _SLUG_REGEX_LITERAL not in src, "Slug-Regex hartkodiert — SLUG_RE importieren"
    assert "from scripts._pkm_common import" in src


# === 2. Eingefrorene Enum-Fixture =============================================

# Soll-Mengen der fixen Enums (Kategorien sind config-getrieben → test_taxonomy).
_EXPECTED_TYPE = {"process-document", "knowledge-article", "compact-reference", "gedanke"}
_EXPECTED_STATUS = {"draft", "review", "stable", "deprecated"}
_EXPECTED_REVIEW = {"ai_drafted", "human_reviewed", "verified"}
_EXPECTED_CONFIDENCE = {"low", "medium", "high"}


def test_enum_values_frozen() -> None:
    """Die fixen Enum-Werte entsprechen der eingefrorenen Soll-Menge."""
    assert common.ALLOWED_TYPE == _EXPECTED_TYPE
    assert common.ALLOWED_STATUS == _EXPECTED_STATUS
    assert common.ALLOWED_REVIEW == _EXPECTED_REVIEW
    assert common.ALLOWED_CONFIDENCE == _EXPECTED_CONFIDENCE


# === 3. Import-Smoke: öffentliche Pfade bleiben auflösbar =====================


def test_public_import_paths_resolve() -> None:
    """Alle bislang genutzten Importpfade aus _pkm_common bleiben verfügbar."""
    from scripts._pkm_common import (  # noqa: F401
        ALLOWED_CATEGORIES,
        ALLOWED_CONFIDENCE,
        ALLOWED_DOC_ROLE,
        ALLOWED_REVIEW,
        ALLOWED_STATUS,
        ALLOWED_TYPE,
        CATEGORY_TO_FOLDER,
        REQUIRED_FIELDS,
        SLUG_RE,
        UMLAUT_MAP,
        canonical_ck_slug,
        compute_body_metrics,
        draft_stem_to_slug,
        normalize_slug,
        normalize_to_slug,
        parse_json_file,
        parse_yaml_text,
        split_md,
    )

    for helper in (
        split_md,
        parse_yaml_text,
        parse_json_file,
        compute_body_metrics,
        normalize_to_slug,
        draft_stem_to_slug,
        canonical_ck_slug,
        normalize_slug,
    ):
        assert callable(helper)
    assert UMLAUT_MAP == {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
