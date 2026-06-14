#!/usr/bin/env python3
"""
publish_assets.py — gebaute Assets add-only in den produktiven Vault übernehmen.

Zweck:
  Manueller Publish-Schritt nach `pkm run` (WP3, Leitplanke 5): kopiert die im
  Build erzeugten Assets aus `output/_assets/` in den Asset-Pool des produktiven
  Obsidian-Vaults (`09_Brain-Vault/_assets/`). Kein Auto-Publish — du rufst das
  selbst auf, nachdem du `output/` geprüft hast (`make publish-check`).

Add-only:
  - Neue Dateien werden kopiert.
  - Schon vorhandene, byte-identische Dateien werden übersprungen (idempotent).
  - Vorhandene Dateien mit ABWEICHENDEM Inhalt werden NICHT überschrieben, sondern
    als Konflikt gemeldet (Namen sind durch den `<slug>__`-Präfix kollisionsfrei;
    ein Konflikt deutet auf ein echtes Problem hin und wird nicht still überschrieben).

Sicherheit:
  - DRY-RUN ist Default. Geschrieben wird nur mit --apply.
  - Schreibt ausschließlich in den Ziel-Asset-Ordner (#3), nie ins Repo (#1).

Aufruf:
  python3 scripts/publish_assets.py                 # dry-run: zeigt, was kopiert würde
  python3 scripts/publish_assets.py --apply         # kopiert neue Assets
  python3 scripts/publish_assets.py --target /pfad/zum/vault/_assets
  PKM_BRAIN_VAULT=/pfad/zum/vault python3 scripts/publish_assets.py --apply

Exit:
  0 = nichts zu tun ODER apply erfolgreich
  1 = Kopien ausstehend (dry-run) ODER Konflikt(e) erkannt
  2 = Setup-Fehler (Quell-Ordner fehlt)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths  # noqa: E402


def plan_publish(src: Path, dst: Path) -> dict[str, list[str]]:
    """Berechnet den add-only Plan ohne zu schreiben.

    Args:
        src: Quell-Asset-Ordner (`output/_assets/`).
        dst: Ziel-Asset-Ordner (`<vault>/_assets/`).

    Returns:
        Dict mit Listen von Dateinamen je Kategorie: ``to_copy`` (neu),
        ``unchanged`` (schon identisch da), ``conflicts`` (da, aber andere Bytes).
    """
    to_copy: list[str] = []
    unchanged: list[str] = []
    conflicts: list[str] = []
    for f in sorted(p for p in src.iterdir() if p.is_file()):
        target = dst / f.name
        if not target.exists():
            to_copy.append(f.name)
        elif target.read_bytes() == f.read_bytes():
            unchanged.append(f.name)
        else:
            conflicts.append(f.name)
    return {"to_copy": to_copy, "unchanged": unchanged, "conflicts": conflicts}


def publish_assets(src: Path, dst: Path, *, apply: bool) -> dict[str, list[str]]:
    """Führt den add-only Merge aus (oder berechnet ihn nur, wenn ``apply`` False ist).

    Konflikte (vorhandene Datei mit anderem Inhalt) werden nie überschrieben.

    Args:
        src: Quell-Asset-Ordner.
        dst: Ziel-Asset-Ordner.
        apply: True → tatsächlich kopieren; False → nur planen (dry-run).

    Returns:
        Plan-Dict wie ``plan_publish`` (die ``to_copy``-Liste ist bei ``apply`` die
        tatsächlich kopierte Menge).
    """
    plan = plan_publish(src, dst)
    if apply and plan["to_copy"]:
        dst.mkdir(parents=True, exist_ok=True)
        for name in plan["to_copy"]:
            shutil.copy2(src / name, dst / name)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Assets add-only in den Produktiv-Vault übernehmen.")
    parser.add_argument("--apply", action="store_true", help="tatsächlich kopieren (Default: dry-run)")
    parser.add_argument(
        "--source",
        type=Path,
        default=_paths.OUTPUT_ASSETS,
        help=f"Quell-Asset-Ordner (Default: {_paths.OUTPUT_ASSETS})",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=_paths.BRAIN_VAULT_ASSETS,
        help=f"Ziel-Asset-Ordner (Default: {_paths.BRAIN_VAULT_ASSETS}; auch PKM_BRAIN_VAULT)",
    )
    args = parser.parse_args()

    src: Path = args.source
    dst: Path = args.target
    if not src.exists():
        print(f"FEHLER: Quell-Ordner fehlt: {src}", file=sys.stderr)
        return 2

    plan = publish_assets(src, dst, apply=args.apply)
    mode = "apply" if args.apply else "dry-run"
    print(f"publish-assets [{mode}]: src={src} → dst={dst}")
    print(
        f"  {'kopiert' if args.apply else 'zu kopieren'}: {len(plan['to_copy'])} · "
        f"unverändert: {len(plan['unchanged'])} · Konflikte: {len(plan['conflicts'])}"
    )
    for name in plan["to_copy"]:
        print(f"  + {name}")
    for name in plan["conflicts"]:
        print(f"  ! Konflikt (nicht überschrieben): {name}")

    if plan["conflicts"]:
        return 1
    if not args.apply and plan["to_copy"]:
        print("  → mit --apply ausführen, um zu kopieren.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
