"""CLI-Entry-Point der PKM-rebuild Pipeline."""

from pathlib import Path

import click
from rich.console import Console

from pipeline.config import load_config
from pipeline.phase_1_inventory import run_phase_1
from pipeline.phase_2_normalize import run_phase_2

console = Console()

_ALL_PHASES = list(range(1, 11))
_IMPLEMENTED_PHASES = {1, 2}
_DEFAULT_CONFIG = "pipeline/pipeline.config.yaml"


def _phases_to_run(phase: int | None, from_phase: int | None) -> list[int]:
    if phase is not None:
        return [phase]
    if from_phase is not None:
        return [p for p in _ALL_PHASES if p >= from_phase]
    return _ALL_PHASES


@click.group()
@click.version_option()
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

        if p == 1:
            effective_sample = (
                sample if sample is not None else (cfg.sample.count if cfg.sample.enabled else None)
            )
            output_path = cfg.paths.pipeline_output / "files_manifest.jsonl"
            try:
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
            except FileNotFoundError as exc:
                console.print(f"[red]Fehler Phase 1:[/red] {exc}")
                raise SystemExit(1) from exc

        elif p == 2:
            manifest_path = cfg.paths.pipeline_output / "files_manifest.jsonl"
            output_path = cfg.paths.pipeline_output / "cleaned_documents.jsonl"
            try:
                records = run_phase_2(
                    manifest_path=manifest_path,
                    output_path=output_path,
                    force=force,
                    max_blank_lines=cfg.normalization.max_blank_lines,
                    tab_replacement=cfg.normalization.tab_replacement,
                    strip_trailing_whitespace=cfg.normalization.strip_trailing_whitespace,
                    parse_frontmatter=cfg.normalization.parse_frontmatter,
                    pipeline_version=cfg.pipeline.version,
                )
                console.print(f"[green]✓ Phase 2:[/green] {len(records)} Dokumente → {output_path}")
            except FileNotFoundError as exc:
                console.print(f"[red]Fehler Phase 2:[/red] {exc}")
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


if __name__ == "__main__":
    cli()
