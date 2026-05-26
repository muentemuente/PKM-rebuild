"""CLI-Entry-Point der PKM-rebuild Pipeline.

Aktueller Stand: Phase 0 (Setup). Phasen-Implementierungen folgen in
nachfolgenden Phasen. Siehe docs/02_pipeline_spec.md Sektion 4 fuer die
finale CLI-Spec.
"""

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option()
def cli() -> None:
    """PKM-rebuild Pipeline."""


@cli.command()
def status() -> None:
    """Aktuellen Pipeline-Status anzeigen."""
    console.print("[bold cyan]PKM-rebuild Pipeline[/bold cyan]")
    console.print("Phase 0: Setup abgeschlossen, Phasen 1-10 noch nicht implementiert.")
    console.print("Siehe docs/02_pipeline_spec.md fuer die geplante Architektur.")


@cli.command()
@click.option("--sample", type=int, default=None, help="Sample-Modus mit N Files")
@click.option("--phase", type=int, default=None, help="Nur diese Phase")
@click.option("--from-phase", type=int, default=None, help="Ab dieser Phase bis Ende")
@click.option("--force", is_flag=True, help="Cache ignorieren, alles neu")
@click.option("--dry-run", is_flag=True, help="Plan zeigen, nichts schreiben")
def run(
    sample: int | None,
    phase: int | None,
    from_phase: int | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Pipeline-Lauf starten (Phase 1-10).

    Placeholder - wird in Phase 1 implementiert.
    """
    console.print("[yellow]Warnung: Pipeline-Run noch nicht implementiert.[/yellow]")
    console.print("Aktueller Stand: Phase 0 (Setup).")
    console.print()
    console.print("Uebergebene Flags:")
    console.print(f"  --sample = {sample}")
    console.print(f"  --phase = {phase}")
    console.print(f"  --from-phase = {from_phase}")
    console.print(f"  --force = {force}")
    console.print(f"  --dry-run = {dry_run}")


if __name__ == "__main__":
    cli()
