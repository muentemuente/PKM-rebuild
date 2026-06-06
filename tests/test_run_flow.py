"""Tests für pipeline/run_flow.py — go-forward-Synthese-Engine (Option B).

Deckt die WP3-Punkte ab: Token-Cap-Segmentierung (1 Doc = 1 Segment unter Cap),
intra-run SHA-Dedup (kein Bestands-Check) und der getrimmte Pfad (kein 5/6/7).
Qwen wird wie in test_ingest über einen openai-Mock ersetzt.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pipeline.config import load_config
from pipeline.phase_4_segment import run_phase_4
from pipeline.run_flow import (
    compute_token_cap_words,
    intra_run_dedup_sets,
    run_synthesis_flow,
)

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "pipeline" / "pipeline.config.yaml"

INBOX_DOC = "# Mein Thema\n\n" + (
    "Ein erklaerender Absatz ueber ein Thema mit genug Woertern fuer ein Segment. " * 30
)

STAGE3_BODY = "# Testartikel\n\n" + ("Genug Fliesstext fuer ein Segment. " * 40)

STAGE4_FM = {
    "title": "Testartikel",
    "slug": "testartikel",
    "aliases": [],
    "summary": "Ein synthetischer Artikel fuer den run_flow-Test.",
    "type": "knowledge-article",
    "doc_role": ["explanation"],
    "category": "grundlagen",
    "subcategory": None,
    "tags": ["api"],
    "related": [],
    "used_in": [],
    "parent_concept": None,
    "child_concepts": [],
    "sources_docs": ["D_x"],
    "source_chunks": ["D_x-S0000"],
    "merged_from": [],
    "status": "draft",
    "review_status": "ai_drafted",
    "confidence": "medium",
    "doc_version": "0.1.0",
    "created": "2026-06-06",
    "updated": "2026-06-06",
    "last_synthesized": "2026-06-06",
    "prompt_version": "v1",
}


# === reine Funktionen =========================================================


def test_compute_token_cap_words_positive() -> None:
    cfg = load_config(CONFIG)
    cap = compute_token_cap_words(cfg)
    # context_window (49152) - stage3 (16000) = 33152 Token * 0.6 ≈ 19891 Wörter
    assert cap > 1000
    assert cap < cfg.qwen.context_window


def test_intra_run_dedup_sets(tmp_path: Path) -> None:
    manifest = tmp_path / "files_manifest.jsonl"
    rows = [
        {"doc_id": "D_a", "sha256": "AAA"},
        {"doc_id": "D_b", "sha256": "BBB"},
        {"doc_id": "D_c", "sha256": "AAA"},  # Duplikat von D_a
    ]
    full = {
        "path": "/x.md",
        "filename": "x.md",
        "size_bytes": 1,
        "modified_at": "2026-06-06T00:00:00",
        "line_count": 1,
        "word_count": 1,
        "char_count": 1,
    }
    manifest.write_text("\n".join(json.dumps({**full, **r}) for r in rows) + "\n", encoding="utf-8")
    kept, dropped = intra_run_dedup_sets(manifest)
    assert kept == {"D_a", "D_b"}
    assert len(dropped) == 1
    assert dropped[0]["doc_id"] == "D_c"
    assert dropped[0]["duplicate_of"] == "D_a"


# === Token-Cap-Segmentierung (Phase 4 go-forward-Modus) =======================


def _phase4(tmp_path: Path, body: str, *, cap: int | None) -> int:
    """Hilfs-Runner: schreibt manifest+cleaned, ruft run_phase_4, gibt Segment-Anzahl."""
    manifest = tmp_path / "files_manifest.jsonl"
    cleaned = tmp_path / "cleaned_documents.jsonl"
    out = tmp_path / "segments.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "doc_id": "D_x",
                "path": "/x.md",
                "filename": "x.md",
                "size_bytes": 1,
                "modified_at": "2026-06-06T00:00:00",
                "sha256": "x",
                "line_count": 1,
                "word_count": 1,
                "char_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cleaned.write_text(
        json.dumps({"doc_id": "D_x", "body": body, "frontmatter": {}, "normalized_sha256": "x"})
        + "\n",
        encoding="utf-8",
    )
    segs = run_phase_4(
        cleaned_path=cleaned,
        manifest_path=manifest,
        output_path=out,
        force=True,
        min_words=150,
        max_words=1500,
        token_cap_words=cap,
    )
    return len(segs)


def test_token_cap_keeps_multiheading_doc_whole(tmp_path: Path) -> None:
    # Doc mit 3 H1 — klassisch ≥3 Segmente, unter Cap aber 1 Segment.
    body = "# A\n\nAbsatz a.\n\n# B\n\nAbsatz b.\n\n# C\n\nAbsatz c.\n"
    assert _phase4(tmp_path, body, cap=100000) == 1


def test_token_cap_overflow_falls_back_to_split(tmp_path: Path) -> None:
    # Großes Doc über Cap (cap=5 Wörter) → klassischer Split greift; viele Absätze
    # (je 100 Wörter) summieren > max_words (1500) → Block-Split → >1 Segment.
    paragraphs = "\n\n".join(["wort " * 100 for _ in range(20)])
    body = "# A\n\n" + paragraphs + "\n"
    assert _phase4(tmp_path, body, cap=5) > 1


def test_no_cap_is_classic_behavior(tmp_path: Path) -> None:
    # token_cap_words=None → Heading-Split wie im Korpus-Erstlauf.
    body = "# A\n\n" + ("wort " * 200) + "\n\n# B\n\n" + ("wort " * 200) + "\n"
    assert _phase4(tmp_path, body, cap=None) > 1


# === e2e: intra-run Dedup im Flow =============================================


@pytest.fixture
def mock_qwen(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    def _resp(messages: list, **_kw: object) -> MagicMock:
        choice = MagicMock()
        if "stage4_frontmatter" in str(messages):
            choice.message.content = f"```json\n{json.dumps(STAGE4_FM)}\n```"
        else:
            choice.message.content = f"```markdown\n{STAGE3_BODY}\n```"
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        return resp

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
        (v1 / name).write_text(f"# System-Prompt\nTest: {name}\n", encoding="utf-8")
    return tmp_path / "prompts"


@pytest.fixture
def cfg(tmp_path: Path):
    c = load_config(CONFIG)
    src = tmp_path / "input"
    src.mkdir()
    c.paths.input = src
    c.paths.work = tmp_path / "work"
    c.paths.drafts = tmp_path / "drafts"
    (tmp_path / "drafts").mkdir()
    tagsys = tmp_path / "tag-system.md"
    tagsys.write_text("## Kern-Vokabular\n\n### Web\n`api`\n", encoding="utf-8")
    c.tags.vocabulary_file = tagsys
    return c


def test_flow_dedup_skips_duplicate_input(cfg, mock_qwen, prompts_dir) -> None:
    # Zwei byte-identische Inputs (verschiedene Namen) → 1 synthetisiert, 1 verworfen.
    (cfg.paths.input / "thema-a.md").write_text(INBOX_DOC, encoding="utf-8")
    (cfg.paths.input / "thema-b.md").write_text(INBOX_DOC, encoding="utf-8")
    result = run_synthesis_flow(cfg, force=True, prompts_dir=prompts_dir)
    assert result["docs_inventoried"] == 2
    assert len(result["dropped_duplicates"]) == 1
    assert result["docs_synthesized"] == 1
