"""CLI-Entry-Point der PKM-rebuild Pipeline."""

import json
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from pipeline.config import PipelineConfig, load_config
from pipeline.ingest import run_ingest
from pipeline.orchestrator import run_pipeline
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2
from pipeline.phase_3_structure import run_phase_3
from pipeline.phase_4_segment import run_phase_4
from pipeline.phase_5_redundancy import run_phase_5
from pipeline.phase_6_embeddings import run_phase_6
from pipeline.phase_7_batches import run_phase_7
from pipeline.phase_8_synthesis import run_phase_8
from pipeline.phase_9_vault_build import run_phase_9
from pipeline.phase_10_reports import run_phase_10
from pipeline.review import apply_review, render_review

console = Console()

_ALL_PHASES = list(range(1, 11))
_IMPLEMENTED_PHASES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
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


def _resolve_filter_doc_ids(filter_files: tuple[str, ...], manifest_path: Path) -> set[str] | None:
    """Corpus-Pfade → doc_ids via files_manifest.jsonl. None wenn keine Filter angegeben."""
    if not filter_files:
        return None
    if not manifest_path.exists():
        raise FileNotFoundError(f"files_manifest.jsonl nicht gefunden: {manifest_path}")
    abs_filter = {str(Path(f).resolve()) for f in filter_files}
    result: set[str] = set()
    matched_paths: set[str] = set()
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        abs_path = str(Path(entry["path"]).resolve())
        if abs_path in abs_filter:
            result.add(entry["doc_id"])
            matched_paths.add(abs_path)
    missing = abs_filter - matched_paths
    if missing:
        console.print(
            f"[yellow]Warnung:[/yellow] {len(missing)} --file-Pfade nicht im Manifest: {missing}"
        )
    return result


def _dispatch_phase_8(cfg: PipelineConfig, force: bool, filter_files: tuple[str, ...] = ()) -> None:
    out = cfg.paths.pipeline_output
    drafts = cfg.paths.drafts
    qwen = cfg.qwen
    filter_doc_ids = _resolve_filter_doc_ids(filter_files, out / "files_manifest.jsonl")
    summary = run_phase_8(
        segments_path=out / "segments.jsonl",
        qwen_output_dir=out / "qwen",
        drafts_dir=drafts,
        endpoint=qwen.endpoint,
        model=qwen.model,
        context_window=qwen.context_window,
        prompt_version=qwen.prompt_version,
        prompts_dir=Path("prompts"),
        temperature_stage3=qwen.temperature.stage3_synthesis,
        temperature_stage4=qwen.temperature.stage4_frontmatter,
        max_retries=qwen.max_retries,
        retry_backoff_seconds=qwen.retry_backoff_seconds,
        timeout_seconds=qwen.timeout_seconds,
        max_tokens_stage3=qwen.max_tokens.stage3,
        max_tokens_stage4=qwen.max_tokens.stage4,
        force=force,
        pipeline_version=cfg.pipeline.version,
        structured_docs_path=out / "documents_structured.jsonl",
        tag_vocab_path=cfg.tags.vocabulary_file,
        tag_strict_vocabulary=cfg.tags.strict_vocabulary,
        filter_doc_ids=filter_doc_ids,
    )
    console.print(
        f"[green]✓ Phase 8:[/green] {summary['docs_processed']} Docs veredelt, "
        f"{summary['concepts_drafted']} Drafts, {summary['needs_human']} needs_human, "
        f"{summary['errors']} Errors ({summary['duration_seconds']}s)"
    )


def _dispatch_phase_9(cfg: PipelineConfig, force: bool, dry_run: bool = False) -> None:
    summary = run_phase_9(
        drafts_dir=cfg.paths.drafts,
        vault_dir=cfg.paths.vault,
        pipeline_output=cfg.paths.pipeline_output,
        backups_dir=cfg.paths.backups,
        force=force,
        dry_run=dry_run,
        repair_on_build=cfg.vault.repair_on_build,
        format_on_build=cfg.vault.format_on_build,
        audit_on_build=cfg.vault.audit_on_build,
        pipeline_version=cfg.pipeline.version,
    )
    prefix = "[cyan]--dry-run:[/cyan] " if dry_run else ""
    if summary.get("skipped"):
        console.print("[yellow]Phase 9: übersprungen (Input-Hash unverändert).[/yellow]")
    console.print(
        f"{prefix}[green]✓ Phase 9:[/green] {summary['articles']} Artikel in "
        f"{summary['folders_used']} Ordnern, {summary['dropped_links']} Links gedroppt "
        f"({summary['dropped_links_drafts']} Drafts), {summary['collisions']} Slug-Kollisionen, "
        f"{summary.get('repaired_files', 0)} Bodies safe-repariert, "
        f"{summary.get('formatted_files', 0)} safe-formatiert, "
        f"{summary['errors']} Errors"
    )
    if summary.get("unknown_categories"):
        console.print(
            f"[yellow]  unbekannte Kategorien → unsortiert:[/yellow] "
            f"{summary['unknown_categories']}"
        )
    # S3 (G4): read-only Post-Build-Audit über output/ (kein Write)
    if summary.get("audit_on_build") and not dry_run:
        rest = summary.get("audit_safe_tier_rest", 0)
        perr = summary.get("audit_parse_errors", 0)
        dang = summary.get("audit_dangling", 0)
        style = "green" if (rest + perr + dang) == 0 else "yellow"
        console.print(
            f"[{style}]  Post-Build-Audit (output/, read-only):[/{style}] "
            f"{rest} Safe-Tier-Rest · {perr} parse-errors · {dang} dangling"
        )
    table = Table(title="Ordner-Verteilung")
    table.add_column("Ordner")
    table.add_column("Artikel", justify="right")
    for folder, n in summary["folder_counts"].items():
        table.add_row(folder, str(n))
    console.print(table)

    # Passives Surfacing (kein P4): 17_unsortiert-Füllstand IMMER ausweisen, bei
    # Überschreiten des Schwellwerts (config: vault.unsorted_warn_threshold) warnen.
    # Read-only, verschiebt nichts; Reuse unsortiert_diagnose.count_unsorted.
    from scripts.unsortiert_diagnose import count_unsorted

    unsorted_folder = cfg.vault.unsorted_folder
    if dry_run:
        n_unsorted = int(summary.get("folder_counts", {}).get(unsorted_folder, 0))
    else:
        n_unsorted = count_unsorted(cfg.paths.vault)
    threshold = cfg.vault.unsorted_warn_threshold
    if n_unsorted > threshold:
        console.print(
            f"[yellow]  ⚠ {unsorted_folder}: {n_unsorted} Artikel — über Schwellwert "
            f"({threshold}). `python3 scripts/unsortiert_diagnose.py` für die "
            f"Domänen-Aufschlüsselung.[/yellow]"
        )
    else:
        console.print(
            f"[dim]  {unsorted_folder}: {n_unsorted} Artikel (Schwellwert {threshold}).[/dim]"
        )


def _dispatch_phase_10(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    summary = run_phase_10(
        manifest_path=out / "files_manifest.jsonl",
        structured_path=out / "documents_structured.jsonl",
        segments_path=out / "segments.jsonl",
        exact_path=out / "exact_duplicates.json",
        edges_path=out / "near_duplicate_edges.jsonl",
        drafts_dir=cfg.paths.drafts,
        vault_dir=cfg.paths.vault,
        corpus_input=cfg.paths.corpus_input,
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
    9: _dispatch_phase_9,
    10: _dispatch_phase_10,
}


@click.group()
@click.version_option(package_name="pkm-rebuild")
def cli() -> None:
    """PKM-rebuild Pipeline."""


@cli.command()
@click.option("--force", is_flag=True, help="Phasen-Cache ignorieren, neu berechnen")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def run(force: bool, config: str) -> None:
    """go-forward: input/ → (Review-Gates) → output/ (resume-fähig, Option B)."""
    cfg = load_config(Path(config))
    summary = run_pipeline(cfg, force=force)

    status = summary["status"]
    if status == "idle":
        console.print("[yellow]run:[/yellow] nichts zu tun (input/ leer, keine offenen Drafts).")
        return
    if status == "review_pending":
        console.print(
            f"[cyan]⏸ run:[/cyan] {summary['new_drafts']} neue Drafts, "
            f"{summary['open']} offene Review-Punkte."
        )
        table = Table(title="Offene Gates")
        table.add_column("Gate")
        table.add_column("Offen", justify="right")
        for gate, n in summary["per_gate"].items():
            if n:
                table.add_row(gate, str(n))
        console.print(table)
        console.print(
            f"[yellow]→ Nächster Schritt:[/yellow] `{summary['decisions_md']}` in Zed ausfüllen, "
            "dann `pkm review --apply`, dann erneut `pkm run`."
        )
        return
    # published
    console.print(
        f"[green]✓ run:[/green] {summary['articles']} Artikel nach output/ gebaut "
        f"({summary['folders_used']} Ordner), {summary['archived_inputs']} Inputs archiviert."
    )


@cli.command(name="corpus-run")
@click.option("--sample", type=int, default=None, help="Sample-Modus: nur N Dateien")
@click.option("--phase", type=int, default=None, help="Nur diese Phase ausführen")
@click.option("--from-phase", "from_phase", type=int, default=None, help="Ab dieser Phase")
@click.option("--force", is_flag=True, help="Cache ignorieren, alles neu berechnen")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben")
@click.option(
    "--file",
    "filter_files",
    type=click.Path(),
    multiple=True,
    help="Nur diese Korpus-Datei(en) verarbeiten (Phase 8; wiederholbar).",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def corpus_run(
    sample: int | None,
    phase: int | None,
    from_phase: int | None,
    force: bool,
    dry_run: bool,
    filter_files: tuple[str, ...],
    config: str,
) -> None:
    """Legacy-Erstlauf über den Gesamtkorpus (Phasen 1-10, Archiv/Alt-Lauf)."""
    if filter_files and phase != 8:
        console.print("[yellow]Hinweis:[/yellow] --file wird nur für --phase 8 ausgewertet.")
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
            elif p == 8:
                dispatch(cfg, force, filter_files)
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
    console.print("[bold]Kommandos:[/bold] run · status · reports · build-vault · ingest")
    console.print(
        "  [dim]ingest[/dim]: inkrementell — neue .md aus input/ durch Phasen 1-4 + 8 (Option B)"
    )

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


@cli.command(name="build-vault")
@click.option("--force", is_flag=True, help="Input-Hash-Cache ignorieren, neu bauen")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def build_vault(force: bool, dry_run: bool, config: str) -> None:
    """Phase 9: Vault aus Drafts aufbauen (output/<NN_Cluster>/<slug>.md)."""
    cfg = load_config(Path(config))
    _dispatch_phase_9(cfg, force, dry_run)


@cli.command()
@click.option("--force", is_flag=True, help="Phasen-Cache ignorieren, neu berechnen")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben, kein Qwen")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def ingest(force: bool, dry_run: bool, config: str) -> None:
    """Inkrementell: neue .md aus input/ durch Phasen 1-4 + 8 (Option B)."""
    cfg = load_config(Path(config))
    summary = run_ingest(cfg, force=force, dry_run=dry_run)

    if summary["inbox_files"] == 0:
        console.print("[yellow]ingest:[/yellow] Inbox leer (input/) — nichts zu tun.")
        return

    if dry_run:
        console.print(f"[cyan]--dry-run:[/cyan] {summary['inbox_files']} Inbox-File(s):")
        table = Table(title="Ingest-Plan")
        table.add_column("Datei")
        table.add_column("Status")
        for name, status in summary.get("plan", []):
            table.add_row(name, status)
        console.print(table)
        console.print("[cyan]--dry-run:[/cyan] nichts geschrieben, kein Qwen-Aufruf.")
        return

    console.print(
        f"[green]✓ ingest:[/green] {summary['inbox_files']} Inbox-File(s) → "
        f"{summary['new_drafts']} neue Drafts "
        f"({summary['new_categories']} neue Kategorien, {summary['new_tags']} neue Tags)"
    )
    if summary.get("report_path"):
        console.print(f"  Report: {summary['report_path']}")
    if summary["new_categories"] or summary["new_tags"]:
        console.print(
            "[yellow]  ⏸ Review:[/yellow] neue category/tag — siehe Report, dann "
            "scripts/manage_vocab.py add-* oder bestehende zuordnen."
        )


@cli.command()
@click.option("--apply", "do_apply", is_flag=True, help="Ausgefüllte decisions.md anwenden")
@click.option(
    "--no-rebuild",
    "no_rebuild",
    is_flag=True,
    help="decisions.jsonl NICHT neu aus Drafts scannen (bestehende nutzen)",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def review(do_apply: bool, no_rebuild: bool, config: str) -> None:
    """Review-Gates: ohne --apply erzeugt es review/decisions.md, mit --apply wendet es an."""
    cfg = load_config(Path(config))
    if do_apply:
        summary = apply_review(cfg)
        console.print(
            f"[green]✓ review --apply:[/green] {len(summary['applied'])} angewandt, "
            f"{summary['remaining']} offen, {len(summary['errors'])} Fehler"
        )
        for note in summary["applied"]:
            console.print(f"  [green]✓[/green] {note}")
        for err in summary["errors"]:
            console.print(f"  [red]✗[/red] {err}")
        return

    summary = render_review(cfg, rebuild=not no_rebuild)
    console.print(
        f"[green]✓ review:[/green] {summary['total']} offene Punkte → {summary['decisions_md']}"
    )
    table = Table(title="Offene Review-Punkte je Gate")
    table.add_column("Gate")
    table.add_column("Offen", justify="right")
    for gate, n in summary["per_gate"].items():
        table.add_row(gate, str(n))
    console.print(table)
    console.print(
        "[dim]decisions.md in Zed ausfüllen (Entscheidung/Wert), dann `pkm review --apply`.[/dim]"
    )


@cli.command(name="format-vault")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Zu formatierender Vault, read-only (default: Brain-Vault aus _paths)",
)
@click.option(
    "--work-dir",
    "work_dir",
    type=click.Path(),
    default=None,
    help="Arbeitskopie + Report (default: work/format aus _paths)",
)
@click.option("--examples", type=int, default=5, help="Beispiel-Diffs je Tier im Report")
def format_vault_cmd(vault_dir: str | None, work_dir: str | None, examples: int) -> None:
    """WP3a: Vault deterministisch formatieren — DRY-RUN (raw read-only → work/).

    Schreibt formatierte Arbeitskopien + diff_report.md nach work/; der Vault (#3)
    bleibt unangetastet. Export nach #3 ist ein separater, Gate-3-pflichtiger Schritt
    (hier NICHT enthalten).
    """
    from pipeline import _paths
    from pipeline.format_vault import render_diff_report, scan_vault

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    work = Path(work_dir) if work_dir else (_paths.WORK / "format")
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)

    console.print(f"[cyan]format-vault (dry-run):[/cyan] {vault} → {work}")
    report = scan_vault(vault, work, write_work=True)
    (work / "diff_report.md").write_text(
        render_diff_report(report, examples_per_tier=examples), encoding="utf-8"
    )
    c = report.counts()
    table = Table(title=f"Format-Blast-Radius ({len(report.results)} Docs)")
    table.add_column("Tier")
    table.add_column("Files", justify="right")
    table.add_row("unchanged", str(c["unchanged"]))
    table.add_row("[green]safe-auto[/green]", str(c["safe"]))
    table.add_row("[yellow]unsafe (Patch-Vorschlag)[/yellow]", str(c["unsafe"]))
    console.print(table)
    console.print(f"[green]✓[/green] {work / 'diff_report.md'}")
    console.print(
        "[dim]Vault unangetastet. Export nach #3 ist Gate-3-pflichtig (nicht hier).[/dim]"
    )


@cli.command(name="vault-audit")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Vault, read-only (default: Brain-Vault)",
)
@click.option(
    "--work-dir",
    "work_dir",
    type=click.Path(),
    default=None,
    help="Report-Ziel (default: work/vault_audit)",
)
@click.option(
    "--baseline",
    default=None,
    help="Doc-Count-Baseline 'content,attic' (default: vault_audit.DOC_COUNT_BASELINE)",
)
def vault_audit_cmd(vault_dir: str | None, work_dir: str | None, baseline: str | None) -> None:
    """WP4: read-only Audit über den Vault (9 Regeln) → Befund-Report in work/."""
    from pipeline import _paths
    from pipeline import vault_audit as va

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    work = Path(work_dir) if work_dir else (_paths.WORK / "vault_audit")
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)
    if baseline:
        base_content, base_attic = (int(x) for x in baseline.split(","))
    else:
        base_content, base_attic = va.DOC_COUNT_BASELINE
    candidates = _paths.WORK / "synthesis_candidates.md"
    findings = va.audit_vault(
        vault,
        baseline=(base_content, base_attic),
        candidates_md=candidates if candidates.is_file() else None,
    )
    work.mkdir(parents=True, exist_ok=True)
    (work / "audit_report.md").write_text(va.render_report(findings), encoding="utf-8")
    sev = va.count_by_severity(findings)
    table = Table(title=f"Vault-Audit ({len(findings)} Befunde)")
    table.add_column("Regel")
    table.add_column("Anzahl", justify="right")
    for rule, count in sorted(va.count_by_rule(findings).items()):
        table.add_row(rule, str(count))
    console.print(table)
    console.print(
        f"[red]{sev['error']} error[/red] · [yellow]{sev['warning']} warning[/yellow] · {sev['info']} info"
    )
    console.print(f"[green]✓[/green] {work / 'audit_report.md'} [dim](Vault unangetastet)[/dim]")


@cli.command(name="vault-repair")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Vault, read-only (default: Brain-Vault)",
)
@click.option(
    "--work-dir",
    "work_dir",
    type=click.Path(),
    default=None,
    help="Arbeitskopien (default: work/vault_repair)",
)
def vault_repair_cmd(vault_dir: str | None, work_dir: str | None) -> None:
    """WP4: Safe-Tier-Repairs (raw read-only → work/), idempotent. Kein Vault-Write."""
    from pipeline import _paths
    from pipeline import vault_audit as va

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    work = Path(work_dir) if work_dir else (_paths.WORK / "vault_repair")
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)
    index = va.build_index(vault)
    changed = 0
    for rel, text in index.audit_files.items():
        repaired, actions = va.repair_text(text)
        if not actions:
            continue
        dest = work / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(repaired, encoding="utf-8")
        changed += 1
        console.print(f"[green]✓[/green] {rel}: {'; '.join(actions)}")
    console.print(
        f"[cyan]vault-repair:[/cyan] {changed} Files mit Safe-Fixes → {work} [dim](Vault unangetastet)[/dim]"
    )


@cli.command(name="vault-review")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Vault, read-only (default: Brain-Vault)",
)
@click.option(
    "--work-dir",
    "work_dir",
    type=click.Path(),
    default=None,
    help="Patch-Ziel (default: work/vault_review)",
)
def vault_review_cmd(vault_dir: str | None, work_dir: str | None) -> None:
    """WP4: Unified-Diff-Patch-Vorschläge für fixable Fälle (kein Auto-Write)."""
    from pipeline import _paths
    from pipeline import vault_audit as va

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    work = Path(work_dir) if work_dir else (_paths.WORK / "vault_review")
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)
    index = va.build_index(vault)
    patches = [
        "".join(patch)
        for rel, text in index.audit_files.items()
        if (patch := va.review_patches(rel, text))
    ]
    work.mkdir(parents=True, exist_ok=True)
    (work / "review_patches.diff").write_text("\n".join(patches), encoding="utf-8")
    console.print(
        f"[cyan]vault-review:[/cyan] {len(patches)} Patch-Vorschläge → {work / 'review_patches.diff'}"
    )


@cli.command(name="vault-apply")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Ziel-Vault (default: Brain-Vault aus _paths)",
)
@click.option(
    "--chain",
    "chain_str",
    default=None,
    help="Transform-Chain, komma-separiert (default: repair-safe,format-safe)",
)
@click.option(
    "--work-dir",
    "work_dir",
    type=click.Path(),
    default=None,
    help="Diff-Report-Ziel im dry-run (default: work/vault_apply)",
)
@click.option(
    "--backup-dir",
    "backup_dir",
    type=click.Path(),
    default=None,
    help="O4-Backup-Verzeichnis für den Präsenz-Check vor --execute (default: _paths.BACKUPS)",
)
@click.option("--execute", is_flag=True, help="Echte D4-Mutation. Default: dry-run (kein Write).")
@click.option(
    "--confirm",
    is_flag=True,
    help="Owner-Bestätigung für --execute (sonst interaktiver Prompt).",
)
def vault_apply_cmd(
    vault_dir: str | None,
    chain_str: str | None,
    work_dir: str | None,
    backup_dir: str | None,
    execute: bool,
    confirm: bool,
) -> None:
    """Phase 1: Transform-Chain auf den Vault anwenden (D4). Default = dry-run.

    Dry-run berechnet Diffs + Audit-Vorschau und schreibt **nichts**. ``--execute`` löst die
    D4-Mutation aus (Snapshot → Canary → Mass-Write → Verify), aber nur hinter einem harten
    Owner-Gate: explizite Bestätigung (``--confirm`` oder interaktiv) **und** ein präsentes
    O4-Backup (``--backup-dir``, sonst Abbruch). tier-Gate: review/audit-mutierende Transforms
    werden nie auto-geschrieben (bleiben Diff).
    """
    from pipeline import _paths
    from pipeline.driver import apply_to_vault
    from pipeline.transforms import DEFAULT_CHAIN, get

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)

    chain = (
        tuple(c.strip() for c in chain_str.split(",") if c.strip()) if chain_str else DEFAULT_CHAIN
    )
    try:
        for name in chain:
            get(name)  # Transform-Namen früh validieren
    except KeyError as e:
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(2) from e

    # === dry-run (Default): Diffs + Audit-Vorschau, kein Write ===
    if not execute:
        report = apply_to_vault(vault, chain=chain)
        work = Path(work_dir) if work_dir else (_paths.WORK / "vault_apply")
        work.mkdir(parents=True, exist_ok=True)
        diffs = "\n".join(p.diff for p in report.plans if p.changed)
        (work / "apply_diff.diff").write_text(diffs, encoding="utf-8")
        table = Table(title=f"vault-apply (dry-run) · chain={'→'.join(chain)}")
        table.add_column("Metrik")
        table.add_column("Wert", justify="right")
        table.add_row("Files total", str(report.files_total))
        table.add_row("[yellow]Files changed[/yellow]", str(report.files_changed))
        if report.audit_counts is not None:
            table.add_row(
                "audit safe_tier_rest", str(report.audit_counts.get("safe_tier_rest", "?"))
            )
        console.print(table)
        if not report.writable:
            console.print(
                f"[yellow]⚠ tier-Gate:[/yellow] {report.reason} → --execute würde nicht schreiben"
            )
        console.print(
            f"[green]✓[/green] {work / 'apply_diff.diff'} [dim](Vault unangetastet)[/dim]"
        )
        return

    # === --execute: harter Owner-Gate VOR jeder Mutation ===
    # 1) explizite Bestätigung (--confirm oder interaktiv; sonst Abbruch ohne Write)
    if not confirm:
        click.confirm(
            f"--execute: Chain {'→'.join(chain)} auf {vault} ANWENDEN (mutiert den Vault)?",
            abort=True,
        )
    # 2) O4-Backup-Präsenz-Check (unabhängiges Backup muss existieren)
    backups = Path(backup_dir) if backup_dir else _paths.BACKUPS
    if not (backups.is_dir() and any(backups.iterdir())):
        console.print(
            f"[red]✗[/red] O4-Backup-Präsenz-Check fehlgeschlagen: kein Backup unter {backups}. "
            "Abbruch (kein Write)."
        )
        raise SystemExit(2)

    report = apply_to_vault(vault, chain=chain, execute=True)

    # tier-Gate: nicht auto-write-fähige Chain → kein Write (driver-seitig erzwungen).
    if not report.writable:
        console.print(f"[yellow]⚠ tier-Gate:[/yellow] {report.reason} — kein Write.")
        raise SystemExit(1)
    # Canary rot → Mass-Write gestoppt, Rollback via Snapshot.
    if not report.executed:
        console.print(
            f"[red]✗[/red] {report.reason or 'Canary-Verify rot'} "
            f"(Snapshot: {report.snapshot}) → restore_snapshot() für Rollback."
        )
        raise SystemExit(1)

    table = Table(title=f"vault-apply (executed) · chain={'→'.join(chain)}")
    table.add_column("Metrik")
    table.add_column("Wert", justify="right")
    table.add_row("Files changed", str(report.files_changed))
    table.add_row("Files written", str(report.files_written))
    table.add_row("Canary", f"{report.canary} ({'ok' if report.canary_ok else 'FAIL'})")
    if report.audit_counts is not None:
        table.add_row("audit safe_tier_rest", str(report.audit_counts.get("safe_tier_rest", "?")))
    console.print(table)
    console.print(f"[dim]Snapshot: {report.snapshot}[/dim]")
    console.print(f"[green]✓[/green] {report.files_written} Files geschrieben + verifiziert.")


@cli.command(name="fence-indented")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Vault, read-only (default: Brain-Vault aus _paths)",
)
@click.option(
    "--work-dir",
    "work_dir",
    type=click.Path(),
    default=None,
    help="Arbeitskopie + Reports (default: work/fence_indented aus _paths)",
)
def fence_indented_cmd(vault_dir: str | None, work_dir: str | None) -> None:
    """WP3b: indentierte Code-Beispiele → fenced — DRY-RUN (raw read-only → work/).

    Konvertiert nur die WP3b-Scope-Files (KAT_B_FILES). Schreibt für `convertible`
    formatierte Arbeitskopien + Diffs, für `flagged` einen Mechanismus-Hinweis, plus
    Report + Sprach-Tag-Vorschläge nach work/. Der Vault (#3) bleibt unangetastet;
    Export ist separat + Gate-3-pflichtig (nicht hier).
    """
    from pipeline import _paths
    from pipeline.fence_indented import (
        KAT_B_FILES,
        render_language_suggestions,
        render_report,
        scan_files,
        write_work,
    )

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    work = Path(work_dir) if work_dir else (_paths.WORK / "fence_indented")
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)

    console.print(f"[cyan]fence-indented (dry-run):[/cyan] {vault} → {work}")
    outcomes = scan_files(vault, KAT_B_FILES)
    write_work(work, vault, outcomes)
    (work / "fence_indented_report.md").write_text(render_report(outcomes, vault), encoding="utf-8")
    (work / "language_tag_suggestions.md").write_text(
        render_language_suggestions(outcomes), encoding="utf-8"
    )
    conv = sum(1 for o in outcomes if o.status == "convertible")
    flag = sum(1 for o in outcomes if o.status == "flagged")
    table = Table(title=f"WP3b Indented→Fenced ({len(outcomes)} Files)")
    table.add_column("Status")
    table.add_column("Files", justify="right")
    table.add_row("[green]convertible[/green]", str(conv))
    table.add_row("[yellow]flagged (Review)[/yellow]", str(flag))
    console.print(table)
    console.print(f"[green]✓[/green] {work / 'fence_indented_report.md'}")
    console.print(
        "[dim]Vault unangetastet. Export nach #3 ist Gate-3-pflichtig (nicht hier).[/dim]"
    )


@cli.command(name="redundancy-scan")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(),
    default=None,
    help="Zu scannender Vault (default: Brain-Vault aus _paths)",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(),
    default=None,
    help="Ziel für Reports (default: work/ aus _paths)",
)
@click.option(
    "--no-embeddings", "no_embeddings", is_flag=True, help="Nur Hash + TF-IDF (ohne mpnet)"
)
@click.option("--qwen", "qwen", is_flag=True, help="Optionale Qwen-Paar-Bewertung aktivieren")
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def redundancy_scan(
    vault_dir: str | None, output_dir: str | None, no_embeddings: bool, qwen: bool, config: str
) -> None:
    """WP2: Vault (read-only) auf Redundanz + Synthese-Potenzial prüfen → Reports."""
    from pipeline import _paths
    from pipeline.redundancy_scan import (
        Thresholds,
        make_qwen_evaluator,
        run_redundancy_scan,
        write_reports,
    )

    cfg = load_config(Path(config))
    rs = cfg.redundancy_scan
    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    out = Path(output_dir) if output_dir else _paths.WORK
    if not vault.is_dir():
        console.print(f"[red]✗[/red] Vault-Verzeichnis fehlt: {vault}")
        raise SystemExit(2)

    use_emb = rs.use_embeddings and not no_embeddings
    evaluator = None
    if qwen or rs.qwen_evaluate:
        evaluator = make_qwen_evaluator(
            endpoint=cfg.qwen.endpoint,
            model=cfg.qwen.model,
            temperature=cfg.qwen.temperature.stage4_frontmatter,
            timeout=cfg.qwen.timeout_seconds,
        )

    th = Thresholds(
        tfidf_near=rs.tfidf_threshold,
        embedding_dup=rs.embedding_dup_threshold,
        embedding_thematic_low=rs.embedding_thematic_low,
        synthesis_min_members=rs.synthesis_min_members,
    )
    console.print(
        f"[cyan]redundancy-scan:[/cyan] {vault} (embeddings={'an' if use_emb else 'aus'}, "
        f"qwen={'an' if evaluator else 'aus'})"
    )
    result = run_redundancy_scan(
        vault,
        thresholds=th,
        use_embeddings=use_emb,
        model_name=cfg.embeddings.model,
        device=cfg.embeddings.device,
        batch_size=cfg.embeddings.batch_size,
        ngram_range=(cfg.redundancy.tfidf.ngram_range[0], cfg.redundancy.tfidf.ngram_range[1]),
        max_features=cfg.redundancy.tfidf.max_features,
        min_df=cfg.redundancy.tfidf.min_df,
        qwen_evaluator=evaluator,
    )
    red_path, syn_path = write_reports(result, out)

    counts = result.counts()
    table = Table(title=f"Redundancy-Scan ({result.n_docs} Docs)")
    table.add_column("Band")
    table.add_column("Paare", justify="right")
    for band in ("exact", "near-dup", "semantic-dup", "thematic"):
        table.add_row(band, str(counts[band]))
    table.add_row("[bold]Synthese-Kandidaten[/bold]", str(counts["synthesis_candidates"]))
    console.print(table)
    console.print(f"[green]✓[/green] {red_path}")
    console.print(f"[green]✓[/green] {syn_path}")


@cli.group()
def taxonomy() -> None:
    """Taxonomie-SSoT pflegen (Kategorien/Tags): anlegen + umbenennen (mit Migration)."""


@taxonomy.command(name="add-category")
@click.argument("name")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben")
def taxonomy_add_category(name: str, dry_run: bool) -> None:
    """Neue category in der SSoT anlegen (config/categories.yaml + Vault-Ordner)."""
    from scripts.manage_vocab import add_category

    try:
        res = add_category(name, dry_run=dry_run)
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(2) from e
    if res.get("already"):
        console.print(f"[yellow]·[/yellow] category '{name}' existiert bereits → {res['folder']}")
    elif dry_run:
        console.print(f"[cyan][dry-run][/cyan] würde anlegen: '{name}' → {res['folder']}/")
    else:
        console.print(f"[green]✓[/green] category '{name}' → {res['folder']}/ angelegt")


@taxonomy.command(name="add-tag")
@click.argument("tag")
@click.option("--reason", required=True, help="Begründung (Pflicht, persistiert im Changelog)")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben")
def taxonomy_add_tag(tag: str, reason: str, dry_run: bool) -> None:
    """Neuen Tag DIREKT ins YAML-SSoT aufnehmen (governed growth) + tag-system.md synchron."""
    from scripts.manage_vocab import add_tag

    try:
        res = add_tag(tag, reason, dry_run=dry_run)
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(2) from e
    if res.get("already"):
        console.print(f"[yellow]·[/yellow] Tag '{tag}' ist bereits im Vokabular (No-op)")
        return
    md_note = "md-Sync ✓" if res.get("md_synced") else "md-Doc nicht gefunden (nur YAML)"
    if dry_run:
        md_note = "md-Sync geplant" if res.get("md_synced") else "md-Doc nicht gefunden"
        console.print(f"[cyan][dry-run][/cyan] würde Tag '{tag}' ins YAML aufnehmen ({md_note})")
    else:
        console.print(f"[green]✓[/green] Tag '{tag}' ins YAML-SSoT aufgenommen ({md_note})")


@taxonomy.command(name="rename")
@click.argument("kind", type=click.Choice(["category", "tag"]))
@click.argument("old")
@click.argument("new")
@click.option("--dry-run", "dry_run", is_flag=True, help="Plan zeigen, nichts schreiben")
def taxonomy_rename(kind: str, old: str, new: str, dry_run: bool) -> None:
    """OLD → NEW umbenennen und Bestand migrieren (SSoT + Frontmatter + Ordner + Index).

    Mutiert den Vault unter output/. Vor dem ersten echten Lauf Snapshot ziehen
    (`bash scripts/snapshot.sh`).
    """
    from pipeline.taxonomy_migrate import rename_category, rename_tag

    try:
        if kind == "category":
            res = rename_category(old, new, dry_run=dry_run)
        else:
            res = rename_tag(old, new, dry_run=dry_run)
    except (ValueError, FileExistsError) as e:
        console.print(f"[red]✗[/red] {e}")
        raise SystemExit(2) from e

    head = "[cyan][dry-run][/cyan]" if dry_run else "[green]✓[/green]"
    console.print(f"{head} rename {kind}: {old} → {new}")
    for c in res.changed:
        console.print(f"  · {c}")
    console.print(
        f"  Vault-Frontmatter: {res.files_frontmatter} · Drafts: {res.drafts_frontmatter}"
        f" · Index-Regen: {res.indexes_regenerated}"
    )
    if res.validation_errors:
        console.print(f"[red]Validierungsfehler ({len(res.validation_errors)}):[/red]")
        for verr in res.validation_errors[:20]:
            console.print(f"  [red]✗[/red] {verr}")
        raise SystemExit(1)


@cli.command()
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Quell-File für die review-Restrukturierung (genau eines, opt-in).",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Draft-Zielordner (default: drafts/). Schreibt NIE in den Vault.",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def restructure(file_path: str, out_dir: str | None, config: str) -> None:
    """review-only: erzeugt einen restructure-Draft via Qwen, schreibt NIE in den Vault."""
    import openai

    from pipeline import _paths
    from pipeline.restructure import RestructureError, restructure_file

    cfg = load_config(Path(config))
    client = openai.OpenAI(
        base_url=cfg.qwen.endpoint,
        api_key="local",
        timeout=cfg.qwen.timeout_seconds,
    )
    out = Path(out_dir) if out_dir else _paths.DRAFTS
    try:
        draft = restructure_file(Path(file_path), client=client, qwen=cfg.qwen, out_dir=out)
    except RestructureError as exc:
        console.print(f"[red]✗ restructure fehlgeschlagen:[/red] {exc}")
        raise SystemExit(1) from exc

    flag = " [yellow]⚠ confidence-Fallback[/yellow]" if draft.confidence_fallback else ""
    console.print(
        f"[green]✓ Draft:[/green] {draft.draft_path} (confidence={draft.confidence}){flag}"
    )
    console.print(
        f"  type={draft.type} (source={draft.type_source}) · action={draft.restructure_action}"
    )
    console.print("  review-Tier: kein Vault-Write, Quell-File unberührt.")


@cli.command()
@click.option(
    "--draft",
    "draft_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Promotions-Quelle (Draft mit review_status: human_reviewed/verified).",
)
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Ziel-Vault (Default: Brain-Vault _paths.BRAIN_VAULT).",
)
@click.option(
    "--on-collision",
    type=click.Choice(["abort", "replace", "suffix"]),
    default="abort",
    help="Kollisions-Auflösung wenn Ziel existiert (Default: abort = STOP).",
)
@click.option("--execute", "do_execute", is_flag=True, help="D4-Live-Write (Owner-Gate!).")
def promote(draft_path: str, vault_dir: str | None, on_collision: str, do_execute: bool) -> None:
    """Promotet einen human_reviewed Draft in den Live-Vault. Default = dry-run."""
    from pipeline import _paths
    from pipeline.promotion import PromotionError, execute_promotion, plan_promotion

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    try:
        plan = plan_promotion(Path(draft_path), vault, on_collision=on_collision)
    except PromotionError as exc:
        console.print(f"[red]✗ Promotion abgebrochen:[/red] {exc}")
        raise SystemExit(1) from exc

    console.print(
        f"[cyan]Plan:[/cyan] {plan.slug} → {plan.target_path} "
        f"(category={plan.category}, folder={plan.folder}, "
        f"{'UPDATE' if plan.is_update else 'NEU'}, doc_count +{plan.doc_count_delta})"
    )
    if plan.collision:
        console.print(
            "[yellow]⚠ Kollision:[/yellow] Ziel existiert. Kein Blind-Overwrite — "
            "Auflösung: --on-collision replace | suffix | abort."
        )
        if plan.diff:
            console.print("[dim]--- Diff (Bestand → promotet) ---[/dim]")
            console.print(plan.diff)
        raise SystemExit(2)

    if not do_execute:
        console.print("[cyan]--dry-run:[/cyan] nichts geschrieben. `--execute` für D4-Write.")
        if plan.diff:
            console.print("[dim]--- Diff (Bestand → promotet) ---[/dim]")
            console.print(plan.diff)
        return

    report = execute_promotion(plan, vault)
    console.print(
        f"[green]✓ Promotet:[/green] {report.target_path} ({report.resolution})\n"
        f"  Index regeneriert: {report.folder}/_index.md ({report.index_article_count} Artikel)\n"
        f"  Draft archiviert: {report.archived_draft}\n"
        f"  Snapshot (Rollback): {report.snapshot}"
    )


@cli.command(name="restructure-batch")
@click.option(
    "--file",
    "files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Quell-File (mehrfach angebbar). Alternativ --cluster.",
)
@click.option(
    "--cluster",
    "cluster",
    default=None,
    help="Vault-Kategorie (Ordner-SSoT) — alle Artikel des Clusters. Opt-in.",
)
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Live-Vault (read-only, promote_mode-Check). Default: Brain-Vault.",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Draft-Zielordner (Default: drafts/_wp3c6/).",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def restructure_batch(
    files: tuple[str, ...],
    cluster: str | None,
    vault_dir: str | None,
    out_dir: str | None,
    config: str,
) -> None:
    """Batch-restructure (review-Tier): erzeugt Drafts + Review-Sheet. KEIN Vault-Write."""
    from datetime import UTC, datetime

    import openai

    from pipeline import _paths, taxonomy
    from pipeline.batch_restructure import run_batch_restructure, write_review_sheet

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    out = Path(out_dir) if out_dir else (_paths.DRAFTS / "_wp3c6")

    # Opt-in-Selektion: genau eine Quelle (Files ODER Cluster), kein All-Vault.
    if bool(files) == bool(cluster):
        console.print("[red]✗[/red] Genau eine Quelle angeben: --file (mehrfach) ODER --cluster.")
        raise SystemExit(1)
    if files:
        selected = [Path(f) for f in files]
    else:
        folder = taxonomy.load_category_to_folder().get(str(cluster))
        if not folder:
            console.print(f"[red]✗[/red] Unbekannte Kategorie/Cluster: {cluster!r}")
            raise SystemExit(1)
        selected = sorted(p for p in (vault / folder).glob("*.md") if p.name != "_index.md")
    if not selected:
        console.print("[yellow]Keine Files selektiert.[/yellow]")
        return

    cfg = load_config(Path(config))
    client = openai.OpenAI(
        base_url=cfg.qwen.endpoint, api_key="local", timeout=cfg.qwen.timeout_seconds
    )
    console.print(
        f"[cyan]Batch:[/cyan] {len(selected)} File(s) → {out} (review-Tier, kein Vault-Write)"
    )
    result = run_batch_restructure(
        selected, client=client, qwen=cfg.qwen, vault_dir=vault, out_dir=out
    )

    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    sheet = write_review_sheet(result, out / f"review_sheet_{ts}.xlsx")
    console.print(f"[green]✓[/green] {len(result.rows)} Draft(s), {len(result.failures)} Fehler.")
    console.print(f"  Review-Sheet: {sheet}")
    for src, reason in result.failures:
        console.print(f"  [yellow]needs_human:[/yellow] {Path(src).name} — {reason}")


@cli.command(name="review-ingest")
@click.option(
    "--sheet",
    "sheet_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Ausgefülltes Review-Sheet (.xlsx) mit Owner-Entscheidungen.",
)
def review_ingest(sheet_path: str) -> None:
    """Liest Owner-Entscheidungen: accept→human_reviewed, reject→archive, edit→Flag. Kein Vault-Write."""
    from pipeline.batch_restructure import ingest_review_sheet

    result = ingest_review_sheet(Path(sheet_path))
    console.print(
        f"[green]✓ Ingest:[/green] {len(result.ready)} promotion-bereit · "
        f"{len(result.edits)} edit · {len(result.rejected)} rejected"
    )
    for p in result.ready:
        console.print(f"  [green]ready:[/green] {p}")
    for slug in result.edits:
        console.print(f"  [yellow]edit:[/yellow] {slug}")
    if result.ready:
        console.print("  → promotieren mit: pkm promote --draft <path> (WP3c-5, Owner-Gate)")


@cli.command(name="frontmatter-audit")
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Zu auditierender Vault (read-only). Default: Brain-Vault.",
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Report-Zielordner (Default: work/audit/).",
)
@click.option("--xlsx", "want_xlsx", is_flag=True, help="Zusätzlich .xlsx schreiben.")
def frontmatter_audit(vault_dir: str | None, out_dir: str | None, want_xlsx: bool) -> None:
    """Read-only Frontmatter-Lücken-Audit (deterministisch, kein LLM, kein Vault-Write)."""
    from datetime import UTC, datetime

    from pipeline import _paths
    from pipeline.frontmatter_audit import audit_vault, render_report, write_audit_xlsx

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    out = Path(out_dir) if out_dir else (_paths.WORK / "audit")
    out.mkdir(parents=True, exist_ok=True)

    result = audit_vault(vault)
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    report_path = out / f"frontmatter_audit_{ts}.md"
    report_path.write_text(render_report(result, vault), encoding="utf-8")

    totals = result.gap_class_totals()
    console.print(
        f"[green]✓ Audit:[/green] {len(result.files)} Files · "
        f"complete={len(result.by_recommendation('complete'))} · "
        f"restructure={len(result.by_recommendation('restructure'))} · "
        f"mechanical-fix={len(result.by_recommendation('mechanical-fix'))} · "
        f"owner={len(result.by_recommendation('owner'))}"
    )
    console.print(
        f"  Lücken: mechanical={totals['mechanical']} llm={totals['llm']} owner={totals['owner']}"
    )
    console.print(f"  Report: {report_path}")
    if want_xlsx:
        xlsx_path = write_audit_xlsx(result, out / f"frontmatter_audit_{ts}.xlsx")
        console.print(f"  Sheet: {xlsx_path}")


@cli.command()
@click.option(
    "--source",
    "source",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Quell-Ordner — ALLE *.md werden erfasst (kein Filter).",
)
@click.option(
    "--vault-dir",
    "vault_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Live-Vault (read-only, promote_mode-Check). Default: Brain-Vault.",
)
@click.option(
    "--resume",
    "do_resume",
    is_flag=True,
    help="Am letzten State fortsetzen + gescheiterte Files erneut versuchen.",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=_DEFAULT_CONFIG,
    help=f"Pfad zur pipeline.config.yaml (default: {_DEFAULT_CONFIG})",
)
def process(source: str, vault_dir: str | None, do_resume: bool, config: str) -> None:
    """Universelle Erstverarbeitung: jedes File → vault-ready bis review_ready. Kein Vault-Write."""
    import openai

    from pipeline import _paths
    from pipeline.process_orchestrator import run_process

    vault = Path(vault_dir) if vault_dir else _paths.BRAIN_VAULT
    cfg = load_config(Path(config))
    client = openai.OpenAI(
        base_url=cfg.qwen.endpoint, api_key="local", timeout=cfg.qwen.timeout_seconds
    )
    console.print(
        f"[cyan]Process:[/cyan] {source} → Stage-Kette bis review_ready "
        "(alle Files, kein Filter; kein Vault-Write)"
    )
    result = run_process(
        Path(source), client=client, qwen=cfg.qwen, vault_dir=vault, resume=do_resume
    )
    console.print(
        f"[green]✓[/green] {len(result.review_ready)} review_ready · {len(result.failures)} needs_human"
    )
    if result.sheet_path:
        console.print(f"  Review-Sheet: {result.sheet_path}")
    for src, stage, err in result.failures:
        console.print(f"  [yellow]needs_human:[/yellow] {Path(src).name} (@{stage}) — {err}")
    if result.review_ready:
        console.print(
            "  → Review-Sheet ausfüllen, dann: pkm review-ingest / pkm promote (Owner-Gate)"
        )


if __name__ == "__main__":
    cli()
