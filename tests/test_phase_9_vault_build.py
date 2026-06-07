"""Tests für Phase 9: Vault-Aufbau.

Fixtures sind synthetisch (nicht gegen den echten Korpus), siehe Task 9.A §2.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from pipeline.phase_9_vault_build import (
    CATEGORY_TO_FOLDER,
    run_phase_9,
)
from pipeline.schemas import FrontmatterDraft

_BASE_FM: dict = {
    "title": "Testartikel",
    "slug": "test-artikel",
    "summary": "Eine synthetische Zusammenfassung für Tests.",
    "type": "knowledge-article",
    "doc_role": ["reference"],
    "category": "grundlagen",
    "tags": ["tag-a", "tag-b"],
    "sources_docs": ["D_test"],
    "source_chunks": ["D_test-S0000"],
    "confidence": "medium",
    "created": "2026-06-01",
    "updated": "2026-06-02",
    "last_synthesized": "2026-06-02",
    "prompt_version": "v1",
}


def _make_draft(
    drafts_dir: Path,
    stem: str,
    *,
    slug: str,
    category: str = "grundlagen",
    title: str | None = None,
    related: list[str] | None = None,
    body: str | None = None,
    updated: str = "2026-06-02",
    tags: list[str] | None = None,
) -> None:
    """Schreibt ein synthetisches Draft-Paar (`CK_<stem>.md` + `.body.md`)."""
    fm = dict(_BASE_FM)
    fm.update(
        slug=slug,
        category=category,
        title=title or f"Artikel {slug}",
        related=related or [],
        updated=updated,
        tags=tags or _BASE_FM["tags"],
    )
    body_text = body or f"# {fm['title']}\n\nKörper von {slug}.\n"
    md = drafts_dir / f"CK_{stem}.md"
    md.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + body_text,
        encoding="utf-8",
    )
    (drafts_dir / f"CK_{stem}.body.md").write_text(body_text, encoding="utf-8")


@pytest.fixture
def vault_env(temp_dir: Path) -> tuple[Path, Path, Path, Path]:
    """Legt drafts/vault/pipeline_output/backups unter temp_dir an."""
    drafts = temp_dir / "drafts"
    vault = temp_dir / "output"
    out = temp_dir / "work"
    backups = temp_dir / "backups"
    for d in (drafts, vault, out, backups):
        d.mkdir(parents=True)
    return drafts, vault, out, backups


def _run(env: tuple[Path, Path, Path, Path], **kw):
    drafts, vault, out, backups = env
    return run_phase_9(drafts, vault, out, backups, **kw)


def _all_vault_md(vault: Path) -> list[Path]:
    return sorted(p for p in vault.rglob("*.md") if p.name != "_index.md")


# === category → folder ========================================================


def test_mapping_covers_all_canonical_folders() -> None:
    """meta + 16 thematische + 17_unsortiert; alle nummeriert (00-17)."""
    assert CATEGORY_TO_FOLDER["meta"] == "00_Meta"
    assert CATEGORY_TO_FOLDER["grundlagen"] == "01_Grundlagen"
    assert CATEGORY_TO_FOLDER["gedanken"] == "15_Gedanken"
    assert CATEGORY_TO_FOLDER["kunst-kultur"] == "16_Kunst-Kultur"
    assert CATEGORY_TO_FOLDER["unsortiert"] == "17_unsortiert"
    # alle 18 Ordner sind nummeriert (00..17), unsortiert ist regulärer Cluster
    numbered = [v for v in CATEGORY_TO_FOLDER.values() if v[:2].isdigit()]
    assert len(numbered) == 18  # 00..17
    assert len(CATEGORY_TO_FOLDER) == 18


def test_each_category_lands_in_correct_folder(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    for i, cat in enumerate(CATEGORY_TO_FOLDER):
        _make_draft(drafts, f"d{i}", slug=f"slug-{i}", category=cat)
    _run(vault_env, force=True)
    for i, (_cat, folder) in enumerate(CATEGORY_TO_FOLDER.items()):
        assert (vault / folder / f"slug-{i}.md").exists()


def test_unknown_category_routes_to_unsortiert(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "x", slug="weird", category="gibt-es-nicht")
    summary = _run(vault_env, force=True)
    assert (vault / "17_unsortiert" / "weird.md").exists()
    assert summary["unknown_categories"] == ["gibt-es-nicht"]


def test_unsortiert_is_regular_cluster_with_index(vault_env) -> None:
    """category=unsortiert landet in 17_unsortiert und bekommt ein _index.md."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "u1", slug="u-eins", category="unsortiert")
    _make_draft(drafts, "u2", slug="u-zwei", category="unsortiert")
    summary = _run(vault_env, force=True)
    assert (vault / "17_unsortiert" / "u-eins.md").exists()
    assert (vault / "17_unsortiert" / "u-zwei.md").exists()
    # regulärer Cluster → _index.md wird erzeugt (anders als 00_Meta)
    idx = vault / "17_unsortiert" / "_index.md"
    assert idx.exists()
    fm = yaml.safe_load(idx.read_text(encoding="utf-8").split("---\n", 2)[1])
    assert fm["article_count"] == 2
    assert fm["folder"] == "17_unsortiert"
    # keine als unknown gewertet (unsortiert ist gültige category)
    assert summary["unknown_categories"] == []


# === frontmatter valid ========================================================


def test_all_outputs_have_valid_frontmatter(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", category="grundlagen")
    _make_draft(drafts, "b", slug="beta", category="webentwicklung")
    _run(vault_env, force=True)
    for p in _all_vault_md(vault):
        text = p.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        fm = yaml.safe_load(text.split("---\n", 2)[1])
        FrontmatterDraft.model_validate(fm)  # wirft bei Fehler


# === slug-collision ===========================================================


def test_slug_collision_gets_suffix(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    # drei Drafts mit gleichem Slug, verschiedene Ordner/Stems
    _make_draft(drafts, "a1", slug="dup", category="grundlagen")
    _make_draft(drafts, "a2", slug="dup", category="webentwicklung")
    _make_draft(drafts, "a3", slug="dup", category="betriebssysteme")
    summary = _run(vault_env, force=True)
    assert summary["collisions"] == 2
    slugs = {p.stem for p in _all_vault_md(vault)}
    assert slugs == {"dup", "dup_2", "dup_3"}
    # final_slug steht auch im Frontmatter (slug == Dateiname)
    for p in _all_vault_md(vault):
        fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---\n", 2)[1])
        assert fm["slug"] == p.stem


# === wikilink-drop ============================================================


def test_dangling_wikilinks_dropped_and_logged(vault_env) -> None:
    drafts, vault, out, _ = vault_env
    _make_draft(drafts, "src", slug="quelle", related=["ziel-da", "ziel-weg", "noch-weg"])
    _make_draft(drafts, "tgt", slug="ziel-da")  # auflösbar
    summary = _run(vault_env, force=True)
    assert summary["dropped_links"] == 2
    assert summary["dropped_links_drafts"] == 1
    # im Output bleibt nur der auflösbare Link
    fm = yaml.safe_load((vault / "01_Grundlagen" / "quelle.md").read_text().split("---\n", 2)[1])
    assert fm["related"] == ["ziel-da"]
    # Log-Datei
    rows = [
        json.loads(ln)
        for ln in (out / "phase9_dropped_links.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert {r["dropped_target"] for r in rows} == {"ziel-weg", "noch-weg"}
    assert all(r["source_slug"] == "quelle" for r in rows)


# === _index.md ================================================================


def test_index_per_used_folder_with_counts(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="a", category="grundlagen", updated="2026-06-05", tags=["x"])
    _make_draft(drafts, "b", slug="b", category="grundlagen", updated="2026-06-09", tags=["x", "y"])
    _make_draft(drafts, "c", slug="c", category="webentwicklung", updated="2026-06-01")
    _run(vault_env, force=True)
    idx_g = (vault / "01_Grundlagen" / "_index.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(idx_g.split("---\n", 2)[1])
    assert fm["article_count"] == 2
    assert "2026-06-09" in idx_g  # max updated
    assert "`x`: 2" in idx_g  # Tag-Häufigkeit
    assert (vault / "02_Webentwicklung" / "_index.md").exists()
    # nur genutzte Ordner haben ein _index
    assert not (vault / "03_Betriebssysteme" / "_index.md").exists()


# === idempotenz ===============================================================


def _sha_map(vault: Path) -> dict[str, str]:
    out = {}
    for p in sorted(vault.rglob("*.md")):
        out[str(p.relative_to(vault))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_idempotent_second_run_byte_identical(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", related=["beta"])
    _make_draft(drafts, "b", slug="beta", category="webentwicklung")
    _run(vault_env, force=True)
    first = _sha_map(vault)
    _run(vault_env, force=True)
    second = _sha_map(vault)
    assert first == second


def test_skip_when_input_unchanged(vault_env) -> None:
    drafts, _, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha")
    _run(vault_env, force=True)
    summary = _run(vault_env)  # ohne force, gleicher Input
    assert summary["skipped"] is True


# === no-dups ==================================================================


def test_no_sha256_duplicates_in_vault(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    for i in range(5):
        _make_draft(
            drafts, f"d{i}", slug=f"slug-{i}", category="grundlagen", body=f"# T{i}\n\nB{i}\n"
        )
    _run(vault_env, force=True)
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in _all_vault_md(vault)]
    assert len(hashes) == len(set(hashes))


# === gedanken-empty ===========================================================


def test_gedanken_folder_stays_empty(vault_env) -> None:
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", category="grundlagen")
    _run(vault_env, force=True)
    gedanken = vault / "15_Gedanken"
    assert not gedanken.exists() or not any(gedanken.iterdir())


# === Fehler-Handling ==========================================================


def test_invalid_frontmatter_logged_not_aborted(vault_env) -> None:
    drafts, vault, out, _ = vault_env
    _make_draft(drafts, "ok", slug="gut")
    # kaputtes Draft: fehlendes Pflichtfeld (kein type/confidence etc.)
    bad = drafts / "CK_bad.md"
    bad.write_text("---\ntitle: nur titel\nslug: schlecht\n---\n\n# x\n", encoding="utf-8")
    (drafts / "CK_bad.body.md").write_text("# x\n", encoding="utf-8")
    summary = _run(vault_env, force=True)
    assert summary["articles"] == 1
    assert summary["errors"] == 1
    assert (vault / "01_Grundlagen" / "gut.md").exists()
    rows = [
        json.loads(ln)
        for ln in (out / "phase9_errors.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert rows[0]["stem"] == "CK_bad"
