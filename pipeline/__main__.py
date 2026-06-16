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
        pipeline_version=cfg.pipeline.version,
    )
    prefix = "[cyan]--dry-run:[/cyan] " if dry_run else ""
    if summary.get("skipped"):
        console.print("[yellow]Phase 9: übersprungen (Input-Hash unverändert).[/yellow]")
    console.print(
        f"{prefix}[green]✓ Phase 9:[/green] {summary['articles']} Artikel in "
        f"{summary['folders_used']} Ordnern, {summary['dropped_links']} Links gedroppt "
        f"({summary['dropped_links_drafts']} Drafts), {summary['collisions']} Slug-Kollisionen, "
        f"{summary['errors']} Errors"
    )
    if summary.get("unknown_categories"):
        console.print(
            f"[yellow]  unbekannte Kategorien → unsortiert:[/yellow] "
            f"{summary['unknown_categories']}"
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


if __name__ == "__main__":
    cli()
