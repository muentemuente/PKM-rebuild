"""Tests für WP3c-4 — typ-bewusstes restructure.

LLM immer gemockt. Belegt:
  - Frontmatter-`type` (Nicht-Article) wird respektiert, kein Klassifikator-Call.
  - fehlender type → Klassifikation greift, type_source: classified.
  - knowledge-article + Funktional-Signal → reclassified (compact-reference).
  - compact-reference → Stage-3-User-Message trägt die type-Direktive (kein Article).
  - Passthrough greift bei bereits gut strukturiertem File (kein Stage-3-Call).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from pipeline.config import (
    QwenConfig,
    QwenMaxTokensConfig,
    QwenRestructureConfig,
    QwenTemperatureConfig,
)
from pipeline.restructure import restructure_file

_FIXED_TS = "2026-06-21T00:00:00+00:00"
_STAGE3_BODY = "# Titel\n\nNeu strukturierter Body."
_STAGE4_FM = {"title": "Titel", "summary": "S", "confidence": "high"}


def _resp(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    r = MagicMock()
    r.choices = [choice]
    return r


def _client(responses: list[str]) -> MagicMock:
    c = MagicMock()
    c.chat.completions.create.side_effect = [_resp(x) for x in responses]
    return c


def _stage4() -> str:
    return f"```json\n{json.dumps(_STAGE4_FM)}\n```"


def _qwen_cfg() -> QwenConfig:
    return QwenConfig(
        endpoint="http://localhost:1234/v1",
        model="qwen/qwen3.6-27b",
        context_window=49152,
        prompt_version="v1",
        json_mode=False,
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=1200,
        temperature=QwenTemperatureConfig(stage3_synthesis=0.4, stage4_frontmatter=0.1),
        max_tokens=QwenMaxTokensConfig(stage3=16000, stage4=10000),
        restructure=QwenRestructureConfig(
            prompt_version="v2",
            reasoning_effort="none",
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            max_tokens_stage3=4000,
            max_tokens_stage4=2000,
        ),
    )


def _prompts_dir(tmp_path: Path) -> Path:
    v2 = tmp_path / "prompts" / "v2"
    v2.mkdir(parents=True)
    (v2 / "stage3_synthesis.md").write_text("Stage-3.\n", encoding="utf-8")
    (v2 / "stage4_frontmatter_json.md").write_text("Stage-4.\n", encoding="utf-8")
    return tmp_path / "prompts"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _run(tmp_path: Path, src: Path, responses: list[str]) -> tuple[Any, MagicMock]:
    client = _client(responses)
    draft = restructure_file(
        src,
        client=client,
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    return draft, client


# === Typ-Auflösung ============================================================


def test_frontmatter_nonarticle_type_respected_no_classifier(tmp_path: Path) -> None:
    """Gültiger Nicht-Article-Frontmatter-type → respektiert, kein Klassifikator-Call."""
    # process-document, unstrukturiert (keine Headings) → rewrite, aber kein classify.
    src = _write(
        tmp_path, "p.md", "---\nslug: proc\ntype: process-document\n---\n\nFließtext ohne H.\n"
    )
    draft, client = _run(tmp_path, src, [f"```markdown\n{_STAGE3_BODY}\n```", _stage4()])
    assert draft.type == "process-document"
    assert draft.type_source == "frontmatter"
    assert client.chat.completions.create.call_count == 2  # nur Stage 3 + Stage 4


def test_missing_type_classified(tmp_path: Path) -> None:
    """Kein Frontmatter-type → Klassifikation, type_source: classified."""
    src = _write(tmp_path, "x.md", "---\nslug: x\n---\n\nFließtext ohne H.\n")
    draft, client = _run(
        tmp_path, src, ["compact-reference", f"```markdown\n{_STAGE3_BODY}\n```", _stage4()]
    )
    assert draft.type == "compact-reference"
    assert draft.type_source == "classified"
    assert client.chat.completions.create.call_count == 3  # classify + Stage 3 + Stage 4


def test_article_reclassified_to_reference(tmp_path: Path) -> None:
    """knowledge-article + Klassifikator sagt compact-reference → reclassified."""
    src = _write(
        tmp_path,
        "a.md",
        "---\nslug: a\ntype: knowledge-article\n---\n\nEin nutzbarer Prompt-Text.\n",
    )
    draft, _ = _run(
        tmp_path, src, ["compact-reference", f"```markdown\n{_STAGE3_BODY}\n```", _stage4()]
    )
    assert draft.type == "compact-reference"
    assert draft.type_source == "reclassified"


def test_article_kept_when_classifier_agrees(tmp_path: Path) -> None:
    """knowledge-article + Klassifikator bestätigt → frontmatter (kein Override)."""
    src = _write(
        tmp_path, "a.md", "---\nslug: a\ntype: knowledge-article\n---\n\nErklärtext ohne H.\n"
    )
    draft, _ = _run(
        tmp_path, src, ["knowledge-article", f"```markdown\n{_STAGE3_BODY}\n```", _stage4()]
    )
    assert draft.type == "knowledge-article"
    assert draft.type_source == "frontmatter"


# === type-Direktive in Stage 3 ===============================================


def test_stage3_user_message_carries_target_type(tmp_path: Path) -> None:
    """compact-reference-Direktive landet in der Stage-3-User-Message (kein Article-Zwang)."""
    src = _write(tmp_path, "r.md", "---\nslug: r\ntype: compact-reference\n---\n\nLnt ohne H.\n")
    _, client = _run(tmp_path, src, [f"```markdown\n{_STAGE3_BODY}\n```", _stage4()])
    # 1. Call = Stage 3 (kein classify bei Nicht-Article). User-Message trägt den type.
    stage3_user = client.chat.completions.create.call_args_list[0].kwargs["messages"][1]["content"]
    assert "Ziel-type: compact-reference" in stage3_user


# === Passthrough ==============================================================


def test_passthrough_when_well_structured(tmp_path: Path) -> None:
    """Headings + konformer Slug + keine Korruption → Passthrough, kein Stage-3-Call."""
    body = "## Abschnitt eins\n\nInhalt.\n\n## Abschnitt zwei\n\nMehr.\n"
    src = _write(
        tmp_path, "s.md", f"---\nslug: gut-strukturiert\ntype: compact-reference\n---\n\n{body}"
    )
    # Nicht-Article-type → kein classify; well-structured → kein Stage 3. Nur Stage 4.
    draft, client = _run(tmp_path, src, [_stage4()])
    assert draft.restructure_action == "passthrough"
    assert client.chat.completions.create.call_count == 1  # nur Stage 4
    # Body verbatim erhalten
    draft_text = draft.draft_path.read_text(encoding="utf-8")
    assert "## Abschnitt eins" in draft_text
    assert "## Abschnitt zwei" in draft_text


def test_rewrite_when_unstructured(tmp_path: Path) -> None:
    """Keine Headings → rewrite-Pfad (Stage 3 läuft)."""
    src = _write(
        tmp_path,
        "u.md",
        "---\nslug: flach\ntype: compact-reference\n---\n\nNur Fließtext, keine Headings.\n",
    )
    draft, _ = _run(tmp_path, src, [f"```markdown\n{_STAGE3_BODY}\n```", _stage4()])
    assert draft.restructure_action == "rewrite"
