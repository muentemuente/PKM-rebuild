"""WP3c-5 — Draft → Live-Vault-Promotion unter D4.

Schließt den restructure-Loop: ein vom Owner auf ``review_status: human_reviewed``
(oder ``verified``) gesetzter Draft wird in den Live-Vault promotiert — korrekter
Ordner (Kategorie-SSoT), finalisiertes Frontmatter, mandatorische Index-Regen, alles
unter der D4-Mechanik (Snapshot → Write → Verify → Index → Reconcile; Rollback bei
Fehler).

Invarianten (Locked Design):

* **Promotion-Gate:** nur ``human_reviewed``/``verified`` promotierbar. ``ai_drafted``
  → hartes Abbrechen, **kein Write** (Bulk-``draft→stable`` bleibt verboten).
* **Ziel-Ordner** aus ``category`` via :func:`pipeline.taxonomy.load_category_to_folder`
  (SSoT) — keine Streu-Logik.
* **Update-Modell:** ein restructure-Draft re-strukturiert ein **bestehendes** Vault-File
  (Slug stammt daher) → der Ziel-Pfad existiert i.d.R. Das ist eine **Kollision** und
  wird **nie blind überschrieben** — :func:`plan_promotion` meldet sie mit Diff; die
  Auflösung (``replace``/``suffix``/``abort``) ist eine Owner-Entscheidung.
* **Provenance erhalten:** ``provenance``/``merged_from``/``sources_*`` sowie die
  WP3c-4-Felder ``type_source``/``restructure_action``/``prompt_version`` aus dem Draft.
* **status** wird nie automatisch ``stable`` (Hard Constraint): Promotion setzt
  ``status: review``.
* **Index-Regen mandatory** nach jedem Write (betroffener Ordner, Generator aus G8).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from pipeline import _paths, taxonomy
from pipeline.driver import restore_snapshot, snapshot_vault
from pipeline.phase_9_vault_build import _INDEX_EXCLUDED_FOLDERS, _Article, _render_index
from pipeline.schemas import FrontmatterDraft
from pipeline.vault_audit import parse_frontmatter, split_frontmatter

#: review_status-Werte, die eine Promotion erlauben.
PROMOTABLE_REVIEW = frozenset({"human_reviewed", "verified"})
#: Felder, die — falls im Draft vorhanden — beim Update über das Bestands-Frontmatter
#: gelegt werden (Content-/Restructure-Felder; Taxonomie/Verlinkung bleibt vom Bestand).
_DRAFT_OVERLAY_FIELDS = (
    "title",
    "summary",
    "type",
    "type_source",
    "restructure_action",
    "prompt_version",
    "confidence",
    "review_status",
    "provenance",
    "confidence_fallback",
)


class PromotionError(RuntimeError):
    """Promotion abgebrochen (Gate verletzt / unvollständig) — kein Write."""


@dataclass(frozen=True)
class PromotionPlan:
    """Read-only Plan einer Promotion (Dry-run-Ergebnis; kein Write)."""

    draft_path: Path
    slug: str
    category: str
    folder: str
    target_path: Path
    collision: bool
    is_update: bool
    final_text: str
    diff: str
    doc_count_delta: int


@dataclass
class PromotionReport:
    """Ergebnis eines ausgeführten (D4) Promotions-Laufs."""

    target_path: Path
    snapshot: Path
    folder: str
    index_article_count: int
    archived_draft: Path
    resolution: str


# === Frontmatter-Finalisierung ================================================


def _split_draft(draft_path: Path) -> tuple[dict[str, Any], str]:
    """Draft → (Frontmatter-dict, Body). Fehlt das Frontmatter → PromotionError."""
    fm_text, body, _ = split_frontmatter(draft_path.read_text(encoding="utf-8"))
    if not fm_text:
        raise PromotionError(f"Draft ohne Frontmatter: {draft_path}")
    data, err = parse_frontmatter(fm_text)
    if data is None:
        raise PromotionError(f"Draft-Frontmatter nicht parsebar ({err}): {draft_path}")
    return data, body


def _finalize_frontmatter(
    draft_fm: dict[str, Any],
    existing_fm: dict[str, Any] | None,
    today: str,
) -> dict[str, Any]:
    """Baut das finale Vault-Frontmatter (Update-Merge bzw. vollständiger Draft).

    Bei Update (``existing_fm`` vorhanden): Bestands-Frontmatter ist die Basis
    (Taxonomie/Verlinkung/Quellen bleiben), die Content-/Restructure-Felder aus dem
    Draft werden überlagert. Bei Neu-Anlage ist der Draft selbst die Basis und muss
    vollständig sein (Pydantic-Validierung erzwingt das).
    """
    fm: dict[str, Any] = dict(existing_fm) if existing_fm else dict(draft_fm)
    if existing_fm:
        for key in _DRAFT_OVERLAY_FIELDS:
            if key in draft_fm and draft_fm[key] is not None:
                fm[key] = draft_fm[key]

    # Finalisierung (in beiden Pfaden): Promotion-Stempel, nie auto-stable.
    fm["status"] = "review"
    fm["updated"] = today
    prov = fm.get("provenance")
    generated = prov.get("generated_at") if isinstance(prov, dict) else None
    fm["last_synthesized"] = str(generated)[:10] if generated else today
    fm.setdefault("created", today)
    fm.setdefault("doc_version", "0.1.0")
    return fm


def _validate_complete(fm: dict[str, Any], slug: str) -> None:
    """Erzwingt ein vollständiges Vault-Frontmatter via Pydantic-SSoT (FrontmatterDraft)."""
    try:
        FrontmatterDraft.model_validate(fm)
    except Exception as exc:  # Pydantic ValidationError → klare Promotion-Meldung
        raise PromotionError(
            f"Frontmatter unvollständig/ungültig für '{slug}' — der human_reviewed "
            f"Draft muss vault-fertig sein (Pflichtfelder/Enums). Details: {str(exc)[:300]}"
        ) from exc


def _render_file(frontmatter: dict[str, Any], body: str) -> str:
    """Frontmatter (YAML, stabile Key-Reihenfolge) + Body → Datei-String."""
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"---\n{fm_yaml}---\n\n{body.strip()}\n"


def _free_suffix_path(target: Path) -> Path:
    """Erste freie ``slug_N.md``-Variante (Kollisions-Auflösung ``suffix``)."""
    stem, suffix = target.stem, target.suffix
    for n in range(2, 1000):
        cand = target.with_name(f"{stem}_{n}{suffix}")
        if not cand.exists():
            return cand
    raise PromotionError(f"Zu viele Slug-Kollisionen für {target.name}")


# === Plan (read-only) =========================================================


def plan_promotion(
    draft_path: Path,
    vault_dir: Path,
    *,
    on_collision: str = "abort",
    today: str | None = None,
) -> PromotionPlan:
    """Berechnet den Promotions-Plan (kein Write). Raises :class:`PromotionError`.

    Args:
        draft_path: Quell-Draft (review_status human_reviewed/verified).
        vault_dir: Ziel-Vault (Live oder tmp/Test).
        on_collision: ``abort`` (Default, meldet nur) | ``replace`` | ``suffix``.
        today: ISO-Datum (injizierbar); ``None`` → heute (UTC).
    """
    if on_collision not in ("abort", "replace", "suffix"):
        raise PromotionError(f"unbekannte on_collision-Option: {on_collision!r}")
    day = today if today is not None else datetime.now(tz=UTC).strftime("%Y-%m-%d")

    draft_fm, body = _split_draft(draft_path)

    # Gate: nur human_reviewed/verified.
    review = draft_fm.get("review_status")
    if review not in PROMOTABLE_REVIEW:
        raise PromotionError(
            f"Promotion-Gate: review_status={review!r} (nur "
            f"{sorted(PROMOTABLE_REVIEW)} promotierbar). Kein Write."
        )

    slug = str(draft_fm.get("slug") or draft_path.stem)

    # Ziel-Ordner aus category (SSoT); Catch-all unsortiert bei unbekannter Kategorie.
    cat_to_folder = taxonomy.load_category_to_folder()
    category = draft_fm.get("category")

    # natürlicher Ziel-Pfad (vor Kollisions-Auflösung): aus category bzw. Bestand.
    natural_folder = _folder_for(category, cat_to_folder) if category else None
    existing_path = (
        _find_existing(vault_dir, slug)
        if natural_folder is None
        else (vault_dir / natural_folder / f"{slug}.md")
    )
    existing_fm: dict[str, Any] | None = None
    if existing_path is not None and existing_path.exists():
        ex_fm_text, _, _ = split_frontmatter(existing_path.read_text(encoding="utf-8"))
        existing_fm, _ = parse_frontmatter(ex_fm_text) if ex_fm_text else (None, None)
        if category is None:
            category = existing_fm.get("category") if existing_fm else None

    if not category:
        raise PromotionError(
            f"category fehlt — weder im Draft '{slug}' noch im Bestands-File. "
            "Der human_reviewed Draft muss eine category tragen (Ziel-Ordner-SSoT)."
        )
    folder = _folder_for(category, cat_to_folder)

    final_fm = _finalize_frontmatter(draft_fm, existing_fm, day)
    final_fm["category"] = category
    final_fm["slug"] = slug
    _validate_complete(final_fm, slug)
    final_text = _render_file(final_fm, body)

    natural_target = vault_dir / folder / f"{slug}.md"
    collision = natural_target.exists()
    is_update = collision

    if collision and on_collision == "suffix":
        target = _free_suffix_path(natural_target)
        collision = False
        is_update = False
    else:
        target = natural_target

    diff = ""
    if natural_target.exists():
        before = natural_target.read_text(encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                final_text.splitlines(keepends=True),
                fromfile=f"a/{slug}.md (Bestand)",
                tofile=f"b/{slug}.md (promotet)",
            )
        )

    return PromotionPlan(
        draft_path=draft_path,
        slug=slug,
        category=str(category),
        folder=folder,
        target_path=target,
        collision=collision and on_collision == "abort",
        is_update=is_update,
        final_text=final_text,
        diff=diff,
        doc_count_delta=0 if is_update else 1,
    )


def _folder_for(category: str, cat_to_folder: dict[str, str]) -> str:
    """category → Ordner (SSoT). Unbekannt → Catch-all ``unsortiert`` (DoD, Phase 9)."""
    return cat_to_folder.get(category) or cat_to_folder["unsortiert"]


def _find_existing(vault_dir: Path, slug: str) -> Path | None:
    """Sucht ein bestehendes ``<slug>.md`` vault-weit (für category-losen Draft)."""
    hits = [p for p in vault_dir.rglob(f"{slug}.md") if p.name != "_index.md"]
    return hits[0] if hits else None


# === Ausführung (D4) ==========================================================


def execute_promotion(
    plan: PromotionPlan,
    vault_dir: Path,
    *,
    archive_dir: Path | None = None,
    backups_dir: Path | None = None,
) -> PromotionReport:
    """Führt die Promotion unter D4 aus (Snapshot → Write → Verify → Index → Archiv).

    **Owner-Gate-pflichtig** (Live-Write). Bei Kollision mit ``abort`` wird **nicht**
    geschrieben. Bei jedem Fehler nach dem Snapshot: vollständiger Rollback.
    """
    if plan.collision:
        raise PromotionError(
            f"Kollision bei {plan.target_path.name}: kein Blind-Overwrite. "
            "Auflösung wählen (on_collision=replace|suffix) oder abbrechen."
        )
    archive = archive_dir if archive_dir is not None else _paths.ARCHIVE
    snapshot = snapshot_vault(vault_dir, backups_dir)
    try:
        plan.target_path.parent.mkdir(parents=True, exist_ok=True)
        plan.target_path.write_text(plan.final_text, encoding="utf-8")
        _verify_written(plan.target_path)
        index_count = _regenerate_folder_index(vault_dir, plan.folder)
        archived = _archive_draft(plan.draft_path, archive)
    except Exception:
        restore_snapshot(snapshot, vault_dir)
        raise
    return PromotionReport(
        target_path=plan.target_path,
        snapshot=snapshot,
        folder=plan.folder,
        index_article_count=index_count,
        archived_draft=archived,
        resolution="update" if plan.is_update else "new",
    )


def _verify_written(path: Path) -> None:
    """Verify-Schritt: geschriebenes File parst, Frontmatter vollständig, Body da."""
    fm_text, body, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    if not fm_text or not body.strip():
        raise PromotionError(f"Verify fehlgeschlagen (FM/Body leer): {path}")
    data, err = parse_frontmatter(fm_text)
    if data is None:
        raise PromotionError(f"Verify fehlgeschlagen (FM-Parse {err}): {path}")
    FrontmatterDraft.model_validate(data)


def _regenerate_folder_index(vault_dir: Path, folder: str) -> int:
    """Regeneriert ``<folder>/_index.md`` (G8-Generator). Returnt Artikel-Anzahl."""
    folder_dir = vault_dir / folder
    if folder in _INDEX_EXCLUDED_FOLDERS:
        return 0
    articles: list[_Article] = []
    for p in sorted(folder_dir.glob("*.md")):
        if p.name == "_index.md":
            continue
        fm_text, body, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        data, _ = parse_frontmatter(fm_text) if fm_text else (None, None)
        if not data:
            continue
        s = str(data.get("slug") or p.stem)
        articles.append(_Article(stem=s, data=data, body=body, folder=folder, final_slug=s))
    (folder_dir / "_index.md").write_text(_render_index(folder, articles), encoding="utf-8")
    return len(articles)


def _archive_draft(draft_path: Path, archive_dir: Path) -> Path:
    """Verschiebt den promoteten Draft nach ``archive_dir`` (Provenance-Spur, kein Delete)."""
    dest_dir = archive_dir / "promoted_drafts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / draft_path.name
    if dest.exists():
        dest = dest.with_name(
            f"{draft_path.stem}_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}{draft_path.suffix}"
        )
    draft_path.rename(dest)
    return dest
