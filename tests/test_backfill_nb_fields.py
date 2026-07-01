"""Tests für A2a — additiver NB-Feld-Backfill (offline, kein Live-Qwen).

Deckt die byte-stabile additive Insertion, die Block-Rendering-Varianten (leere vs.
gefüllte Listen, Sonderzeichen), die Additiv-Verifikation und das Skip-Verhalten
(Feld bereits vorhanden / kein Frontmatter). Der Qwen-Call selbst wird über einen
injizierten Fake-Client geplumbt — **nicht** als Ground-Truth-Mock; der reale
Qwen-Output wird im Owner-Report vorgelegt, nicht hier als „korrekt" fixiert.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pipeline.backfill_nb_fields import (
    NB_FIELDS,
    BackfillError,
    NbFields,
    _render_nb_blocks,
    _strip_nb_blocks,
    add_nb_fields_to_frontmatter,
    backfill_note_to_draft,
    extract_nb_fields,
    verify_additive,
)

# Bestands-Note (Frontmatter + Body), byte-genau wie im Vault (LF, 2-Space-Listen).
_NOTE = (
    "---\n"
    "title: REST-Architektur\n"
    "slug: rest-architektur\n"
    "type: knowledge-article\n"
    "tags:\n"
    "  - rest\n"
    "  - http\n"
    "review_status: ai_drafted\n"
    "---\n"
    "\n"
    "# REST-Architektur\n"
    "\n"
    "REST ist ein Architektur-Stil für verteilte Systeme.\n"
)

_FIELDS = NbFields(
    key_points=["REST entkoppelt Client und Server.", "Zustandslosigkeit skaliert."],
    open_questions=["Wie vs. GraphQL?"],
    next_steps=[],
)


class _FakeQwen:
    """QwenConfig-Ersatz mit nur dem, was der Backfill-Pfad liest."""

    class _RC:
        prompt_version = "v2"
        temperature = 0.7
        top_p = 0.8
        presence_penalty = 1.5
        reasoning_effort = "none"
        max_tokens_stage4 = 2000

    restructure = _RC()
    model = "test-model"
    max_retries = 0
    retry_backoff_seconds = 0


def _fake_client(payload: dict[str, Any]) -> Any:
    """OpenAI-kompatibler Fake-Client: liefert das ``payload`` als ```json``-Block."""
    from unittest.mock import MagicMock

    choice = MagicMock()
    choice.message.content = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


# === Block-Rendering ==========================================================


def test_render_empty_list_is_canonical_inline() -> None:
    assert _render_nb_blocks(NbFields()) == "key_points: []\nopen_questions: []\nnext_steps: []\n"


def test_render_filled_and_empty_mixed() -> None:
    out = _render_nb_blocks(_FIELDS)
    assert "key_points:\n  - REST entkoppelt Client und Server.\n" in out
    assert "open_questions:\n  - Wie vs. GraphQL?\n" in out
    assert "next_steps: []\n" in out


def test_render_escapes_colon_and_umlaut() -> None:
    f = NbFields(key_points=["Merke: Zustand ist König"], open_questions=[], next_steps=[])
    block = _render_nb_blocks(f)
    # Muss YAML-roundtrip-fähig sein (Doppelpunkt im Wert wird gequotet).
    parsed = yaml.safe_load("x:\n" + "\n".join("  " + ln for ln in block.splitlines()))
    assert parsed["x"]["key_points"] == ["Merke: Zustand ist König"]


# === Additive Insertion + Verify ==============================================


def test_additive_insert_is_byte_stable_except_fields() -> None:
    written = add_nb_fields_to_frontmatter(_NOTE, _FIELDS)
    # Rest byte-identisch: Strippen der NB-Blöcke ergibt das Original.
    assert _strip_nb_blocks(written) == _NOTE
    # Body unangetastet.
    assert written.endswith("REST ist ein Architektur-Stil für verteilte Systeme.\n")
    # Roundtrip-Verify wirft nicht.
    verify_additive(_NOTE, written, _FIELDS)


def test_written_frontmatter_parses_with_expected_values() -> None:
    written = add_nb_fields_to_frontmatter(_NOTE, _FIELDS)
    fm = written.split("---\n")[1]
    data = yaml.safe_load(fm)
    assert data["key_points"] == _FIELDS.key_points
    assert data["open_questions"] == _FIELDS.open_questions
    assert data["next_steps"] == []
    # Bestehende Felder unverändert.
    assert data["title"] == "REST-Architektur"
    assert data["tags"] == ["rest", "http"]


def test_insert_refuses_when_field_already_present() -> None:
    already = _NOTE.replace(
        "review_status: ai_drafted\n", "review_status: ai_drafted\nkey_points: []\n"
    )
    with pytest.raises(BackfillError, match="key_points bereits vorhanden"):
        add_nb_fields_to_frontmatter(already, _FIELDS)


def test_insert_refuses_without_frontmatter() -> None:
    with pytest.raises(BackfillError, match="kein parsebares Frontmatter"):
        add_nb_fields_to_frontmatter("# Kein Frontmatter\n\nText.\n", _FIELDS)


def test_verify_detects_body_tamper() -> None:
    written = add_nb_fields_to_frontmatter(_NOTE, _FIELDS)
    tampered = written + "ANHANG\n"
    with pytest.raises(BackfillError, match="nicht ausschließlich"):
        verify_additive(_NOTE, tampered, _FIELDS)


# === extract_nb_fields (Plumbing, Fake-Client) ================================


def test_extract_maps_all_three_fields() -> None:
    client = _fake_client({"key_points": ["a", "b"], "open_questions": ["q"], "next_steps": ["n"]})
    fields = extract_nb_fields(
        "Body " * 20, client=client, qwen=_FakeQwen(), prompts_dir=Path("prompts")
    )
    assert fields.key_points == ["a", "b"]
    assert fields.open_questions == ["q"]
    assert fields.next_steps == ["n"]


def test_extract_graceful_on_missing_keys() -> None:
    client = _fake_client({"key_points": ["only"]})  # open_questions/next_steps fehlen
    fields = extract_nb_fields(
        "Body " * 20, client=client, qwen=_FakeQwen(), prompts_dir=Path("prompts")
    )
    assert fields.key_points == ["only"]
    assert fields.open_questions == []
    assert fields.next_steps == []


# === backfill_note_to_draft (end-to-end offline) ==============================


def test_backfill_to_draft_writes_additive_draft(tmp_path: Path) -> None:
    note = tmp_path / "rest-architektur.md"
    note.write_text(_NOTE, encoding="utf-8")
    out = tmp_path / "drafts"
    client = _fake_client(
        {"key_points": ["k1", "k2", "k3"], "open_questions": [], "next_steps": []}
    )
    res = backfill_note_to_draft(note, out, client=client, qwen=_FakeQwen())
    assert res.status == "drafted"
    assert res.draft_path is not None
    assert res.draft_path.exists()
    # Vault-Quelle unverändert.
    assert note.read_text(encoding="utf-8") == _NOTE
    # Draft = additiv.
    assert _strip_nb_blocks(res.draft_path.read_text(encoding="utf-8")) == _NOTE


def test_backfill_skips_when_field_present(tmp_path: Path) -> None:
    note = tmp_path / "x.md"
    note.write_text(
        _NOTE.replace("review_status: ai_drafted\n", "review_status: ai_drafted\nnext_steps: []\n"),
        encoding="utf-8",
    )
    out = tmp_path / "drafts"
    # Fake-Client würde crashen, wenn er aufgerufen würde → Skip erfolgt VOR dem Call.
    from unittest.mock import MagicMock

    client = MagicMock()
    client.chat.completions.create.side_effect = AssertionError("Qwen darf nicht aufgerufen werden")
    res = backfill_note_to_draft(note, out, client=client, qwen=_FakeQwen())
    assert res.status == "skip-existing"
    assert res.draft_path is None


def test_nb_fields_constant_matches_order() -> None:
    assert NB_FIELDS == ("key_points", "open_questions", "next_steps")
