"""Tests für WP-A1a — deterministischer keyphrases-Backfill-Dry-Run (read-only).

Kein Modell-Download: der Extraktor wird injiziert. Verifiziert die vier
Klassifikations-Bänder + dass nichts in den Vault geschrieben wird.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import backfill_dryrun as bd

_FM = (
    "---\n"
    "title: T\n"
    "slug: {slug}\n"
    "summary: x\n"
    "type: knowledge-article\n"
    "doc_role:\n  - reference\n"
    "category: grundlagen\n"
    "tags: []\n"
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
    "{extra}"
    "---\n\n# Titel\n\nInhalt.\n"
)


def _note(vault: Path, slug: str, extra: str = "") -> None:
    folder = vault / "01_Grundlagen"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.md").write_text(_FM.format(slug=slug, extra=extra), encoding="utf-8")


def test_classify_bands() -> None:
    assert bd.classify([], ["a"]) == bd.KLASS_ADD
    assert bd.classify([], []) == bd.KLASS_SKIP_EMPTY
    assert bd.classify(["a"], ["a"]) == bd.KLASS_UNCHANGED
    assert bd.classify(["a"], ["b"]) == bd.KLASS_CHANGE


def test_dryrun_classifies_and_writes_nothing(tmp_path: Path) -> None:
    _note(tmp_path, "add-note")  # bekommt keyphrases
    _note(tmp_path, "short-note")  # liefert leer → skip-empty
    _note(tmp_path, "keep-note", extra="keyphrases:\n  - alpha\n")  # identisch → unchanged

    # Marker-basierter Fake: leere Liste nur für die SKIP-markierte Note.
    def extractor(body: str) -> list[str]:
        return [] if "SKIP" in body else ["alpha"]

    # short-note bekommt SKIP-Marker in den Body
    (tmp_path / "01_Grundlagen" / "short-note.md").write_text(
        _FM.format(slug="short-note", extra="").replace("Inhalt.", "SKIP"),
        encoding="utf-8",
    )

    snapshot = {p: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.md")}
    results = bd.run_keyphrase_dryrun(tmp_path, top_n=8, extractor=extractor)
    by_slug = {Path(r.relpath).stem: r.klass for r in results}

    assert by_slug["add-note"] == bd.KLASS_ADD
    assert by_slug["short-note"] == bd.KLASS_SKIP_EMPTY
    assert by_slug["keep-note"] == bd.KLASS_UNCHANGED

    # read-only: keine Note-Datei verändert
    after = {p: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.md")}
    assert after == snapshot


def test_summarize_and_render(tmp_path: Path) -> None:
    results = [
        bd.NoteResult("a.md", bd.KLASS_ADD, ["x"], []),
        bd.NoteResult("b.md", bd.KLASS_SKIP_EMPTY, [], []),
        bd.NoteResult("c.md", bd.KLASS_CHANGE, ["new"], ["old"]),
    ]
    counts = bd.summarize(results)
    assert counts[bd.KLASS_ADD] == 1
    assert counts[bd.KLASS_CHANGE] == 1
    report = bd.render_report(
        results, today="2026-06-26", fx1_commit="672c064", roundtrip="166/166", top_n=8
    )
    assert "would-add: 1" in report
    assert "| a.md | would-add | x |" in report
    assert "old" in report  # would-change zeigt alt
