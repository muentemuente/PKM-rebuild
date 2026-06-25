"""Tests für den BRAIN_VAULT-Index-Regen (Ersatz für rebuild_indices.py, D-WP4-2)."""

from __future__ import annotations

from pathlib import Path

from pipeline.regenerate_indices import regenerate_indices


def _article(folder: Path, slug: str, title: str, updated: str = "2026-06-01") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.md").write_text(
        f"---\ntitle: {title}\nslug: {slug}\nstatus: draft\n"
        f"tags:\n  - demo\nupdated: '{updated}'\n---\n\n# {title}\n\nBody.\n",
        encoding="utf-8",
    )


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    # Inhalts-Ordner mit existierendem (stale) Index
    _article(vault / "01_Grundlagen", "alpha", "Alpha")
    _article(vault / "01_Grundlagen", "beta", "Beta")
    (vault / "01_Grundlagen" / "_index.md").write_text(
        "---\ntitle: 'Index: 01_Grundlagen'\ntype: index\nfolder: 01_Grundlagen\n"
        "article_count: 1\n---\n\n# Index — 01_Grundlagen\n\nveraltet\n",
        encoding="utf-8",
    )
    # Schutzbereich _attic mit Datei, ohne Index
    _article(vault / "_attic", "old", "Old")
    # 00_Meta mit Datei + Index (darf nicht angefasst werden)
    _article(vault / "00_Meta", "tmpl", "Template")
    (vault / "00_Meta" / "_index.md").write_text("eigenes Format\n", encoding="utf-8")
    return vault


def test_regenerate_detects_stale_dry_run(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    changes = regenerate_indices(vault, dry_run=True)
    by = {c.folder: c for c in changes}
    assert by["01_Grundlagen"].status == "regenerated"
    assert by["01_Grundlagen"].article_count == 2
    # dry-run schreibt nichts
    assert "veraltet" in (vault / "01_Grundlagen" / "_index.md").read_text(encoding="utf-8")


def test_apply_writes_phase9_format_and_is_idempotent(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    archive = tmp_path / "archive"
    regenerate_indices(vault, dry_run=False, archive_root=archive)
    idx = (vault / "01_Grundlagen" / "_index.md").read_text(encoding="utf-8")
    assert "type: index" in idx
    assert "article_count: 2" in idx
    assert "veraltet" not in idx
    # archive-before hat das alte File gesichert
    assert (archive / "01_Grundlagen" / "_index.md").exists()
    # 2. Lauf = idempotent (keine Änderung mehr)
    second = regenerate_indices(vault, dry_run=False, archive_root=archive)
    assert all(c.status == "unchanged" for c in second)


def test_protected_and_indexless_folders_untouched(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    regenerate_indices(vault, dry_run=False, archive_root=tmp_path / "a")
    # _attic bekommt keinen Index (Schutzbereich, hatte keinen)
    assert not (vault / "_attic" / "_index.md").exists()
    # 00_Meta-Index bleibt unverändert (eigenes Format)
    assert (vault / "00_Meta" / "_index.md").read_text(encoding="utf-8") == "eigenes Format\n"
    # _attic/00_Meta tauchen nicht als geänderte Ordner auf
    folders = {c.folder for c in regenerate_indices(vault, dry_run=True)}
    assert "_attic" not in folders
    assert "00_Meta" not in folders
