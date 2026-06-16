"""Tests für pipeline/taxonomy.py — Single-Source-Facade + Runtime-Validierung.

Bewacht die pipeline-v2-Invariante: ``pipeline.taxonomy`` ist die *einzige*
Quelle des kontrollierten Vokabulars (Kategorien, Tags, Wert-Enums); kein
Konsument definiert ein Enum selbst, und ``FrontmatterDraft`` validiert die
Lebenszyklus-Enums zur Laufzeit dagegen (kein ``Literal`` mehr).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import _paths, taxonomy
from pipeline.schemas import FrontmatterDraft

# === Single-Source: Facade == config/-YAMLs ===================================


def test_enums_match_enums_yaml() -> None:
    """Alle Wert-Enums der Facade stammen 1:1 aus config/enums.yaml."""
    raw = yaml.safe_load(_paths.ENUMS_FILE.read_text(encoding="utf-8"))
    assert set(raw["type"]) == taxonomy.ALLOWED_TYPE
    assert set(raw["status"]) == taxonomy.ALLOWED_STATUS
    assert set(raw["review_status"]) == taxonomy.ALLOWED_REVIEW
    assert set(raw["confidence"]) == taxonomy.ALLOWED_CONFIDENCE
    assert set(raw["doc_role"]) == taxonomy.ALLOWED_DOC_ROLE


def test_gedanke_is_allowed_type() -> None:
    """F1-Gegenprobe: `gedanke` ist Teil des Typ-Vokabulars (keine Enum-Drift)."""
    assert "gedanke" in taxonomy.ALLOWED_TYPE


def test_categories_match_categories_yaml() -> None:
    raw = yaml.safe_load(_paths.CATEGORIES_FILE.read_text(encoding="utf-8"))
    assert raw["categories"] == taxonomy.CATEGORY_TO_FOLDER
    assert set(raw["categories"]) == taxonomy.ALLOWED_CATEGORIES


def test_tags_match_tag_vocabulary_yaml() -> None:
    raw = yaml.safe_load(_paths.TAG_VOCABULARY_FILE.read_text(encoding="utf-8"))
    expected = {t for tags in raw["sections"].values() for t in (tags or [])}
    assert expected == taxonomy.ALLOWED_TAGS
    assert raw["synonyms"] == taxonomy.TAG_SYNONYMS


def test_folder_and_synonym_helpers() -> None:
    assert taxonomy.folder_for_category("gedanken") == "15_Gedanken"
    assert taxonomy.folder_for_category("gibt-es-nicht") is None
    # kanonischer Tag → selbst, Alias → kanonisch, verworfen/unbekannt → None
    assert taxonomy.resolve_tag_synonym("python") == "python"
    assert taxonomy.resolve_tag_synonym("api-design") == "api"
    assert taxonomy.resolve_tag_synonym("ai-prompts") is None  # gedroppt
    assert taxonomy.resolve_tag_synonym("voellig-unbekannt") is None


# === 0-Dup-Enum-Guard: Konsumenten re-exportieren, definieren nicht ============


def test_pkm_common_reexports_same_objects() -> None:
    """scripts/_pkm_common spiegelt die Facade-Objekte (Identität, keine Kopie/Def)."""
    from scripts import _pkm_common as common

    assert common.ALLOWED_TYPE is taxonomy.ALLOWED_TYPE
    assert common.ALLOWED_STATUS is taxonomy.ALLOWED_STATUS
    assert common.ALLOWED_REVIEW is taxonomy.ALLOWED_REVIEW
    assert common.ALLOWED_CONFIDENCE is taxonomy.ALLOWED_CONFIDENCE
    assert common.ALLOWED_DOC_ROLE is taxonomy.ALLOWED_DOC_ROLE
    assert common.ALLOWED_CATEGORIES is taxonomy.ALLOWED_CATEGORIES
    assert common.CATEGORY_TO_FOLDER is taxonomy.CATEGORY_TO_FOLDER


def test_phase9_reexports_same_mapping() -> None:
    from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER

    assert CATEGORY_TO_FOLDER is taxonomy.CATEGORY_TO_FOLDER


def test_schema_has_no_literal_enums() -> None:
    """type/status/review_status/confidence sind str (Runtime-Check), kein Literal."""
    fields = FrontmatterDraft.model_fields
    for name in ("type", "status", "review_status", "confidence", "category"):
        assert fields[name].annotation is str, f"{name} sollte str sein (kein Literal)"


# === Runtime-Validator: valid / invalid =======================================

_BASE = dict(
    title="T",
    slug="t",
    summary="s",
    type="knowledge-article",
    doc_role=["reference"],
    category="grundlagen",
    tags=["pkm"],
    sources_docs=["D_x"],
    source_chunks=["D_x-S0001"],
    confidence="medium",
    created="2026-06-15",
    updated="2026-06-15",
    last_synthesized="2026-06-15",
    prompt_version="v1",
)


def test_validator_accepts_all_allowed_types() -> None:
    for t in taxonomy.ALLOWED_TYPE:
        FrontmatterDraft.model_validate({**_BASE, "type": t})


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("type", "bogus-type"),
        ("status", "archived"),
        ("review_status", "approved"),
        ("confidence", "very-high"),
    ],
)
def test_validator_rejects_unknown_enum(field: str, bad: str) -> None:
    with pytest.raises(ValueError, match="nicht im Vokabular"):
        FrontmatterDraft.model_validate({**_BASE, field: bad})


def test_unknown_category_is_not_hard_rejected() -> None:
    """`category` bleibt bewusst weich: unbekannt → kein Validierungs-Fail (Phase-9-Routing)."""
    m = FrontmatterDraft.model_validate({**_BASE, "category": "gibt-es-nicht"})
    assert m.category == "gibt-es-nicht"


# === Loader: Pfad-parametrisiert + reload =====================================


def test_load_enums_from_custom_path(tmp_path: Path) -> None:
    p = tmp_path / "enums.yaml"
    p.write_text("type: [a, b]\nstatus: [x]\n", encoding="utf-8")
    loaded = taxonomy.load_enums(p)
    assert loaded == {"type": {"a", "b"}, "status": {"x"}}
