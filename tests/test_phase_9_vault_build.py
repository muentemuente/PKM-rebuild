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


# === Assets (WP3) =============================================================


def _asset_dirs(temp_dir: Path) -> tuple[Path, Path]:
    """Legt input/_assets (Quelle) + output/_assets (Ziel) unter temp_dir an."""
    src = temp_dir / "input" / "_assets"
    dst = temp_dir / "output" / "_assets"
    src.mkdir(parents=True)
    return src, dst


def test_referenced_asset_copied_and_embed_verbatim(vault_env, temp_dir: Path) -> None:
    drafts, vault, _, _ = vault_env
    src, dst = _asset_dirs(temp_dir)
    (src / "slug__bild.png").write_bytes(b"\x89PNG-fake-bytes")
    _make_draft(drafts, "a", slug="alpha", body="# Alpha\n\n![[slug__bild.png]]\n")
    summary = _run(vault_env, force=True, assets_src=src, assets_dst=dst)
    # Asset kopiert, Name unverändert, Bytes identisch
    assert (dst / "slug__bild.png").read_bytes() == b"\x89PNG-fake-bytes"
    assert summary["assets_copied"] == 1
    assert summary["missing_assets"] == 0
    # Embed bleibt im gebauten Body wörtlich erhalten
    built = (vault / "01_Grundlagen" / "alpha.md").read_text(encoding="utf-8")
    assert "![[slug__bild.png]]" in built


def test_missing_asset_logged_not_aborted(vault_env, temp_dir: Path) -> None:
    drafts, vault, out, _ = vault_env
    src, dst = _asset_dirs(temp_dir)  # leer → Asset fehlt
    _make_draft(drafts, "a", slug="alpha", body="# Alpha\n\n![[fehlt.png]]\n")
    summary = _run(vault_env, force=True, assets_src=src, assets_dst=dst)
    # Build nicht abgebrochen, Artikel da, Embed bleibt (Obsidian zeigt broken)
    assert summary["articles"] == 1
    assert summary["missing_assets"] == 1
    assert (vault / "01_Grundlagen" / "alpha.md").exists()
    rows = [
        json.loads(ln)
        for ln in (out / "phase9_missing_assets.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert rows[0] == {"source_slug": "alpha", "asset": "fehlt.png", "reason": "asset_not_found"}


def test_orphan_asset_logged(vault_env, temp_dir: Path) -> None:
    drafts, _, out, _ = vault_env
    src, dst = _asset_dirs(temp_dir)
    (src / "genutzt.png").write_bytes(b"x")
    (src / "waise.png").write_bytes(b"y")  # von keinem Body referenziert
    _make_draft(drafts, "a", slug="alpha", body="# Alpha\n\n![[genutzt.png]]\n")
    summary = _run(vault_env, force=True, assets_src=src, assets_dst=dst)
    assert summary["orphan_assets"] == 1
    rows = [
        json.loads(ln)
        for ln in (out / "phase9_orphan_assets.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert rows[0]["asset"] == "waise.png"


def test_asset_copy_idempotent(vault_env, temp_dir: Path) -> None:
    drafts, _, _, _ = vault_env
    src, dst = _asset_dirs(temp_dir)
    (src / "slug__bild.png").write_bytes(b"\x89PNG-fake-bytes")
    _make_draft(drafts, "a", slug="alpha", body="# Alpha\n\n![[slug__bild.png]]\n")
    _run(vault_env, force=True, assets_src=src, assets_dst=dst)
    before = (dst / "slug__bild.png").read_bytes()
    summary = _run(vault_env, force=True, assets_src=src, assets_dst=dst)
    assert (dst / "slug__bild.png").read_bytes() == before
    # zweiter Lauf: nichts neu kopiert (unchanged), kein Re-Write
    assert summary["assets_copied"] == 0


def test_no_assets_without_dirs(vault_env) -> None:
    """Ohne assets_src/dst läuft der Build wie bisher (kein Asset-Handling)."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body="# Alpha\n\n![[slug__bild.png]]\n")
    summary = _run(vault_env, force=True)
    assert summary["assets_copied"] == 0
    assert summary["missing_assets"] == 0
    assert (vault / "01_Grundlagen" / "alpha.md").exists()


# === S1 / G1: Safe-Tier-repair_text am Body-Chokepoint (Phase 9) ==============

# Body mit Safe-Tier-Defekten (entboldbares Heading + PUA-Wrapper + Junk-Heading)
# UND einem Review-Tier-Defekt (turn…-Token), der NICHT angefasst werden darf.
_DEFECT_BODY = (
    "# Unbenannt\n\n"  # Junk-Heading → Safe-Tier: entfernt
    "## **Wichtig**\n\n"  # `**`-Heading → Safe-Tier: entboldet
    "Ein markierter Begriff.\n\n"  # PUA-Wrapper → Safe-Tier: bereinigt
    "Ein Leak turn0view0 hier.\n"  # turn…-Token → Review-Tier: bleibt
)


def _built_body(vault: Path, slug: str = "alpha", folder: str = "01_Grundlagen") -> str:
    """Body-Teil (nach Frontmatter) der gebauten Datei."""
    text = (vault / folder / f"{slug}.md").read_text(encoding="utf-8")
    return text.split("\n---\n\n", 1)[1]


def test_repair_on_build_applies_safe_tier(vault_env) -> None:
    """Default an: Safe-Tier-Fixes landen im gebauten output/-Body, Zähler stimmt."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body=_DEFECT_BODY)
    summary = _run(vault_env, force=True)
    body = _built_body(vault)
    assert "## Wichtig" in body  # entboldet
    assert "**Wichtig**" not in body
    assert "" not in body  # PUA-Open bereinigt
    assert "" not in body  # PUA-Close bereinigt
    assert "# Unbenannt" not in body  # Junk-Heading entfernt
    assert summary["repaired_files"] == 1


def test_repair_on_build_skips_review_tier(vault_env) -> None:
    """Review-Tier (turn…-Token, url-Mash) wird NICHT automatisch angewandt."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body=_DEFECT_BODY)
    _run(vault_env, force=True)
    body = _built_body(vault)
    assert "turn0view0" in body  # Review-Tier bleibt unangetastet


def test_repair_on_build_lossless(vault_env) -> None:
    """Verlustfrei: inhaltlicher Text bleibt erhalten, nur Defekt-Marker verschwinden."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body=_DEFECT_BODY)
    _run(vault_env, force=True)
    body = _built_body(vault)
    assert "markierter" in body  # Wort im PUA-Wrapper bleibt
    assert "Wichtig" in body
    assert "Ein Leak" in body
    assert "hier." in body


def test_repair_on_build_idempotent(vault_env) -> None:
    """2. Build (force) ist byte-identisch — Safe-Tier ist idempotent."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body=_DEFECT_BODY)
    _run(vault_env, force=True)
    first = (vault / "01_Grundlagen" / "alpha.md").read_text(encoding="utf-8")
    _run(vault_env, force=True)
    second = (vault / "01_Grundlagen" / "alpha.md").read_text(encoding="utf-8")
    assert first == second


def test_repair_off_keeps_defects(vault_env) -> None:
    """Abschaltbar via Flag: repair_on_build=False baut die Defekte unverändert."""
    drafts, vault, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body=_DEFECT_BODY)
    summary = _run(vault_env, force=True, repair_on_build=False)
    body = _built_body(vault)
    assert "**Wichtig**" in body  # nicht entboldet
    assert "" in body  # PUA bleibt
    assert "# Unbenannt" in body  # Junk bleibt
    assert summary["repaired_files"] == 0


def test_repair_on_build_does_not_mutate_source_drafts(vault_env) -> None:
    """Input read-only: die Quell-Drafts (drafts/) bleiben byte-identisch.

    Der Hook wirkt ausschließlich auf den nach output/ geschriebenen Body —
    nie auf die Quelle (und damit erst recht nicht auf den Live-Vault, der gar
    nicht als Ziel übergeben wird).
    """
    drafts, _, _, _ = vault_env
    _make_draft(drafts, "a", slug="alpha", body=_DEFECT_BODY)
    md_before = (drafts / "CK_a.md").read_text(encoding="utf-8")
    body_before = (drafts / "CK_a.body.md").read_text(encoding="utf-8")
    _run(vault_env, force=True)
    assert (drafts / "CK_a.md").read_text(encoding="utf-8") == md_before
    assert (drafts / "CK_a.body.md").read_text(encoding="utf-8") == body_before
