"""Tests für pipeline/format_vault.py — WP3a deterministische Formatierung.

Kern-Garantien: (1) Obsidian-Schutzbereiche bleiben byte-genau erhalten,
(2) Formatierung ist idempotent, (3) der Tier-Klassifikator flaggt jede Änderung
an einem Schutzbereich/Heading-Text/Code-Inhalt als ``unsafe``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import format_vault as fv

_GOLDEN = Path(__file__).parent / "fixtures" / "format_golden"


# === Golden-Files: Schutzbereiche bleiben erhalten + Idempotenz ===============


@pytest.mark.parametrize("name", ["wikilinks", "callouts", "codeblocks", "messy"])
def test_golden_idempotent(name: str) -> None:
    src = (_GOLDEN / f"{name}.md").read_text(encoding="utf-8")
    once, ok = fv.format_markdown(src)
    assert ok
    twice, _ = fv.format_markdown(once)
    assert twice == once  # idempotent (2. Lauf = no-op)


def test_wikilinks_and_embeds_survive() -> None:
    src = (_GOLDEN / "wikilinks.md").read_text(encoding="utf-8")
    out, ok = fv.format_markdown(src)
    assert ok
    for token in (
        "[[einfacher-link]]",
        "[[ziel|Alias]]",
        "[[note#Heading]]",
        "[[note#^block42]]",
        "![[diagramm.png]]",
        "![[doc.md#Abschnitt]]",
    ):
        assert token in out, f"Schutzbereich verloren: {token}"
    # mdformat hätte sie sonst escaped:
    assert "\\[[" not in out


def test_callouts_survive() -> None:
    src = (_GOLDEN / "callouts.md").read_text(encoding="utf-8")
    out, _ = fv.format_markdown(src)
    assert "[!note]" in out
    assert "[!warning]" in out
    tier, reasons = fv.classify(src, out)
    assert tier in (fv._TIER_SAFE, fv._TIER_UNCHANGED), reasons


def test_codeblock_contents_verbatim() -> None:
    src = (_GOLDEN / "codeblocks.md").read_text(encoding="utf-8")
    out, _ = fv.format_markdown(src)
    assert "x =1" in out
    assert "def  f( ):" in out
    assert 'echo  "spaces   bleiben"' in out
    # [[...]] im Code wird NICHT zu einem echten Link/escaped
    assert "[[das ist kein link]]" in out


def test_messy_is_safe_normalized() -> None:
    src = (_GOLDEN / "messy.md").read_text(encoding="utf-8")
    res = fv.format_file(src, "messy.md")
    assert res.tier == fv._TIER_SAFE
    assert res.added > 0 or res.removed > 0
    out, _ = fv.format_markdown(src)
    assert "#   Unsaubere" not in out  # Heading-Abstand normalisiert
    assert "# Unsaubere Abstände" in out  # Heading-TEXT erhalten


# === Tier-Klassifikator =======================================================


def test_thematic_break_stays_dashes() -> None:
    """E1: Thematic Break bleibt `---` (kein `___`); Idempotenz erhalten."""
    src = "# A\n\n---\n\nB\n\n***\n\nC\n"
    out, _ = fv.format_markdown(src)
    assert "---" in out
    assert "___" not in out
    assert "____" not in out
    assert "*" * 3 not in out  # *** ebenfalls zu --- normalisiert
    twice, _ = fv.format_markdown(out)
    assert twice == out  # idempotent


def test_underscores_in_code_not_converted() -> None:
    """`___`-Zeile im Code-Block bleibt unangetastet (fence-aware)."""
    src = "```\n___\nx = 1\n```\n"
    out, _ = fv.format_markdown(src)
    assert "___" in out  # im Code erhalten


def test_classify_unchanged() -> None:
    clean = "# Titel\n\nSauberer Text.\n"
    out, _ = fv.format_markdown(clean)
    assert fv.classify(clean, out)[0] == fv._TIER_UNCHANGED


def test_classify_safe() -> None:
    messy = "# Titel\n\n\n\nText   mit   Spaces.\n"
    out, _ = fv.format_markdown(messy)
    assert fv.classify(messy, out)[0] == fv._TIER_SAFE


def test_classify_unsafe_on_wikilink_change() -> None:
    original = "Text mit [[link-a]] und [[link-b]].\n"
    tampered = "Text mit [[link-a]].\n"  # ein Wikilink entfernt
    tier, reasons = fv.classify(original, tampered)
    assert tier == fv._TIER_UNSAFE
    assert any("wikilink" in r for r in reasons)


def test_classify_unsafe_on_heading_text_change() -> None:
    original = "# Altes Heading\n\nText.\n"
    tampered = "# Neues Heading\n\nText.\n"
    tier, reasons = fv.classify(original, tampered)
    assert tier == fv._TIER_UNSAFE
    assert any("heading-text" in r for r in reasons)


def test_classify_unsafe_on_codeblock_change() -> None:
    original = "```\nalt\n```\n"
    tampered = "```\nneu\n```\n"
    tier, reasons = fv.classify(original, tampered)
    assert tier == fv._TIER_UNSAFE
    assert any("codeblock" in r for r in reasons)


def test_classify_unsafe_on_frontmatter_value_change() -> None:
    original = "---\ntitle: A\n---\n\nText.\n"
    tampered = "---\ntitle: B\n---\n\nText.\n"
    tier, reasons = fv.classify(original, tampered)
    assert tier == fv._TIER_UNSAFE
    assert any("frontmatter" in r for r in reasons)


def test_trailing_ws_in_codeblock_is_safe_not_unsafe() -> None:
    """mdformat strippt Trailing-WS in Code (kosmetisch) → safe, nicht unsafe."""
    original = "```\nx = 1   \ny = 2\n```\n"  # Zeile mit Trailing-Spaces
    formatted, _ = fv.format_markdown(original)
    tier, reasons = fv.classify(original, formatted)
    assert tier in (fv._TIER_SAFE, fv._TIER_UNCHANGED), reasons
    assert "x = 1" in formatted  # Inhalt erhalten
    assert "y = 2" in formatted


def test_example_frontmatter_in_body_not_flagged_as_heading() -> None:
    """`---`-Zeilen im Body (Beispiel-Frontmatter) lösen keinen Heading-Fehlalarm aus."""
    original = (
        "---\ntitle: T\n---\n\n# Echtes Heading\n\n"
        'Beispiel:\n\n<!--\nslug: x\nprompt_version: "v1"\n-->\n\n---\n\nText.\n'
    )
    res = fv.format_file(original, "tmpl.md")
    assert res.tier in (fv._TIER_SAFE, fv._TIER_UNCHANGED), res.reasons


def test_indented_to_fenced_code_is_safe() -> None:
    """mdformat konvertiert indented Code → fenced (Code-Fence-Normalisierung = safe)."""
    original = "Beispiel:\n\n    x = 1\n    y = 2\n\nEnde.\n"
    formatted, _ = fv.format_markdown(original)
    assert "```" in formatted  # wurde gefenced
    tier, reasons = fv.classify(original, formatted)
    assert tier == fv._TIER_SAFE, reasons  # NICHT unsafe
    assert "x = 1" in formatted
    assert "y = 2" in formatted


def test_sentinel_collision_is_unsafe() -> None:
    text = f"Text mit {fv._SENTINEL_BASE}0000x und [[link]].\n"
    out, ok = fv.format_markdown(text)
    assert ok is False
    assert out == text  # unverändert zurück
    assert fv.classify(text, out, format_ok=ok)[0] == fv._TIER_UNSAFE


# === Scan (3-State raw → work) ================================================


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_scan_vault_writes_work_and_patches(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    _write(vault / "01_A" / "clean.md", "# Clean\n\nText.\n")
    _write(vault / "01_A" / "messy.md", "# Messy\n\n\n\nText   x.\n")
    _write(vault / "01_A" / "_index.md", "# Index\n\n\n\nwird übersprungen\n")

    report = fv.scan_vault(vault, work, write_work=True)
    counts = report.counts()
    assert counts["unchanged"] == 1
    assert counts["safe"] == 1
    # _index.md übersprungen
    assert {r.relpath for r in report.results} == {"01_A/clean.md", "01_A/messy.md"}
    # Vault (raw) unangetastet
    assert (vault / "01_A" / "messy.md").read_text(encoding="utf-8") == "# Messy\n\n\n\nText   x.\n"
    # work-Arbeitskopie der safe-Datei ist formatiert
    assert (work / "01_A" / "messy.md").read_text(encoding="utf-8") == "# Messy\n\nText x.\n"


def test_render_diff_report_has_tiers(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write(vault / "messy.md", "#  Titel\n\n\n\nText   x.\n")
    report = fv.scan_vault(vault, tmp_path / "work", write_work=False)
    text = fv.render_diff_report(report)
    assert "## Safe-auto" in text
    assert "## Unsafe" in text
    assert "Schutzbereiche" in text
