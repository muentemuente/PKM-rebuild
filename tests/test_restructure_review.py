"""Tests für pipeline.restructure (WP3c-1 — restructure-review Scaffold).

LLM ist immer gemockt (kein realer Qwen-Call). Belegt:
  - Draft byte-stabil aus gemocktem Client erzeugt
  - Frontmatter: ai_drafted + confidence (Enum) + vollständige provenance
  - Driver-Invariante: review-Tier-Transform löst KEINEN Vault-Write aus
  - Quell-File unverändert (Byte-Snapshot)
  - fehlende/ungültige confidence → konservativer Fallback (low) + Flag
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from pipeline import driver, transforms
from pipeline.config import QwenConfig, QwenMaxTokensConfig, QwenTemperatureConfig
from pipeline.restructure import RestructureReviewTransform, restructure_file

_FIXED_TS = "2026-06-21T00:00:00+00:00"
_STAGE3_BODY = "# Titel\n\nRe-strukturierter Body.\n\n## Abschnitt\n\nInhalt."
_STAGE4_FM = {
    "title": "Titel",
    "type": "knowledge-article",
    "summary": "Kurzfassung des Artikels.",
    "confidence": "high",
}


# === Helfer ===================================================================


def _mock_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_client(stage4_fm: dict[str, Any] | None = None) -> MagicMock:
    """Client mit fixer Stage-3- (Body) + Stage-4- (JSON) Antwort."""
    fm = _STAGE4_FM if stage4_fm is None else stage4_fm
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _mock_response(f"```markdown\n{_STAGE3_BODY}\n```"),
        _mock_response(f"```json\n{json.dumps(fm)}\n```"),
    ]
    return client


def _qwen_cfg() -> QwenConfig:
    return QwenConfig(
        endpoint="http://localhost:1234/v1",
        model="qwen/qwen3.6-27b",
        context_window=49152,
        prompt_version="v1",
        json_mode=False,
        max_retries=2,
        retry_backoff_seconds=0,
        timeout_seconds=60,
        temperature=QwenTemperatureConfig(stage3_synthesis=0.3, stage4_frontmatter=0.1),
        max_tokens=QwenMaxTokensConfig(stage3=2000, stage4=800),
    )


def _prompts_dir(tmp_path: Path) -> Path:
    """Minimale Prompt-Stubs (Stage 3 + Stage 4)."""
    v1 = tmp_path / "prompts" / "v1"
    v1.mkdir(parents=True)
    (v1 / "stage3_synthesis.md").write_text("Stage-3 System-Prompt.\n", encoding="utf-8")
    (v1 / "stage4_frontmatter_json.md").write_text("Stage-4 System-Prompt.\n", encoding="utf-8")
    return tmp_path / "prompts"


def _source_file(tmp_path: Path) -> Path:
    src = tmp_path / "quelle.md"
    src.write_text(
        "---\nslug: quell-artikel\n---\n\nUnstrukturierter Fließtext als Quelle.\n",
        encoding="utf-8",
    )
    return src


def _parse_draft(draft_text: str) -> tuple[dict[str, Any], str]:
    assert draft_text.startswith("---\n")
    _, fm_text, body = draft_text.split("---\n", 2)
    return yaml.safe_load(fm_text), body


# === Tests ====================================================================


def test_draft_byte_stable(tmp_path: Path) -> None:
    """Gemockter Client + fixer Timestamp → byte-identischer Draft bei Wiederholung."""
    src = _source_file(tmp_path)
    prompts = _prompts_dir(tmp_path)
    out = tmp_path / "drafts"

    first = restructure_file(
        src,
        client=_mock_client(),
        qwen=_qwen_cfg(),
        out_dir=out,
        prompts_dir=prompts,
        timestamp=_FIXED_TS,
    )
    bytes_first = first.draft_path.read_bytes()

    second = restructure_file(
        src,
        client=_mock_client(),
        qwen=_qwen_cfg(),
        out_dir=out,
        prompts_dir=prompts,
        timestamp=_FIXED_TS,
    )
    assert second.draft_path.read_bytes() == bytes_first
    assert first.draft_path == out / "quell-artikel.md"
    # Body stammt aus Stage 3
    _, body = _parse_draft(bytes_first.decode("utf-8"))
    assert "Re-strukturierter Body." in body


def test_frontmatter_contract(tmp_path: Path) -> None:
    """ai_drafted + confidence (Enum) + vollständige provenance."""
    src = _source_file(tmp_path)
    draft = restructure_file(
        src,
        client=_mock_client(),
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    fm, _ = _parse_draft(draft.draft_path.read_text(encoding="utf-8"))

    assert fm["review_status"] == "ai_drafted"
    assert fm["confidence"] == "high"
    assert fm["prompt_version"] == "v1"
    prov = fm["provenance"]
    assert prov["source"] == "quell-artikel"
    assert prov["model"] == "qwen/qwen3.6-27b"
    assert prov["prompt_version"] == "v1"
    assert prov["generated_at"] == _FIXED_TS
    assert "confidence_fallback" not in fm  # high ist valide → kein Flag


def test_confidence_enum_not_float(tmp_path: Path) -> None:
    """confidence bleibt Vault-Enum-String, kein Float."""
    src = _source_file(tmp_path)
    draft = restructure_file(
        src,
        client=_mock_client({"title": "T", "confidence": "MEDIUM"}),
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    assert draft.confidence == "medium"  # normalisiert (lower)
    assert not draft.confidence_fallback


@pytest.mark.parametrize(
    "stage4_fm",
    [
        {"title": "T"},  # confidence fehlt
        {"title": "T", "confidence": 0.7},  # Float → ungültig
        {"title": "T", "confidence": "sehr-hoch"},  # unbekannter Wert
    ],
)
def test_missing_confidence_fallback(tmp_path: Path, stage4_fm: dict[str, Any]) -> None:
    """Fehlende/ungültige confidence → konservativ low + Flag."""
    src = _source_file(tmp_path)
    draft = restructure_file(
        src,
        client=_mock_client(stage4_fm),
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    assert draft.confidence == "low"
    assert draft.confidence_fallback is True
    fm, _ = _parse_draft(draft.draft_path.read_text(encoding="utf-8"))
    assert fm["confidence"] == "low"
    assert fm["confidence_fallback"] is True


def test_source_file_untouched(tmp_path: Path) -> None:
    """Quell-File bleibt byte-identisch (read-only)."""
    src = _source_file(tmp_path)
    before = src.read_bytes()
    restructure_file(
        src,
        client=_mock_client(),
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    assert src.read_bytes() == before


def test_slug_fallback_from_filename(tmp_path: Path) -> None:
    """Ohne slug im Quell-Frontmatter → Slug aus Dateiname (Umlaut-Map)."""
    src = tmp_path / "Größe und Maß.md"
    src.write_text("Fließtext ohne Frontmatter.\n", encoding="utf-8")
    draft = restructure_file(
        src,
        client=_mock_client(),
        qwen=_qwen_cfg(),
        out_dir=tmp_path / "drafts",
        prompts_dir=_prompts_dir(tmp_path),
        timestamp=_FIXED_TS,
    )
    assert draft.slug == "groesse-und-mass"


# === Driver-Invariante: review-Tier → kein Vault-Write ========================


def test_review_tier_blocks_vault_write(tmp_path: Path) -> None:
    """apply_to_vault mit review-Tier-Transform schreibt NICHT (auch execute=True)."""
    transform = RestructureReviewTransform(
        client=_mock_client(),
        model="qwen/qwen3.6-27b",
        system_prompt="Stage-3 System-Prompt.",
        temperature=0.3,
        max_tokens=2000,
    )
    assert transform.tier == transforms.TIER_REVIEW
    assert transform.mutating is True

    transforms.register(transform, replace=True)
    try:
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "note.md"
        original = "---\nslug: note\n---\n\nOriginaler Body.\n"
        note.write_text(original, encoding="utf-8")

        report = driver.apply_to_vault(vault, ["restructure-review"], execute=True)

        assert report.writable is False
        assert report.executed is False
        assert "tier" in report.reason.lower()
        assert note.read_text(encoding="utf-8") == original  # nichts geschrieben
    finally:
        transforms.unregister("restructure-review")


def test_transform_is_review_tier_in_registry(tmp_path: Path) -> None:
    """_chain_writable stuft eine restructure-review-Chain als nicht auto-write-fähig ein."""
    transform = RestructureReviewTransform(
        client=_mock_client(),
        model="m",
        system_prompt="p",
        temperature=0.0,
        max_tokens=10,
    )
    transforms.register(transform, replace=True)
    try:
        writable, reason = driver._chain_writable(["restructure-review"])
        assert writable is False
        assert "restructure-review" in reason
    finally:
        transforms.unregister("restructure-review")
