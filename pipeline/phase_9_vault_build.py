"""Phase 9: Vault-Aufbau.

Baut aus den aktiven Drafts (`03_drafts/*.md`, ohne `_hold/`, ohne `*.body.md`)
den finalen Obsidian-Vault unter `data/04_vault/<NN_Cluster>/<slug>.md`.

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

Idempotent: gleicher Input-Hash → skip (ohne `--force`). Deterministische
Serialisierung → 2. Lauf byte-identisch. Existierendes Ziel:
archive-before-delete (Kopie nach `backups/phase9_vault_build_<ts>/`).
"""

from __future__ import annotations

import hashlib
import json
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

from pipeline.schemas import FrontmatterDraft

log = structlog.get_logger()

# === Category → Vault-Ordner ==================================================
# Single Source of Truth: docs/03_vault_standard.md, Appendix A
# ("Kanonische `category`-Werte", 18 Werte). Nummern-Präfix ist nur Ordnername,
# nicht Teil des `category`-Feldes. NICHT hier divergieren lassen — bei Änderung
# der kanonischen Liste hier UND in der Doku anpassen.
CATEGORY_TO_FOLDER: dict[str, str] = {
    "meta": "00_Meta",
    "grundlagen": "01_Grundlagen",
    "webentwicklung": "02_Webentwicklung",
    "betriebssysteme": "03_Betriebssysteme",
    "protokolle-und-standards": "04_Protokolle-und-Standards",
    "dateitypen-und-konfiguration": "05_Dateitypen-und-Konfiguration",
    "methoden-und-prozesse": "06_Methoden-und-Prozesse",
    "best-practices": "07_Best-Practices",
    "cheatsheets": "08_Cheatsheets",
    "ki-und-semantische-systeme": "09_KI-und-Semantische-Systeme",
    "datenarchitektur-und-datenbanken": "10_Datenarchitektur-und-Datenbanken",
    "dokumentenverarbeitung-und-extraktion": "11_Dokumentenverarbeitung-und-Extraktion",
    "wissensmodellierung-und-knowledge-graphs": "12_Wissensmodellierung-und-Knowledge-Graphs",
    "visualisierung-reporting-und-design-systeme": "13_Visualisierung-Reporting-und-Design-Systeme",
    "automatisierung-scripting-und-pipelines": "14_Automatisierung-Scripting-und-Pipelines",
    "gedanken": "15_Gedanken",
    "kunst-kultur": "16_Kunst-Kultur",
    "unsortiert": "unsortiert",
}

_PHASE = "phase_9_vault_build"

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
    force: bool = False,
    dry_run: bool = False,
    pipeline_version: str = "0.1.0",
) -> dict[str, Any]:
    """Baut den Vault aus den aktiven Drafts.

    Args:
        drafts_dir: `data/03_drafts`.
        vault_dir: `data/04_vault`.
        pipeline_output: Ziel für Error-/Drop-Logs + Meta.
        backups_dir: Wurzel für archive-before-delete.
        force: Cache (Input-Hash) ignorieren und neu bauen.
        dry_run: Plan berechnen, nichts schreiben.
        pipeline_version: für Meta-Datei.

    Returns:
        Summary-dict mit Counts (articles, errors, dropped_links, folders, collisions, skipped).
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
    now_iso = datetime.now(tz=UTC).isoformat()
    run_ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    archive_root = backups_dir / f"{_PHASE}_{run_ts}"

    write_stats: Counter[str] = Counter()
    if not dry_run:
        for art in plan.articles:
            target = vault_dir / art.folder / f"{art.final_slug}.md"
            content = _render_article(art.data, art.body)
            write_stats[_write_if_changed(target, content, archive_root, dry_run)] += 1

        # _index.md pro genutztem Ordner (außer ausgeschlossene Sonderordner)
        by_folder: dict[str, list[_Article]] = defaultdict(list)
        for art in plan.articles:
            by_folder[art.folder].append(art)
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

        # Logs
        _write_jsonl(pipeline_output / "phase9_errors.jsonl", plan.errors)
        _write_jsonl(pipeline_output / "phase9_dropped_links.jsonl", plan.dropped_links)

    summary: dict[str, Any] = {
        "articles": len(plan.articles),
        "errors": len(plan.errors),
        "dropped_links": len(plan.dropped_links),
        "dropped_links_drafts": len({d["source_slug"] for d in plan.dropped_links}),
        "folders_used": len(plan.folder_counts),
        "collisions": len(plan.collisions),
        "unknown_categories": sorted(set(plan.unknown_categories)),
        "folder_counts": dict(sorted(plan.folder_counts.items())),
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
            "summary": summary,
        }
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info("phase9_done", **{k: summary[k] for k in ("articles", "errors", "dropped_links")})
    return summary
