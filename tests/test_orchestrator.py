"""Tests für pipeline/orchestrator.py — `pkm run` State-Maschine + Smoke-Run (WP5).

Der Smoke-Run ist die WP5-Akzeptanz: 3 synthetische .md (Prosa→stage3,
Code→passthrough, unbekannter Tag→Gate C) laufen bis zum Gate, `pkm review --apply`,
Fortsetzung bis output/. Qwen ist über einen openai-Mock ersetzt; config/ läuft
gegen tmp-Kopien.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from pipeline.config import load_config
from pipeline.orchestrator import _archive_inputs, load_state, run_pipeline, save_state
from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER
from pipeline.review import apply_review

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "pipeline" / "pipeline.config.yaml"


def _fm(slug: str, category: str, tags: list[str]) -> dict:
    return {
        "title": slug.replace("-", " ").title(),
        "slug": slug,
        "aliases": [],
        "summary": "Synthetischer Artikel für den Orchestrator-Smoke mit Text.",
        "type": "knowledge-article",
        "doc_role": ["explanation"],
        "category": category,
        "subcategory": None,
        "tags": tags,
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


# Token → Stage-4-Frontmatter (Mock differenziert die 3 Docs).
_TOKENS = {
    "ZZPROSA": _fm("prosa-thema", "grundlagen", ["api"]),
    "ZZCODE": _fm("code-thema", "webentwicklung", ["python"]),
    "ZZTAG": _fm("tag-thema", "grundlagen", ["api", "voellig-neuer-tag"]),
}


def _which_token(s: str) -> str:
    for tok in _TOKENS:
        if tok in s:
            return tok
    return "ZZPROSA"


@pytest.fixture(autouse=True)
def _restore_category_map() -> Iterator[None]:
    snapshot = dict(CATEGORY_TO_FOLDER)
    yield
    CATEGORY_TO_FOLDER.clear()
    CATEGORY_TO_FOLDER.update(snapshot)


@pytest.fixture
def mock_qwen(monkeypatch: pytest.MonkeyPatch):
    def _resp(messages: list, **_kw: object):
        s = str(messages)
        from unittest.mock import MagicMock

        choice = MagicMock()
        tok = _which_token(s)
        if "stage4_frontmatter" in s:
            choice.message.content = f"```json\n{json.dumps(_TOKENS[tok])}\n```"
        else:
            choice.message.content = f"```markdown\n# Artikel\n\n{tok} veredelter Text.\n```"
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    from unittest.mock import MagicMock

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
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    for name in ("categories.yaml", "tag_vocabulary.yaml", "tag_merge_map.json"):
        shutil.copy(REPO / "config" / name, cfg_dir / name)
    c.paths.config = cfg_dir
    c.paths.input = tmp_path / "input"
    c.paths.work = tmp_path / "work"
    c.paths.drafts = tmp_path / "drafts"
    c.paths.output = tmp_path / "output"
    c.paths.review = tmp_path / "review"
    c.paths.archive = tmp_path / "archive"
    c.paths.backups = tmp_path / "archive" / "backups"
    for p in (
        c.paths.input,
        c.paths.work,
        c.paths.drafts,
        c.paths.output,
        c.paths.review,
        c.paths.archive,
        c.paths.backups,
    ):
        p.mkdir(parents=True, exist_ok=True)
    c.tags.vocabulary_file = cfg_dir / "tag_vocabulary.yaml"
    return c


# === State-Maschine ===========================================================


def test_state_roundtrip(cfg) -> None:
    state = load_state(cfg)
    assert state["docs"] == {}
    state["docs"]["CK_x"] = "drafted"
    save_state(cfg, state)
    assert load_state(cfg)["docs"]["CK_x"] == "drafted"


def test_run_idle_on_empty_input(cfg) -> None:
    summary = run_pipeline(cfg, prompts_dir=Path("prompts"))
    assert summary["status"] == "idle"


# === Input-Assets Auto-Cleanup ===============================================


def test_archive_inputs_also_archives_and_clears_input_assets(cfg) -> None:
    """Nach Build: input/_assets/ wird mit-archiviert und geleert; output/_assets/ unberührt."""
    md = cfg.paths.input / "doc.md"
    md.write_text("# Doc\n\n![[bild.png]]\n", encoding="utf-8")
    assets = cfg.paths.input / "_assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "bild.png").write_bytes(b"PNG-bytes")
    (assets / "orphan.png").write_bytes(
        b"orphan"
    )  # nicht referenziert → wandert dennoch ins Archiv
    # output/_assets/ simuliert den abgeschlossenen Build (Phase 9 hat schon kopiert)
    out_assets = cfg.paths.output / "_assets"
    out_assets.mkdir(parents=True, exist_ok=True)
    (out_assets / "bild.png").write_bytes(b"PNG-bytes")

    n = _archive_inputs(cfg, [md])

    assert n == 1
    # input/ (md) + input/_assets/ vollständig geleert
    assert not any(cfg.paths.input.glob("*.md"))
    assert list(assets.iterdir()) == []
    # Assets liegen im selben processed_<ts>/_assets/
    processed = list(cfg.paths.archive.glob("processed_*"))
    assert len(processed) == 1
    archived_assets = {p.name for p in (processed[0] / "_assets").iterdir()}
    assert archived_assets == {"bild.png", "orphan.png"}
    assert (processed[0] / "doc.md").exists()
    # output/_assets/ unangetastet
    assert (out_assets / "bild.png").exists()


def test_archive_inputs_idempotent_when_assets_empty(cfg) -> None:
    """Zweiter Lauf ohne neue Inputs/Assets ist ein No-op (kein Fehler, input/_assets bleibt leer)."""
    (cfg.paths.input / "_assets").mkdir(parents=True, exist_ok=True)
    assert _archive_inputs(cfg, []) == 0  # keine Inputs → früher Abbruch
    md = cfg.paths.input / "doc.md"
    md.write_text("# Doc\n", encoding="utf-8")
    assert _archive_inputs(cfg, [md]) == 1  # Inputs da, aber _assets leer → kein Crash
    assert list((cfg.paths.input / "_assets").iterdir()) == []


# === Smoke-Run (WP5-Akzeptanz) ================================================


def test_smoke_run_to_gate_then_apply_then_publish(cfg, mock_qwen, prompts_dir) -> None:
    # 3 synthetische Inputs: Prosa→stage3, Code→passthrough, unbekannter Tag→Gate C
    # >500 Wörter reine Prosa (kein Code/Tabelle, <3 Headings) → doc_type explanation → stage3
    (cfg.paths.input / "prosa.md").write_text(
        "# Prosa Thema\n\nZZPROSA " + ("erklaerender Fliesstext fuer ein Segment hier. " * 90),
        encoding="utf-8",
    )
    # Code-Block → passthrough (kein stage3-LLM-Call, nur stage4)
    (cfg.paths.input / "code.md").write_text(
        "# Code Thema\n\nZZCODE Einleitung.\n\n```python\nprint('hallo')\n```\n",
        encoding="utf-8",
    )
    # >500 Wörter, trägt einen unbekannten Tag → Gate C
    (cfg.paths.input / "tag.md").write_text(
        "# Tag Thema\n\nZZTAG " + ("noch ein Absatz mit ausreichend Woertern hier drin. " * 90),
        encoding="utf-8",
    )

    # Lauf 1: bis Gate
    s1 = run_pipeline(cfg, prompts_dir=prompts_dir)
    assert s1["status"] == "review_pending"
    assert s1["new_drafts"] == 3
    assert s1["per_gate"]["tags"] >= 1  # unbekannter Tag → Gate C
    assert s1["per_gate"]["final"] == 3  # Publish-Punkt pro Draft

    # Mensch entscheidet in decisions.md: Tag droppen + alle 3 publish
    md = cfg.paths.review / "decisions.md"
    text = md.read_text(encoding="utf-8")
    # Gate C steht vor Gate D → erste leere Entscheidung = Tag (droppen), Rest = publish
    text = text.replace("**Entscheidung:** \n", "**Entscheidung:** droppen\n", 1)
    text = text.replace("**Entscheidung:** \n", "**Entscheidung:** publish\n")
    md.write_text(text, encoding="utf-8")
    applied = apply_review(cfg)
    assert applied["errors"] == []

    # Lauf 2: Fortsetzung → Build nach output/
    s2 = run_pipeline(cfg, prompts_dir=prompts_dir)
    assert s2["status"] == "published"
    assert s2["articles"] == 3
    # output/ enthält 3 Artikel in den gemappten Ordnern
    built = list(cfg.paths.output.rglob("*.md"))
    article_md = [p for p in built if p.name != "_index.md"]
    assert len(article_md) == 3
    # verarbeitete Inputs archiviert
    assert s2["archived_inputs"] == 3
    assert not any(cfg.paths.input.glob("*.md"))
    # State: alle published
    state = load_state(cfg)
    assert all(st == "published" for st in state["docs"].values())
