"""Tests für scripts/manage_vocab.py — Vokabular-Pflege (category + tags).

Alle Funktionen arbeiten auf temp-Kopien (Pfad-Parameter); der echte Repo-Zustand
wird nicht angefasst.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import manage_vocab as mv

CATEGORIES_STUB = """# =============================================================================
# categories.yaml — Single Source: category-Wert → Vault-Ordnername
# =============================================================================

categories:
  meta: 00_Meta
  grundlagen: 01_Grundlagen
  unsortiert: 17_unsortiert
"""

TAGSYS_STUB = """---
title: Tag-System
updated: 2026-01-01
---

# Tag-System

## Kern-Vokabular (2)

### Web
`api` · `http`

---

## Synonym-Map

| Qwen-Vorschlag | Canonical |
|---|---|
| `metadaten` | `metadata` |

---

## Änderungs-Log

- 2026-01-01 — Initial
"""

VAULTSTD_STUB = """---
title: vault std
updated: 2026-01-01
---

## 4. Cluster-Struktur

```
output/
├── 00_Meta/
├── 01_Grundlagen/
├── 17_unsortiert/
└── _attic/
```
"""


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Path]:
    cats = tmp_path / "categories.yaml"
    cats.write_text(CATEGORIES_STUB, encoding="utf-8")
    tagsys = tmp_path / "tag-system.md"
    tagsys.write_text(TAGSYS_STUB, encoding="utf-8")
    vstd = tmp_path / "vault_std.md"
    vstd.write_text(VAULTSTD_STUB, encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    for f in ("00_Meta", "01_Grundlagen", "17_unsortiert"):
        (vault / f).mkdir()
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    return {"cats": cats, "tagsys": tagsys, "vstd": vstd, "vault": vault, "drafts": drafts}


# === category ================================================================


def test_parse_category_mapping(env: dict[str, Path]) -> None:
    m = mv.parse_category_mapping(env["cats"])
    assert m == {"meta": "00_Meta", "grundlagen": "01_Grundlagen", "unsortiert": "17_unsortiert"}


def test_add_category_consistent_three_places(env: dict[str, Path]) -> None:
    res = mv.add_category(
        "business",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
    )
    assert res["already"] is False
    assert res["folder"] == "18_Business"
    # 1. config/categories.yaml (Single Source)
    m = mv.parse_category_mapping(env["cats"])
    assert m["business"] == "18_Business"
    # 2. ALLOWED_CATEGORIES (abgeleitet = set der Mapping-Keys)
    assert "business" in set(m)
    # 3. Vault-Ordner
    assert (env["vault"] / "18_Business").is_dir()
    # Doku §4 ergänzt
    assert "18_Business/" in env["vstd"].read_text(encoding="utf-8")


def test_add_category_idempotent(env: dict[str, Path]) -> None:
    mv.add_category(
        "business",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
    )
    res2 = mv.add_category(
        "business",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
    )
    assert res2["already"] is True
    # nur ein Eintrag in categories.yaml
    src = env["cats"].read_text(encoding="utf-8")
    assert src.count("business:") == 1


def test_add_category_preserves_yaml_header(env: dict[str, Path]) -> None:
    """categories.yaml behält seinen Kommentar-Header nach add-category (Single-Source intakt)."""
    mv.add_category(
        "business",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
    )
    text = env["cats"].read_text(encoding="utf-8")
    assert text.startswith("# ===")
    assert "Single Source" in text


def test_add_category_next_number(env: dict[str, Path]) -> None:
    r1 = mv.add_category(
        "alpha",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
    )
    r2 = mv.add_category(
        "beta", categories_path=env["cats"], vault_dir=env["vault"], vault_standard_path=env["vstd"]
    )
    assert r1["folder"] == "18_Alpha"
    assert r2["folder"] == "19_Beta"


def test_add_category_folder_display_keeps_small_words(env: dict[str, Path]) -> None:
    res = mv.add_category(
        "wissen-und-praxis",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
    )
    assert res["folder"] == "18_Wissen-und-Praxis"


def test_add_category_invalid_slug(env: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="category-Slug"):
        mv.add_category(
            "Ungültig Slug",
            categories_path=env["cats"],
            vault_dir=env["vault"],
            vault_standard_path=env["vstd"],
        )


def test_add_category_dry_run_writes_nothing(env: dict[str, Path]) -> None:
    before = env["cats"].read_text(encoding="utf-8")
    res = mv.add_category(
        "business",
        categories_path=env["cats"],
        vault_dir=env["vault"],
        vault_standard_path=env["vstd"],
        dry_run=True,
    )
    assert res["dry_run"] is True
    assert env["cats"].read_text(encoding="utf-8") == before
    assert not (env["vault"] / "18_Business").exists()


# === tags ====================================================================


def test_add_tag_registers_in_vocab(env: dict[str, Path]) -> None:
    res = mv.add_tag(
        "observability", "Monitoring- und Tracing-Thema", tag_system_path=env["tagsys"]
    )
    assert res["already"] is False
    vocab = mv.parse_tag_vocab(env["tagsys"])
    assert "observability" in vocab
    assert "api" in vocab  # Bestand bleibt


def test_add_tag_idempotent(env: dict[str, Path]) -> None:
    mv.add_tag("observability", "Grund", tag_system_path=env["tagsys"])
    res2 = mv.add_tag("observability", "Grund", tag_system_path=env["tagsys"])
    assert res2["already"] is True


def test_add_tag_reason_required(env: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="Begründung"):
        mv.add_tag("observability", "   ", tag_system_path=env["tagsys"])


def test_add_tag_rejects_backtick_reason(env: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="darf kein"):
        mv.add_tag("observability", "Grund mit `code`", tag_system_path=env["tagsys"])


def test_add_tag_invalid_slug(env: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="ungültiger Tag"):
        mv.add_tag("Groß", "Grund", tag_system_path=env["tagsys"])


# === validate ================================================================


def _write_draft(drafts: Path, slug: str, tags: list[str], category: str | None = None) -> None:
    tag_yaml = "\n".join(f"  - {t}" for t in tags)
    cat_line = f"category: {category}\n" if category else ""
    (drafts / f"CK_{slug}.md").write_text(
        f"---\nslug: {slug}\n{cat_line}tags:\n{tag_yaml}\n---\n\n# {slug}\n", encoding="utf-8"
    )


def test_validate_clean(env: dict[str, Path]) -> None:
    res = mv.validate(
        categories_path=env["cats"],
        vault_dir=env["vault"],
        drafts_dir=env["drafts"],
        tag_system_path=env["tagsys"],
        vault_standard_path=env["vstd"],
    )
    assert res["category_issues"] == []
    assert res["tag_issues"] == []


def test_validate_detects_missing_folder_for_used_category(env: dict[str, Path]) -> None:
    # belegte category 'grundlagen' (Artikel vorhanden), aber Ordner fehlt → Drift
    _write_draft(env["drafts"], "doc-g", ["api"], category="grundlagen")
    (env["vault"] / "01_Grundlagen").rmdir()
    res = mv.validate(
        categories_path=env["cats"],
        vault_dir=env["vault"],
        drafts_dir=env["drafts"],
        tag_system_path=env["tagsys"],
        vault_standard_path=env["vstd"],
    )
    assert any("01_Grundlagen" in i for i in res["category_issues"])


def test_validate_ignores_missing_folder_for_unused_category(env: dict[str, Path]) -> None:
    # 'unsortiert' hat keinen Artikel → fehlender Ordner ist KEIN Drift
    (env["vault"] / "17_unsortiert").rmdir()
    res = mv.validate(
        categories_path=env["cats"],
        vault_dir=env["vault"],
        drafts_dir=env["drafts"],
        tag_system_path=env["tagsys"],
        vault_standard_path=env["vstd"],
    )
    assert not any("17_unsortiert" in i for i in res["category_issues"])


def test_validate_detects_unknown_tag(env: dict[str, Path]) -> None:
    _write_draft(env["drafts"], "doc-x", ["api", "nicht-im-vokabular"])
    res = mv.validate(
        categories_path=env["cats"],
        vault_dir=env["vault"],
        drafts_dir=env["drafts"],
        tag_system_path=env["tagsys"],
        vault_standard_path=env["vstd"],
    )
    assert any("nicht-im-vokabular" in i for i in res["tag_issues"])


# === list ====================================================================


def test_list_vocab(env: dict[str, Path]) -> None:
    v = mv.list_vocab(categories_path=env["cats"], tag_system_path=env["tagsys"])
    assert v["categories"]["grundlagen"] == "01_Grundlagen"
    assert set(v["tags"]) == {"api", "http"}
