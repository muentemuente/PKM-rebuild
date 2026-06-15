"""Tests für pipeline/taxonomy_migrate.py — Rename-Migration NUR gegen Fixtures.

Wichtig: keine Migration läuft hier gegen ``data``/``output`` — alle Funktionen
sind pfad-parametrisiert und bekommen Fixture-Verzeichnisse (tmp_path).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import taxonomy_migrate as tm

# === Fixtures =================================================================


def _fm(**over: object) -> dict:
    base = dict(
        title="Idee Eins",
        slug="idee-eins",
        summary="Eine kurze Idee zum Testen.",
        type="gedanke",
        doc_role=["explanation"],
        category="gedanken",
        tags=["pkm", "obsidian"],
        related=[],
        sources_docs=["D_x"],
        source_chunks=["D_x-S0001"],
        status="draft",
        review_status="ai_drafted",
        confidence="medium",
        doc_version="0.1.0",
        created="2026-06-15",
        updated="2026-06-15",
        last_synthesized="2026-06-15",
        prompt_version="v1",
    )
    base.update(over)
    return base


def _write_md(path: Path, fm: dict, body: str = "# Idee\n\nText.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip("\n")
    path.write_text(f"---\n{head}\n---\n\n{body}", encoding="utf-8")


@pytest.fixture
def vault_env(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Fixture-Vault: config/categories.yaml + output/15_Gedanken + drafts/CK_idee-eins.*"""
    cfg = tmp_path / "config" / "categories.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "# header\ncategories:\n  gedanken: 15_Gedanken\n  grundlagen: 01_Grundlagen\n",
        encoding="utf-8",
    )
    vault = tmp_path / "output"
    _write_md(vault / "15_Gedanken" / "idee-eins.md", _fm())
    (vault / "15_Gedanken" / "_index.md").write_text(
        "---\ntitle: 'Index: 15_Gedanken'\n---\n", encoding="utf-8"
    )
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    _write_md(drafts / "CK_idee-eins.md", _fm())
    (drafts / "CK_idee-eins.frontmatter.json").write_text(
        json.dumps(_fm(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return cfg, vault, drafts


# === category rename ==========================================================


def test_rename_category_dry_run_writes_nothing(vault_env) -> None:
    cfg, vault, drafts = vault_env
    before = cfg.read_text(encoding="utf-8")
    res = tm.rename_category(
        "gedanken",
        "notizen",
        categories_path=cfg,
        vault_dir=vault,
        drafts_dir=drafts,
        dry_run=True,
    )
    assert res.dry_run
    assert res.folder_to == "15_Notizen"
    assert res.files_frontmatter == 1
    assert res.drafts_frontmatter == 1
    assert cfg.read_text(encoding="utf-8") == before  # unverändert
    assert (vault / "15_Gedanken").is_dir()  # kein Move


def test_rename_category_migrates_everything(vault_env) -> None:
    cfg, vault, drafts = vault_env
    res = tm.rename_category(
        "gedanken",
        "notizen",
        categories_path=cfg,
        vault_dir=vault,
        drafts_dir=drafts,
    )
    # SSoT
    mapping = yaml.safe_load(cfg.read_text(encoding="utf-8"))["categories"]
    assert "gedanken" not in mapping
    assert mapping["notizen"] == "15_Notizen"
    # Ordner-Move
    assert not (vault / "15_Gedanken").exists()
    assert (vault / "15_Notizen" / "idee-eins.md").exists()
    # Vault-Frontmatter
    vfm = yaml.safe_load(
        (vault / "15_Notizen" / "idee-eins.md").read_text(encoding="utf-8").split("---\n")[1]
    )
    assert vfm["category"] == "notizen"
    # Draft-.md + .json
    dfm = yaml.safe_load((drafts / "CK_idee-eins.md").read_text(encoding="utf-8").split("---\n")[1])
    assert dfm["category"] == "notizen"
    jfm = json.loads((drafts / "CK_idee-eins.frontmatter.json").read_text(encoding="utf-8"))
    assert jfm["category"] == "notizen"
    # Index regeneriert + Validierung sauber
    idx = (vault / "15_Notizen" / "_index.md").read_text(encoding="utf-8")
    assert "folder: 15_Notizen" in idx
    assert res.indexes_regenerated == 1
    assert res.validation_errors == []
    assert res.ok


def test_rename_category_rejects_existing_target(vault_env) -> None:
    cfg, vault, drafts = vault_env
    with pytest.raises(ValueError, match="existiert bereits"):
        tm.rename_category(
            "gedanken", "grundlagen", categories_path=cfg, vault_dir=vault, drafts_dir=drafts
        )


def test_rename_category_rejects_unknown_source(vault_env) -> None:
    cfg, vault, drafts = vault_env
    with pytest.raises(ValueError, match="existiert nicht"):
        tm.rename_category(
            "gibtsnicht", "x", categories_path=cfg, vault_dir=vault, drafts_dir=drafts
        )


# === tag rename ===============================================================


def test_rename_tag_migrates_frontmatter_and_ssot(tmp_path: Path) -> None:
    vocab = tmp_path / "config" / "tag_vocabulary.yaml"
    vocab.parent.mkdir(parents=True)
    vocab.write_text(
        "sections:\n  PKM:\n    - obsidian\n    - pkm\nsynonyms:\n  alt-alias: pkm\n",
        encoding="utf-8",
    )
    vault = tmp_path / "output"
    _write_md(vault / "15_Gedanken" / "idee-eins.md", _fm(tags=["pkm", "obsidian"]))
    drafts = tmp_path / "drafts"
    drafts.mkdir()

    res = tm.rename_tag(
        "obsidian",
        "obsidian-md",
        tag_vocab_path=vocab,
        vault_dir=vault,
        drafts_dir=drafts,
    )
    data = yaml.safe_load(vocab.read_text(encoding="utf-8"))
    flat = {t for tags in data["sections"].values() for t in tags}
    assert "obsidian" not in flat
    assert "obsidian-md" in flat
    assert data["synonyms"]["obsidian"] == "obsidian-md"
    vfm = yaml.safe_load(
        (vault / "15_Gedanken" / "idee-eins.md").read_text(encoding="utf-8").split("---\n")[1]
    )
    assert "obsidian-md" in vfm["tags"]
    assert "obsidian" not in vfm["tags"]
    assert res.validation_errors == []


def test_rename_tag_rejects_unknown(tmp_path: Path) -> None:
    vocab = tmp_path / "config" / "tag_vocabulary.yaml"
    vocab.parent.mkdir(parents=True)
    vocab.write_text("sections:\n  PKM:\n    - pkm\nsynonyms: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="existiert nicht"):
        tm.rename_tag(
            "nope",
            "x",
            tag_vocab_path=vocab,
            vault_dir=tmp_path / "out",
            drafts_dir=tmp_path / "dr",
        )
