"""Go-forward-Flow (Option B) — kanonische Synthese-Engine für `pkm run` + `ingest`.

Dies ist der **einzige** schlanke go-forward-Pfad. Embedding (Phase 6),
LLM-Batch-Bildung (Phase 7) und der korpus-interne Redundanz-Schritt (Phase 5)
sind **nicht** Teil dieses Pfads (Embedding-Clustering verworfen, R9). Der alte
Code bleibt für Archiv-/Erstlauf erhalten, wird hier aber nicht aufgerufen.

go-forward-Pfad (Synthese-Hälfte — Steps 1-4 der neuen Nummerierung)::

    input/*.md (1-10)
     → [intra-run SHA-Dedup: Byte-identische Inputs DESSELBEN Laufs entfallen]
     → 1 Inventar        (run_phase_1 auf source_dir → work/files_manifest.jsonl)
     → 2 Normalisierung  (run_phase_2)
     → 3 Struktur+Routing(run_phase_3; doc_type_guess steuert passthrough/stage3/gedanke)
     → [Segmentierung NUR bei Token-Cap-Überschreitung — sonst 1 Doc = 1 Segment]
     → 4 Qwen            (run_phase_8: stage3 ODER passthrough + stage4 Frontmatter)
     → drafts/CK_<slug>.{md,body.md,frontmatter.json}

Die zweite Hälfte (Validierung → review/-Queues, Category-Mapping, Tag-Apply,
Build nach output/, validate_output) plus die Review-Gates A-D liegen in den
Review-Gates (WP4) und der `pkm run`-Orchestrierung (WP5). Diese Engine endet bei
den fertigen Drafts.

Intermediate-Outputs (manifest, cleaned, structured, segments) landen in einem
**isolierten** Work-Dir (default `work/run/`), damit Korpus-weite Outputs und der
bestehende Vault unberührt bleiben.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_3_structure import run_phase_3
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_8_synthesis import run_phase_8
from pipeline.schemas import DocumentRecord

log = structlog.get_logger()

# Konservativer Wörter-pro-Token-Faktor (DE/EN-Mix; eher zu klein → Cap greift früher).
_WORDS_PER_TOKEN = 0.6


def compute_token_cap_words(cfg: PipelineConfig) -> int:
    """Token-Cap als Wortzahl: Context-Window minus Stage-3-Output-Budget, in Wörtern.

    Unter diesem Cap bleibt ein Doc ungeteilt (1 Segment); darüber greift der
    klassische Heading-Split als Fallback.
    """
    input_token_budget = cfg.qwen.context_window - cfg.qwen.max_tokens.stage3
    return max(1, int(input_token_budget * _WORDS_PER_TOKEN))


def intra_run_dedup_sets(
    manifest_path: Path,
) -> tuple[set[str], list[dict[str, str]]]:
    """Erkennt Byte-identische Inputs DESSELBEN Laufs über die SHA-256 aus dem Manifest.

    Args:
        manifest_path: Pfad zur files_manifest.jsonl (Phase 1 Output).

    Returns:
        ``(kept, dropped)`` — kept = doc_ids, die synthetisiert werden (erster pro
        SHA-Gruppe, manifest-Reihenfolge); dropped = Liste von
        ``{"doc_id", "sha256", "duplicate_of"}`` für die übersprungenen Duplikate.
        Kein Bestands-Check gegen Vault/Drafts — rein lauf-intern.
    """
    first_for_sha: dict[str, str] = {}
    kept: set[str] = set()
    dropped: list[dict[str, str]] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = DocumentRecord.model_validate_json(line)
        if rec.sha256 in first_for_sha:
            dropped.append(
                {
                    "doc_id": rec.doc_id,
                    "sha256": rec.sha256,
                    "duplicate_of": first_for_sha[rec.sha256],
                }
            )
        else:
            first_for_sha[rec.sha256] = rec.doc_id
            kept.add(rec.doc_id)
    return kept, dropped


def _draft_stems(drafts_dir: Path) -> set[str]:
    """Aktive Draft-Stems (`CK_<slug>`) im Drafts-Verzeichnis."""
    if not drafts_dir.exists():
        return set()
    return {
        p.name[: -len(".md")]
        for p in drafts_dir.glob("*.md")
        if not p.name.endswith(".body.md") and not p.name.startswith(".")
    }


def run_synthesis_flow(
    cfg: PipelineConfig,
    *,
    source_dir: Path | None = None,
    work_dir: Path | None = None,
    force: bool = False,
    prompts_dir: Path = Path("prompts"),
    intra_run_dedup: bool = True,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Fährt den go-forward-Synthese-Flow (Steps 1-4) von ``source_dir`` bis Drafts.

    Args:
        cfg: Geladene PipelineConfig.
        source_dir: Quell-Verzeichnis mit Roh-`.md` (default `cfg.paths.input`).
        work_dir: Isoliertes Work-Dir für Intermediates (default `cfg.paths.work / "run"`).
        force: Phasen-Cache (Input-Hash) ignorieren.
        prompts_dir: Pfad zum prompts/-Verzeichnis (für Phase 8).
        intra_run_dedup: Byte-identische Inputs desselben Laufs nur einmal synthetisieren.
        max_files: Obergrenze Inputs pro Lauf (1-10-Regel); None = alle.

    Returns:
        Summary-Dict: ``new_stems`` (neue Draft-Stems), ``dropped_duplicates``
        (Liste), ``docs_inventoried``, ``docs_synthesized``, ``phase8`` (Phase-8-Summary).
    """
    source = source_dir if source_dir is not None else cfg.paths.input
    work = work_dir if work_dir is not None else (cfg.paths.work / "run")
    work.mkdir(parents=True, exist_ok=True)

    manifest = work / "files_manifest.jsonl"
    cleaned = work / "cleaned_documents.jsonl"
    structured = work / "documents_structured.jsonl"
    segments = work / "segments.jsonl"

    # --- 1 Inventar -----------------------------------------------------------
    inventory = run_phase_1(
        corpus_input=source,
        output_path=manifest,
        force=force,
        sample=max_files,
        recursive=cfg.inventory.recursive,
        exclude_patterns=cfg.inventory.exclude_patterns,
        include_extensions=cfg.inventory.include_extensions,
        pipeline_version=cfg.pipeline.version,
    )

    # --- intra-run SHA-Dedup (kein Bestands-Check) ----------------------------
    kept: set[str] | None = None
    dropped: list[dict[str, str]] = []
    if intra_run_dedup:
        kept, dropped = intra_run_dedup_sets(manifest)
        if dropped:
            log.info("intra_run_duplicates_dropped", count=len(dropped))

    # --- 2 Normalisierung -----------------------------------------------------
    run_phase_2(
        manifest_path=manifest,
        output_path=cleaned,
        force=force,
        max_blank_lines=cfg.normalization.max_blank_lines,
        tab_replacement=cfg.normalization.tab_replacement,
        strip_trailing_whitespace=cfg.normalization.strip_trailing_whitespace,
        parse_frontmatter=cfg.normalization.parse_frontmatter,
        pipeline_version=cfg.pipeline.version,
    )

    # --- 3 Struktur + Routing-Signale -----------------------------------------
    run_phase_3(
        cleaned_path=cleaned,
        output_path=structured,
        force=force,
        pipeline_version=cfg.pipeline.version,
        book_word_threshold=cfg.structure.book_word_threshold,
    )

    # --- 4 Segmentierung (Token-Cap-Fallback) ---------------------------------
    run_phase_4(
        cleaned_path=cleaned,
        manifest_path=manifest,
        output_path=segments,
        force=force,
        min_words=cfg.segmentation.min_words_per_segment,
        max_words=cfg.segmentation.max_words_per_segment,
        book_max_words=cfg.segmentation.book_max_words_per_segment,
        structured_path=structured,
        token_cap_words=compute_token_cap_words(cfg),
        pipeline_version=cfg.pipeline.version,
    )

    # --- 4/Qwen: Stage 3/passthrough + Stage 4 → Drafts -----------------------
    before = _draft_stems(cfg.paths.drafts)
    qwen = cfg.qwen
    phase8 = run_phase_8(
        segments_path=segments,
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
        structured_docs_path=structured,
        tag_vocab_path=cfg.tags.vocabulary_file,
        tag_strict_vocabulary=cfg.tags.strict_vocabulary,
        filter_doc_ids=kept,
    )
    after = _draft_stems(cfg.paths.drafts)

    return {
        "new_stems": sorted(after - before),
        "dropped_duplicates": dropped,
        "docs_inventoried": len(inventory),
        "docs_synthesized": len(kept) if kept is not None else len(inventory),
        "phase8": phase8,
    }
