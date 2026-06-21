"""G8 — der Sonderordner ``17_unsortiert`` bekommt IMMER ein ``_index.md``.

Auch ohne Artikel (leerer Auffang-Bucket). Struktur identisch zu regulären Clustern,
idempotent/byte-stabil bei wiederholtem Lauf. Läuft auf ``tmp_path`` — kein Live-Vault.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER, run_phase_9

_UNSORTED = CATEGORY_TO_FOLDER["unsortiert"]  # "17_unsortiert"

_FM: dict = {
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


def _make_draft(drafts: Path, stem: str, *, slug: str, category: str) -> None:
    fm = dict(_FM, slug=slug, category=category, title=f"Artikel {slug}", related=[])
    body = f"# {fm['title']}\n\nKörper von {slug}.\n"
    (drafts / f"CK_{stem}.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + body,
        encoding="utf-8",
    )
    (drafts / f"CK_{stem}.body.md").write_text(body, encoding="utf-8")


def _env(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    drafts, vault, out, backups = (tmp_path / n for n in ("drafts", "output", "work", "backups"))
    for d in (drafts, vault, out, backups):
        d.mkdir(parents=True)
    return drafts, vault, out, backups


def test_empty_unsorted_still_gets_index(tmp_path: Path) -> None:
    """Kein einziger unsortiert-Artikel → 17_unsortiert/_index.md wird trotzdem erzeugt."""
    drafts, vault, out, backups = _env(tmp_path)
    _make_draft(drafts, "eins", slug="eins", category="grundlagen")  # nur regulärer Cluster
    run_phase_9(drafts, vault, out, backups)

    idx = vault / _UNSORTED / "_index.md"
    assert idx.is_file()
    text = idx.read_text(encoding="utf-8")
    assert "type: index" in text
    assert f"folder: {_UNSORTED}" in text
    assert "article_count: 0" in text


def test_unsorted_index_structure_matches_regular_cluster(tmp_path: Path) -> None:
    """Sonderordner-Index trägt dieselben Sektionen wie ein regulärer Cluster."""
    drafts, vault, out, backups = _env(tmp_path)
    _make_draft(drafts, "eins", slug="eins", category="grundlagen")
    run_phase_9(drafts, vault, out, backups)

    regular = (vault / CATEGORY_TO_FOLDER["grundlagen"] / "_index.md").read_text(encoding="utf-8")
    unsorted = (vault / _UNSORTED / "_index.md").read_text(encoding="utf-8")
    for marker in (
        "type: index",
        "# Index — ",
        "## Artikel",
        "## Tag-Häufigkeiten",
        "| Titel | Slug | Status |",
    ):
        assert marker in regular, marker
        assert marker in unsorted, marker


def test_unsorted_index_lists_articles_when_present(tmp_path: Path) -> None:
    drafts, vault, out, backups = _env(tmp_path)
    _make_draft(drafts, "u1", slug="micro-eins", category="unsortiert")
    _make_draft(drafts, "u2", slug="micro-zwei", category="unsortiert")
    run_phase_9(drafts, vault, out, backups)

    text = (vault / _UNSORTED / "_index.md").read_text(encoding="utf-8")
    assert "article_count: 2" in text
    assert "`micro-eins`" in text
    assert "`micro-zwei`" in text


def test_unsorted_index_idempotent(tmp_path: Path) -> None:
    """2. Build erzeugt byte-identisches _index.md (kein Wall-Clock, idempotent)."""
    drafts, vault, out, backups = _env(tmp_path)
    _make_draft(drafts, "eins", slug="eins", category="grundlagen")
    run_phase_9(drafts, vault, out, backups)
    idx = vault / _UNSORTED / "_index.md"
    first = idx.read_text(encoding="utf-8")
    run_phase_9(drafts, vault, out, backups, force=True)
    assert idx.read_text(encoding="utf-8") == first
