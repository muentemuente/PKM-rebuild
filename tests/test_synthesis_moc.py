"""Tests für pipeline/synthesis_moc.py — WP3b additive MOC-Generierung (D6, RV13)."""

from __future__ import annotations

from pathlib import Path

from pipeline.synthesis_moc import (
    ApprovedCluster,
    Member,
    build_moc,
    generate_mocs,
    load_member,
    strip_reasoning,
)

_CL = ApprovedCluster(
    title="API & Protokolle",
    candidate_id="SC_002",
    member_slugs=["api-grundlagen", "api-usage-guide"],
    mean_similarity=0.683,
)
_MEMBERS = [
    Member(
        slug="api-grundlagen",
        title="Was sind APIs?",
        summary="APIs sind Schnittstellen.",
        category="grundlagen",
    ),
    Member(
        slug="api-usage-guide",
        title="API-Nutzung",
        summary="Wie man APIs nutzt.",
        category="grundlagen",
    ),
]


def test_strip_reasoning_removes_think_block() -> None:
    assert strip_reasoning("<think>überlege</think>\nErgebnis.") == "Ergebnis."
    assert strip_reasoning("nur text") == "nur text"


def test_build_moc_with_qwen_framing_is_ai_drafted() -> None:
    r = build_moc(_CL, _MEMBERS, "Diese Artikel verbinden API-Konzepte.", today="2026-06-24")
    assert r.slug == "moc-api-protokolle"
    assert r.review_status == "ai_drafted"
    assert r.confidence in ("high", "medium")
    assert r.framing_source == "qwen"
    # Frontmatter-Pflichtfelder (D6) + Vault-Pflichtfelder (promotierbar)
    assert "doc_type: moc" in r.text
    assert "merged_from: []" in r.text
    assert "status: draft" in r.text
    assert "summary: " in r.text
    assert "doc_role:" in r.text
    assert "sources_docs: []" in r.text
    assert "source_chunks: []" in r.text
    # Wikilinks + Descriptor aus echtem summary (RV13)
    assert "[[api-grundlagen|Was sind APIs?]] — APIs sind Schnittstellen." in r.text
    assert "Diese Artikel verbinden API-Konzepte." in r.text


def test_build_moc_deterministic_framing_marks_needs_human() -> None:
    r = build_moc(_CL, _MEMBERS, None, today="2026-06-24")
    assert r.framing_source == "deterministic"
    assert r.review_status == "needs_human"
    assert "review_status: needs_human" in r.text


def test_build_moc_missing_member_needs_human() -> None:
    members = [_MEMBERS[0], Member(slug="weg", title="weg", summary="", found=False)]
    r = build_moc(_CL, members, "Rahmung.", today="2026-06-24")
    assert r.review_status == "needs_human"
    assert r.missing_members == ["weg"]
    assert "⚠️ Ziel-Doc nicht gefunden" in r.text


def test_build_moc_redundancy_note_rendered() -> None:
    cl = ApprovedCluster(
        title="NLP-Grundlagen",
        candidate_id="SC_008",
        member_slugs=["a"],
        mean_similarity=0.82,
        redundancy_note="Dublette X ↔ Y — zu konsolidieren (→ WP4).",
    )
    r = build_moc(cl, [Member(slug="a", title="A", summary="s")], "f", today="2026-06-24")
    assert "## Hinweise" in r.text
    assert "→ WP4" in r.text


def test_load_member_reads_frontmatter(tmp_path: Path) -> None:
    doc = tmp_path / "01_X" / "foo.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nslug: foo\ntitle: Foo Titel\nsummary: Kurzfassung.\ncategory: grundlagen\n---\nBODY-NICHT-KOPIEREN\n",
        encoding="utf-8",
    )
    m = load_member(tmp_path, "foo")
    assert m.found
    assert m.title == "Foo Titel"
    assert m.summary == "Kurzfassung."
    assert m.category == "grundlagen"


def test_load_member_missing_returns_not_found(tmp_path: Path) -> None:
    m = load_member(tmp_path, "gibt-es-nicht")
    assert not m.found


def test_generate_mocs_writes_files_and_no_body_copy(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_X").mkdir(parents=True)
    (vault / "01_X" / "api-grundlagen.md").write_text(
        "---\nslug: api-grundlagen\ntitle: Was sind APIs?\nsummary: APIs sind Schnittstellen.\n---\nSENTINEL-BODY-INHALT\n",
        encoding="utf-8",
    )
    (vault / "01_X" / "api-usage-guide.md").write_text(
        "---\nslug: api-usage-guide\ntitle: API-Nutzung\nsummary: Wie man APIs nutzt.\n---\nNOCH-EIN-BODY\n",
        encoding="utf-8",
    )
    out = tmp_path / "drafts" / "_moc"
    results = generate_mocs(
        [_CL], vault, out, framer=lambda title, members: "Rahmung aus Test.", today="2026-06-24"
    )
    assert len(results) == 1
    written = (out / "moc-api-protokolle.md").read_text(encoding="utf-8")
    # Kein Body-Transfer aus den Quell-Artikeln (nur summary als Descriptor)
    assert "SENTINEL-BODY-INHALT" not in written
    assert "NOCH-EIN-BODY" not in written
    assert "APIs sind Schnittstellen." in written  # summary ja
