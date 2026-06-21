"""Phase 9: Vault-Aufbau.

Baut aus den aktiven Drafts (`drafts/*.md`, ohne `_hold/`, ohne `*.body.md`)
den finalen Obsidian-Vault unter `output/<NN_Cluster>/<slug>.md`.

Pro Draft:
  1. YAML-Frontmatter parsen → Pydantic `FrontmatterDraft` validieren.
     Fail → `phase9_errors.jsonl`, skip, weiter (kein Abort).
  2. Body 1:1 aus `<stem>.body.md` (Fallback: embedded Body der `.md`).
  3. `category` → nummerierter Vault-Ordner via `CATEGORY_TO_FOLDER`
     (Single Source of Truth: docs/03_vault_standard.md Appendix A).
  4. Slug-Kollision (vault-weit) → Suffix `_2`, `_3` (Vault-Standard §2).
  5. Wikilink-Validierung (E4): `related`-Targets gegen Menge aller
     geschriebenen Vault-Slugs prüfen. Unauflösbar → droppen + loggen
     nach `phase9_dropped_links.jsonl`.
  6. Datei schreiben: Frontmatter (YAML) + Leerzeile + Body.

Pro genutztem Ordner wird ein regenerierbares `_index.md` erzeugt.

Assets (WP3): ![[…]]-Embeds in den finalen Bodies werden geparst und die
referenzierten Dateien aus `input/_assets/` nach `output/_assets/` kopiert
(Namen unverändert) — IM Build, also vor der Input-Archivierung im Orchestrator.
Embed ohne Quell-Datei → `phase9_missing_assets.jsonl` (E4-analog, kein Abort);
Asset ohne referenzierenden Body → `phase9_orphan_assets.jsonl` (informativ).

Idempotent: gleicher Input-Hash → skip (ohne `--force`). Deterministische
Serialisierung → 2. Lauf byte-identisch. Existierendes Ziel:
archive-before-delete (Kopie nach `backups/phase9_vault_build_<ts>/`).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from pipeline.format_vault import format_body_safe
from pipeline.schemas import FrontmatterDraft

# Expliziter Re-Export (PEP 484 `as`-Muster) — erhält den eingeführten Importpfad
# pipeline.phase_9_vault_build.CATEGORY_TO_FOLDER für Bestands-Konsumenten
# (phase_10_reports, review, ingest) und macht mypy den Re-Export sichtbar.
from pipeline.taxonomy import CATEGORY_TO_FOLDER as CATEGORY_TO_FOLDER
from pipeline.vault_audit import audit_build_output, repair_text

log = structlog.get_logger()


# === Category → Vault-Ordner ==================================================
# Single Source: config/categories.yaml, geladen über die Taxonomie-Facade
# (pipeline.taxonomy.CATEGORY_TO_FOLDER) — kein Code-Literal, kein eigener Loader
# mehr. Re-Export hier erhält den eingeführten Importpfad
# (pipeline.phase_9_vault_build.CATEGORY_TO_FOLDER) für Bestands-Konsumenten.
# Gate B (pkm review --apply) und scripts/manage_vocab.py ergänzen neue Kategorien
# in der YAML. Nummern-Präfix ist nur Ordnername, nicht Teil des `category`-Feldes.
# Doku: docs/03_vault_standard.md App. A.

_PHASE = "phase_9_vault_build"

# Obsidian-Embed ![[target]] / ![[target|alias]] — pfad-frei nach ingest_md_download.
# Anker (#…, ^…) werden beim Auflösen abgeschnitten (Asset = Dateiname).
_EMBED_RE = re.compile(r"!\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]+)?\]\]")

# Ordner, die KEIN auto-generiertes `_index.md` bekommen (eigene Regeln,
# enthalten Templates/Standards statt Concept-Notes).
_INDEX_EXCLUDED_FOLDERS = {"00_Meta"}


@dataclass
class _Article:
    """Interner Record eines zu schreibenden Vault-Artikels."""

    stem: str  # CK_-Stem der Quell-Draft (Pairing-Schlüssel)
    data: dict[str, Any]  # validiertes Frontmatter als dict (Feld-Reihenfolge)
    body: str
    folder: str
    final_slug: str


@dataclass
class _Plan:
    """Ergebnis des Build-Plans (für dry-run und realen Lauf identisch berechnet)."""

    articles: list[_Article] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    dropped_links: list[dict[str, str]] = field(default_factory=list)
    folder_counts: Counter[str] = field(default_factory=Counter)
    collisions: list[tuple[str, str]] = field(default_factory=list)  # (base, final)
    unknown_categories: list[str] = field(default_factory=list)


# === Helpers ==================================================================


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _combined_input_hash(md_paths: list[Path]) -> str:
    """Kombinierter SHA-256 über alle Input-Drafts (`.md` + zugehörige `.body.md`)."""
    h = hashlib.sha256()
    for md in sorted(md_paths, key=lambda p: p.name):
        h.update(md.name.encode("utf-8"))
        h.update(_sha256_file(md).encode("ascii"))
        body = md.with_suffix(".body.md")
        if body.exists():
            h.update(_sha256_file(body).encode("ascii"))
    return f"sha256:{h.hexdigest()}"


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Trennt YAML-Frontmatter vom Body.

    Returns:
        (frontmatter_yaml | None, body). None wenn kein `---`-Block am Anfang.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "".join(lines[1:i])
            body = "".join(lines[i + 1 :])
            return fm, body
    return None, text


def _load_drafts(drafts_dir: Path) -> list[Path]:
    """Aktive Draft-`.md` (top-level, ohne `_hold/`, ohne `*.body.md`), sortiert."""
    return sorted(
        (p for p in drafts_dir.glob("*.md") if not p.name.endswith(".body.md")),
        key=lambda p: p.name,
    )


def _dump_frontmatter(data: dict[str, Any]) -> str:
    """Serialisiert das Frontmatter-dict deterministisch als YAML.

    Feld-Reihenfolge bleibt erhalten (kein Sortieren), Unicode bleibt lesbar,
    keine Zeilen-Umbrüche in Scalars (width hoch) für stabile, idempotente Bytes.
    """
    dumped: str = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=4096,
    )
    return dumped


def _render_article(data: dict[str, Any], body: str) -> str:
    """Baut den finalen Datei-Inhalt: Frontmatter + Leerzeile + Body (genau ein \\n am Ende)."""
    fm = _dump_frontmatter(data)
    body_norm = body.strip("\n")
    return f"---\n{fm}---\n\n{body_norm}\n"


def _finalize_body(
    body: str, repair_on_build: bool, format_on_build: bool
) -> tuple[str, bool, bool]:
    """Deterministische Finalize-Stufe am Body-Chokepoint, bevor nach output/ geschrieben wird.

    Reihenfolge (Architect-Entscheidung): **repair → format**.

    1. S1/G1 — Safe-Tier-`repair_text` (entbolden · Junk-Heading · Setext · PUA ·
       unclosed-Fence · Fence-Tag high-conf). Review-Tier (url-Mash, turn…-Token) bleibt
       außen vor.
    2. S2/G2 — safe-tier-`format_body_safe` (mdformat, deterministisch/idempotent):
       nur übernommen, wenn kein Schutzbereich berührt wird und Code-Fences + Tabellen
       byte-identisch bleiben.

    Beides verlustfrei + idempotent. Wirkt NUR auf den Build-Body, nie auf die
    Quell-Drafts oder den Live-Vault.

    Returns:
        ``(body, was_repaired, was_formatted)``.
    """
    was_repaired = False
    if repair_on_build:
        body, actions = repair_text(body)
        was_repaired = bool(actions)
    was_formatted = False
    if format_on_build:
        body, was_formatted = format_body_safe(body)
    return body, was_repaired, was_formatted


def _render_index(folder: str, articles: list[_Article]) -> str:
    """Erzeugt regenerierbaren `_index.md`-Inhalt für einen Ordner.

    Rein inhalts-abgeleitet (keine Wall-Clock-Zeit) → idempotent / byte-identisch.
    """
    arts = sorted(articles, key=lambda a: a.final_slug)
    tag_counter: Counter[str] = Counter()
    updates: list[str] = []
    for a in arts:
        tag_counter.update(a.data.get("tags") or [])
        if a.data.get("updated"):
            updates.append(str(a.data["updated"]))
    last_update = max(updates) if updates else "—"

    lines = [
        "---",
        f"title: 'Index: {folder}'",
        "type: index",
        f"folder: {folder}",
        f"article_count: {len(arts)}",
        "---",
        "",
        f"# Index — {folder}",
        "",
        f"**Artikel:** {len(arts)} · **Letzte Aktualisierung:** {last_update}",
        "",
        "## Artikel",
        "",
        "| Titel | Slug | Status |",
        "|---|---|---|",
    ]
    for a in arts:
        title = str(a.data.get("title", "")).replace("|", "\\|")
        lines.append(f"| {title} | `{a.final_slug}` | {a.data.get('status', '')} |")
    lines += ["", "## Tag-Häufigkeiten", ""]
    if tag_counter:
        for tag, n in sorted(tag_counter.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{tag}`: {n}")
    else:
        lines.append("- (keine Tags)")
    return "\n".join(lines) + "\n"


def _write_indexes(
    articles: list[_Article], vault_dir: Path, archive_root: Path, dry_run: bool
) -> None:
    """Schreibt `_index.md` pro genutztem Ordner (außer ausgeschlossene Sonderordner).

    Der Sonderordner `unsortiert` bekommt IMMER einen Index — auch leer (G8): er ist ein
    permanenter Auffang-Bucket, dessen (Nicht-)Befüllung sichtbar bleiben soll.
    """
    by_folder: dict[str, list[_Article]] = defaultdict(list)
    for art in articles:
        by_folder[art.folder].append(art)
    unsorted_folder = CATEGORY_TO_FOLDER["unsortiert"]
    if unsorted_folder not in _INDEX_EXCLUDED_FOLDERS:
        by_folder.setdefault(unsorted_folder, [])
    for folder, arts in by_folder.items():
        idx_path = vault_dir / folder / "_index.md"
        if folder in _INDEX_EXCLUDED_FOLDERS:
            # 00_Meta enthält Templates/Standards, keine Concept-Notes → kein Index.
            # Stale Index aus früherem Lauf entfernen (archive-before-delete).
            if idx_path.exists():
                _archive_existing(idx_path, archive_root)
                idx_path.unlink()
            continue
        idx_content = _render_index(folder, arts)
        _write_if_changed(idx_path, idx_content, archive_root, dry_run)


def _archive_existing(path: Path, archive_root: Path) -> None:
    """Kopiert eine zu überschreibende Datei nach archive_root (archive-before-delete)."""
    dest = archive_root / path.parent.name / path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def _write_if_changed(path: Path, content: str, archive_root: Path, dry_run: bool) -> str:
    """Schreibt content nach path. Existierendes Ziel → archive-before-delete.

    Returns: 'written' | 'overwritten' | 'unchanged'.
    """
    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return "unchanged"
        if not dry_run:
            _archive_existing(path, archive_root)
            path.write_text(content, encoding="utf-8")
        return "overwritten"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return "written"


# === Assets (WP3) =============================================================


def _extract_embed_targets(body: str) -> list[str]:
    """Liest die ![[…]]-Embed-Targets (Asset-Dateinamen) aus einem Body, in Reihenfolge."""
    return [m.group(1).strip() for m in _EMBED_RE.finditer(body) if m.group(1).strip()]


def _copy_asset_if_changed(src: Path, dst: Path, archive_root: Path, dry_run: bool) -> str:
    """Kopiert eine Asset-Datei binär nach dst. Existierendes Ziel → archive-before-delete.

    Returns: 'copied' | 'overwritten' | 'unchanged'.
    """
    if dst.exists():
        if dst.read_bytes() == src.read_bytes():
            return "unchanged"
        if not dry_run:
            _archive_existing(dst, archive_root)
            shutil.copy2(src, dst)
        return "overwritten"
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return "copied"


@dataclass
class _AssetPlan:
    """Ergebnis der Asset-Auflösung (gleich berechnet für dry-run und realen Lauf)."""

    needed: dict[str, list[str]] = field(default_factory=dict)  # asset_name → [source_slugs]
    missing: list[dict[str, str]] = field(default_factory=list)  # Embed ohne Quell-Datei
    orphans: list[str] = field(default_factory=list)  # Asset in src ohne referenzierenden Body


def _build_asset_plan(articles: list[_Article], assets_src: Path | None) -> _AssetPlan:
    """Sammelt benötigte Assets aus den finalen Bodies und gleicht gegen ``assets_src`` ab.

    Args:
        articles: gebaute Artikel (deren Bodies wörtlich in den Vault gehen).
        assets_src: Quell-Asset-Ordner (``input/_assets/``) oder None.

    Returns:
        ``_AssetPlan`` mit needed (asset → referenzierende Slugs), missing (Embed
        zeigt auf nicht vorhandenes Asset, E4-analog) und orphans (Asset-Datei in
        src, die kein Body referenziert). ``assets_src=None`` → Feature aus, leerer Plan.
    """
    plan = _AssetPlan()
    if assets_src is None:
        return plan
    for art in articles:
        for target in _extract_embed_targets(art.body):
            plan.needed.setdefault(target, []).append(art.final_slug)

    present = (
        {p.name for p in assets_src.iterdir() if p.is_file()}
        if assets_src and assets_src.exists()
        else set()
    )
    for name in sorted(plan.needed):
        if name not in present:
            for slug in plan.needed[name]:
                plan.missing.append(
                    {"source_slug": slug, "asset": name, "reason": "asset_not_found"}
                )
                log.warning("phase9_missing_asset", source=slug, asset=name)
    plan.orphans = sorted(present - set(plan.needed))
    return plan


def _copy_needed_assets(
    asset_plan: _AssetPlan,
    assets_src: Path | None,
    assets_dst: Path | None,
    archive_root: Path,
    dry_run: bool,
) -> Counter[str]:
    """Kopiert die in ``asset_plan.needed`` referenzierten, vorhandenen Assets nach assets_dst.

    Returns: Counter mit 'copied'/'overwritten'/'unchanged'. Leerer Counter, wenn
    Asset-Handling aus ist (assets_src/dst None).
    """
    stats: Counter[str] = Counter()
    if assets_src is None or assets_dst is None:
        return stats
    for name in sorted(asset_plan.needed):
        src = assets_src / name
        if src.exists():
            stats[_copy_asset_if_changed(src, assets_dst / name, archive_root, dry_run)] += 1
    return stats


# === Plan-Aufbau ==============================================================


def _build_plan(drafts_dir: Path) -> _Plan:
    """Liest alle Drafts, validiert, löst Ordner + Slug-Kollisionen, dropt dangling Links."""
    plan = _Plan()
    used_slugs: set[str] = set()

    # Pass 1: parsen, validieren, Ordner + finalen Slug bestimmen
    for md in _load_drafts(drafts_dir):
        stem = md.name[: -len(".md")]
        fm_yaml, embedded_body = _split_frontmatter(md.read_text(encoding="utf-8"))
        if fm_yaml is None:
            plan.errors.append({"stem": stem, "reason": "kein_frontmatter_block"})
            log.error("phase9_frontmatter_missing", stem=stem)
            continue
        try:
            raw = yaml.safe_load(fm_yaml) or {}
            model = FrontmatterDraft.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            plan.errors.append({"stem": stem, "reason": str(exc)[:500]})
            log.error("phase9_validation_failed", stem=stem, error=str(exc)[:200])
            continue

        body_path = md.with_suffix(".body.md")
        body = body_path.read_text(encoding="utf-8") if body_path.exists() else embedded_body

        category = model.category
        folder = CATEGORY_TO_FOLDER.get(category)
        if folder is None:
            folder = CATEGORY_TO_FOLDER["unsortiert"]
            plan.unknown_categories.append(category)
            log.warning("phase9_unknown_category", stem=stem, category=category, routed_to=folder)

        base_slug = model.slug
        final_slug = base_slug
        i = 2
        while final_slug in used_slugs:
            final_slug = f"{base_slug}_{i}"
            i += 1
        if final_slug != base_slug:
            plan.collisions.append((base_slug, final_slug))
        used_slugs.add(final_slug)

        data = model.model_dump()
        data["slug"] = final_slug  # Slug = Dateiname (Vault-Standard §5)

        plan.articles.append(
            _Article(stem=stem, data=data, body=body, folder=folder, final_slug=final_slug)
        )
        plan.folder_counts[folder] += 1

    # Pass 2: Wikilink-Validierung (E4) gegen Menge aller finalen Slugs
    for art in plan.articles:
        related = art.data.get("related") or []
        kept = []
        for target in related:
            if target in used_slugs:
                kept.append(target)
            else:
                plan.dropped_links.append(
                    {
                        "source_slug": art.final_slug,
                        "dropped_target": target,
                        "reason": "unresolved_wikilink",
                    }
                )
                log.warning("phase9_dropped_link", source=art.final_slug, target=target)
        art.data["related"] = kept

    return plan


def _write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# === Entry-Point ==============================================================


def run_phase_9(
    drafts_dir: Path,
    vault_dir: Path,
    pipeline_output: Path,
    backups_dir: Path,
    *,
    assets_src: Path | None = None,
    assets_dst: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    repair_on_build: bool = True,
    format_on_build: bool = True,
    audit_on_build: bool = True,
    pipeline_version: str = "0.1.0",
) -> dict[str, Any]:
    """Baut den Vault aus den aktiven Drafts.

    Args:
        drafts_dir: `drafts`.
        vault_dir: `output`.
        pipeline_output: Ziel für Error-/Drop-Logs + Meta.
        backups_dir: Wurzel für archive-before-delete.
        assets_src: Quell-Asset-Ordner (`input/_assets/`) für ![[…]]-Embeds; None → kein Copy.
        assets_dst: Ziel-Asset-Ordner (`output/_assets/`); None → kein Copy.
        force: Cache (Input-Hash) ignorieren und neu bauen.
        dry_run: Plan berechnen, nichts schreiben.
        repair_on_build: Safe-Tier-`repair_text` (deterministisch/verlustfrei/idempotent)
            auf jeden Body anwenden, bevor er nach output/ geschrieben wird (S1, G1 —
            single-pass für neue Files). Default an; nur output/ betroffen, nie der
            Live-Vault. Abschaltbar via `vault.repair_on_build` in der Config.
        format_on_build: Safe-tier-`format_body_safe` (mdformat) NACH dem Repair anwenden
            (S2, G2). Nur übernommen, wenn kein Schutzbereich berührt wird und Code-Fences
            + Tabellen byte-identisch bleiben. Default an; nur output/, nie der Live-Vault.
            Abschaltbar via `vault.format_on_build` in der Config.
        audit_on_build: read-only Audit-Pass über das gebaute output/ NACH dem Build
            (S3, G4) — verifiziert Safe-Tier-Rest (erwartet 0), Frontmatter-Parse-Errors
            und dangling Wikilinks. Befund landet als `audit_*`-Felder im Summary.
            Mutiert NICHTS. Default an; abschaltbar via `vault.audit_on_build`.
        pipeline_version: für Meta-Datei.

    Returns:
        Summary-dict mit Counts (articles, errors, dropped_links, folders, collisions,
        assets_copied, missing_assets, orphan_assets, skipped).
    """
    start = time.monotonic()
    md_paths = _load_drafts(drafts_dir)
    input_hash = _combined_input_hash(md_paths)
    meta_path = pipeline_output / f".{_PHASE}.meta.json"

    # Idempotenz: gleicher Input-Hash + Meta vorhanden → skip (außer --force/--dry-run)
    if not force and not dry_run and meta_path.exists():
        try:
            cached = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            cached = {}
        if cached.get("input_hash") == input_hash:
            log.info("phase9_skip_cached", input_hash=input_hash)
            cached_summary: dict[str, Any] = dict(cached.get("summary", {}))
            cached_summary["skipped"] = True
            return cached_summary

    plan = _build_plan(drafts_dir)
    asset_plan = _build_asset_plan(plan.articles, assets_src)
    now_iso = datetime.now(tz=UTC).isoformat()
    run_ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    archive_root = backups_dir / f"{_PHASE}_{run_ts}"

    write_stats: Counter[str] = Counter()
    asset_stats: Counter[str] = Counter()
    audit_counts: dict[str, int] = {}
    repaired_files = 0
    formatted_files = 0
    if not dry_run:
        for art in plan.articles:
            target = vault_dir / art.folder / f"{art.final_slug}.md"
            body, was_repaired, was_formatted = _finalize_body(
                art.body, repair_on_build, format_on_build
            )
            repaired_files += int(was_repaired)
            formatted_files += int(was_formatted)
            content = _render_article(art.data, body)
            write_stats[_write_if_changed(target, content, archive_root, dry_run)] += 1

        _write_indexes(plan.articles, vault_dir, archive_root, dry_run)

        # Asset-Copy (vor der Input-Archivierung im Orchestrator) — Namen unverändert.
        asset_stats = _copy_needed_assets(asset_plan, assets_src, assets_dst, archive_root, dry_run)

        # Logs
        _write_jsonl(pipeline_output / "phase9_errors.jsonl", plan.errors)
        _write_jsonl(pipeline_output / "phase9_dropped_links.jsonl", plan.dropped_links)
        _write_jsonl(pipeline_output / "phase9_missing_assets.jsonl", asset_plan.missing)
        _write_jsonl(
            pipeline_output / "phase9_orphan_assets.jsonl",
            [{"asset": a, "reason": "unreferenced_in_built_bodies"} for a in asset_plan.orphans],
        )

        # S3 (G4): read-only Audit-Pass über das frisch gebaute output/ (nach repair+format).
        # Verifiziert den sauberen Build (Safe-Tier-Rest erwartet 0); mutiert nichts.
        if audit_on_build:
            audit_counts = audit_build_output(vault_dir)

    summary: dict[str, Any] = {
        "articles": len(plan.articles),
        "errors": len(plan.errors),
        "dropped_links": len(plan.dropped_links),
        "dropped_links_drafts": len({d["source_slug"] for d in plan.dropped_links}),
        "folders_used": len(plan.folder_counts),
        "collisions": len(plan.collisions),
        "unknown_categories": sorted(set(plan.unknown_categories)),
        "folder_counts": dict(sorted(plan.folder_counts.items())),
        "repaired_files": repaired_files,
        "formatted_files": formatted_files,
        "audit_on_build": audit_on_build,
        "audit_safe_tier_rest": audit_counts.get("safe_tier_rest", 0),
        "audit_parse_errors": audit_counts.get("parse_errors", 0),
        "audit_dangling": audit_counts.get("dangling", 0),
        "assets_needed": len(asset_plan.needed),
        "assets_copied": asset_stats["copied"] + asset_stats["overwritten"],
        "missing_assets": len(asset_plan.missing),
        "orphan_assets": len(asset_plan.orphans),
        "duration_seconds": round(time.monotonic() - start, 2),
        "skipped": False,
    }

    if not dry_run:
        meta = {
            "phase": _PHASE,
            "input_hash": input_hash,
            "created_at": now_iso,
            "duration_seconds": summary["duration_seconds"],
            "pipeline_version": pipeline_version,
            "write_stats": dict(write_stats),
            "asset_stats": dict(asset_stats),
            "summary": summary,
        }
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info(
        "phase9_done",
        **{
            k: summary[k]
            for k in ("articles", "errors", "dropped_links", "assets_copied", "missing_assets")
        },
    )
    return summary
