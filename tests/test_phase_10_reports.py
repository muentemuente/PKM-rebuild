"""Tests für Phase 10 — Kontroll-Berichte.

Fixtures sind synthetisch (nicht gegen den echten Korpus). Der Vault wird über
den echten Phase-9-Builder aus synthetischen Drafts erzeugt, damit cluster_report
und corpus_report gegen realistische Ground Truth laufen.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pipeline.phase_9_vault_build import run_phase_9
from pipeline.phase_10_reports import (
    generate_cluster_report,
    generate_corpus_report,
    generate_duplicate_report,
    run_phase_10,
)

_BASE_FM: dict = {
    "title": "Testartikel",
    "slug": "test-artikel",
    "summary": "Synthetische Zusammenfassung.",
    "type": "knowledge-article",
    "doc_role": ["reference"],
    "category": "grundlagen",
    "tags": ["tag-a", "tag-b"],
    "sources_docs": ["D_test"],
    "source_chunks": ["D_test-S0000"],
    "confidence": "medium",
    "created": "2026-06-01",
    "updated": "2026-06-02",
    "last_synthesized": "2026-06-02",
    "prompt_version": "v1",
}


def _make_draft(
    drafts_dir: Path,
    stem: str,
    *,
    slug: str,
    category: str = "grundlagen",
    tags: list[str] | None = None,
) -> None:
    fm = dict(_BASE_FM)
    fm.update(slug=slug, category=category, title=f"Artikel {slug}", tags=tags or ["tag-a"])
    body = f"# {fm['title']}\n\nKörper von {slug}.\n"
    (drafts_dir / f"CK_{stem}.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + body,
        encoding="utf-8",
    )
    (drafts_dir / f"CK_{stem}.body.md").write_text(body, encoding="utf-8")


def _write_manifest(path: Path, n_docs: int) -> None:
    now = datetime.now(tz=UTC).isoformat()
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n_docs):
            rec = {
                "doc_id": f"D_doc{i}",
                "path": f"/corpus/doc{i}.md",
                "filename": f"doc{i}.md",
                "size_bytes": 1000 + i,
                "modified_at": now,
                "sha256": f"{i:064x}",
                "line_count": 10,
                "word_count": 100 + i * 50,
                "char_count": 600,
            }
            fh.write(json.dumps(rec) + "\n")


def _write_structured(path: Path, n_docs: int) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n_docs):
            rec = {
                "doc_id": f"D_doc{i}",
                "title": f"Doc {i}",
                "headings": [],
                "code_blocks": [],
                "tables_count": 0,
                "links": [],
                "images": [],
                "doc_type_guess": {"label": "reference", "confidence": 0.8, "signals": []},
            }
            fh.write(json.dumps(rec) + "\n")


def _write_segments(path: Path, n_segments: int) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n_segments):
            fh.write(json.dumps({"segment_id": f"D_doc0-S{i:04d}"}) + "\n")


def _write_exact(path: Path, groups: list[list[str]]) -> None:
    path.write_text(
        json.dumps([{"sha256": f"{i:064x}", "doc_ids": g} for i, g in enumerate(groups)]),
        encoding="utf-8",
    )


def _write_edges(path: Path, edges: list[tuple[str, str, float]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for a, b, s in edges:
            fh.write(json.dumps({"segment_id_a": a, "segment_id_b": b, "similarity": s}) + "\n")


@pytest.fixture
def env(temp_dir: Path):
    """Baut drafts + vault (via Phase 9) + Phase-1/5-Fixtures unter temp_dir."""
    drafts = temp_dir / "03_drafts"
    vault = temp_dir / "04_vault"
    out = temp_dir / "02_pipeline_output"
    corpus = temp_dir / "01_corpus_input"
    backups = temp_dir / "backups"
    for d in (drafts, vault, out, corpus, backups):
        d.mkdir(parents=True)

    # 5 Drafts: 3 grundlagen, 1 webentwicklung, 1 unsortiert
    _make_draft(drafts, "a", slug="alpha", category="grundlagen", tags=["x", "y"])
    _make_draft(drafts, "b", slug="beta", category="grundlagen", tags=["x"])
    _make_draft(drafts, "c", slug="gamma", category="grundlagen", tags=["x"])
    _make_draft(drafts, "d", slug="delta", category="webentwicklung", tags=["z"])
    _make_draft(drafts, "e", slug="epsilon", category="unsortiert", tags=["w"])
    run_phase_9(drafts, vault, out, backups, force=True)

    _write_manifest(out / "files_manifest.jsonl", 8)  # 8 Korpus-Docs
    _write_structured(out / "documents_structured.jsonl", 8)
    _write_segments(out / "segments.jsonl", 25)  # 25 Segmente ≠ 8 Docs
    _write_exact(out / "exact_duplicates.json", [["D_doc0", "D_doc1"]])
    _write_edges(out / "near_duplicate_edges.jsonl", [("D_doc0-S0000", "D_doc1-S0000", 0.95)])
    (corpus / "_excluded").mkdir()
    (corpus / "_excluded" / "x1.md").write_text("x", encoding="utf-8")
    (corpus / "_excluded" / "x2.md").write_text("x", encoding="utf-8")
    return drafts, vault, out, corpus


def _corpus(env, **kw) -> Path:
    drafts, vault, out, corpus = env
    return generate_corpus_report(
        out / "files_manifest.jsonl",
        out / "documents_structured.jsonl",
        out / "segments.jsonl",
        out / "corpus_report.md",
        drafts_dir=drafts,
        vault_dir=vault,
        corpus_input=corpus,
        **kw,
    )


def _cluster(env, **kw) -> Path:
    drafts, vault, out, _ = env
    return generate_cluster_report(drafts, vault, out / "cluster_report.md", **kw)


def _duplicate(env, **kw) -> Path:
    drafts, vault, out, _ = env
    return generate_duplicate_report(
        out / "exact_duplicates.json",
        out / "near_duplicate_edges.jsonl",
        out / "duplicate_report.md",
        drafts_dir=drafts,
        vault_dir=vault,
        **kw,
    )


# === corpus counts ============================================================


def test_corpus_doc_count_and_segment_separation(env) -> None:
    text = _corpus(env, force=True).read_text(encoding="utf-8")
    assert "Files gesamt (Korpus, Doc-Ebene): 8" in text
    assert "Segmente gesamt (Segment-Ebene, ≠ Doc-Count): 25" in text


def test_corpus_processing_status(env) -> None:
    """ready=5 (gebaut), excluded=2, hold=8-5-2=1; Summe == 8."""
    text = _corpus(env, force=True).read_text(encoding="utf-8")
    assert "`ready` (im Vault) | 5" in text
    assert "`excluded` | 2" in text
    assert "`hold` (pending) | 1" in text
    assert "**Summe** | **8**" in text


# === duplicate report =========================================================


def test_duplicate_groups_and_merged_from_note(env) -> None:
    text = _duplicate(env, force=True).read_text(encoding="utf-8")
    assert "Anzahl Gruppen: 1" in text
    assert "Keine Konsolidierungen" in text
    assert "`merged_from` ist bei allen 5 Vault-Artikeln leer (0 mit Einträgen)" in text


# === cluster sum ==============================================================


def test_cluster_sum_equals_total(env) -> None:
    text = _cluster(env, force=True).read_text(encoding="utf-8")
    assert "Vault-Artikel gesamt: 5" in text
    assert "| 01_Grundlagen | 3 |" in text
    assert "| 02_Webentwicklung | 1 |" in text
    assert "| **Summe** | **5** |" in text
    assert "⚠️ Abweichung" not in text


def test_cluster_unsorted_section(env) -> None:
    text = _cluster(env, force=True).read_text(encoding="utf-8")
    assert "## `unsortiert/`" in text
    assert "`epsilon`" in text
    assert "kein** echtes" in text  # Kennzeichnung Mapping-Lücke vs Mikrocluster


def test_cluster_tag_frequencies(env) -> None:
    text = _cluster(env, force=True).read_text(encoding="utf-8")
    assert "| `x` | 3 |" in text  # x in alpha+beta+gamma


# === idempotenz ===============================================================


def _run_all(env, out: Path) -> dict[str, str]:
    drafts, vault, _, corpus = env
    run_phase_10(
        out / "files_manifest.jsonl",
        out / "documents_structured.jsonl",
        out / "segments.jsonl",
        out / "exact_duplicates.json",
        out / "near_duplicate_edges.jsonl",
        drafts,
        vault,
        corpus,
        out,
        force=True,
    )
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("*_report.md")}


def test_reports_idempotent(env) -> None:
    out = env[2]
    first = _run_all(env, out)
    second = _run_all(env, out)
    assert first == second
    assert len(first) == 3


# === human-readable ===========================================================


def test_reports_are_human_readable_markdown(env) -> None:
    for path in (_corpus(env, force=True), _duplicate(env, force=True), _cluster(env, force=True)):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")  # YAML-Frontmatter
        assert "\n# " in text  # Markdown-H1
        assert "|---" in text  # mind. eine Tabelle
        assert not text.lstrip().startswith("{")  # kein roher JSON-Dump


def test_run_phase_10_returns_summary(env) -> None:
    drafts, vault, out, corpus = env
    summary = run_phase_10(
        out / "files_manifest.jsonl",
        out / "documents_structured.jsonl",
        out / "segments.jsonl",
        out / "exact_duplicates.json",
        out / "near_duplicate_edges.jsonl",
        drafts,
        vault,
        corpus,
        out,
        force=True,
    )
    assert summary["reports_generated"] == 3
    assert len(summary["report_paths"]) == 3
