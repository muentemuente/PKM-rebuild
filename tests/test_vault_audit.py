"""Tests für pipeline/vault_audit.py — WP4 Audit/Repair-Tooling.

Kern-Garantien: (1) jede Detektionsregel hat clean/defekt-Fälle, (2) Safe-Repair
ist idempotent und lässt Schutzbereiche (Code, Frontmatter) unberührt, (3) der
Dangling-Klassifikator trennt intendierte Stubs von echt-defekten Links.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
    py = ["```", "def f():", "    return 1", "```"]
    sh = ["```", "$ pip install x", "```"]
    rx = ["```", "/\\[\\[.*\\]\\]/  # wikilinks", "```"]
    txt = ["```", "einfach prosa ohne signal", "```"]
    assert va.detect_fence_lang(py, 0) == "python"
    assert va.detect_fence_lang(sh, 0) == "bash"
    assert va.detect_fence_lang(rx, 0) == "regex"
    assert va.detect_fence_lang(txt, 0) is None


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


def test_repair_clean_tokens() -> None:
    text = _doc("a", "leak turn1view2 und \ue200 ende\n")
    out, actions = va.repair_text(text)
    assert "turn1view2" not in out
    assert "\ue200" not in out
    assert any("Token/PUA" in a for a in actions)


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


def test_review_patch_for_fixable() -> None:
    patch = va.review_patches("a.md", _doc("a", "## **Fett**\n"))
    assert patch
    assert any(line.startswith("+") for line in patch)


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
