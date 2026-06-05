"""Tests für scripts/_pkm_common.py — Drift-Schutz Enums ↔ Pipeline-Schemas.

Der Sinn von _pkm_common ist Single Source of Truth: die Skript-Enums dürfen
nicht von den kanonischen Pipeline-Definitionen (pipeline.schemas /
phase_9_vault_build) abweichen. Diese Tests machen Drift unmöglich.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER
from pipeline.schemas import FrontmatterDraft
from scripts import _pkm_common as common

_FIELDS = FrontmatterDraft.model_fields


def test_allowed_type_matches_schema() -> None:
    assert set(get_args(_FIELDS["type"].annotation)) == common.ALLOWED_TYPE


def test_allowed_status_matches_schema() -> None:
    assert set(get_args(_FIELDS["status"].annotation)) == common.ALLOWED_STATUS


def test_allowed_review_matches_schema() -> None:
    assert set(get_args(_FIELDS["review_status"].annotation)) == common.ALLOWED_REVIEW


def test_allowed_confidence_matches_schema() -> None:
    assert set(get_args(_FIELDS["confidence"].annotation)) == common.ALLOWED_CONFIDENCE


def test_allowed_categories_match_vault_mapping() -> None:
    """ALLOWED_CATEGORIES == kanonische Vault-Ordner-Keys (phase_9)."""
    assert set(CATEGORY_TO_FOLDER) == common.ALLOWED_CATEGORIES


def test_required_fields_subset_of_schema() -> None:
    """Jedes Pflichtfeld existiert auch im Pydantic-Schema."""
    assert set(_FIELDS) >= common.REQUIRED_FIELDS


def test_enums_are_nonempty() -> None:
    for name in (
        "ALLOWED_TYPE",
        "ALLOWED_STATUS",
        "ALLOWED_REVIEW",
        "ALLOWED_CONFIDENCE",
        "ALLOWED_CATEGORIES",
        "ALLOWED_DOC_ROLE",
    ):
        assert getattr(common, name), f"{name} darf nicht leer sein"


def test_canonical_ck_slug_examples() -> None:
    """Slug-Ableitung: NFC-Umlaut, Akzent-Strip, Sonderzeichen, Fallback."""
    assert common.canonical_ck_slug("Erklärung Sage") == "erklaerung-sage"
    assert common.canonical_ck_slug("API_Grundlagen") == "api-grundlagen"
    assert common.canonical_ck_slug("café-déjà") == "cafe-deja"
    assert common.canonical_ck_slug("!!!") == "concept"


def test_normalize_and_stem_helpers() -> None:
    assert common.normalize_to_slug("API_Grundlagen") == "api-grundlagen"
    assert common.normalize_slug is common.normalize_to_slug
    assert common.draft_stem_to_slug("CK_foo") == "foo"
    assert common.draft_stem_to_slug("foo") == "foo"


def test_split_md_roundtrip() -> None:
    fm, body = common.split_md("---\na: 1\n---\n\n# Titel\n")
    assert fm == "a: 1"
    assert body.strip() == "# Titel"
    assert common.split_md("kein frontmatter")[0] is None
