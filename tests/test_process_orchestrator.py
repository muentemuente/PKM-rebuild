"""Tests für Process-1 — universeller Erstverarbeitungs-Orchestrator.

LLM + Vault gemockt, KEIN realer Lauf. tmp-Source + tmp-Vault; Live-Vault unberührt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from pipeline.config import (
    QwenConfig,
    QwenMaxTokensConfig,
    QwenRestructureConfig,
    QwenTemperatureConfig,
)
from pipeline.process_orchestrator import (
    FileState,
    _stage_assets,
    _stage_links,
    _stage_normalize,
    _stage_tags,
    load_state,
    run_process,
)
from pipeline.restructure import RestructureDraft

_TS = "2026-06-22T00:00:00+00:00"


def _resp(content: str) -> MagicMock:
    ch = MagicMock()
    ch.message.content = content
    ch.finish_reason = "stop"
    r = MagicMock()
    r.choices = [ch]
    return r


def _smart_client() -> MagicMock:
    """Mock-Client: erkennt Klassifikator/Stage-3/Stage-4 an den Messages."""
    c = MagicMock()

    def _se(**kw: Any) -> MagicMock:
        msgs = kw["messages"]
        system = msgs[0]["content"]
        user = msgs[-1]["content"]
        if "klassifizierst" in system:
            return _resp("compact-reference")
        if "Ziel-type:" in user:
            return _resp("```markdown\n# Titel\n\nRe-strukturierter Body.\n```")
        return _resp('```json\n{"title":"Titel","summary":"S","confidence":"high"}\n```')

    c.chat.completions.create.side_effect = _se
    return c


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


def _prompts(tmp_path: Path) -> Path:
    v2 = tmp_path / "prompts" / "v2"
    v2.mkdir(parents=True)
    (v2 / "stage3_synthesis.md").write_text("Stage-3.\n", encoding="utf-8")
    (v2 / "stage4_frontmatter_json.md").write_text("Stage-4.\n", encoding="utf-8")
    return tmp_path / "prompts"


_VARIANTS = {
    "formatted": "---\nslug: formatted\ntype: compact-reference\ntags:\n  - api-design\n---\n\n## H\n\nText.\n",
    "scraped": "# Roh-Titel\n\n\n\nText   mit   doppeltem   Spacing.\n",
    "copypaste": "Einfach Prosa, copy-paste, ohne Frontmatter und ohne Headings.\n",
    "unformatted": "**fett** und kram\nzweite zeile\n",
}


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "source"
    src.mkdir()
    for name, content in _VARIANTS.items():
        (src / f"{name}.md").write_text(content, encoding="utf-8")
    return src


def _run(tmp_path: Path, *, client: MagicMock | None = None, resume: bool = False) -> Any:
    return run_process(
        _make_source(tmp_path) if not (tmp_path / "source").exists() else tmp_path / "source",
        client=client or _smart_client(),
        qwen=_qwen_cfg(),
        vault_dir=tmp_path / "vault",
        work_dir=tmp_path / "work",
        prompts_dir=_prompts(tmp_path)
        if not (tmp_path / "prompts").exists()
        else tmp_path / "prompts",
        timestamp=_TS,
        resume=resume,
    )


# === Stage-Kette: alle Files, kein Filter =====================================


def test_all_variants_reach_review_ready(tmp_path: Path) -> None:
    (tmp_path / "vault").mkdir()
    result = _run(tmp_path)
    assert len(result.review_ready) == 4  # jede Variante, keine gefiltert
    for st in result.review_ready:
        assert st.stage == "review_ready"
        fm = yaml.safe_load(Path(st.working_path).read_text(encoding="utf-8").split("---\n")[1])
        assert fm.get("slug")  # vault-ready: Frontmatter mit Slug
        assert fm.get("type")  # type aufgelöst
    assert result.sheet_path is not None
    assert result.sheet_path.exists()


# === Deterministische Stages: korrekt + idempotent ============================


def _working(tmp_path: Path, content: str) -> FileState:
    p = tmp_path / "w.md"
    p.write_text(content, encoding="utf-8")
    return FileState("src", "w", "sha256:x", "ingested", str(p), _TS)


def test_normalize_adds_slug_and_idempotent(tmp_path: Path) -> None:
    st = _working(tmp_path, "# H\n\n\n\nText   mit   spacing.\n")
    _stage_normalize(st)
    first = Path(st.working_path).read_bytes()
    fm = yaml.safe_load(first.decode().split("---\n")[1])
    assert fm["slug"] == "w"
    _stage_normalize(st)
    assert Path(st.working_path).read_bytes() == first  # idempotent


def test_tags_map_to_vocab_drop_freetext_idempotent(tmp_path: Path) -> None:
    st = _working(
        tmp_path,
        "---\nslug: w\ntags:\n  - api-design\n  - zzz-freitext\n  - architecture\n---\n\nBody.\n",
    )
    _stage_tags(st)
    fm = yaml.safe_load(Path(st.working_path).read_text(encoding="utf-8").split("---\n")[1])
    assert fm["tags"] == ["api", "architecture"]  # Synonym→api, Freitext gedroppt, sortiert
    first = Path(st.working_path).read_bytes()
    _stage_tags(st)
    assert Path(st.working_path).read_bytes() == first  # idempotent


def test_assets_and_links_normalize_idempotent(tmp_path: Path) -> None:
    st = _working(tmp_path, "---\nslug: w\n---\n\n![[ bild.png ]] und [[ Notiz ]].\n")
    _stage_assets(st)
    _stage_links(st)
    body = Path(st.working_path).read_text(encoding="utf-8")
    assert "![[bild.png]]" in body
    assert "[[Notiz]]" in body
    first = Path(st.working_path).read_bytes()
    _stage_assets(st)
    _stage_links(st)
    assert Path(st.working_path).read_bytes() == first  # idempotent


# === Idempotenz gesamt ========================================================


def test_overall_idempotent_no_double_work(tmp_path: Path) -> None:
    (tmp_path / "vault").mkdir()
    client = _smart_client()
    r1 = _run(tmp_path, client=client)
    calls_after_1 = client.chat.completions.create.call_count
    drafts_1 = {st.slug: Path(st.working_path).read_bytes() for st in r1.review_ready}

    r2 = _run(tmp_path, client=client)  # 2. Lauf, unveränderte Source
    assert client.chat.completions.create.call_count == calls_after_1  # keine neuen LLM-Calls
    assert len(r2.review_ready) == 4
    drafts_2 = {st.slug: Path(st.working_path).read_bytes() for st in r2.review_ready}
    assert drafts_2 == drafts_1  # byte-stabil


# === Resilienz + Resume =======================================================


def _fake_restructure_factory(fail_slug: str) -> Any:
    from pipeline.restructure import RestructureError

    def _fake(
        source_path: Path,
        *,
        client: Any,
        qwen: Any,
        out_dir: Path,
        prompts_dir: Any = None,
        timestamp: Any = None,
    ) -> RestructureDraft:
        fm_text = source_path.read_text(encoding="utf-8").split("---\n")
        slug = source_path.stem
        if len(fm_text) >= 3:
            data = yaml.safe_load(fm_text[1]) or {}
            slug = data.get("slug") or slug
        if slug == fail_slug:
            raise RestructureError(f"Stage 3 (Body) fehlgeschlagen für {slug}. Kein Draft.")
        out_dir.mkdir(parents=True, exist_ok=True)
        dp = out_dir / f"{slug}.md"
        dp.write_text(
            f"---\nslug: {slug}\ntype: compact-reference\ntype_source: frontmatter\n"
            f"restructure_action: passthrough\nreview_status: ai_drafted\nconfidence: high\n"
            f"---\n\n# T\n\nBody.\n",
            encoding="utf-8",
        )
        return RestructureDraft(
            slug, dp, "high", False, "compact-reference", "frontmatter", "passthrough"
        )

    return _fake


def test_resilience_one_fail_rest_reach_review_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "vault").mkdir()
    monkeypatch.setattr(
        "pipeline.process_orchestrator.restructure_file", _fake_restructure_factory("copypaste")
    )
    result = _run(tmp_path)
    assert {st.slug for st in result.review_ready} == {"formatted", "scraped", "unformatted"}
    assert len(result.failures) == 1
    assert result.failures[0][0].name == "copypaste.md"
    assert (tmp_path / "work" / "needs_human.txt").exists()


def test_resume_continues_after_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "vault").mkdir()
    # Lauf 1: 'scraped' scheitert in restructure → needs_human.
    monkeypatch.setattr(
        "pipeline.process_orchestrator.restructure_file", _fake_restructure_factory("scraped")
    )
    r1 = _run(tmp_path)
    assert any(f[0].name == "scraped.md" for f in r1.failures)
    state = load_state(tmp_path / "work" / "state.jsonl")
    scraped_key = next(k for k in state if k.endswith("scraped.md"))
    assert state[scraped_key].stage == "normalize"  # vor restructure stehengeblieben
    assert state[scraped_key].last_error is not None

    # Lauf 2 mit --resume + funktionierendem restructure → scraped erreicht review_ready.
    monkeypatch.setattr(
        "pipeline.process_orchestrator.restructure_file", _fake_restructure_factory("___none___")
    )
    r2 = _run(tmp_path, resume=True)
    assert "scraped" in {st.slug for st in r2.review_ready}
    assert not r2.failures


# === STOP an review_ready: kein Vault-Write ===================================


def test_no_vault_write_no_promotion(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "01_Grundlagen").mkdir()
    (vault / "01_Grundlagen" / "bestand.md").write_text(
        "---\nslug: bestand\n---\n\nx\n", encoding="utf-8"
    )
    before = {p: p.read_bytes() for p in vault.rglob("*.md")}
    _run(tmp_path)
    after = {p: p.read_bytes() for p in vault.rglob("*.md")}
    assert after == before  # Live-Vault unberührt, keine Promotion
