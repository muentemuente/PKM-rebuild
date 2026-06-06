"""Inkrementeller Ingest-Modus (Option B).

Verarbeitet **nur** neue Roh-`.md` aus `input/` durch die Per-Doc-Pipeline:
Phasen 1→4 (Inventar, Normalisierung, Struktur, Segmentierung) plus Phase 8
(Qwen-Veredelung, Option-B-Routing passthrough/stage3/gedanken).

Die Phasen 5/6/7 (Redundanz, Embeddings, LLM-Batch-Bildung) **entfallen** im
inkrementellen Modus — Option B konsumiert ihre Outputs nicht
(Embedding-Clustering ist verworfen, R9).

Der bestehende Korpus/Vault/Drafts werden nicht verändert:
- Phasen 1→4 schreiben in ein **isoliertes** Work-Dir
  (`02_pipeline_output/ingest/`), nicht in die Korpus-weiten Outputs.
- Phase 8 schreibt neue Drafts nach `drafts/`; bestehende Slugs werden per
  Hash-/Slug-Skip übersprungen.

Erzeugt `02_pipeline_output/ingest_report.md`: pro neuem Doc die vorgeschlagene
`category` + `tags`, mit Flag, ob `category` ∈ bestehende Kategorien bzw. jeder
Tag ∈ kontrolliertes Vokabular ist — oder **NEU** (Review-Punkt).

Idempotent: zweiter Lauf ohne neue Files → keine neuen Drafts (no-op).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from pipeline.config import PipelineConfig
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_3_structure import run_phase_3
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_8_synthesis import _load_tag_vocabulary, run_phase_8
from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER

log = structlog.get_logger()

_REPORT_NAME = "ingest_report.md"


def _inbox_files(inbox: Path) -> list[Path]:
    """Roh-`.md` direkt in der Inbox (ohne Hidden-/Underscore-Files), sortiert."""
    if not inbox.exists():
        return []
    return sorted(
        p for p in inbox.glob("*.md") if p.is_file() and not p.name.startswith((".", "_"))
    )


def _draft_stems(drafts_dir: Path) -> set[str]:
    """Aktive Draft-Stems (`CK_<slug>`) im Drafts-Verzeichnis."""
    if not drafts_dir.exists():
        return set()
    return {
        p.name[: -len(".md")]
        for p in drafts_dir.glob("*.md")
        if not p.name.endswith(".body.md") and not p.name.startswith(".")
    }


def _read_draft_frontmatter(drafts_dir: Path, stem: str) -> dict[str, Any]:
    """Liest das Frontmatter eines Drafts (`.frontmatter.json` bevorzugt, sonst `.md`)."""
    fm_json = drafts_dir / f"{stem}.frontmatter.json"
    if fm_json.exists():
        try:
            data = json.loads(fm_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    md = drafts_dir / f"{stem}.md"
    if md.exists():
        text = md.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                try:
                    data = yaml.safe_load(text[4:end]) or {}
                    if isinstance(data, dict):
                        return data
                except yaml.YAMLError:
                    pass
    return {}


def _flag(ok: bool) -> str:
    return "✓ bestehend" if ok else "🆕 NEU"


def _build_report(
    new_stems: list[str],
    drafts_dir: Path,
    allowed_categories: set[str],
    tag_vocab: set[str],
) -> tuple[str, dict[str, int]]:
    """Baut den ingest_report.md-Inhalt + Zähl-Statistik (neue Kategorien/Tags)."""
    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    lines = [
        "---",
        "title: Ingest-Report (inkrementeller Lauf)",
        "slug: ingest-report",
        "status: generated",
        f"generated: {now}",
        "---",
        "",
        "# Ingest-Report — inkrementeller Lauf",
        "",
        f"**Neue Drafts:** {len(new_stems)} · **Lauf:** `{now}`",
        "",
    ]
    new_cats: set[str] = set()
    new_tags: set[str] = set()

    if not new_stems:
        lines += ["_Keine neuen Drafts erzeugt (Inbox leer oder bereits verarbeitet)._", ""]
    else:
        lines += ["## Neue Drafts", ""]
        for stem in new_stems:
            fm = _read_draft_frontmatter(drafts_dir, stem)
            cat = str(fm.get("category") or "")
            cat_ok = cat in allowed_categories
            if cat and not cat_ok:
                new_cats.add(cat)
            tags = fm.get("tags") or []
            tag_cells = []
            for t in tags:
                ok = t in tag_vocab
                if not ok:
                    new_tags.add(t)
                tag_cells.append(f"`{t}` {_flag(ok)}")
            slug = str(fm.get("slug") or stem)
            lines += [
                f"### `{slug}` ({stem})",
                "",
                f"- **type:** `{fm.get('type', '?')}` · **confidence:** `{fm.get('confidence', '?')}`",
                f"- **category:** `{cat or '—'}` — {_flag(cat_ok)}"
                + ("" if cat_ok else " (nicht in den bestehenden Kategorien)"),
                f"- **doc_role:** `{', '.join(fm.get('doc_role') or []) or '—'}`",
                "- **tags:** " + (", ".join(tag_cells) if tag_cells else "—"),
                "",
            ]

    lines += [
        "## Review-Punkt (Mensch)",
        "",
        f"- Neue Kategorien (🆕): {', '.join(f'`{c}`' for c in sorted(new_cats)) or 'keine'}",
        f"- Neue Tags (🆕): {', '.join(f'`{t}`' for t in sorted(new_tags)) or 'keine'}",
        "",
        "Bei 🆕: entweder `scripts/manage_vocab.py add-category <name>` bzw. "
        "`add-tag <tag> --reason …` ausführen, **oder** den Draft auf eine bestehende "
        "category/Tags umbiegen (Frontmatter-Edit / `apply_category_mapping`), bevor "
        "`build-vault` läuft.",
        "",
    ]
    stats = {"new_categories": len(new_cats), "new_tags": len(new_tags)}
    return "\n".join(lines) + "\n", stats


def run_ingest(
    cfg: PipelineConfig,
    *,
    force: bool = False,
    dry_run: bool = False,
    prompts_dir: Path = Path("prompts"),
) -> dict[str, Any]:
    """Führt einen inkrementellen Ingest-Lauf über `input/` aus.

    Args:
        cfg: Geladene PipelineConfig.
        force: Phasen-Cache (Input-Hash) ignorieren und neu berechnen.
        dry_run: Nur Plan zeigen (Inbox-Files + neu/bestehend), nichts schreiben,
            kein Qwen-Aufruf.
        prompts_dir: Pfad zum prompts/-Verzeichnis (für Phase 8; in Tests überschreibbar).

    Returns:
        Summary-Dict (inbox_files, new_drafts, new_categories, new_tags, report_path,
        skipped, dry_run).
    """
    inbox = cfg.paths.inbox
    out = cfg.paths.pipeline_output
    work = out / "ingest"
    files = _inbox_files(inbox)

    summary: dict[str, Any] = {
        "inbox_files": len(files),
        "new_drafts": 0,
        "new_categories": 0,
        "new_tags": 0,
        "report_path": None,
        "skipped": False,
        "dry_run": dry_run,
    }

    if not files:
        log.info("ingest_no_inbox_files", inbox=str(inbox))
        summary["skipped"] = True
        return summary

    if dry_run:
        existing = _draft_stems(cfg.paths.drafts)
        plan = []
        for f in files:
            # grobe Slug-Heuristik nur für die Plan-Anzeige (Phase 1 ist kanonisch)
            stem_guess = "CK_" + f.stem.lower().replace(" ", "-")
            status = "bestehend" if stem_guess in existing else "neu"
            plan.append((f.name, status))
        summary["plan"] = plan
        log.info("ingest_dry_run", files=len(files))
        return summary

    # === Phasen 1→4 in isoliertem Work-Dir (Korpus-Outputs unberührt) ===
    work.mkdir(parents=True, exist_ok=True)
    run_phase_1(
        corpus_input=inbox,
        output_path=work / "files_manifest.jsonl",
        force=force,
        sample=None,
        recursive=cfg.inventory.recursive,
        exclude_patterns=cfg.inventory.exclude_patterns,
        include_extensions=cfg.inventory.include_extensions,
        pipeline_version=cfg.pipeline.version,
    )
    run_phase_2(
        manifest_path=work / "files_manifest.jsonl",
        output_path=work / "cleaned_documents.jsonl",
        force=force,
        max_blank_lines=cfg.normalization.max_blank_lines,
        tab_replacement=cfg.normalization.tab_replacement,
        strip_trailing_whitespace=cfg.normalization.strip_trailing_whitespace,
        parse_frontmatter=cfg.normalization.parse_frontmatter,
        pipeline_version=cfg.pipeline.version,
    )
    run_phase_3(
        cleaned_path=work / "cleaned_documents.jsonl",
        output_path=work / "documents_structured.jsonl",
        force=force,
        pipeline_version=cfg.pipeline.version,
        book_word_threshold=cfg.structure.book_word_threshold,
    )
    run_phase_4(
        cleaned_path=work / "cleaned_documents.jsonl",
        manifest_path=work / "files_manifest.jsonl",
        output_path=work / "segments.jsonl",
        force=force,
        min_words=cfg.segmentation.min_words_per_segment,
        max_words=cfg.segmentation.max_words_per_segment,
        book_max_words=cfg.segmentation.book_max_words_per_segment,
        structured_path=work / "documents_structured.jsonl",
        pipeline_version=cfg.pipeline.version,
    )

    # === Phase 8 (Option B) → neue Drafts nach drafts/ ===
    before = _draft_stems(cfg.paths.drafts)
    qwen = cfg.qwen
    run_phase_8(
        segments_path=work / "segments.jsonl",
        qwen_output_dir=work / "qwen",
        drafts_dir=cfg.paths.drafts,
        endpoint=qwen.endpoint,
        model=qwen.model,
        context_window=qwen.context_window,
        prompt_version=qwen.prompt_version,
        prompts_dir=prompts_dir,
        temperature_stage3=qwen.temperature.stage3_synthesis,
        temperature_stage4=qwen.temperature.stage4_frontmatter,
        max_retries=qwen.max_retries,
        retry_backoff_seconds=qwen.retry_backoff_seconds,
        timeout_seconds=qwen.timeout_seconds,
        max_tokens_stage3=qwen.max_tokens.stage3,
        max_tokens_stage4=qwen.max_tokens.stage4,
        force=force,
        pipeline_version=cfg.pipeline.version,
        structured_docs_path=work / "documents_structured.jsonl",
        tag_vocab_path=cfg.tags.vocabulary_file,
        tag_strict_vocabulary=cfg.tags.strict_vocabulary,
    )
    after = _draft_stems(cfg.paths.drafts)
    new_stems = sorted(after - before)

    # === Auswertungs-Report ===
    allowed_categories = set(CATEGORY_TO_FOLDER)
    tag_vocab = _load_tag_vocabulary(cfg.tags.vocabulary_file)
    report, stats = _build_report(new_stems, cfg.paths.drafts, allowed_categories, tag_vocab)
    report_path = out / _REPORT_NAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    summary.update(
        new_drafts=len(new_stems),
        new_categories=stats["new_categories"],
        new_tags=stats["new_tags"],
        report_path=str(report_path),
        new_stems=new_stems,
    )
    log.info("ingest_done", **{k: summary[k] for k in ("inbox_files", "new_drafts")})
    return summary
