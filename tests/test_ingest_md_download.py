"""Tests für pipeline/ingest_md_download.py (WP2 — Browser-Download-Ingest).

Alles läuft in temp-Pfaden; ``_ingest/`` wird nie verändert (read-only-Garantie).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pipeline.ingest_md_download import (
    detect_asset_dir,
    has_local_image_links,
    ingest_all,
    ingest_one,
    quell_slug,
)
from pipeline.phase_1_inventory import _filename_to_slug

# Minimales 1x1-PNG (Bytes-Inhalt egal, nur != zwischen Bildern).
_PNG_A = b"\x89PNG\r\n\x1a\nAAAA"
_PNG_B = b"\x89PNG\r\n\x1a\nBBBB"


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    """Legt _ingest/, input/, input/_assets/, _quarantine/ in tmp an."""
    ingest = tmp_path / "_ingest"
    input_dir = tmp_path / "input"
    assets = input_dir / "_assets"
    quarantine = ingest / "_quarantine"
    ingest.mkdir()
    return {
        "ingest": ingest,
        "input": input_dir,
        "assets": assets,
        "quarantine": quarantine,
    }


def _make_fixture_a(ingest: Path) -> Path:
    """Fixture (a): .md + <name>_files/ mit 2 Bildern, beide lokal eingebettet."""
    md = ingest / "Mein Artikel.md"
    files = ingest / "Mein Artikel_files"
    files.mkdir()
    (files / "img1.png").write_bytes(_PNG_A)
    (files / "img2.png").write_bytes(_PNG_B)
    md.write_text(
        "# Titel\n\n"
        "![erstes](Mein%20Artikel_files/img1.png)\n\n"
        "Text dazwischen.\n\n"
        "![zweites](Mein Artikel_files/img2.png)\n",
        encoding="utf-8",
    )
    return md


def _make_fixture_b(ingest: Path) -> Path:
    """Fixture (b): .md mit externem http-Bild + 1 lokalem Bild."""
    md = ingest / "Notiz.md"
    files = ingest / "Notiz_files"
    files.mkdir()
    (files / "local.png").write_bytes(_PNG_A)
    md.write_text(
        "# Notiz\n\n"
        "![remote](https://example.com/remote.png)\n\n"
        "![lokal](Notiz_files/local.png)\n\n"
        "[normaler Link](https://example.com/seite) bleibt auch.\n",
        encoding="utf-8",
    )
    return md


# --- Slug -------------------------------------------------------------------


def test_slug_uses_phase1_logic() -> None:
    """Quell-Slug-Präfix entspricht der Phase-1-Slug-Logik."""
    assert quell_slug("Mein Artikel") == _filename_to_slug("Mein Artikel")
    assert quell_slug("Lösung Übersicht") == "loesung-uebersicht"


def test_slug_60_cap() -> None:
    """Lange Namen werden auf 60 Zeichen gekappt."""
    long_name = "wort-" * 30
    assert len(quell_slug(long_name)) <= 60


# --- Detection --------------------------------------------------------------


def test_detect_name_files_dir(dirs: dict[str, Path]) -> None:
    md = _make_fixture_a(dirs["ingest"])
    asset_dir, status = detect_asset_dir(md)
    assert status == "ok"
    assert asset_dir == dirs["ingest"] / "Mein Artikel_files"


def test_detect_ambiguous(dirs: dict[str, Path]) -> None:
    """Zwei spezifische Kandidaten → ambiguous (nicht raten)."""
    md = dirs["ingest"] / "Doc.md"
    md.write_text("![x](Doc_files/a.png)", encoding="utf-8")
    (dirs["ingest"] / "Doc").mkdir()
    (dirs["ingest"] / "Doc_files").mkdir()
    (dirs["ingest"] / "Doc" / "a.png").write_bytes(_PNG_A)
    _, status = detect_asset_dir(md)
    assert status == "ambiguous"


def test_detect_none(dirs: dict[str, Path]) -> None:
    md = dirs["ingest"] / "Solo.md"
    md.write_text("# nur Text", encoding="utf-8")
    _, status = detect_asset_dir(md)
    assert status == "none"


# --- Rewrite ----------------------------------------------------------------


def test_has_local_image_links() -> None:
    assert has_local_image_links("![a](local.png)") is True
    assert has_local_image_links("![a](https://x/y.png)") is False
    assert has_local_image_links("[link](local.html)") is False


def test_rewrite_external_untouched(dirs: dict[str, Path]) -> None:
    """Externe http(s)-URLs und normale Links bleiben unverändert."""
    md = _make_fixture_b(dirs["ingest"])
    res = ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    out = (dirs["input"] / "Notiz.md").read_text(encoding="utf-8")
    assert "![remote](https://example.com/remote.png)" in out
    assert "[normaler Link](https://example.com/seite)" in out
    # lokales Bild → pfad-freier Embed mit Quell-Slug-Präfix
    assert f"![[{res.slug}__local.png]]" in out


def test_rewrite_local_to_wikilink(dirs: dict[str, Path]) -> None:
    md = _make_fixture_a(dirs["ingest"])
    res = ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    out = (dirs["input"] / "Mein Artikel.md").read_text(encoding="utf-8")
    assert f"![[{res.slug}__img1.png]]" in out
    assert f"![[{res.slug}__img2.png]]" in out
    assert "](Mein" not in out  # kein Pfad-Embed mehr


# --- Einspeisen + Naming ----------------------------------------------------


def test_assets_renamed_with_slug_prefix(dirs: dict[str, Path]) -> None:
    md = _make_fixture_a(dirs["ingest"])
    res = ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    slug = _filename_to_slug("Mein Artikel")
    assert (dirs["assets"] / f"{slug}__img1.png").exists()
    assert (dirs["assets"] / f"{slug}__img2.png").exists()
    assert set(res.renamed.values()) == {f"{slug}__img1.png", f"{slug}__img2.png"}


def test_collision_gets_numeric_suffix(dirs: dict[str, Path]) -> None:
    """Gleicher Basename in Unterordnern → numerisches Suffix."""
    md = dirs["ingest"] / "Doc.md"
    files = dirs["ingest"] / "Doc_files"
    (files / "sub1").mkdir(parents=True)
    (files / "sub2").mkdir(parents=True)
    (files / "sub1" / "img.png").write_bytes(_PNG_A)
    (files / "sub2" / "img.png").write_bytes(_PNG_B)
    md.write_text(
        "![a](Doc_files/sub1/img.png)\n![b](Doc_files/sub2/img.png)\n",
        encoding="utf-8",
    )
    ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    # Gleicher Basename → ein Asset bekommt das numerische Suffix.
    names = sorted(p.name for p in dirs["assets"].iterdir())
    assert names == ["doc__img.png", "doc__img_2.png"]


# --- Quarantäne -------------------------------------------------------------


def test_quarantine_when_no_asset_dir_but_links(dirs: dict[str, Path]) -> None:
    """Lokale Bild-Links, aber kein Asset-Ordner → Quarantäne, kein input/."""
    md = dirs["ingest"] / "Kaputt.md"
    md.write_text("![x](irgendwo/bild.png)", encoding="utf-8")
    res = ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    assert res.status == "quarantined"
    assert (dirs["quarantine"] / "Kaputt.md").exists()
    assert not (dirs["input"] / "Kaputt.md").exists()


def test_no_links_just_copies(dirs: dict[str, Path]) -> None:
    """Keine Bild-Links → .md wird ohne Asset-Ordner eingespeist (keine Quarantäne)."""
    md = dirs["ingest"] / "Text.md"
    md.write_text("# nur Text, kein Bild", encoding="utf-8")
    res = ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    assert res.status == "ingested"
    assert (dirs["input"] / "Text.md").exists()


# --- Safety + Idempotenz ----------------------------------------------------


def test_ingest_is_read_only_on_source(dirs: dict[str, Path]) -> None:
    """_ingest/ bleibt unverändert (Original-Download erhalten)."""
    md = _make_fixture_a(dirs["ingest"])
    before = {p: p.read_bytes() for p in dirs["ingest"].rglob("*") if p.is_file()}
    ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=False)
    after = {p: p.read_bytes() for p in dirs["ingest"].rglob("*") if p.is_file()}
    assert before == after


def test_idempotent(dirs: dict[str, Path]) -> None:
    """Zweiter Lauf erzeugt identische Outputs (kein Suffix-Aufschaukeln)."""
    _make_fixture_a(dirs["ingest"])
    _make_fixture_b(dirs["ingest"])

    ingest_all(dirs["ingest"], dirs["input"], dirs["assets"], dirs["quarantine"])
    snap1 = {
        p.relative_to(dirs["input"]): p.read_bytes()
        for p in dirs["input"].rglob("*")
        if p.is_file()
    }
    ingest_all(dirs["ingest"], dirs["input"], dirs["assets"], dirs["quarantine"])
    snap2 = {
        p.relative_to(dirs["input"]): p.read_bytes()
        for p in dirs["input"].rglob("*")
        if p.is_file()
    }
    assert snap1 == snap2


def test_dry_run_writes_nothing(dirs: dict[str, Path]) -> None:
    md = _make_fixture_a(dirs["ingest"])
    ingest_one(md, dirs["input"], dirs["assets"], dirs["quarantine"], dry_run=True)
    assert not dirs["input"].exists() or not any(dirs["input"].rglob("*"))
