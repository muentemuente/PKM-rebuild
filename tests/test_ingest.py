"""Tests für pipeline/ingest.py — inkrementeller Ingest-Modus (Option B).

Qwen wird wie in test_phase_8_synthesis über einen openai-Mock ersetzt; der
bestehende Vault/Korpus wird nicht berührt (alles läuft in temp-Pfaden).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pipeline.config import load_config
from pipeline.ingest import run_ingest

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "pipeline" / "pipeline.config.yaml"

STAGE3_BODY = "# Inbox Testartikel\n\n" + ("Dies ist ausreichend Fliesstext fuer ein Segment. " * 40)

STAGE4_FM = {
    "title": "Inbox Testartikel",
    "slug": "inbox-testartikel",
    "aliases": [],
    "summary": "Ein synthetischer Inbox-Artikel fuer den Ingest-Test.",
    "type": "knowledge-article",
    "doc_role": ["explanation"],
    "category": "grundlagen",
    "subcategory": None,
    "tags": ["api", "neuer-tag"],
    "related": [],
    "used_in": [],
    "parent_concept": None,
    "child_concepts": [],
    "sources_docs": ["D_inbox-testartikel"],
    "source_chunks": ["D_inbox-testartikel-S0000"],
    "merged_from": [],
    "status": "draft",
    "review_status": "ai_drafted",
    "confidence": "medium",
    "doc_version": "0.1.0",
    "created": "2026-06-05",
    "updated": "2026-06-05",
    "last_synthesized": "2026-06-05",
    "prompt_version": "v1",
}

TAGSYS = """---
title: Tag-System
updated: 2026-01-01
---

## Kern-Vokabular (1)

### Web
`api`

---

## Synonym-Map

| Qwen-Vorschlag | Canonical |
|---|---|
| `x` | `api` |
"""

INBOX_DOC = "# Mein Inbox Thema\n\n" + (
    "Ein erklaerender Absatz ueber ein Thema mit genug Woertern fuer ein Segment. " * 30
)


def _make_mock_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def mock_qwen(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    def _resp(messages: list, **_kw: object) -> MagicMock:
        if "stage4_frontmatter" in str(messages):
            return _make_mock_response(f"```json\n{json.dumps(STAGE4_FM)}\n```")
        return _make_mock_response(f"```markdown\n{STAGE3_BODY}\n```")

    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: _resp(kw.get("messages", []))

    import pipeline.phase_8_synthesis as m8

    monkeypatch.setattr(m8, "openai", MagicMock(OpenAI=lambda **_: client))
    return client


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    v1 = tmp_path / "prompts" / "v1"
    v1.mkdir(parents=True)
    for name in (
        "stage3_synthesis.md",
        "stage4_frontmatter_json.md",
        "stage4_frontmatter_gedanken.md",
    ):
        (v1 / name).write_text(f"# System-Prompt\nTest-Prompt: {name}\n", encoding="utf-8")
    return tmp_path / "prompts"


@pytest.fixture
def cfg(tmp_path: Path):
    c = load_config(CONFIG)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    vault = tmp_path / "vault"
    (vault / "01_Grundlagen").mkdir(parents=True)
    tagsys = tmp_path / "tag-system.md"
    tagsys.write_text(TAGSYS, encoding="utf-8")
    c.paths.inbox = inbox
    c.paths.pipeline_output = out
    c.paths.drafts = drafts
    c.paths.vault = vault
    c.tags.vocabulary_file = tagsys
    return c


def test_ingest_empty_inbox_is_noop(cfg) -> None:
    summary = run_ingest(cfg, force=True)
    assert summary["inbox_files"] == 0
    assert summary["skipped"] is True


def test_ingest_dry_run_writes_nothing(cfg) -> None:
    (cfg.paths.inbox / "thema.md").write_text(INBOX_DOC, encoding="utf-8")
    summary = run_ingest(cfg, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["inbox_files"] == 1
    # nichts geschrieben
    assert list(cfg.paths.drafts.glob("*.md")) == []
    assert not (cfg.paths.pipeline_output / "ingest_report.md").exists()


def test_ingest_produces_draft_and_report(cfg, mock_qwen, prompts_dir) -> None:
    (cfg.paths.inbox / "thema.md").write_text(INBOX_DOC, encoding="utf-8")
    summary = run_ingest(cfg, force=True, prompts_dir=prompts_dir)

    assert summary["inbox_files"] == 1
    assert summary["new_drafts"] >= 1
    # neuer Draft liegt in 03_drafts (temp)
    assert any(p.name.startswith("CK_") for p in cfg.paths.drafts.glob("*.md"))
    # Report existiert + enthält neu-vs-bestehend-Flags
    report = (cfg.paths.pipeline_output / "ingest_report.md").read_text(encoding="utf-8")
    assert "Ingest-Report" in report
    assert "grundlagen" in report  # bestehende category
    # neuer-tag ist NEU, api bestehend
    assert summary["new_tags"] >= 1
    assert "🆕 NEU" in report


def test_ingest_existing_vault_untouched(cfg, mock_qwen, prompts_dir) -> None:
    sentinel = cfg.paths.vault / "01_Grundlagen" / "bestehend.md"
    sentinel.write_text("---\nslug: bestehend\n---\n\n# bestehend\n", encoding="utf-8")
    before = sentinel.read_text(encoding="utf-8")
    (cfg.paths.inbox / "thema.md").write_text(INBOX_DOC, encoding="utf-8")
    run_ingest(cfg, force=True, prompts_dir=prompts_dir)
    assert sentinel.read_text(encoding="utf-8") == before


def test_ingest_idempotent_second_run_no_new_drafts(cfg, mock_qwen, prompts_dir) -> None:
    (cfg.paths.inbox / "thema.md").write_text(INBOX_DOC, encoding="utf-8")
    run_ingest(cfg, force=True, prompts_dir=prompts_dir)
    summary2 = run_ingest(cfg, prompts_dir=prompts_dir)
    assert summary2["new_drafts"] == 0
