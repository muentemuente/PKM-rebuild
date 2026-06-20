"""Tests für pipeline/vault_audit.py — WP4 Audit/Repair-Tooling.

Kern-Garantien: (1) jede Detektionsregel hat clean/defekt-Fälle, (2) Safe-Repair
ist idempotent und lässt Schutzbereiche (Code, Frontmatter) unberührt, (3) der
Dangling-Klassifikator trennt intendierte Stubs von echt-defekten Links.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import vault_audit as va

# === Helfer ===================================================================

_FM = (
    "---\n"
    "title: Test\n"
    "slug: {slug}\n"
    "aliases: {aliases}\n"
    "summary: x\n"
    "type: knowledge-article\n"
    "doc_role:\n  - reference\n"
    "category: grundlagen\n"
    "tags: []\n"
    "related: {related}\n"
    "used_in: []\n"
    "sources_docs:\n  - D_x\n"
    "source_chunks:\n  - D_x-S0000\n"
    "status: draft\n"
    "review_status: ai_drafted\n"
    "confidence: medium\n"
    "doc_version: 0.1.0\n"
    "created: '2026-06-18'\n"
    "updated: '2026-06-18'\n"
    "last_synthesized: '2026-06-18'\n"
    "prompt_version: v1\n"
    "---\n"
)


def _doc(slug: str, body: str = "# Titel\n", aliases: str = "[]", related: str = "[]") -> str:
    return _FM.format(slug=slug, aliases=aliases, related=related) + body


def _rules(findings: list[va.Finding]) -> set[str]:
    return {f.rule for f in findings}


def _make_vault(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


# === split_frontmatter ========================================================


def test_split_frontmatter_roundtrip() -> None:
    fm, body, start = va.split_frontmatter(_doc("a", "# H\n\ntext\n"))
    assert fm is not None
    assert "slug: a" in fm
    assert body.startswith("# H")
    assert start > 1


def test_split_frontmatter_none_without_fm() -> None:
    fm, body, start = va.split_frontmatter("# Nur Body\n")
    assert fm is None
    assert body == "# Nur Body\n"
    assert start == 1


# === Regel 1: Frontmatter ====================================================


def test_frontmatter_clean() -> None:
    fm, err = va.parse_frontmatter(va.split_frontmatter(_doc("a"))[0] or "")
    assert va.check_frontmatter("a.md", fm, err) == []


def test_frontmatter_missing_and_enum_and_slug() -> None:
    fm = {"title": "x", "slug": "Bad Slug", "type": "nope", "category": "grundlagen"}
    findings = va.check_frontmatter("a.md", fm, None)
    msgs = " ".join(f.message for f in findings)
    assert "fehlende Pflichtfelder" in msgs
    assert "type='nope'" in msgs
    assert "slug ungültig" in msgs


def test_frontmatter_slug_mismatch_filename() -> None:
    fm, _ = va.parse_frontmatter(va.split_frontmatter(_doc("a"))[0] or "")
    findings = va.check_frontmatter("anders.md", fm, None)
    assert any("≠ Dateiname" in f.message for f in findings)


def test_frontmatter_unparsable() -> None:
    findings = va.check_frontmatter("a.md", None, "yaml_error")
    assert findings
    assert findings[0].severity == "error"


# === Regel 2: Wikilinks ======================================================


def test_wikilink_classification(tmp_path: Path) -> None:
    vault = _make_vault(
        tmp_path,
        {
            "01_Grundlagen/quelle.md": _doc(
                "quelle",
                "## Inhalt\n\n[[ziel]] und [[fehlt-wirklich]].\n\n"
                "## Verwandte Themen\n\n- [[stub-only]]\n\n"
                "## Code\n\n```\n[[im-code]]\n```\n",
            ),
            "01_Grundlagen/ziel.md": _doc("ziel"),
        },
    )
    index = va.build_index(vault)
    findings = va.check_wikilinks(
        "01_Grundlagen/quelle.md", index.audit_files["01_Grundlagen/quelle.md"], index
    )
    rules = _rules(findings)
    assert "wikilink" in rules  # fehlt-wirklich = defekt
    assert "wikilink-stub" in rules  # stub-only unter "Verwandte Themen"
    msgs = " ".join(f.message for f in findings)
    assert "ziel" not in msgs  # auflösbar → kein Befund
    assert "im-code" not in msgs  # in Code-Fence → ignoriert


def test_wikilink_inline_code_masked(tmp_path: Path) -> None:
    # `[[…]]` in Inline-Code ist Syntax-Demo → kein Dangling; echtes Prosa-[[…]] bleibt Defekt.
    vault = _make_vault(
        tmp_path,
        {
            "a.md": _doc(
                "a",
                "Beispiel-Syntax: `[[Beispiel-Notiz]]` zeigt einen Wikilink.\n\n"
                "Echter defekter Link: [[fehlt-wirklich]].\n\n"
                "Prosa neben `inline code` mit [[auch-defekt]] im Fließtext.\n",
            )
        },
    )
    index = va.build_index(vault)
    findings = va.check_wikilinks("a.md", index.audit_files["a.md"], index)
    msgs = " ".join(f.message for f in findings)
    assert "Beispiel-Notiz" not in msgs  # in Inline-Code → maskiert, kein Befund
    assert "fehlt-wirklich" in msgs  # Prosa → weiterhin Dangling
    assert "auch-defekt" in msgs  # Prosa neben (nicht in) Inline-Code → weiterhin Dangling


def test_wikilink_alias_resolves(tmp_path: Path) -> None:
    vault = _make_vault(
        tmp_path,
        {
            "a.md": _doc("a", "[[Mein Alias]]\n"),
            "b.md": _doc("b", aliases="[Mein Alias]"),
        },
    )
    index = va.build_index(vault)
    findings = va.check_wikilinks("a.md", index.audit_files["a.md"], index)
    assert findings == []  # über Alias auflösbar


# === Regel 3: Headings =======================================================


def test_heading_defects() -> None:
    text = _doc(
        "a",
        "# Titel\n\n## **Fett**\n\n### Klar\n\n# Unbenannt\n\nProsa-Zeile\n---\n",
    )
    findings = va.check_headings("a.md", text)
    rules = _rules(findings)
    assert "heading-bold" in rules
    assert "heading-junk" in rules
    assert "heading-setext" in rules


def test_heading_literal_newline() -> None:
    findings = va.check_headings("a.md", _doc("a", "# Erste\\nZweite\n"))
    assert any(f.rule == "heading-newline" for f in findings)


def test_heading_bold_inside_fence_ignored() -> None:
    findings = va.check_headings("a.md", _doc("a", "# Ok\n\n```\n## **nicht-heading**\n```\n"))
    assert all(f.rule != "heading-bold" for f in findings)


# === Regel 4: Fences =========================================================


def test_fence_untagged_detected() -> None:
    findings = va.check_fences("a.md", _doc("a", "```\nplain text\n```\n"))
    assert any(f.rule == "fence-untagged" for f in findings)


def test_fence_tagged_clean() -> None:
    findings = va.check_fences("a.md", _doc("a", "```python\nprint(1)\n```\n"))
    assert findings == []


def test_detect_fence_lang() -> None:
    cases = {
        "python": ["```", "def f():", "    return 1", "```"],
        "bash": ["```", "$ pip install x", "```"],
        "regex": ["```", "/\\[\\[.*\\]\\]/  # wikilinks", "```"],
        "json": ["```", '{"a": 1, "b": 2}', "```"],
        "toml": ["```", "[section]", "key = 1", "```"],
        "yaml": ["```", "title: x", "count: 3", "```"],
        "md": ["```", "| A | B |", "|---|---|", "```"],
        "text": ["```", "Dies ist ein ganzer Satz mit Woertern.", "```"],
    }
    for lang, block in cases.items():
        assert va.detect_fence_lang(block, 0) == lang, lang


def test_detect_fence_lang_ambiguous_none() -> None:
    # Shortcut mit Sonderzeichen + zu kurze Zeile -> kein eindeutiges Signal
    assert va.detect_fence_lang(["```", "Cmd/Ctrl + Shift + F", "```"], 0) is None
    assert va.detect_fence_lang(["```", "ab cd", "```"], 0) is None


def test_detect_fence_lang_v2() -> None:
    # v2: verschärfte Heuristik (bash-Tools, sql, html, md-Listen) — je Repräsentant
    cases = {
        "bash": ["```", "npm install left-pad", "docker compose up", "```"],
        "sql": ["```", "SELECT name FROM users WHERE id = 1;", "```"],
        "html": ["```", '<div class="x">', "  <p>Hallo</p>", "</div>", "```"],
        "md": ["```", "- Punkt eins", "- Punkt zwei", "- Punkt drei", "```"],
    }
    for lang, block in cases.items():
        assert va.detect_fence_lang(block, 0) == lang, lang


def test_detect_fence_lang_v2_negatives() -> None:
    # edit-Fälle bleiben None: ASCII-Box-Diagramm, JS-$0 (kein bash), Excel-Formel+Kommentar
    box = ["```", "┌────────┐", "│ Client │", "└────────┘", "```"]
    assert va.detect_fence_lang(box, 0) is None
    js = ["```", "# Element finden", "document.querySelector('h1')", "$0", "```"]
    assert va.detect_fence_lang(js, 0) is None
    excel = ["```", "=LEN(A1)", "# 6 Zeichen", "```"]
    assert va.detect_fence_lang(excel, 0) is None
    # yaml-artiger Block (key: + Liste) wird nicht als md getaggt
    assert va.detect_fence_lang(["```", "tags:", "  - a", "  - b", "```"], 0) != "md"


# === Regel 5: Korruption =====================================================


def test_corruption_scan() -> None:
    text = _doc(
        "a",
        "normal\nturn12view34 leak\n\ue200pua\nsiehe <Text>https://x.io\n\u041a\u0438\u0440 hier\n",
    )
    rules = _rules(va.check_corruption("a.md", text))
    assert {
        "corruption-token",
        "corruption-pua",
        "corruption-urlmash",
        "corruption-script",
    } <= rules


def test_corruption_clean() -> None:
    assert va.check_corruption("a.md", _doc("a", "saubere ASCII-Prosa.\n")) == []


# === Regel 6/7/8/9 (Vault-Ebene) =============================================


def test_alias_collision(tmp_path: Path) -> None:
    vault = _make_vault(
        tmp_path,
        {"a.md": _doc("a", aliases="[Gemeinsam]"), "b.md": _doc("b", aliases="[Gemeinsam]")},
    )
    index = va.build_index(vault)
    findings = va.check_alias_collisions(index)
    assert any("gemeinsam" in f.message.lower() for f in findings)


def test_doc_count_and_reconcile(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, {"a.md": _doc("a"), "_attic/old.md": _doc("old")})
    index = va.build_index(vault)
    counts = va.doc_count(index, vault)
    assert counts["content"] == 1
    assert counts["attic"] == 1
    findings = va.reconcile_doc_count(counts, baseline=(1, 1))
    assert all(f.rule == "doc-count" for f in findings)


def test_quarantine_unparsable(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, {"broken.md": "---\n: : bad yaml\n: :\n---\n# x\n"})
    findings = va.audit_vault(vault, baseline=(1, 0))
    assert any(f.rule in ("quarantine", "frontmatter") and f.severity == "error" for f in findings)


def test_cross_link_candidates(tmp_path: Path) -> None:
    md = tmp_path / "synthesis_candidates.md"
    md.write_text("# x\n\n## SC_001 — 5 Docs\n\n## SC_002 — 3 Docs\n", encoding="utf-8")
    findings = va.read_cross_link_candidates(md)
    assert len([f for f in findings if "SC_0" in f.message]) == 2


def test_excludes_templates_and_attic(tmp_path: Path) -> None:
    vault = _make_vault(
        tmp_path,
        {
            "01_Grundlagen/artikel-formatierung.md": _doc("artikel-formatierung"),
            "_attic/x.md": _doc("x"),
            "00_Meta/tag-system.md": _doc("tag-system"),
            "01_Grundlagen/echt.md": _doc("echt"),
        },
    )
    index = va.build_index(vault)
    assert set(index.audit_files) == {"01_Grundlagen/echt.md"}


# === Repair (Safe-Tier) ======================================================


def test_repair_debold_and_idempotent() -> None:
    text = _doc("a", "# Ok\n\n## **Fett**\n\n### **Auch fett**\n")
    once, actions = va.repair_text(text)
    assert "**" not in once.split("---\n", 2)[2]  # Body ohne **
    assert any("entboldet" in a for a in actions)
    twice, actions2 = va.repair_text(once)
    assert twice == once  # idempotent
    assert actions2 == []


def test_repair_clean_pua_lossless() -> None:
    text = _doc("a", "siehe \ue200cite\ue201 hier\n")
    out, actions = va.repair_text(text)
    assert "\ue200" not in out
    assert "\ue201" not in out
    assert "cite" in out  # verlustfrei: nur PUA-Wrapper raus
    assert any("PUA-Wrapper" in a for a in actions)


def test_repair_keeps_turn_token() -> None:
    # turn-Token-Leak ist verlustbehaftet -> NICHT im Safe-Tier, sondern Review-Patch
    text = _doc("a", "x citeturn29search5 y\n")
    out, actions = va.repair_text(text)
    assert "turn29search5" in out  # repair_text fasst es NICHT an
    assert all("Token" not in a for a in actions)
    patch = va.review_patches("a.md", text)
    assert patch
    assert any(line.startswith("-") and "turn29search5" in line for line in patch)


def test_repair_setext_decouple() -> None:
    text = _doc("a", "# Ok\n\nProsa-Zeile\n---\n\nweiter\n")
    out, actions = va.repair_text(text)
    assert "Prosa-Zeile\n\n---" in out  # entkoppelt
    assert any("Setext" in a for a in actions)
    twice, acts2 = va.repair_text(out)
    assert twice == out  # idempotent
    assert acts2 == []


def test_repair_junk_heading_removed() -> None:
    text = _doc("a", "# Ok\n\n# Unbenannt\n\nInhalt\n")
    out, actions = va.repair_text(text)
    assert "# Unbenannt" not in out
    assert "Inhalt" in out
    assert any("Junk-Heading" in a for a in actions)


def test_repair_keeps_url_mash() -> None:
    # url-Mashup ist an der URL/Prosa-Grenze nicht deterministisch (CANARY A-2.1)
    # -> NICHT im Safe-Tier, sondern Review-Patch (analog turn-Token).
    text = _doc("a", "siehe urlFigmahttps://www.figma.com hier\n")
    out, actions = va.repair_text(text)
    assert "urlFigmahttps://www.figma.com" in out  # repair_text fasst es NICHT an
    assert all("Mashup" not in a for a in actions)
    patch = va.review_patches("a.md", text)
    assert patch
    assert any(line.startswith("+") and "[Figma](https://www.figma.com)" in line for line in patch)


@pytest.mark.parametrize(
    "mashup",
    [
        # CANARY-Realfälle: beweisen die Nicht-Determinismus-Verschiebung in den Review-Tier.
        "urlFigmahttps://figma.com: weiter",  # Trailing-Doppelpunkt wird mitgegriffen
        "urlSetuphttps://affinity.serif.com/-Setup runter",  # angehängte Prosa verschluckt
        "urlDochttps://example.com, danach",  # Trailing-Komma wird mitgegriffen
    ],
)
def test_url_mash_is_review_only(mashup: str) -> None:
    text = _doc("a", f"{mashup}\n")
    out, actions = va.repair_text(text)
    assert out == text  # Safe-Tier lässt den Mashup unangetastet
    assert actions == []
    assert va.review_patches("a.md", text)  # erscheint als Review-Patch-Vorschlag


def test_repair_tag_fences_highconf() -> None:
    text = _doc("a", "# Ok\n\n```\ndef f():\n    return 1\n```\n")
    out, actions = va.repair_text(text)
    assert "```python" in out
    assert any("Fence" in a for a in actions)
    twice, _ = va.repair_text(out)
    assert twice == out  # idempotent (nicht doppelt taggen)


def test_repair_tag_fences_lowconf_untouched() -> None:
    text = _doc("a", "# Ok\n\n```\nCmd/Ctrl + Shift + F\n```\n")
    out, actions = va.repair_text(text)
    assert "```\nCmd/Ctrl" in out  # bleibt untagged (kein Signal)
    assert all("Fence" not in a for a in actions)


def test_repair_close_unclosed_fence() -> None:
    # genuin unclosed ```bash → schließt vor erster Leerzeile; Prosa/Heading wieder ausserhalb
    text = _doc("a", "# Ok\n\n```bash\nexport PATH=x\n\nMerktext\n\n## Weiter\n")
    out, actions = va.repair_text(text)
    assert any("unclosed" in a for a in actions)
    _, body, _ = va.split_frontmatter(out)
    assert body.count("```") % 2 == 0  # Fence-Parität jetzt gerade
    assert "```bash\nexport PATH=x\n```" in out  # nur die Code-Zeile im Block
    assert "## Weiter" in out  # Heading ausserhalb
    assert "```\n\nMerktext" in out  # Prosa ausserhalb
    twice, act2 = va.repair_text(out)
    assert twice == out  # idempotent
    assert act2 == []


def test_repair_balanced_fence_untouched() -> None:
    # inline-``` in Prosa (line-start balanciert) → KEIN Close eingefügt
    text = _doc("a", "# Ok\n\nNutze ``` zum Starten eines Codeblocks.\n\nNormaler Text.\n")
    out, actions = va.repair_text(text)
    assert all("unclosed" not in a for a in actions)
    assert out == text


def test_repair_preserves_code_and_frontmatter() -> None:
    text = _doc("a", "# Ok\n\n```\n## **bleibt**\n```\n")
    out, _ = va.repair_text(text)
    assert "## **bleibt**" in out  # ** in Code-Fence unangetastet
    assert out.split("\n---\n")[0] == text.split("\n---\n")[0]  # Frontmatter identisch


def test_repair_noop_on_clean() -> None:
    text = _doc("a", "# Sauber\n\nProsa.\n")
    out, actions = va.repair_text(text)
    assert out == text
    assert actions == []


# === Repair: bidirektionale related: ========================================


def test_bidirectional_related() -> None:
    files = {"a.md": _doc("a"), "b.md": _doc("b")}
    changed = va.add_bidirectional_related(files, [("a", "b")])
    assert set(changed) == {"a.md", "b.md"}
    assert "  - b" in changed["a.md"]
    assert "  - a" in changed["b.md"]
    # idempotent: zweiter Lauf auf den geänderten Files = keine Änderung
    again = va.add_bidirectional_related(changed, [("a", "b")])
    assert again == {}


def test_bidirectional_related_skips_unknown() -> None:
    files = {"a.md": _doc("a")}
    assert va.add_bidirectional_related(files, [("a", "fehlt")]) == {}


# === Review-Modus ============================================================


def test_review_patch_empty_for_safe_only() -> None:
    # reiner Safe-Fall (`**`-Heading) erzeugt KEINEN Review-Patch (laeuft ueber repair)
    assert va.review_patches("a.md", _doc("a", "## **Fett**\n")) == []


def test_review_patch_empty_for_clean() -> None:
    assert va.review_patches("a.md", _doc("a", "# Sauber\n")) == []


# === Audit-Orchestrierung (Smoke) ============================================


def test_audit_vault_smoke(tmp_path: Path) -> None:
    vault = _make_vault(
        tmp_path,
        {
            "01_Grundlagen/a.md": _doc("a", "# A\n\n## **Fett**\n\n[[fehlt]]\n"),
            "01_Grundlagen/b.md": _doc("b"),
        },
    )
    findings = va.audit_vault(vault, baseline=(2, 0))
    rules = _rules(findings)
    assert {"heading-bold", "wikilink", "doc-count"} <= rules
