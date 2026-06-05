#!/usr/bin/env python3
"""
pkm_triage.py — End-to-End-Triage über Korpus, Drafts, Vault.

Vergleicht in einem einzigen Lauf:
  - 01_corpus_input/       Original-Markdown (Source-of-Truth)
  - 03_drafts/             LLM-generierte Drafts (CK_<slug>.{md,body.md,frontmatter.json})
  - 04_vault/              finaler Obsidian-Vault

Liefert pro Korpus-Slug eine eindeutige Action:

  IN_VAULT          — bereits im Vault, fertig
  READY_TO_MIGRATE  — Draft sauber, kann übernommen werden
  POSTPROCESS       — Draft hat deterministisch fixbare Issues (category, slug-Umlaute, doc_role)
  RERUN_LM          — Draft hat semantische/strukturelle Probleme → LM-Studio neu
  FRESH_RUN         — kein Draft vorhanden, Korpus-File muss erstmalig durchlaufen

Plus separate Aufstellung:
  ORPHAN_DRAFT      — Draft existiert, aber kein Korpus-File dazu (Korpus wurde umbenannt?)
  EXCLUDED          — Korpus-File in _excluded/

Outputs (alle in data/02_pipeline_output/triage/):
  triage_report.md            Master-Übersicht
  triage.jsonl                machine-readable, eine Zeile pro Korpus-Slug
  actions/
    ready_to_migrate.txt
    postprocess.txt
    rerun_lm.txt
    fresh_run.txt
    orphan_draft.txt
  rerun_batches/              10er-Batches für LM-Studio (Re-Run existierender Drafts)
    batch_001.md
    batch_002.md
    ...
  fresh_run_batches/          10er-Batches für Korpus-Files ohne Draft
    batch_001.md
    ...

Read-only auf Korpus, Drafts und Vault. Modifiziert nichts.
Idempotent (mehrmaliger Lauf identische Outputs).

Aufruf:
  python3 scripts/pkm_triage.py

Exit-Codes:
  0 = Triage erfolgreich
  2 = Setup-Fehler
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("FEHLER: pyyaml fehlt. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._pkm_common import (
    ALLOWED_CATEGORIES,
    ALLOWED_CONFIDENCE,
    ALLOWED_DOC_ROLE,
    ALLOWED_REVIEW,
    ALLOWED_STATUS,
    ALLOWED_TYPE,
    CRITICAL_DIFF_FIELDS,
    MIN_BODY_WORDS,
    MINOR_DIFF_FIELDS,
    REQUIRED_FIELDS,
    SLUG_RE,
    UMLAUT_CHARS,
    compute_body_metrics,
    draft_stem_to_slug,
    normalize_to_slug,
    parse_json_file,
    parse_yaml_text,
    split_md,
)

# === Pfade ===
DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
CORPUS_DIR = DATA_ROOT / "01_corpus_input"
DRAFTS_DIR = DATA_ROOT / "03_drafts"
VAULT_DIR = DATA_ROOT / "04_vault"
OUTPUT_DIR = DATA_ROOT / "02_pipeline_output" / "triage"

# Batch-Größe für Re-Run-Listen
BATCH_SIZE = 10

# Fixable durch Post-Processing-Skript
FIXABLE_ISSUE_PREFIXES = (
    "unknown_category:", "invalid_doc_role:",
    "umlaut_in_slug:", "invalid_slug_format:",
)

# Draft-File-Variants (Reihenfolge wichtig: längere Suffixe zuerst)
DRAFT_VARIANTS = [
    ("body_meta",   ".body.meta.json"),
    ("fm_meta",     ".frontmatter.meta.json"),
    ("frontmatter", ".frontmatter.json"),
    ("body_md",     ".body.md"),
    ("md",          ".md"),
]


# Slug-Normalisierung (normalize_to_slug, draft_stem_to_slug) → scripts/_pkm_common.py


# === Discover ===

def discover_corpus() -> dict[str, Path]:
    """Slug → Korpus-Pfad. Top-Level + alle Subordner (außer _excluded/)."""
    result: dict[str, Path] = {}
    for p in CORPUS_DIR.rglob("*.md"):
        if "_excluded" in p.parts:
            continue
        if not p.is_file():
            continue
        slug = normalize_to_slug(p.stem)
        if slug in result:
            # Slug-Kollision: erste Match gewinnt, Warnung im Report
            continue
        result[slug] = p
    return result


def discover_excluded() -> list[Path]:
    excluded = CORPUS_DIR / "_excluded"
    if not excluded.exists():
        return []
    return sorted(p for p in excluded.rglob("*.md") if p.is_file())


def discover_drafts() -> tuple[dict[str, dict[str, Path | None]], list[Path]]:
    """
    Stem → {variant: Path}, plus Liste hidden Files (Pipeline-Artefakte).

    Hidden Files (Leading-Dot) werden übersprungen.
    """
    result: dict[str, dict[str, Path | None]] = {}
    hidden: list[Path] = []
    empty = {v: None for v, _ in DRAFT_VARIANTS}
    if not DRAFTS_DIR.exists():
        return result, hidden
    for p in DRAFTS_DIR.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith("."):
            hidden.append(p)
            continue
        for variant, sfx in DRAFT_VARIANTS:
            if p.name.endswith(sfx):
                stem = p.name[:-len(sfx)]
                if stem not in result:
                    result[stem] = dict(empty)
                result[stem][variant] = p
                break
    return result, hidden


def discover_vault() -> set[str]:
    """Slugs, die schon im Vault liegen (nicht in 00_Meta/)."""
    slugs: set[str] = set()
    if not VAULT_DIR.exists():
        return slugs
    for p in VAULT_DIR.rglob("*.md"):
        # 00_Meta enthält Templates, keine Concepts
        if "00_Meta" in p.parts:
            continue
        if p.name.startswith("_") or p.name == "index.md":
            continue
        if not p.is_file():
            continue
        # Filename ist der Slug
        slugs.add(p.stem)
    return slugs


# Frontmatter-Parsing + Body-Metriken (split_md, parse_yaml_text, parse_json_file,
# compute_body_metrics) → scripts/_pkm_common.py


# === Schema-Check ===

def check_schema(fm: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    missing = REQUIRED_FIELDS - set(fm.keys())
    if missing:
        issues.append(f"missing_fields:{','.join(sorted(missing))}")

    if (t := fm.get("type")) is not None and t not in ALLOWED_TYPE:
        issues.append(f"invalid_type:{t}")

    roles = fm.get("doc_role")
    if roles is not None:
        if not isinstance(roles, list):
            issues.append("doc_role_not_list")
        else:
            inv = set(roles) - ALLOWED_DOC_ROLE
            if inv:
                issues.append(f"invalid_doc_role:{','.join(sorted(inv))}")

    for fld, allowed in [("status", ALLOWED_STATUS),
                         ("review_status", ALLOWED_REVIEW),
                         ("confidence", ALLOWED_CONFIDENCE)]:
        v = fm.get(fld)
        if v is not None and v not in allowed:
            issues.append(f"invalid_{fld}:{v}")

    cat = fm.get("category")
    if cat is not None and cat not in ALLOWED_CATEGORIES:
        issues.append(f"unknown_category:{cat}")

    slug = fm.get("slug")
    if slug is not None:
        if not isinstance(slug, str):
            issues.append("slug_not_str")
        else:
            for ch in UMLAUT_CHARS:
                if ch in slug:
                    issues.append(f"umlaut_in_slug:{ch}")
            if not SLUG_RE.match(slug):
                issues.append(f"invalid_slug_format:{slug}")

    for fld in ("sources_docs", "source_chunks", "tags", "aliases"):
        if fld in fm and fm[fld] is not None and not isinstance(fm[fld], list):
            issues.append(f"{fld}_not_list")

    return issues


# === FM-Vergleich (md ↔ json) ===

def _norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, list):
        return tuple(v) if v else None
    if isinstance(v, str) and not v:
        return None
    return v


def compare_frontmatter(yaml_fm: dict[str, Any], json_fm: dict[str, Any]) -> list[str]:
    diffs = []
    for k in set(yaml_fm) | set(json_fm):
        if _norm(yaml_fm.get(k)) != _norm(json_fm.get(k)):
            diffs.append(k)
    return diffs


# === Draft-Bewertung ===

@dataclass
class DraftAssessment:
    stem: str

    # File-Präsenz
    has_md: bool = False
    has_body_md: bool = False
    has_frontmatter: bool = False

    # Parse-Status
    md_yaml_error: str | None = None
    json_error: str | None = None

    # Body-Metriken
    body_words: int = 0
    body_headings: int = 0
    body_code_blocks: int = 0
    body_tables: int = 0
    body_wikilinks: int = 0
    body_source: str | None = None  # "md" | "body_md"

    # FM
    fm_source: str | None = None  # "md" | "json"
    title: str | None = None
    summary_words: int = 0
    tags_count: int = 0
    has_provenance: bool = False
    confidence: str | None = None
    category: str | None = None

    # Schema
    md_schema_issues: list[str] = field(default_factory=list)
    json_schema_issues: list[str] = field(default_factory=list)

    # Konsistenz
    diff_fields_critical: list[str] = field(default_factory=list)
    diff_fields_minor: list[str] = field(default_factory=list)
    diff_fields_other: list[str] = field(default_factory=list)

    # Klassifikation
    classification: str = ""


def assess_draft(stem: str, files: dict[str, Path | None]) -> DraftAssessment:
    a = DraftAssessment(stem=stem)
    a.has_md = files.get("md") is not None
    a.has_body_md = files.get("body_md") is not None
    a.has_frontmatter = files.get("frontmatter") is not None

    yaml_fm: dict[str, Any] | None = None
    md_body = ""
    if a.has_md:
        assert files["md"] is not None
        try:
            text = files["md"].read_text(encoding="utf-8")
            yaml_text, md_body = split_md(text)
            if yaml_text is None:
                a.md_yaml_error = "no_frontmatter"
            else:
                yaml_fm, err = parse_yaml_text(yaml_text)
                if err:
                    a.md_yaml_error = err
        except Exception as e:
            a.md_yaml_error = f"read_error: {type(e).__name__}"

    body_md_text = ""
    if a.has_body_md:
        assert files["body_md"] is not None
        try:
            body_md_text = files["body_md"].read_text(encoding="utf-8")
        except Exception:
            pass

    json_fm: dict[str, Any] | None = None
    if a.has_frontmatter:
        assert files["frontmatter"] is not None
        json_fm, err = parse_json_file(files["frontmatter"])
        if err:
            a.json_error = err

    # Body-Quelle: .md bevorzugt, sonst .body.md
    if md_body.strip():
        body, a.body_source = md_body, "md"
    elif body_md_text.strip():
        body, a.body_source = body_md_text, "body_md"
    else:
        body = ""
    bm = compute_body_metrics(body)
    a.body_words = bm["words"]
    a.body_headings = bm["headings"]
    a.body_code_blocks = bm["code_blocks"]
    a.body_tables = bm["tables"]
    a.body_wikilinks = bm["wikilinks"]

    # Schema-Issues
    if yaml_fm is not None:
        a.md_schema_issues = check_schema(yaml_fm)
    if json_fm is not None:
        a.json_schema_issues = check_schema(json_fm)

    # FM-Metriken aus bevorzugter Quelle
    primary = yaml_fm if yaml_fm is not None else json_fm
    if primary is not None:
        a.fm_source = "md" if yaml_fm is not None else "json"
        a.title = primary.get("title")
        summary = primary.get("summary") or ""
        a.summary_words = len(summary.split()) if isinstance(summary, str) else 0
        tags = primary.get("tags") or []
        a.tags_count = len(tags) if isinstance(tags, list) else 0
        a.has_provenance = bool(
            primary.get("sources_docs") or primary.get("source_chunks"))
        a.confidence = primary.get("confidence")
        a.category = primary.get("category")

    # Konsistenz
    if yaml_fm is not None and json_fm is not None:
        for fld in compare_frontmatter(yaml_fm, json_fm):
            if fld in CRITICAL_DIFF_FIELDS:
                a.diff_fields_critical.append(fld)
            elif fld in MINOR_DIFF_FIELDS:
                a.diff_fields_minor.append(fld)
            else:
                a.diff_fields_other.append(fld)

    a.classification = classify_draft(a)
    return a


def classify_draft(a: DraftAssessment) -> str:
    # Parse-Fehler
    if a.md_yaml_error and a.md_yaml_error not in ("no_frontmatter",):
        return "BROKEN"
    if a.json_error:
        return "BROKEN"

    # Lifecycle-Lücken
    has_content = a.has_md or a.has_body_md or a.has_frontmatter
    if not has_content:
        return "EMPTY"
    if a.has_body_md and a.has_frontmatter and not a.has_md:
        return "INCOMPLETE_ASSEMBLY"
    if a.has_md and not a.has_frontmatter and not a.has_body_md:
        return "ORPHAN"
    if a.has_frontmatter and not a.has_md and not a.has_body_md:
        return "ORPHAN"
    if a.has_body_md and not a.has_md and not a.has_frontmatter:
        return "ORPHAN"

    # Inhalt zu kurz
    if a.body_words < MIN_BODY_WORDS:
        return "STUB"

    # Inkonsistenz
    if a.diff_fields_critical:
        return "INCONSISTENT_CRITICAL"
    if a.diff_fields_minor or a.diff_fields_other:
        return "INCONSISTENT_MINOR"

    # Schema
    issues = a.md_schema_issues or a.json_schema_issues
    fixable = [i for i in issues if i.startswith(FIXABLE_ISSUE_PREFIXES)]
    non_fixable = [i for i in issues if not i.startswith(FIXABLE_ISSUE_PREFIXES)]
    if non_fixable:
        return "NEEDS_REVIEW"
    if fixable:
        return "SCHEMA_FIXABLE"

    return "READY"


# === Action-Bestimmung pro Korpus-Slug ===

DRAFT_CLASS_TO_ACTION = {
    "READY":                  "READY_TO_MIGRATE",
    "SCHEMA_FIXABLE":         "POSTPROCESS",
    "INCONSISTENT_MINOR":     "POSTPROCESS",
    "INCONSISTENT_CRITICAL":  "RERUN_LM",
    "STUB":                   "RERUN_LM",
    "BROKEN":                 "RERUN_LM",
    "ORPHAN":                 "RERUN_LM",
    "INCOMPLETE_ASSEMBLY":    "RERUN_LM",
    "NEEDS_REVIEW":           "RERUN_LM",
    "EMPTY":                  "FRESH_RUN",
}


@dataclass
class TriageRecord:
    slug: str
    corpus_path: str | None = None
    in_vault: bool = False
    draft_stem: str | None = None
    draft_classification: str | None = None
    draft_paths: dict[str, str] = field(default_factory=dict)
    body_words: int = 0
    title: str | None = None
    confidence: str | None = None
    category: str | None = None
    md_schema_issues: list[str] = field(default_factory=list)
    diff_critical: list[str] = field(default_factory=list)
    diff_minor: list[str] = field(default_factory=list)
    action: str = ""
    rationale: str = ""


def determine_triage(
    corpus_slugs: dict[str, Path],
    draft_assessments: dict[str, DraftAssessment],  # key: draft slug (ohne CK_)
    vault_slugs: set[str],
) -> tuple[list[TriageRecord], list[str]]:
    """
    Pro Korpus-Slug eine TriageRecord. Returnt zusätzlich orphan_drafts.
    """
    records: list[TriageRecord] = []
    matched_drafts: set[str] = set()

    for slug in sorted(corpus_slugs):
        rec = TriageRecord(slug=slug, corpus_path=str(corpus_slugs[slug]))

        # Vault-Match: Slug 1:1 oder mit `CK_`-Prefix
        if slug in vault_slugs or f"CK_{slug}" in vault_slugs:
            rec.in_vault = True
            rec.action = "IN_VAULT"
            rec.rationale = "Slug existiert bereits im Vault"
            records.append(rec)
            continue

        # Draft-Match
        if slug in draft_assessments:
            a = draft_assessments[slug]
            matched_drafts.add(slug)
            rec.draft_stem = a.stem
            rec.draft_classification = a.classification
            rec.body_words = a.body_words
            rec.title = a.title
            rec.confidence = a.confidence
            rec.category = a.category
            rec.md_schema_issues = a.md_schema_issues
            rec.diff_critical = a.diff_fields_critical
            rec.diff_minor = a.diff_fields_minor

            rec.action = DRAFT_CLASS_TO_ACTION.get(a.classification, "RERUN_LM")
            rec.rationale = f"Draft-Klassifikation: {a.classification}"
        else:
            rec.action = "FRESH_RUN"
            rec.rationale = "Kein Draft vorhanden"

        records.append(rec)

    # Orphan-Drafts: Draft-Stems ohne Korpus-Pendant
    orphan_drafts = sorted(set(draft_assessments) - matched_drafts)
    return records, orphan_drafts


# === Output ===

def write_triage_jsonl(records: list[TriageRecord], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def write_action_lists(
    records: list[TriageRecord],
    orphan_drafts: list[str],
    outdir: Path,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    by_action: dict[str, list[str]] = {}
    for r in records:
        by_action.setdefault(r.action, []).append(r.slug)
    for action, slugs in by_action.items():
        (outdir / f"{action.lower()}.txt").write_text(
            "\n".join(sorted(slugs)) + "\n", encoding="utf-8")
    if orphan_drafts:
        (outdir / "orphan_draft.txt").write_text(
            "\n".join(orphan_drafts) + "\n", encoding="utf-8")


def write_batches(
    records: list[TriageRecord],
    action: str,
    outdir: Path,
    title_prefix: str,
) -> int:
    """Generiert 10er-Batches im Markdown-Format. Returnt Anzahl Batches."""
    candidates = sorted(
        (r for r in records if r.action == action),
        key=lambda r: r.slug,
    )
    if not candidates:
        return 0
    outdir.mkdir(parents=True, exist_ok=True)
    n_batches = (len(candidates) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(n_batches):
        chunk = candidates[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        lines = [f"# {title_prefix} Batch {i+1:03d}/{n_batches:03d}",
                 "",
                 f"**{len(chunk)} Slugs** — Action: `{action}`",
                 ""]
        for r in chunk:
            lines.append(f"## `{r.slug}`")
            lines.append("")
            lines.append(f"- Korpus: `{r.corpus_path}`")
            if r.draft_stem:
                lines.append(f"- Draft-Stem: `{r.draft_stem}`")
                lines.append(f"- Klassifikation: `{r.draft_classification}`")
                lines.append(f"- Begründung: {r.rationale}")
                if r.body_words:
                    lines.append(f"- Body-Wörter (aktuell): {r.body_words}")
                if r.diff_critical:
                    lines.append(
                        f"- Kritische Diffs: `{','.join(r.diff_critical)}`")
                if r.md_schema_issues:
                    issues_short = [i.split(":")[0]
                                    for i in r.md_schema_issues]
                    lines.append(
                        f"- Schema-Issues: `{','.join(sorted(set(issues_short)))}`")
            lines.append("")
        (outdir / f"batch_{i+1:03d}.md").write_text(
            "\n".join(lines), encoding="utf-8")
    return n_batches


def write_report(
    records: list[TriageRecord],
    orphan_drafts: list[str],
    excluded: list[Path],
    hidden_count: int,
    rerun_batch_count: int,
    fresh_batch_count: int,
    path: Path,
) -> None:
    L: list[str] = []
    L.append("# PKM-Triage Master-Report")
    L.append("")
    L.append(f"**Lauf:** `{datetime.now().isoformat(timespec='seconds')}`")
    L.append("")
    L.append(f"- Korpus: `{CORPUS_DIR}`")
    L.append(f"- Drafts: `{DRAFTS_DIR}`")
    L.append(f"- Vault:  `{VAULT_DIR}`")
    L.append("")

    # 1. Kennzahlen
    L.append("## 1. Kennzahlen")
    L.append("")
    L.append("| Bereich | Anzahl |")
    L.append("|---|---:|")
    L.append(f"| Korpus-Files (`01_corpus_input`, ohne `_excluded/`) | {len(records)} |")
    L.append(f"| Davon excluded | {len(excluded)} |")
    L.append(f"| Vault-Slugs (`04_vault`) | {sum(1 for r in records if r.in_vault)} |")
    matched_drafts = sum(1 for r in records if r.draft_stem is not None)
    L.append(f"| Drafts mit Korpus-Match | {matched_drafts} |")
    L.append(f"| Orphan-Drafts (kein Korpus-Pendant) | {len(orphan_drafts)} |")
    L.append(f"| Hidden Files in Drafts (Pipeline-Artefakte) | {hidden_count} |")
    L.append("")

    # 2. Actions
    L.append("## 2. Action-Verteilung")
    L.append("")
    action_counter = Counter(r.action for r in records)
    descriptions = {
        "IN_VAULT":          "✅ Bereits im Vault, fertig",
        "READY_TO_MIGRATE":  "✅ Draft sauber, übernehmen",
        "POSTPROCESS":       "🔧 Deterministisch fixbar (Python-Skript)",
        "RERUN_LM":          "🔁 Draft fragwürdig → neuer LM-Studio-Lauf",
        "FRESH_RUN":         "🆕 Kein Draft → erstmaliger Lauf",
    }
    L.append("| Action | Anzahl | Bedeutung |")
    L.append("|---|---:|---|")
    for action in ["IN_VAULT", "READY_TO_MIGRATE", "POSTPROCESS",
                   "RERUN_LM", "FRESH_RUN"]:
        c = action_counter.get(action, 0)
        L.append(f"| `{action}` | {c} | {descriptions.get(action, '')} |")
    L.append("")

    # 3. Re-Run-Aufwand
    L.append("## 3. LM-Studio-Aufwand")
    L.append("")
    rerun_count = action_counter.get("RERUN_LM", 0)
    fresh_count = action_counter.get("FRESH_RUN", 0)
    total_lm = rerun_count + fresh_count
    L.append(f"- RERUN_LM: **{rerun_count}** Slugs → "
             f"{rerun_batch_count} Batches à {BATCH_SIZE}")
    L.append(f"- FRESH_RUN: **{fresh_count}** Slugs → "
             f"{fresh_batch_count} Batches à {BATCH_SIZE}")
    L.append(f"- Total LM-Studio-Last: **{total_lm}** Slugs")
    L.append("")
    L.append("Bei ~6–8 Min/Slug für Stage 4 (Frontmatter) und vergleichbar "
             "für Stage 3 (Body): "
             f"grobe Schätzung **{total_lm * 7 // 60}–{total_lm * 10 // 60} h** "
             "Laufzeit, pausierbar in Batches.")
    L.append("")

    # 4. Klassifikations-Übersicht (für RERUN_LM-Detail)
    rerun_records = [r for r in records if r.action == "RERUN_LM"]
    if rerun_records:
        L.append("## 4. RERUN_LM — Aufschlüsselung nach Draft-Klassifikation")
        L.append("")
        cls_counter = Counter(r.draft_classification for r in rerun_records)
        L.append("| Klassifikation | Anzahl |")
        L.append("|---|---:|")
        for cls, c in cls_counter.most_common():
            L.append(f"| `{cls}` | {c} |")
        L.append("")

    # 5. Orphan-Drafts
    if orphan_drafts:
        L.append("## 5. Orphan-Drafts (Draft ohne Korpus-Pendant)")
        L.append("")
        L.append("Diese Drafts haben keinen passenden Slug im Korpus. "
                 "Mögliche Ursachen: Korpus-Umbenennung, Slug-Generierungs-Drift, "
                 "oder Draft aus alter Korpus-Version.")
        L.append("")
        for s in orphan_drafts:
            L.append(f"- `{s}`")
        L.append("")

    # 6. Excluded
    if excluded:
        L.append("## 6. Excluded Korpus-Files")
        L.append("")
        L.append(f"{len(excluded)} Files in `_excluded/` — werden nicht "
                 "verarbeitet.")
        L.append("")
        for p in excluded:
            L.append(f"- `{p.name}`")
        L.append("")

    # 7. Detail-Listen pro Action
    L.append("## 7. Slugs pro Action")
    L.append("")
    for action in ["IN_VAULT", "READY_TO_MIGRATE", "POSTPROCESS",
                   "RERUN_LM", "FRESH_RUN"]:
        slugs = sorted(r.slug for r in records if r.action == action)
        if not slugs:
            continue
        L.append(f"### {action} ({len(slugs)})")
        L.append("")
        for s in slugs:
            L.append(f"- `{s}`")
        L.append("")

    path.write_text("\n".join(L), encoding="utf-8")


# === Main ===

def main() -> int:
    for d, label in [(CORPUS_DIR, "Korpus"),
                     (DRAFTS_DIR, "Drafts")]:
        if not d.exists():
            print(f"FEHLER: {label}-Verzeichnis fehlt: {d}", file=sys.stderr)
            return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    actions_dir = OUTPUT_DIR / "actions"
    rerun_dir = OUTPUT_DIR / "rerun_batches"
    fresh_dir = OUTPUT_DIR / "fresh_run_batches"

    # Discover
    corpus_slugs = discover_corpus()
    excluded = discover_excluded()
    draft_files, hidden = discover_drafts()
    vault_slugs = discover_vault()

    # Assess each draft
    draft_assessments: dict[str, DraftAssessment] = {}
    for stem, files in draft_files.items():
        a = assess_draft(stem, files)
        slug = draft_stem_to_slug(stem)
        if slug in draft_assessments:
            # Slug-Kollision unter Drafts (selten); erste Match gewinnt
            continue
        draft_assessments[slug] = a

    # Triage
    records, orphan_drafts = determine_triage(
        corpus_slugs, draft_assessments, vault_slugs)

    # Outputs
    write_triage_jsonl(records, OUTPUT_DIR / "triage.jsonl")
    write_action_lists(records, orphan_drafts, actions_dir)
    rerun_n = write_batches(records, "RERUN_LM", rerun_dir, "Re-Run LM-Studio")
    fresh_n = write_batches(records, "FRESH_RUN", fresh_dir, "Fresh Run")
    write_report(records, orphan_drafts, excluded, len(hidden),
                 rerun_n, fresh_n, OUTPUT_DIR / "triage_report.md")

    # Konsolen-Summary
    action_counter = Counter(r.action for r in records)
    print()
    print("=== PKM-Triage ===")
    print(f"Korpus:           {len(records)} Slugs (+ {len(excluded)} excluded)")
    print(f"Vault:            {len(vault_slugs)} Slugs")
    print(f"Drafts (matched): {sum(1 for r in records if r.draft_stem)}")
    print(f"Orphan-Drafts:    {len(orphan_drafts)}")
    print(f"Hidden Files:     {len(hidden)} (übersprungen)")
    print()
    print("Action:")
    for action in ["IN_VAULT", "READY_TO_MIGRATE", "POSTPROCESS",
                   "RERUN_LM", "FRESH_RUN"]:
        print(f"  {action:18} {action_counter.get(action, 0):4}")
    print()
    print(f"Batches:          RERUN_LM={rerun_n}, FRESH_RUN={fresh_n}")
    print()
    print(f"Report:           {OUTPUT_DIR / 'triage_report.md'}")
    print(f"Listen:           {actions_dir}/")
    print(f"Re-Run-Batches:   {rerun_dir}/")
    print(f"Fresh-Batches:    {fresh_dir}/")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
