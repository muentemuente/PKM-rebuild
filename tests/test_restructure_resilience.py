"""Tests für WP3c-3 — restructure Performance/Resilienz.

LLM immer gemockt (kein realer Call). Belegt:
  - Timeout (APITimeoutError) → kein Draft, Quell-Byte-stabil, RestructureError
  - CLI mappt den Fehler auf Exit-Code ≠ 0
  - non-thinking (enable_thinking:false) + Sampler werden an den Client durchgereicht
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APITimeoutError
from pipeline.config import (
    QwenConfig,
    QwenMaxTokensConfig,
    QwenRestructureConfig,
    QwenTemperatureConfig,
)
from pipeline.restructure import RestructureError, restructure_file

_FIXED_TS = "2026-06-21T00:00:00+00:00"
_STAGE3_BODY = "# Titel\n\nRe-strukturierter Body."
_STAGE4_FM = {"title": "Titel", "type": "knowledge-article", "confidence": "high"}


def _mock_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _ok_client() -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _mock_response(f"```markdown\n{_STAGE3_BODY}\n```"),
        _mock_response(f"```json\n{json.dumps(_STAGE4_FM)}\n```"),
    ]
    return client


def _timeout_client() -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.side_effect = APITimeoutError(
        request=httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
    )
    return client


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
            reasoning_effort="none",
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            max_tokens_stage3=4000,
            max_tokens_stage4=2000,
        ),
    )


def _prompts_dir(tmp_path: Path) -> Path:
    v1 = tmp_path / "prompts" / "v1"
    v1.mkdir(parents=True)
    (v1 / "stage3_synthesis.md").write_text("Stage-3 Prompt.\n", encoding="utf-8")
    (v1 / "stage4_frontmatter_json.md").write_text("Stage-4 Prompt.\n", encoding="utf-8")
    return tmp_path / "prompts"


def _source_file(tmp_path: Path) -> Path:
    src = tmp_path / "quelle.md"
    src.write_text("---\nslug: quell-artikel\n---\n\nFließtext.\n", encoding="utf-8")
    return src


# === Resilienz ================================================================


def test_timeout_no_draft_source_untouched(tmp_path: Path) -> None:
    """APITimeoutError → RestructureError, kein Draft, Quell-File byte-stabil."""
    src = _source_file(tmp_path)
    before = src.read_bytes()
    out = tmp_path / "drafts"

    with pytest.raises(RestructureError) as excinfo:
        restructure_file(
            src,
            client=_timeout_client(),
            qwen=_qwen_cfg(),
            out_dir=out,
            prompts_dir=_prompts_dir(tmp_path),
            timestamp=_FIXED_TS,
        )

    assert "Stage 3" in str(excinfo.value)
    assert "Kein Draft" in str(excinfo.value)
    assert src.read_bytes() == before  # Quelle unberührt
    assert not out.exists() or list(out.glob("*.md")) == []  # kein Draft


def test_cli_exit_code_nonzero_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI mappt RestructureError auf Exit-Code ≠ 0 (rote Fehlerzeile, kein Traceback)."""
    from click.testing import CliRunner
    from pipeline.__main__ import cli

    src = _source_file(tmp_path)
    monkeypatch.setattr("openai.OpenAI", lambda **_: _timeout_client())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["restructure", "--file", str(src), "--out", str(tmp_path / "drafts")],
    )
    assert result.exit_code == 1
    assert "fehlgeschlagen" in result.output


# === non-thinking + Sampler durchgereicht =====================================


def test_reasoning_disabled_and_sampler_passed(tmp_path: Path) -> None:
    """reasoning_effort:none + Sampler landen in den create()-Kwargs beider Stages."""
    client = _ok_client()
    restructure_file(
        _source_file(tmp_path),
        client=client,
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )

    calls = client.chat.completions.create.call_args_list
    assert len(calls) == 2  # Stage 3 + Stage 4
    for call in calls:
        kw = call.kwargs
        assert kw["reasoning_effort"] == "none"
        assert kw["top_p"] == 0.8
        assert kw["presence_penalty"] == 1.5
        assert kw["temperature"] == 0.7


def test_max_tokens_lowered_for_restructure(tmp_path: Path) -> None:
    """restructure nutzt die gesenkten max_tokens (kein 16000-Reasoning-Budget)."""
    client = _ok_client()
    restructure_file(
        _source_file(tmp_path),
        client=client,
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    calls = client.chat.completions.create.call_args_list
    assert calls[0].kwargs["max_tokens"] == 4000  # Stage 3
    assert calls[1].kwargs["max_tokens"] == 2000  # Stage 4


def test_phase8_call_unchanged_without_sampler() -> None:
    """Phase-8-Pfad (ohne Sampler-Args) ruft create() ohne extra_body/top_p auf."""
    from pipeline.phase_8_synthesis import _call_qwen_api

    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("ok")
    _call_qwen_api(client, "m", [{"role": "user", "content": "x"}], 0.4, 100)

    kw = client.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kw
    assert "top_p" not in kw
    assert "presence_penalty" not in kw
    assert "reasoning_effort" not in kw
    assert kw["temperature"] == 0.4
