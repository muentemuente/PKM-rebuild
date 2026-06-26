"""Tests für WP-A1b — additiver, byte-stabiler keyphrases-Write.

Kern-Garantien: (1) nur der keyphrases-Block wird eingefügt, alles andere byte-stabil,
(2) keyphrases-Roundtrip stimmt, (3) Idempotenz-Schutz (kein Overwrite), (4) robustes
Scalar-Escaping (Doppelpunkt/Umlaut).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import backfill_write as bw

_NOTE = (
    "---\n"
    "title: Test\n"
    "slug: test\n"
    "type: knowledge-article\n"
    "doc_role:\n  - reference\n"
    "tags:\n  - python\n"
    "created: '2026-06-18'\n"
    "updated: '2026-06-18'\n"
    "---\n\n"
    "# Titel\n\nInhalt mit mehreren Wörtern.\n"
)


def test_add_keyphrases_byte_stable_except_block() -> None:
    phrases = ["rest api", "python pandas"]
    out = bw.add_keyphrases_to_frontmatter(_NOTE, phrases)
    # Body + alle Original-FM-Zeilen unverändert
    assert "# Titel\n\nInhalt mit mehreren Wörtern.\n" in out
    assert "title: Test\n" in out
    # Block eingefügt vor schließendem ---
    assert "keyphrases:\n  - rest api\n  - python pandas\n---\n" in out
    # Diff-Probe: Block entfernen → exakt Original
    assert bw._strip_keyphrases_block(out) == _NOTE


def test_verify_additive_passes_and_roundtrips() -> None:
    phrases = ["rest api", "knowledge graph"]
    out = bw.add_keyphrases_to_frontmatter(_NOTE, phrases)
    bw.verify_additive(_NOTE, out, phrases)  # darf nicht werfen
    fm = yaml.safe_load(out.split("---\n")[1])
    assert fm["keyphrases"] == phrases
    assert fm["title"] == "Test"  # bestehende Keys intakt


def test_idempotency_guard_blocks_overwrite() -> None:
    out = bw.add_keyphrases_to_frontmatter(_NOTE, ["a phrase"])
    with pytest.raises(bw.BackfillError, match="bereits vorhanden"):
        bw.add_keyphrases_to_frontmatter(out, ["other"])


def test_special_characters_escaped() -> None:
    phrases = ["key: value", "äöü begriff"]
    out = bw.add_keyphrases_to_frontmatter(_NOTE, phrases)
    # Roundtrip muss die exakten Phrasen rekonstruieren
    bw.verify_additive(_NOTE, out, phrases)
    fm = yaml.safe_load(out.split("---\n")[1])
    assert fm["keyphrases"] == phrases


def test_no_frontmatter_raises() -> None:
    with pytest.raises(bw.BackfillError, match="kein parsebares Frontmatter"):
        bw.add_keyphrases_to_frontmatter("# Nur Body\n\nText.\n", ["x"])


def test_write_keyphrases_roundtrip(tmp_path: Path) -> None:
    note = tmp_path / "n.md"
    note.write_text(_NOTE, encoding="utf-8")
    original = bw.write_keyphrases(note, ["alpha beta", "gamma"])
    assert original == _NOTE
    written = note.read_text(encoding="utf-8")
    assert bw._strip_keyphrases_block(written) == _NOTE
    assert yaml.safe_load(written.split("---\n")[1])["keyphrases"] == ["alpha beta", "gamma"]
