"""WP2 — Browser-Download-Ingest: Markdown + Asset-Ordner pipeline-fertig aufbereiten.

Ein Mensch wirft Browser-Downloads (eine ``.md`` plus zugehörigen Asset-Ordner)
in ``_ingest/``. Dieses Modul bereitet sie für die Pipeline auf:

1. **Detect** — zu jeder ``.md`` den zugehörigen Asset-Ordner finden
   (gleichnamiger Ordner, ``<name>_files/``, ``<name>.assets/``, ``assets/`` oder
   einziger Bild-Unterordner daneben). Mehrdeutig / nicht gefunden, aber lokale
   Bild-Links vorhanden → Quarantäne, **nicht raten**.
2. **Slug** — Quell-Slug aus dem Original-Dateinamen über die Phase-1-Slug-Logik
   (`pipeline.phase_1_inventory._filename_to_slug`) + 60-Zeichen-Cap (Vault-Standard §5).
3. **Rename** — Assets → ``<quell-slug>__<original-name>.ext`` (Kollision: numerisches Suffix).
4. **Rewrite** — lokale Bild-Embeds ``![alt](rel/pfad.ext)`` → ``![[<quell-slug>__name.ext]]``.
   Externe ``http(s)``-Bild-URLs bleiben unangetastet; normale Links ebenso.
5. **Einspeisen** — ``.md`` → ``input/``, umbenannte Assets → ``input/_assets/``.

Sicherheit & Idempotenz:
  - ``_ingest/`` ist **read-only** — es wird kopiert, nie verschoben/gelöscht
    (der Original-Download bleibt erhalten).
  - Ziel-Namen sind eine reine Funktion der Quelle → ein zweiter Lauf erzeugt
    identische Outputs (kein Aufschaukeln von Kollisions-Suffixen).

Scope OUT (= WP3): kein Vault-Build, kein Schreibzugriff auf den Produktiv-Vault.
Die Assets warten in ``input/_assets/`` auf das Durchschleusen durch WP3.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

import click
import structlog
from rich.console import Console
from rich.table import Table

from pipeline import _paths
from pipeline.phase_1_inventory import _filename_to_slug

log = structlog.get_logger()

# CK-Slug-Cap aus dem Vault-Standard (§5, Schritt 5) — identisch zu phase_8._slugify_ck.
_SLUG_MAX_LEN = 60

# Markdown-Bild-Embed: ![alt](inner). ``inner`` wird in _split_url_title zerlegt,
# damit auch rohe Leerzeichen im Pfad (häufig in Browser-Exporten) tragen.
_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<inner>[^)]*)\)")

# Optionaler Markdown-Title am Ende: ` "…"` oder ` '…'`.
_TITLE_RE = re.compile(r"\s+(?:\"[^\"]*\"|'[^']*')$")

# URL mit Schema (http://, https://, data:, //host) → extern, nicht anfassen.
_EXTERNAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:|//)", re.IGNORECASE)


def _split_url_title(inner: str) -> str:
    """Extrahiert die URL aus dem ``(…)``-Teil eines Markdown-Links.

    Behandelt ``<url>``-Klammerung und einen optionalen ``"title"`` am Ende.
    Rohe Leerzeichen im Pfad bleiben Teil der URL (kein Title vorhanden).
    """
    s = inner.strip()
    if s.startswith("<"):
        end = s.find(">")
        return s[1:end] if end != -1 else s[1:]
    m = _TITLE_RE.search(s)
    return s[: m.start()].strip() if m else s


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif", ".tiff"}


def quell_slug(md_stem: str) -> str:
    """Leitet den Quell-Slug aus einem ``.md``-Dateinamen-Stamm ab.

    Verwendet die kanonische Phase-1-Slug-Logik (NFC → Umlaut-Map → NFKD-Strip)
    und kappt auf 60 Zeichen (Vault-Standard §5). Keine Duplikation der Logik.

    Args:
        md_stem: Dateiname ohne Endung (``Path.stem``).

    Returns:
        URL-sicherer Slug, max. 60 Zeichen; ``"note"`` als Fallback bei leerem Ergebnis.
    """
    slug = _filename_to_slug(md_stem)
    return slug[:_SLUG_MAX_LEN].strip("-") or "note"


@dataclass
class IngestResult:
    """Ergebnis der Aufbereitung einer einzelnen ``.md``."""

    md_path: Path
    status: str  # "ingested" | "quarantined" | "skipped_no_links"
    slug: str = ""
    asset_dir: Path | None = None
    renamed: dict[str, str] = field(default_factory=dict)  # original-name → ziel-name
    reason: str = ""


def _contains_image(directory: Path) -> bool:
    """True, wenn der Ordner (rekursiv) mindestens eine Bilddatei enthält."""
    return any(f.is_file() and f.suffix.lower() in _IMAGE_EXTS for f in directory.rglob("*"))


def detect_asset_dir(md_path: Path) -> tuple[Path | None, str]:
    """Findet den zu einer ``.md`` gehörenden Asset-Ordner.

    Args:
        md_path: Pfad zur Markdown-Datei.

    Returns:
        ``(asset_dir, status)``. ``status`` ist ``"ok"`` (Ordner gefunden),
        ``"none"`` (kein Kandidat) oder ``"ambiguous"`` (mehrere Kandidaten →
        nicht raten). Bei ``"none"``/``"ambiguous"`` ist ``asset_dir`` ``None``.
    """
    parent = md_path.parent
    stem = md_path.stem

    # Spezifische, namensgebundene Kandidaten haben Vorrang.
    specific = [parent / stem, parent / f"{stem}_files", parent / f"{stem}.assets"]
    existing_specific = [d for d in specific if d.is_dir()]
    if len(existing_specific) == 1:
        return existing_specific[0], "ok"
    if len(existing_specific) > 1:
        return None, "ambiguous"

    # Generischer ``assets/``-Ordner daneben.
    generic = parent / "assets"
    if generic.is_dir():
        return generic, "ok"

    # Heuristik: genau ein Bild-Unterordner daneben (ohne ``_``-Präfix).
    image_subdirs = [
        d
        for d in parent.iterdir()
        if d.is_dir() and not d.name.startswith("_") and _contains_image(d)
    ]
    if len(image_subdirs) == 1:
        return image_subdirs[0], "ok"
    if len(image_subdirs) > 1:
        return None, "ambiguous"

    return None, "none"


def _target_name(slug: str, original_name: str, used: set[str]) -> str:
    """Bildet ``<slug>__<original-name>`` mit numerischem Suffix bei Kollision."""
    base = f"{slug}__{original_name}"
    if base not in used:
        used.add(base)
        return base
    stem, dot, ext = original_name.rpartition(".")
    i = 2
    while True:
        cand = f"{slug}__{stem}_{i}.{ext}" if dot else f"{slug}__{original_name}_{i}"
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


def _build_rename_map(asset_dir: Path, slug: str) -> tuple[dict[Path, str], dict[str, str]]:
    """Erzeugt die Umbenennungs-Map für alle Assets eines Docs.

    Args:
        asset_dir: Gefundener Asset-Ordner.
        slug: Quell-Slug der zugehörigen ``.md``.

    Returns:
        ``(by_resolved, by_basename)`` — Map vom aufgelösten Asset-Pfad bzw.
        vom Basename auf den Ziel-Namen. Deterministisch (sortiert nach Pfad).
    """
    used: set[str] = set()
    by_resolved: dict[Path, str] = {}
    by_basename: dict[str, str] = {}
    files = sorted(f for f in asset_dir.rglob("*") if f.is_file())
    for f in files:
        target = _target_name(slug, f.name, used)
        by_resolved[f.resolve()] = target
        # Erstes Vorkommen eines Basenames gewinnt die Kurz-Auflösung.
        by_basename.setdefault(f.name, target)
    return by_resolved, by_basename


def has_local_image_links(text: str) -> bool:
    """True, wenn der Text mindestens einen lokalen (nicht-externen) Bild-Embed hat."""
    for m in _IMG_RE.finditer(text):
        url = _split_url_title(m.group("inner"))
        if url and not _EXTERNAL_RE.match(url):
            return True
    return False


def rewrite_links(
    text: str,
    md_dir: Path,
    by_resolved: dict[Path, str],
    by_basename: dict[str, str],
) -> tuple[str, int, int]:
    """Schreibt lokale Bild-Embeds auf pfad-freie Wikilinks um.

    Externe ``http(s)``-URLs und normale (Nicht-Bild-)Links bleiben unverändert.

    Args:
        text: Markdown-Quelltext.
        md_dir: Verzeichnis der ``.md`` (zur Auflösung relativer Pfade).
        by_resolved: Map aufgelöster Asset-Pfad → Ziel-Name.
        by_basename: Map Basename → Ziel-Name (Fallback).

    Returns:
        ``(neuer_text, anzahl_umgeschrieben, anzahl_unaufgeloest)``.
    """
    rewritten = 0
    unresolved = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal rewritten, unresolved
        url = _split_url_title(m.group("inner"))
        if not url or _EXTERNAL_RE.match(url):
            return m.group(0)  # extern oder leer → unangetastet

        link = unquote(url).split("#", 1)[0].split("?", 1)[0]
        target: str | None = None
        try:
            resolved = (md_dir / link).resolve()
            target = by_resolved.get(resolved)
        except (OSError, ValueError):
            target = None
        if target is None:
            target = by_basename.get(Path(link).name)

        if target is None:
            unresolved += 1
            return m.group(0)  # lokal, aber kein passendes Asset → unverändert
        rewritten += 1
        return f"![[{target}]]"

    return _IMG_RE.sub(repl, text), rewritten, unresolved


def _copy_if_changed(src: Path, dst: Path, dry_run: bool) -> None:
    """Kopiert ``src`` nach ``dst``, wenn ``dst`` fehlt oder sich der Inhalt unterscheidet."""
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        return
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def ingest_one(
    md_path: Path,
    input_dir: Path,
    input_assets: Path,
    quarantine_dir: Path,
    dry_run: bool = False,
) -> IngestResult:
    """Bereitet eine einzelne ``.md`` auf (Detect → Rename → Rewrite → Einspeisen).

    Args:
        md_path: Quell-Markdown in ``_ingest/``.
        input_dir: Ziel für die ``.md`` (``input/``).
        input_assets: Ziel für umbenannte Assets (``input/_assets/``).
        quarantine_dir: Ablage für nicht auflösbare Fälle (``_ingest/_quarantine/``).
        dry_run: Wenn True, wird nichts geschrieben.

    Returns:
        ``IngestResult`` mit Status und Detail-Infos.
    """
    text = md_path.read_text(encoding="utf-8", errors="replace")
    slug = quell_slug(md_path.stem)
    has_links = has_local_image_links(text)

    asset_dir, det_status = detect_asset_dir(md_path)

    # Kein Asset-Ordner (oder mehrdeutig), aber lokale Bild-Links → Quarantäne.
    if det_status != "ok" and has_links:
        if not dry_run:
            dst = quarantine_dir / md_path.name
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(md_path, dst)
        log.warning(
            "ingest_quarantine",
            md=md_path.name,
            reason=det_status,
            has_local_image_links=True,
        )
        return IngestResult(md_path, "quarantined", slug=slug, reason=det_status)

    by_resolved: dict[Path, str] = {}
    by_basename: dict[str, str] = {}
    if asset_dir is not None:
        by_resolved, by_basename = _build_rename_map(asset_dir, slug)

    new_text, n_rewritten, n_unresolved = rewrite_links(
        text, md_path.parent, by_resolved, by_basename
    )

    # Assets kopieren (umbenannt).
    renamed: dict[str, str] = {}
    if asset_dir is not None:
        for src in sorted(by_resolved):
            target = by_resolved[src]
            _copy_if_changed(src, input_assets / target, dry_run)
            renamed[src.name] = target

    # Markdown einspeisen.
    if not dry_run:
        input_dir.mkdir(parents=True, exist_ok=True)
        out_md = input_dir / md_path.name
        if not (out_md.exists() and out_md.read_text(encoding="utf-8") == new_text):
            out_md.write_text(new_text, encoding="utf-8")

    status = "ingested" if (has_links or asset_dir) else "skipped_no_links"
    log.info(
        "ingest_ok",
        md=md_path.name,
        slug=slug,
        assets=len(renamed),
        rewritten=n_rewritten,
        unresolved=n_unresolved,
    )
    return IngestResult(
        md_path,
        "ingested",
        slug=slug,
        asset_dir=asset_dir,
        renamed=renamed,
        reason="no_local_links" if status == "skipped_no_links" else "",
    )


def ingest_all(
    ingest_dir: Path,
    input_dir: Path,
    input_assets: Path,
    quarantine_dir: Path,
    dry_run: bool = False,
) -> list[IngestResult]:
    """Verarbeitet alle ``.md`` aus ``ingest_dir`` (rekursiv, ``_quarantine/`` ausgenommen).

    Returns:
        Liste der Einzelergebnisse.
    """
    results: list[IngestResult] = []
    md_files = sorted(
        f for f in ingest_dir.rglob("*.md") if f.is_file() and quarantine_dir not in f.parents
    )
    for md in md_files:
        results.append(ingest_one(md, input_dir, input_assets, quarantine_dir, dry_run))
    return results


def _render_summary(results: list[IngestResult], dry_run: bool) -> None:
    """Gibt eine Ergebnis-Tabelle auf der Konsole aus."""
    console = Console()
    table = Table(title="Ingest" + (" (dry-run)" if dry_run else ""))
    table.add_column("Markdown")
    table.add_column("Status")
    table.add_column("Slug")
    table.add_column("Assets", justify="right")
    table.add_column("Hinweis")
    for r in results:
        table.add_row(r.md_path.name, r.status, r.slug, str(len(r.renamed)), r.reason)
    console.print(table)


@click.command()
@click.option(
    "--ingest-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Eingangsordner (default: pkm-pipeline/_ingest/).",
)
@click.option(
    "--input-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Ziel für .md (default: pkm-pipeline/input/).",
)
@click.option("--dry-run", is_flag=True, help="Plan zeigen, nichts schreiben.")
def main(ingest_dir: Path | None, input_dir: Path | None, dry_run: bool) -> None:
    """Browser-Downloads aus ``_ingest/`` pipeline-fertig nach ``input/`` aufbereiten."""
    ingest = ingest_dir or _paths.INGEST
    inp = input_dir or _paths.INPUT
    assets = inp / "_assets"
    quarantine = ingest / "_quarantine"

    if not ingest.is_dir():
        raise click.ClickException(f"Eingangsordner fehlt: {ingest}")

    results = ingest_all(ingest, inp, assets, quarantine, dry_run)
    _render_summary(results, dry_run)


if __name__ == "__main__":
    main()
