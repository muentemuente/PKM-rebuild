"""Tests für pipeline/review.py — Review-Gate-System (WP4).

Pro Gate ein Wirkungs-Test (Fixture-Item → Entscheidung → erwartete Wirkung) plus
Round-Trip (render → parse) und Producer. Die echten config/-Dateien werden NICHT
angefasst: cfg.paths.config zeigt auf eine tmp-Kopie; CATEGORY_TO_FOLDER wird je
Test gesnapshottet und zurückgesetzt.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from pipeline import review
from pipeline.config import load_config
from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER
from pipeline.review import (
    DecisionItem,
    apply_review,
    build_decisions,
    parse_decisions_md,
    render_decisions_md,
    render_review,
)

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "pipeline" / "pipeline.config.yaml"

VALID_FM = {
    "title": "Testartikel",
    "slug": "testartikel",
    "aliases": [],
    "summary": "Ein gültiges Frontmatter für den Review-Test mit genug Text.",
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


@pytest.fixture(autouse=True)
def _restore_category_map() -> Iterator[None]:
    """Snapshot + Restore des globalen CATEGORY_TO_FOLDER (Gate B mutiert es)."""
    snapshot = dict(CATEGORY_TO_FOLDER)
    yield
    CATEGORY_TO_FOLDER.clear()
    CATEGORY_TO_FOLDER.update(snapshot)


@pytest.fixture
def cfg(tmp_path: Path):
    """PipelineConfig mit tmp-Pfaden + tmp-Kopie der echten config/-Dateien."""
    c = load_config(CONFIG)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    for name in ("categories.yaml", "tag_vocabulary.yaml", "tag_merge_map.json"):
        shutil.copy(REPO / "config" / name, cfg_dir / name)
    c.paths.config = cfg_dir
    c.paths.drafts = tmp_path / "drafts"
    c.paths.output = tmp_path / "output"
    c.paths.work = tmp_path / "work"
    c.paths.review = tmp_path / "review"
    for p in (c.paths.drafts, c.paths.output, c.paths.work, c.paths.review):
        p.mkdir(parents=True, exist_ok=True)
    c.tags.vocabulary_file = cfg_dir / "tag_vocabulary.yaml"
    return c


def _write_draft(cfg, stem: str, fm: dict) -> None:
    (cfg.paths.drafts / f"{stem}.frontmatter.json").write_text(
        json.dumps(fm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    (cfg.paths.drafts / f"{stem}.md").write_text(
        f"---\n{dumped}\n---\n\n# {fm['title']}\n\nBody.\n", encoding="utf-8"
    )


# === Round-Trip render ↔ parse ===============================================


def test_render_parse_roundtrip() -> None:
    items = [
        DecisionItem("CK_a", "category", "Frage", "fremd", ["zuweisen"], "grundlagen"),
        DecisionItem("CK_b", "tags", "Frage", "neuer-tag", ["aufnehmen"], "webentwicklung"),
    ]
    md = render_decisions_md(items)
    # leere decisions.md → nichts entschieden
    assert parse_decisions_md(md) == {}
    # Mensch füllt die erste Entscheidung aus
    filled = md.replace("**Entscheidung:** \n", "**Entscheidung:** zuweisen\n", 1)
    parsed = parse_decisions_md(filled)
    assert items[0].item_id in parsed
    assert parsed[items[0].item_id][0] == "zuweisen"


# === Gate A — quality =========================================================


def test_gate_quality_nachbessern_moves_to_needs_human(cfg) -> None:
    _write_draft(cfg, "CK_bad", VALID_FM)
    item = DecisionItem("CK_bad", "quality", "?", "low", ["nachbessern"], "grundlagen")
    item.decision = "nachbessern"
    review.apply_decision(item, cfg)
    assert (cfg.paths.review / "needs_human" / "CK_bad.md").exists()
    assert not (cfg.paths.drafts / "CK_bad.md").exists()


def test_gate_quality_quarantaene_moves_to_quarantine(cfg) -> None:
    _write_draft(cfg, "CK_bad", VALID_FM)
    item = DecisionItem("CK_bad", "quality", "?", "low", ["quarantaene"], "grundlagen")
    item.decision = "quarantaene"
    review.apply_decision(item, cfg)
    assert (cfg.paths.review / "quarantine" / "CK_bad.frontmatter.json").exists()


# === Gate B — category ========================================================


def test_gate_category_zuweisen_sets_category(cfg) -> None:
    fm = {**VALID_FM, "category": "fremd-x"}
    _write_draft(cfg, "CK_c", fm)
    item = DecisionItem("CK_c", "category", "?", "fremd-x", [], "fremd-x")
    item.decision, item.value = "zuweisen", "webentwicklung"
    review.apply_decision(item, cfg)
    assert review.read_draft_frontmatter(cfg.paths.drafts, "CK_c")["category"] == "webentwicklung"


def test_gate_category_neu_lands_in_config_and_creates_folder(cfg) -> None:
    fm = {**VALID_FM, "category": "robotik"}
    _write_draft(cfg, "CK_r", fm)
    item = DecisionItem("CK_r", "category", "?", "robotik", [], "robotik")
    item.decision, item.value = "neu", "robotik"
    review.apply_decision(item, cfg)
    # 1. config/categories.yaml enthält die neue Kategorie
    data = yaml.safe_load((cfg.paths.config / "categories.yaml").read_text(encoding="utf-8"))
    assert "robotik" in data["categories"]
    folder = data["categories"]["robotik"]
    # 2. output/-Ordner angelegt
    assert (cfg.paths.output / folder).is_dir()
    # 3. CATEGORY_TO_FOLDER (Laufzeit) aktualisiert
    assert CATEGORY_TO_FOLDER["robotik"] == folder
    # 4. Draft trägt die neue category
    assert review.read_draft_frontmatter(cfg.paths.drafts, "CK_r")["category"] == "robotik"


# === Gate C — tags ============================================================


def test_gate_tags_aufnehmen_lands_in_vocab(cfg) -> None:
    fm = {**VALID_FM, "tags": ["api", "observability"]}
    _write_draft(cfg, "CK_t", fm)
    item = DecisionItem("CK_t", "tags", "?", "observability", [], "grundlagen")
    item.decision = "aufnehmen"
    review.apply_decision(item, cfg)
    vocab = yaml.safe_load((cfg.paths.config / "tag_vocabulary.yaml").read_text(encoding="utf-8"))
    all_tags = {t for tags in vocab["sections"].values() for t in tags}
    assert "observability" in all_tags


def test_gate_tags_mappen_replaces_and_records(cfg) -> None:
    fm = {**VALID_FM, "tags": ["api", "command-line"]}
    _write_draft(cfg, "CK_m", fm)
    item = DecisionItem("CK_m", "tags", "?", "command-line", [], "grundlagen")
    item.decision, item.value = "mappen", "cli"
    review.apply_decision(item, cfg)
    tags = review.read_draft_frontmatter(cfg.paths.drafts, "CK_m")["tags"]
    assert "cli" in tags
    assert "command-line" not in tags
    merge = json.loads((cfg.paths.config / "tag_merge_map.json").read_text(encoding="utf-8"))
    assert merge["remap"]["command-line"] == "cli"


def test_gate_tags_droppen_removes_and_records(cfg) -> None:
    fm = {**VALID_FM, "tags": ["api", "wegwerf-tag"]}
    _write_draft(cfg, "CK_d", fm)
    item = DecisionItem("CK_d", "tags", "?", "wegwerf-tag", [], "grundlagen")
    item.decision = "droppen"
    review.apply_decision(item, cfg)
    tags = review.read_draft_frontmatter(cfg.paths.drafts, "CK_d")["tags"]
    assert "wegwerf-tag" not in tags
    merge = json.loads((cfg.paths.config / "tag_merge_map.json").read_text(encoding="utf-8"))
    assert "wegwerf-tag" in merge["drop"]


# === Vocab-Writer: kommentar-/struktur-erhaltend (Option 2) ==================


def _comments(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.lstrip().startswith("#")]


def test_vocab_add_preserves_comment_header(cfg) -> None:
    """Der 12-zeilige Single-Source-Kommentar-Header bleibt nach Tag-Add intakt."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    before = _comments(path.read_text(encoding="utf-8"))
    assert len(before) == 12  # Beweis: es gibt einen Header zu erhalten
    review._add_tag_to_vocab(cfg, "observability")
    assert _comments(path.read_text(encoding="utf-8")) == before


def test_vocab_add_preserves_section_key_quoting(cfg) -> None:
    """Gequotete Section-Keys (Sonderzeichen) bleiben wörtlich gequotet."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    review._add_tag_to_vocab(cfg, "observability")
    after = path.read_text(encoding="utf-8")
    assert '  "Sprachen & Code":' in after
    assert '  "Terminal, Shell & Scripting":' in after


def test_vocab_add_is_idempotent(cfg) -> None:
    """Gleicher Tag zweimal → nicht doppelt, zweiter Aufruf liefert False, Datei unverändert."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    assert review._add_tag_to_vocab(cfg, "observability") is True
    after_first = path.read_text(encoding="utf-8")
    assert review._add_tag_to_vocab(cfg, "observability") is False
    assert path.read_text(encoding="utf-8") == after_first
    assert after_first.count("- observability") == 1


def test_vocab_add_creates_section_when_missing(cfg) -> None:
    """Fehlt 'Erweiterungen (review)', wird die Sektion korrekt angelegt."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    assert "Erweiterungen (review)" not in path.read_text(encoding="utf-8")
    review._add_tag_to_vocab(cfg, "observability")
    after = path.read_text(encoding="utf-8")
    assert "  Erweiterungen (review):" in after
    assert "    - observability" in after
    data = yaml.safe_load(after)
    assert data["sections"]["Erweiterungen (review)"] == ["observability"]


def test_vocab_add_inserts_before_synonyms(cfg) -> None:
    """Der neue Tag landet im sections-Block, vor dem synonyms-Block."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    review._add_tag_to_vocab(cfg, "observability")
    lines = path.read_text(encoding="utf-8").splitlines()
    item_idx = lines.index("    - observability")
    syn_idx = next(i for i, ln in enumerate(lines) if ln.startswith("synonyms:"))
    assert item_idx < syn_idx


def test_vocab_add_second_tag_into_existing_section(cfg) -> None:
    """Zweiter Tag wird an die bestehende Erweiterungs-Sektion angehängt (Reihenfolge erhalten)."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    review._add_tag_to_vocab(cfg, "observability")
    review._add_tag_to_vocab(cfg, "tracing")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["sections"]["Erweiterungen (review)"] == ["observability", "tracing"]


def test_review_apply_aufnehmen_preserves_single_source(cfg) -> None:
    """Regression: ein Gate-C 'aufnehmen' lässt die Single-Source strukturell unverändert (nur +Eintrag)."""
    path = cfg.paths.config / "tag_vocabulary.yaml"
    before = path.read_text(encoding="utf-8").splitlines()
    _write_draft(cfg, "CK_obs", {**VALID_FM, "tags": ["api", "observability"]})
    item = DecisionItem("CK_obs", "tags", "?", "observability", [], "grundlagen")
    item.decision = "aufnehmen"
    review.apply_decision(item, cfg)
    after = path.read_text(encoding="utf-8").splitlines()
    # Nur Sektion-Header + Tag-Zeile kommen hinzu; jede Original-Zeile bleibt wörtlich erhalten.
    added = ["  Erweiterungen (review):", "    - observability"]
    assert [ln for ln in after if ln not in added] == before
    assert len(after) == len(before) + 2


# === Gate D — final ===========================================================


def test_gate_final_publish_writes_state(cfg) -> None:
    item = DecisionItem("CK_f", "final", "?", "draft", [], "grundlagen")
    item.decision = "publish"
    review.apply_decision(item, cfg)
    state = json.loads((cfg.paths.work / "state.json").read_text(encoding="utf-8"))
    assert state["docs"]["CK_f"] == "approved"


# === Producer + End-to-End render/apply ======================================


def test_build_decisions_detects_open_points(cfg) -> None:
    _write_draft(cfg, "CK_unknown", {**VALID_FM, "category": "fremd", "tags": ["api", "x-neu"]})
    _write_draft(cfg, "CK_clean", VALID_FM)
    items = build_decisions(cfg)
    gates = {(it.doc_id, it.gate) for it in items}
    assert ("CK_unknown", "category") in gates
    assert ("CK_unknown", "tags") in gates
    assert ("CK_clean", "final") in gates  # sauberer Draft → nur Gate D


def test_render_review_then_apply_end_to_end(cfg) -> None:
    _write_draft(cfg, "CK_e", {**VALID_FM, "tags": ["api", "x-neu"]})
    render_review(cfg)  # erzeugt decisions.jsonl + decisions.md
    md_path = cfg.paths.review / "decisions.md"
    text = md_path.read_text(encoding="utf-8")
    # Mensch entscheidet: x-neu droppen
    text = text.replace("**Entscheidung:** \n", "**Entscheidung:** droppen\n")
    md_path.write_text(text, encoding="utf-8")
    summary = apply_review(cfg)
    assert any("x-neu" in note for note in summary["applied"])
    assert "x-neu" not in review.read_draft_frontmatter(cfg.paths.drafts, "CK_e")["tags"]
