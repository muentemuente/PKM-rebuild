"""CLI-Entry-Point der PKM-rebuild Pipeline."""

from pathlib import Path
from typing import Any

import click
from rich.console import Console

from pipeline.config import PipelineConfig, load_config
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_3_structure import run_phase_3
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_5_redundancy import run_phase_5
from pipeline.phase_6_embeddings import run_phase_6
from pipeline.phase_7_batches import run_phase_7
from pipeline.phase_8_synthesis import run_phase_8
from pipeline.phase_10_reports import run_phase_10

console = Console()

_ALL_PHASES = list(range(1, 11))
_IMPLEMENTED_PHASES = {1, 2, 3, 4, 5, 6, 7, 8, 10}
_DEFAULT_CONFIG = "pipeline/pipeline.config.yaml"


def _phases_to_run(phase: int | None, from_phase: int | None) -> list[int]:
    if phase is not None:
        return [phase]
    if from_phase is not None:
        return [p for p in _ALL_PHASES if p >= from_phase]
    return _ALL_PHASES


def _dispatch_phase_1(cfg: PipelineConfig, force: bool, sample: int | None) -> None:
    effective_sample = (
        sample if sample is not None else (cfg.sample.count if cfg.sample.enabled else None)
    )
    output_path = cfg.paths.pipeline_output / "files_manifest.jsonl"
    records = run_phase_1(
        corpus_input=cfg.paths.corpus_input,
        output_path=output_path,
        force=force,
        sample=effective_sample,
        recursive=cfg.inventory.recursive,
        exclude_patterns=cfg.inventory.exclude_patterns,
        include_extensions=cfg.inventory.include_extensions,
        pipeline_version=cfg.pipeline.version,
    )
    console.print(f"[green]✓ Phase 1:[/green] {len(records)} Dokumente → {output_path}")


def _dispatch_phase_2(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    records = run_phase_2(
        manifest_path=out / "files_manifest.jsonl",
        output_path=out / "cleaned_documents.jsonl",
        force=force,
        max_blank_lines=cfg.normalization.max_blank_lines,
        tab_replacement=cfg.normalization.tab_replacement,
        strip_trailing_whitespace=cfg.normalization.strip_trailing_whitespace,
        parse_frontmatter=cfg.normalization.parse_frontmatter,
        pipeline_version=cfg.pipeline.version,
    )
    console.print(
        f"[green]✓ Phase 2:[/green] {len(records)} Dokumente → {out / 'cleaned_documents.jsonl'}"
    )


def _dispatch_phase_3(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    records = run_phase_3(
        cleaned_path=out / "cleaned_documents.jsonl",
        output_path=out / "documents_structured.jsonl",
        force=force,
        pipeline_version=cfg.pipeline.version,
        book_word_threshold=cfg.structure.book_word_threshold,
    )
    console.print(
        f"[green]✓ Phase 3:[/green] {len(records)} Dokumente → {out / 'documents_structured.jsonl'}"
    )


def _dispatch_phase_4(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    records = run_phase_4(
        cleaned_path=out / "cleaned_documents.jsonl",
        manifest_path=out / "files_manifest.jsonl",
        output_path=out / "segments.jsonl",
        force=force,
        min_words=cfg.segmentation.min_words_per_segment,
        max_words=cfg.segmentation.max_words_per_segment,
        book_max_words=cfg.segmentation.book_max_words_per_segment,
        structured_path=out / "documents_structured.jsonl",
        pipeline_version=cfg.pipeline.version,
    )
    console.print(f"[green]✓ Phase 4:[/green] {len(records)} Segmente → {out / 'segments.jsonl'}")


def _dispatch_phase_5(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    tfidf = cfg.redundancy.tfidf
    exact_groups, edges = run_phase_5(
        cleaned_path=out / "cleaned_documents.jsonl",
        segments_path=out / "segments.jsonl",
        exact_output_path=out / "exact_duplicates.json",
        edges_output_path=out / "near_duplicate_edges.jsonl",
        force=force,
        tfidf_enabled=tfidf.enabled,
        tfidf_threshold=tfidf.threshold,
        ngram_range=(tfidf.ngram_range[0], tfidf.ngram_range[1]),
        max_features=tfidf.max_features,
        min_df=tfidf.min_df,
        pipeline_version=cfg.pipeline.version,
    )
    exact_doc_count = sum(len(g.doc_ids) for g in exact_groups)
    console.print(
        f"[green]✓ Phase 5:[/green] "
        f"{exact_doc_count} exakte Duplikate in {len(exact_groups)} Gruppen, "
        f"{len(edges)} nahe-Duplikat-Kanten"
    )


def _dispatch_phase_7(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    batch_paths = run_phase_7(
        segments_path=out / "segments.jsonl",
        clusters_path=out / "cluster_proposals.json",
        edges_path=out / "near_duplicate_edges.jsonl",
        output_dir=out / "batches",
        force=force,
        max_input_tokens=cfg.batching.max_input_tokens,
        split_oversized_clusters=cfg.batching.split_oversized_clusters,
        pipeline_version=cfg.pipeline.version,
    )
    console.print(f"[green]✓ Phase 7:[/green] {len(batch_paths)} Batch-Files → {out / 'batches'}")


def _dispatch_phase_6(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    emb = cfg.embeddings
    n_emb, proposals = run_phase_6(
        segments_path=out / "segments.jsonl",
        embeddings_path=out / "embeddings.parquet",
        clusters_path=out / "cluster_proposals.json",
        force=force,
        model_name=emb.model,
        batch_size=emb.batch_size,
        device=emb.device,
        similarity_threshold=emb.similarity_threshold,
        min_cluster_size=cfg.clustering.min_cluster_size,
        pipeline_version=cfg.pipeline.version,
    )
    named = sum(1 for p in proposals if p.cluster_id != "C_unsortiert")
    unsorted = next((p for p in proposals if p.cluster_id == "C_unsortiert"), None)
    unsorted_count = len(unsorted.segment_ids) if unsorted else 0
    console.print(
        f"[green]✓ Phase 6:[/green] {n_emb} Embeddings, "
        f"{named} Cluster, {unsorted_count} unsortiert"
    )


def _dispatch_phase_8(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    drafts = cfg.paths.drafts
    qwen = cfg.qwen
    summary = run_phase_8(
        batches_dir=out / "batches",
        segments_path=out / "segments.jsonl",
        qwen_output_dir=out / "qwen",
        drafts_dir=drafts,
        endpoint=qwen.endpoint,
        model=qwen.model,
        context_window=qwen.context_window,
        prompt_version=qwen.prompt_version,
        prompts_dir=Path("prompts"),
        temperature_stage1=qwen.temperature.stage1_cluster_analysis,
        temperature_stage2=qwen.temperature.stage2_merge_proposal,
        temperature_stage3=qwen.temperature.stage3_synthesis,
        temperature_stage4=qwen.temperature.stage4_frontmatter,
        max_retries=qwen.max_retries,
        retry_backoff_seconds=qwen.retry_backoff_seconds,
        timeout_seconds=qwen.timeout_seconds,
        max_tokens_stage1=qwen.max_tokens.stage1,
        max_tokens_stage2=qwen.max_tokens.stage2,
        max_tokens_stage3=qwen.max_tokens.stage3,
        max_tokens_stage4=qwen.max_tokens.stage4,
        force=force,
        pipeline_version=cfg.pipeline.version,
    )
    console.print(
        f"[green]✓ Phase 8:[/green] {summary['batches_processed']} Batches verarbeitet, "
        f"{summary['concepts_drafted']} Konzepte, {summary['needs_human']} needs_human, "
        f"{summary['errors']} Errors ({summary['duration_seconds']}s)"
    )


def _dispatch_phase_10(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    summary = run_phase_10(
        manifest_path=out / "files_manifest.jsonl",
        structured_path=out / "documents_structured.jsonl",
        segments_path=out / "segments.jsonl",
        exact_path=out / "exact_duplicates.json",
        edges_path=out / "near_duplicate_edges.jsonl",
        clusters_path=out / "cluster_proposals.json",
        batches_dir=out / "batches",
        output_dir=out,
        cleaned_path=out / "cleaned_documents.jsonl",
        force=force,
        pipeline_version=cfg.pipeline.version,
    )
    console.print(
        f"[green]✓ Phase 10:[/green] {summary['reports_generated']} Reports → {out} "
        f"({summary['duration_seconds']}s)"
    )


_PHASE_DISPATCH: dict[int, Any] = {
    1: _dispatch_phase_1,
    2: _dispatch_phase_2,
    3: _dispatch_phase_3,
    4: _dispatch_phase_4,
    5: _dispatch_phase_5,
    6: _dispatch_phase_6,
    7: _dispatch_phase_7,
    8: _dispatch_phase_8,
    10: _dispatch_phase_10,
}


@click.group()
@click.version_option(package_name="pkm-rebuild")
def cli() -> None:
    """PKM-rebuild Pipeline."""


@cli.command()
@click.option("--sample", type=int, default=None, help="Sample-Modus: nur N Dateien")
@click.option("--phase", type=int, default=None, help="Nur diese Phase ausführen")
@click.option("--from-phase", "from_phase", type=int, default=None, help="Ab dieser Phase")
@click.option("--force", is_flag=True, help="Cache ignorieren, alles neu berechnen")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def run(
    sample: int | None,
    phase: int | None,
    from_phase: int | None,
    force: bool,
    dry_run: bool,
    config: str,
) -> None:
    """Pipeline-Lauf starten (Phasen 1-10)."""
    cfg = load_config(Path(config))
    phases = _phases_to_run(phase, from_phase)

    for p in phases:
        if p not in _IMPLEMENTED_PHASES:
            console.print(f"[yellow]Phase {p}: noch nicht implementiert — gestoppt.[/yellow]")
            break

        if dry_run:
            console.print(f"[cyan]--dry-run:[/cyan] würde Phase {p} ausführen")
            continue

        dispatch = _PHASE_DISPATCH[p]
        try:
            if p == 1:
                dispatch(cfg, force, sample)
            else:
                dispatch(cfg, force)
        except FileNotFoundError as exc:
            console.print(f"[red]Fehler Phase {p}:[/red] {exc}")
            raise SystemExit(1) from exc


@cli.command()
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def status(config: str) -> None:
    """Aktuellen Pipeline-Status anzeigen."""
    cfg = load_config(Path(config))
    pipeline_output = cfg.paths.pipeline_output

    console.print("[bold cyan]PKM-rebuild Pipeline[/bold cyan]")
    console.print()
    for p in _ALL_PHASES:
        label = "[green]implementiert[/green]" if p in _IMPLEMENTED_PHASES else "[dim]Stub[/dim]"
        console.print(f"  Phase {p:2d}: {label}")

    console.print()
    manifest = pipeline_output / "files_manifest.jsonl"
    if manifest.exists():
        lines = manifest.read_text(encoding="utf-8").splitlines()
        console.print(f"  files_manifest.jsonl: {len(lines)} Einträge")
    else:
        console.print("  files_manifest.jsonl: noch nicht vorhanden")


@cli.command()
@click.option("--force", is_flag=True, help="Cache ignorieren, Reports neu generieren")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def reports(force: bool, config: str) -> None:
    """Kontroll-Berichte generieren (corpus, duplicate, cluster)."""
    cfg = load_config(Path(config))
    _dispatch_phase_10(cfg, force)


if __name__ == "__main__":
    cli()
