"""Tests für pipeline/fence_indented.py — WP3b indented→fenced Konversion.

Kern-Garantien: (1) indentierte Code-Beispiele werden in bare ``` ``` `` gelegt,
(2) verschachtelte Listen werden NICHT zu Code, (3) list-aware Platzierung erhält
geordnete Listen, (4) das Sicherheits-Gate weist nur textverlustfreie, danach safe +
idempotente Konversionen als ``convertible`` aus — sonst ``flagged``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import fence_indented as fi
from pipeline import format_vault as fv

_FIX = Path(__file__).parent / "fixtures" / "fence_indented"


# === Konversion (T1) ==========================================================


def test_top_level_indented_fenced_at_col0() -> None:
    src = "Beispiel:\n\n    # Config\n    key: value\n\nEnde.\n"
    out, blocks = fi.convert_indented(src)
    assert len(blocks) == 1
    assert "```\n# Config\nkey: value\n```" in out
    # bare Fence (kein Auto-Sprach-Tag)
    assert "```config" not in out
    assert "```yaml" not in out


def test_list_aware_keeps_ordered_list() -> None:
    """Code unter Item ``3.`` wird auf 3-Space gefenced → bleibt im Listen-Item."""
    src = "1. A\n\n2. B\n\n3. C:\n\n    # cmd\n    run x\n\nEnde.\n"
    out, blocks = fi.convert_indented(src)
    assert len(blocks) == 1
    assert "   ```\n   # cmd\n   run x\n   ```" in out  # 3-Space-Indent


def test_nested_list_not_fenced() -> None:
    """Verschachtelte Listen-Items (`    - x`) sind kein Code → unangetastet."""
    src = "- Punkt:\n\n    - sub eins\n    - sub zwei\n\nEnde.\n"
    out, blocks = fi.convert_indented(src)
    assert blocks == []
    assert "```" not in out


def test_existing_fence_untouched() -> None:
    src = "```python\n    x = 1\n```\n\nText.\n"
    out, blocks = fi.convert_indented(src)
    assert blocks == []
    assert out == src  # echte Fences + ihr Inhalt unverändert


def test_frontmatter_untouched() -> None:
    src = "---\ntitle: T\n---\n\n    # code\n    a = 1\n"
    out, _ = fi.convert_indented(src)
    assert out.startswith("---\ntitle: T\n---\n")


# === Sicherheits-Gate =========================================================


def test_golden_convertible_safe_and_idempotent() -> None:
    src = (_FIX / "list_nested.md").read_text(encoding="utf-8")
    outcome = fi.evaluate_file(src, "list_nested.md")
    assert outcome.status == "convertible", outcome.reasons
    # nach Konversion safe + idempotent
    assert fv.format_file(outcome.converted, "x").tier in ("safe", "unchanged")
    twice, _ = fv.format_markdown(outcome.final)
    assert twice == outcome.final  # 2. Formatlauf = no-op


def test_no_indented_block_is_flagged() -> None:
    src = "# Titel\n\nNur Prosa, kein indented Code.\n"
    outcome = fi.evaluate_file(src, "x.md")
    assert outcome.status == "flagged"
    assert any("kein indented" in r for r in outcome.reasons)


def test_textloss_free_content_preserved() -> None:
    src = (_FIX / "list_nested.md").read_text(encoding="utf-8")
    outcome = fi.evaluate_file(src, "list_nested.md")
    assert fi._content_lines(src) == fi._content_lines(outcome.converted)


# === Sprach-Heuristik (nur Vorschlag) =========================================


def test_suggest_language_basic() -> None:
    assert fi.suggest_language("SELECT * FROM t WHERE x > 1;") == "sql"
    assert fi.suggest_language('{ "a": 1, "b": 2 }') == "json"
    assert fi.suggest_language("<projekt><name>X</name></projekt>") == "xml"
    assert fi.suggest_language("id,vorname,nachname\n1,Max,Mustermann") == "csv"


def test_hash_comment_does_not_force_bash() -> None:
    """`#`-Kommentar ist sprach-übergreifend → kein bash-Fehlsignal (yaml gewinnt)."""
    assert fi.suggest_language("# Beispiel\nkey: value\nother: 1") == "yaml"


# === Mechanismus-Hinweis (flagged) ============================================


def test_mechanism_hint_setext() -> None:
    src = "---\ntitle: T\n---\n\nProsa-Zeile\n---\n\nText.\n"
    assert "Setext" in fi.mechanism_hint(src)


def test_mechanism_hint_example_frontmatter() -> None:
    src = "---\ntitle: T\n---\n\nText.\n\n---\nkey: val\n---\n"
    assert "Beispiel-Frontmatter" in fi.mechanism_hint(src)


# === Scan / Reports ===========================================================


def test_scan_and_reports(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    (vault).mkdir()
    (vault / "a.md").write_text("Beispiel:\n\n    # x\n    a = 1\n\nEnde.\n", encoding="utf-8")
    (vault / "b.md").write_text("# Nur Prosa\n\nText.\n", encoding="utf-8")

    outcomes = fi.scan_files(vault, ["a.md", "b.md"])
    by = {o.relpath: o.status for o in outcomes}
    assert by == {"a.md": "convertible", "b.md": "flagged"}

    fi.write_work(work, vault, outcomes)
    assert (work / "a.md").exists()  # Arbeitskopie (final) geschrieben
    assert (work / "a.md.diff").exists()
    assert (work / "b.md.flag").exists()
    # Vault (raw) unangetastet
    assert (vault / "a.md").read_text(encoding="utf-8").startswith("Beispiel:")

    report = fi.render_report(outcomes, vault)
    assert "Convertible" in report
    assert "Flagged" in report
    langs = fi.render_language_suggestions(outcomes)
    assert "a.md" in langs
