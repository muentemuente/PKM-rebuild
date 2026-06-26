"""Tests für die additive NB-Field-Layer (WP-N2) — offline, kein Live-Qwen.

Abdeckung: (1) Schema parst neue Felder + Bestands-Note ohne sie validiert weiter,
(2) deterministischer Keyphrase-Extraktor (Fake-Modell, kein Download),
(3) Stage-4-Mapping graceful mit/ohne die Felder,
(4) frontmatter-audit wertet die neuen Felder nicht als Pflicht.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import keyphrase
from pipeline.schemas import FrontmatterDraft

# Gültiges Bestands-Frontmatter OHNE die neuen WP-N2-Felder (= 165er-Bestand).
_FM_LEGACY = {
    "title": "Test Konzept",
    "slug": "test",
    "summary": "Ein Test-Konzept für die Pipeline.",
    "type": "knowledge-article",
    "doc_role": ["explanation"],
    "category": "grundlagen",
    "tags": ["test"],
    "sources_docs": ["D_test"],
    "source_chunks": ["D_test-S0000"],
    "status": "draft",
    "review_status": "ai_drafted",
    "confidence": "medium",
    "doc_version": "0.1.0",
    "created": "2026-05-27",
    "updated": "2026-05-27",
    "last_synthesized": "2026-05-27",
    "prompt_version": "v1",
}


# === Schema ===================================================================


def test_legacy_note_validates_without_new_fields() -> None:
    fm = FrontmatterDraft.model_validate(_FM_LEGACY)
    assert fm.keyphrases == []
    assert fm.key_points == []
    assert fm.open_questions == []
    assert fm.next_steps == []


def test_new_fields_parse_when_present() -> None:
    data = {
        **_FM_LEGACY,
        "keyphrases": ["rest", "http"],
        "key_points": ["Zustandslosigkeit skaliert."],
        "open_questions": ["Wie vs. GraphQL?"],
        "next_steps": ["HATEOAS vertiefen."],
    }
    fm = FrontmatterDraft.model_validate(data)
    assert fm.keyphrases == ["rest", "http"]
    assert fm.key_points == ["Zustandslosigkeit skaliert."]
    assert fm.open_questions == ["Wie vs. GraphQL?"]
    assert fm.next_steps == ["HATEOAS vertiefen."]


def test_new_field_defaults_are_independent_lists() -> None:
    a = FrontmatterDraft.model_validate(_FM_LEGACY)
    b = FrontmatterDraft.model_validate(_FM_LEGACY)
    a.keyphrases.append("x")
    assert b.keyphrases == []  # kein geteiltes Mutable-Default


# === Keyphrase-Extraktor (2.1) ================================================


class _FakeKeyBERT:
    """Deterministisches Fake-KeyBERT (kein Modell-Download)."""

    def __init__(self, phrases: list[tuple[str, float]]) -> None:
        self._phrases = phrases

    def extract_keywords(self, text: str, **kwargs: object) -> list[tuple[str, float]]:
        return self._phrases


def test_keyphrase_extracts_and_filters() -> None:
    fake = _FakeKeyBERT(
        [("rest architektur", 0.8), ("rest architektur", 0.7), ("http", 0.6), ("x", 0.5)]
    )
    body = "REST ist ein Architektur-Stil. " * 5  # genug Wörter über dem Minimum
    out = keyphrase.extract_keyphrases(body, top_n=8, model=fake)
    assert out == ["rest architektur", "http"]  # dedupe + Längen-Filter (>=3 Zeichen)


def test_keyphrase_empty_on_short_body() -> None:
    fake = _FakeKeyBERT([("ignored", 0.9)])
    assert keyphrase.extract_keyphrases("zu kurz", model=fake) == []


def test_keyphrase_respects_top_n() -> None:
    fake = _FakeKeyBERT([(f"phrase nummer {i}", 0.9) for i in range(20)])
    body = "wort " * 50
    out = keyphrase.extract_keyphrases(body, top_n=3, model=fake)
    assert len(out) == 3


# === Stage-4-Mapping (graceful) ===============================================


def test_stage4_mapping_with_fields() -> None:
    from pipeline.restructure import _build_draft_frontmatter

    stage4 = {
        "title": "T",
        "summary": "S",
        "key_points": ["a", "b"],
        "open_questions": ["q"],
        "next_steps": ["n"],
    }
    fm = _build_draft_frontmatter(
        stage4=stage4,
        resolved_type="knowledge-article",
        type_source="classified",
        restructure_action="rewrite",
        confidence="medium",
        fallback=False,
        source_slug="t",
        model="m",
        prompt_version="v2",
        timestamp="2026-06-26T00:00:00",
        keyphrases=["kp1", "kp2"],
    )
    assert fm["keyphrases"] == ["kp1", "kp2"]
    assert fm["key_points"] == ["a", "b"]
    assert fm["open_questions"] == ["q"]
    assert fm["next_steps"] == ["n"]


def test_stage4_mapping_without_fields_defaults_empty() -> None:
    from pipeline.restructure import _build_draft_frontmatter

    fm = _build_draft_frontmatter(
        stage4={"title": "T", "summary": "S"},  # keine NB-Felder im Qwen-JSON
        resolved_type="knowledge-article",
        type_source="classified",
        restructure_action="rewrite",
        confidence="medium",
        fallback=False,
        source_slug="t",
        model="m",
        prompt_version="v2",
        timestamp="2026-06-26T00:00:00",
    )
    assert fm["keyphrases"] == []
    assert fm["key_points"] == []
    assert fm["open_questions"] == []
    assert fm["next_steps"] == []


# === frontmatter-audit (Pflichtwertung) =======================================


def _write_legacy_note(vault: Path) -> Path:
    import yaml

    folder = vault / "01_Grundlagen"
    folder.mkdir(parents=True, exist_ok=True)
    note = folder / "test.md"
    fm_yaml = yaml.safe_dump(_FM_LEGACY, sort_keys=False, allow_unicode=True)
    note.write_text(f"---\n{fm_yaml}---\n\n# Test\n\nInhalt.\n", encoding="utf-8")
    return note


def test_audit_does_not_flag_new_fields_as_missing(tmp_path: Path) -> None:
    from pipeline.frontmatter_audit import audit_file

    note = _write_legacy_note(tmp_path)
    audit = audit_file(note, tmp_path)
    missing_labels = {g.label for g in audit.gaps}
    for fld in ("keyphrases", "key_points", "open_questions", "next_steps"):
        assert f"missing:{fld}" not in missing_labels
    assert audit.complete  # Bestands-Note bleibt ohne neue Felder vollständig
