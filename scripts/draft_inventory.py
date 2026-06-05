#!/usr/bin/env python3
"""
draft_inventory.py — Umfassendes Inventar + Klassifikation aller Drafts

Zweck:
  Vollständige qualitative Einordnung aller Files unter
  ~/projects/aktiv/PKM_rebuild/data/03_drafts/.

  Liefert die Entscheidungsgrundlage:
   - welche Drafts sind vault-ready
   - welche durch deterministisches Post-Processing
   - welche brauchen Re-Run durch LM Studio
   - welche brauchen manuellen Review

Pro Stem erfasst:
  1. File-Existenz + Größen + Timestamps
     (.md / .body.md / .frontmatter.json / *.meta.json)
  2. Routing-Inferenz (passthrough | stage3 | unknown)
  3. Parseability (YAML in .md, JSON in .frontmatter.json)
  4. Body-Metriken (Wörter, Headings, Code, Tabellen, Wikilinks, offene Fragen)
  5. Frontmatter-Metriken (Pflichtfelder, Enums, summary-Länge, Provenance)
  6. Schema-Konformität gegen Vault-Standard
  7. Konsistenz embedded YAML ↔ .frontmatter.json (Diff klassifiziert
     in critical / minor / other)
  8. Klassifikation:
     READY | SCHEMA_FIXABLE | INCONSISTENT_MINOR | INCONSISTENT_CRITICAL
     | STUB | BROKEN | ORPHAN | INCOMPLETE_ASSEMBLY | NEEDS_REVIEW

Outputs:
  data/02_pipeline_output/
    draft_inventory.jsonl              — alle Metriken, eine Zeile pro Stem
    draft_inventory_report.md          — menschen-lesbarer Übersichts-Report
    classification/
      ready.txt                        — Stems pro Klassifikation
      schema_fixable.txt
      inconsistent_minor.txt
      inconsistent_critical.txt
      stub.txt
      broken.txt
      orphan.txt
      incomplete_assembly.txt
      needs_review.txt
      needs_rerun.txt                  — Sammelliste für LM-Studio-Re-Run

Read-only. Modifiziert keine Drafts.

Aufruf:
  python3 scripts/draft_inventory.py

Exit-Codes:
  0 = Inventar erfolgreich erstellt
  2 = Setup-Fehler (Pfade, Dependencies)
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
    print("FEHLER: pyyaml fehlt. Installation: pip install pyyaml",
          file=sys.stderr)
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
    MAX_SUMMARY_WORDS,
    MAX_TAGS,
    MIN_BODY_WORDS,
    MIN_SUMMARY_WORDS,
    MINOR_DIFF_FIELDS,
    REQUIRED_FIELDS,
    SLUG_RE,
    UMLAUT_CHARS,
    _normalize_for_diff,
    compute_body_metrics,
    parse_json_file,
    parse_yaml_text,
    split_md,
)

# === Pfad-Konfiguration ===
DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
DRAFTS_DIR = DATA_ROOT / "03_drafts"
OUTPUT_DIR = DATA_ROOT / "02_pipeline_output"
INVENTORY_JSONL = OUTPUT_DIR / "draft_inventory.jsonl"
INVENTORY_REPORT = OUTPUT_DIR / "draft_inventory_report.md"
CLASSIFICATION_DIR = OUTPUT_DIR / "classification"

# === Schwellwerte (skript-lokal; geteilte in _pkm_common) ===
RICH_BODY_WORDS = 300  # ab dann inhaltlich substanziell (Report-Bucket)

# Variants pro Stem (Reihenfolge wichtig: längere Suffixe zuerst!)
FILE_VARIANTS = [
    ("body_meta", ".body.meta.json"),
    ("fm_meta",   ".frontmatter.meta.json"),
    ("frontmatter", ".frontmatter.json"),
    ("body_md",   ".body.md"),
    ("md",        ".md"),
]


# === Datenmodell ===

@dataclass
class DraftRecord:
    stem: str

    # Existenz
    has_md: bool = False
    has_body_md: bool = False
    has_frontmatter: bool = False
    has_body_meta: bool = False
    has_fm_meta: bool = False

    # Größen
    md_bytes: int = 0
    body_md_bytes: int = 0
    frontmatter_bytes: int = 0

    # Timestamps (ISO, sekunden-genau)
    md_mtime: str | None = None
    body_md_mtime: str | None = None
    frontmatter_mtime: str | None = None

    # Routing
    routing: str = "unknown"  # passthrough | stage3 | unknown

    # Parse
    md_yaml_error: str | None = None
    md_body_present: bool = False
    json_error: str | None = None
    body_md_present: bool = False

    # Schema
    md_schema_issues: list[str] = field(default_factory=list)
    json_schema_issues: list[str] = field(default_factory=list)

    # Body-Metriken (aus bevorzugter Quelle: .md > .body.md)
    body_source: str | None = None
    body_words: int = 0
    body_chars: int = 0
    body_headings: int = 0
    body_code_blocks: int = 0
    body_tables: int = 0
    body_wikilinks: int = 0
    body_open_questions: int = 0

    # Frontmatter-Metriken (bevorzugte Quelle: embedded YAML > json)
    fm_source: str | None = None
    title: str | None = None
    title_lang_guess: str | None = None
    summary_words: int = 0
    summary_too_short: bool = False
    summary_too_long: bool = False
    tags_count: int = 0
    tags_too_many: bool = False
    aliases_count: int = 0
    sources_docs_count: int = 0
    source_chunks_count: int = 0
    has_provenance: bool = False
    confidence: str | None = None
    fm_type: str | None = None
    category: str | None = None

    # Konsistenz md ↔ json
    diff_count: int = 0
    diff_fields_critical: list[str] = field(default_factory=list)
    diff_fields_minor: list[str] = field(default_factory=list)
    diff_fields_other: list[str] = field(default_factory=list)

    # Klassifikation (am Ende gesetzt)
    classification: str = ""
    flags: list[str] = field(default_factory=list)


# === File-Discovery ===

def discover_files() -> dict[str, dict[str, Path | None]]:
    """Gruppiert Files im DRAFTS_DIR nach Stem."""
    result: dict[str, dict[str, Path | None]] = {}
    empty = {v: None for v, _ in FILE_VARIANTS}
    for p in DRAFTS_DIR.iterdir():
        if not p.is_file():
            continue
        for variant, sfx in FILE_VARIANTS:
            if p.name.endswith(sfx):
                stem = p.name[:-len(sfx)]
                if stem not in result:
                    result[stem] = dict(empty)
                result[stem][variant] = p
                break
    return result


# Body-/Frontmatter-Verarbeitung (split_md, compute_body_metrics, parse_yaml_text,
# parse_json_file) → scripts/_pkm_common.py


def check_schema(fm: dict) -> list[str]:
    """Schema-Issues. Format: '<key>:<detail>' für Aggregation."""
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

    for fld in ("sources_docs", "source_chunks",
                "tags", "aliases", "related", "child_concepts"):
        if fld in fm and fm[fld] is not None and not isinstance(fm[fld], list):
            issues.append(f"{fld}_not_list")

    return issues


def guess_title_lang(text: str | None) -> str:
    """Sehr grobe DE/EN-Heuristik nur für Reporting."""
    if not text or not isinstance(text, str):
        return "unknown"
    if any(ch in text.lower() for ch in UMLAUT_CHARS):
        return "de"
    de = {"und", "der", "die", "das", "mit", "für", "fuer", "über", "ueber",
          "von", "ist", "ein", "eine", "im", "des"}
    en = {"and", "the", "with", "for", "of", "is", "are", "a", "to", "in"}
    words = set(text.lower().split())
    d, e = len(words & de), len(words & en)
    if d > e:
        return "de"
    if e > d:
        return "en"
    return "mixed"


def compute_fm_metrics(fm: dict) -> dict[str, Any]:
    summary = fm.get("summary") or ""
    sw = len(summary.split()) if isinstance(summary, str) else 0
    tags = fm.get("tags") or []
    aliases = fm.get("aliases") or []
    sdocs = fm.get("sources_docs") or []
    schunks = fm.get("source_chunks") or []
    return {
        "title_lang_guess": guess_title_lang(fm.get("title")),
        "summary_words": sw,
        "summary_too_short": sw < MIN_SUMMARY_WORDS,
        "summary_too_long": sw > MAX_SUMMARY_WORDS,
        "tags_count": len(tags) if isinstance(tags, list) else 0,
        "tags_too_many": isinstance(tags, list) and len(tags) > MAX_TAGS,
        "aliases_count": len(aliases) if isinstance(aliases, list) else 0,
        "sources_docs_count": len(sdocs) if isinstance(sdocs, list) else 0,
        "source_chunks_count": len(schunks) if isinstance(schunks, list) else 0,
        "has_provenance": bool(sdocs or schunks),
        "confidence": fm.get("confidence"),
        "type": fm.get("type"),
        "category": fm.get("category"),
    }


def compare_frontmatter(yaml_fm: dict, json_fm: dict) -> list[str]:
    """Returnt Liste der inkonsistenten Feldnamen."""
    diffs = []
    for k in set(yaml_fm) | set(json_fm):
        if _normalize_for_diff(yaml_fm.get(k)) != _normalize_for_diff(json_fm.get(k)):
            diffs.append(k)
    return diffs


# === Record-Aufbau pro Stem ===

def build_record(stem: str, files: dict[str, Path | None]) -> DraftRecord:
    r = DraftRecord(stem=stem)

    # Existenz + Größen + Timestamps
    for variant, attr in [("md", "has_md"), ("body_md", "has_body_md"),
                          ("frontmatter", "has_frontmatter"),
                          ("body_meta", "has_body_meta"),
                          ("fm_meta", "has_fm_meta")]:
        p = files.get(variant)
        if p is not None:
            setattr(r, attr, True)

    def stamp(p: Path) -> tuple[int, str]:
        st = p.stat()
        return st.st_size, datetime.fromtimestamp(st.st_mtime).isoformat(
            timespec="seconds")

    if r.has_md:
        r.md_bytes, r.md_mtime = stamp(files["md"])
    if r.has_body_md:
        r.body_md_bytes, r.body_md_mtime = stamp(files["body_md"])
    if r.has_frontmatter:
        r.frontmatter_bytes, r.frontmatter_mtime = stamp(files["frontmatter"])

    # Routing-Inferenz
    if r.has_body_md:
        r.routing = "stage3"
    elif r.has_md and r.has_frontmatter:
        r.routing = "passthrough"

    # Parse .md
    yaml_fm: dict | None = None
    md_body = ""
    if r.has_md:
        try:
            text = files["md"].read_text(encoding="utf-8")
            yaml_text, md_body = split_md(text)
            r.md_body_present = bool(md_body.strip())
            if yaml_text is None:
                r.md_yaml_error = "no_frontmatter"
            else:
                yaml_fm, err = parse_yaml_text(yaml_text)
                if err:
                    r.md_yaml_error = err
        except Exception as e:
            r.md_yaml_error = f"read_error: {type(e).__name__}"

    # Parse .body.md
    body_md_text = ""
    if r.has_body_md:
        try:
            body_md_text = files["body_md"].read_text(encoding="utf-8")
            r.body_md_present = bool(body_md_text.strip())
        except Exception:
            pass

    # Parse .frontmatter.json
    json_fm: dict | None = None
    if r.has_frontmatter:
        json_fm, err = parse_json_file(files["frontmatter"])
        if err:
            r.json_error = err

    # Body-Quelle wählen (md bevorzugt, weil das Phase 9 lesen würde)
    if md_body.strip():
        body, r.body_source = md_body, "md"
    elif body_md_text.strip():
        body, r.body_source = body_md_text, "body_md"
    else:
        body = ""
    bm = compute_body_metrics(body)
    r.body_words = bm["words"]
    r.body_chars = bm["chars"]
    r.body_headings = bm["headings"]
    r.body_code_blocks = bm["code_blocks"]
    r.body_tables = bm["tables"]
    r.body_wikilinks = bm["wikilinks"]
    r.body_open_questions = bm["open_questions"]

    # Schema-Check beider Frontmatter
    if yaml_fm is not None:
        r.md_schema_issues = check_schema(yaml_fm)
    if json_fm is not None:
        r.json_schema_issues = check_schema(json_fm)

    # FM-Metriken (embedded YAML bevorzugt)
    primary_fm = yaml_fm if yaml_fm is not None else json_fm
    if primary_fm is not None:
        r.fm_source = "md" if yaml_fm is not None else "json"
        m = compute_fm_metrics(primary_fm)
        r.title = primary_fm.get("title")
        r.title_lang_guess = m["title_lang_guess"]
        r.summary_words = m["summary_words"]
        r.summary_too_short = m["summary_too_short"]
        r.summary_too_long = m["summary_too_long"]
        r.tags_count = m["tags_count"]
        r.tags_too_many = m["tags_too_many"]
        r.aliases_count = m["aliases_count"]
        r.sources_docs_count = m["sources_docs_count"]
        r.source_chunks_count = m["source_chunks_count"]
        r.has_provenance = m["has_provenance"]
        r.confidence = m["confidence"]
        r.fm_type = m["type"]
        r.category = m["category"]

    # Konsistenz md ↔ json
    if yaml_fm is not None and json_fm is not None:
        diffs = compare_frontmatter(yaml_fm, json_fm)
        r.diff_count = len(diffs)
        for fld in diffs:
            if fld in CRITICAL_DIFF_FIELDS:
                r.diff_fields_critical.append(fld)
            elif fld in MINOR_DIFF_FIELDS:
                r.diff_fields_minor.append(fld)
            else:
                r.diff_fields_other.append(fld)

    # Klassifikation
    r.classification, r.flags = classify(r)
    return r


# === Klassifikation ===

def classify(r: DraftRecord) -> tuple[str, list[str]]:
    """
    Erste Bedingung gewinnt für `classification`.
    Flags sind orthogonal und immer alle gesetzten.
    """
    flags: list[str] = []

    # Orthogonale Flags (immer evaluieren)
    if r.category == "gedanken":
        flags.append("gedanken")
    if r.confidence == "low":
        flags.append("low_confidence")
    if r.summary_too_short:
        flags.append("summary_too_short")
    if r.summary_too_long:
        flags.append("summary_too_long")
    if r.tags_too_many:
        flags.append("tags_too_many")
    if r.fm_source is not None and not r.has_provenance:
        flags.append("no_provenance")
    if r.body_open_questions > 0:
        flags.append("has_open_questions")
    if r.title_lang_guess == "en":
        flags.append("title_en")

    # Klassifikation (priorisiert)

    # Parse-Fehler in mindestens einer Quelle
    if r.md_yaml_error and r.md_yaml_error not in ("no_frontmatter",):
        return "BROKEN", flags + [f"md_parse_error:{r.md_yaml_error.split(':')[0]}"]
    if r.json_error:
        return "BROKEN", flags + [f"json_parse_error:{r.json_error.split(':')[0]}"]

    # Spezialfälle: Files vorhanden, aber Lifecycle unvollständig
    has_content = r.has_md or r.has_body_md or r.has_frontmatter
    has_meta = r.has_body_meta or r.has_fm_meta

    # Stems ohne Content-Files (häufige Ursache: hängengebliebene Meta-Files
    # nach abgebrochenen Runs)
    if not has_content:
        if has_meta:
            return "META_ONLY", flags
        return "EMPTY", flags  # absurder Edge-Case (sollte nie auftreten)

    if r.has_body_md and r.has_frontmatter and not r.has_md:
        return "INCOMPLETE_ASSEMBLY", flags
    if r.has_md and not r.has_frontmatter and not r.has_body_md:
        return "ORPHAN", flags + ["only_md"]
    if r.has_frontmatter and not r.has_md and not r.has_body_md:
        return "ORPHAN", flags + ["only_json"]
    if r.has_body_md and not r.has_md and not r.has_frontmatter:
        return "ORPHAN", flags + ["only_body_md"]

    # Inhalt zu kurz
    if r.body_words < MIN_BODY_WORDS:
        return "STUB", flags + [f"body_words:{r.body_words}"]

    # Inkonsistenz zwischen .md und .json
    if r.diff_fields_critical:
        return ("INCONSISTENT_CRITICAL",
                flags + [f"crit:{','.join(r.diff_fields_critical)}"])
    if r.diff_fields_minor or r.diff_fields_other:
        return "INCONSISTENT_MINOR", flags

    # Schema-Issues
    md_issues = r.md_schema_issues
    fixable_keys = ("unknown_category:", "invalid_doc_role:",
                    "umlaut_in_slug:", "invalid_slug_format:")
    fixable = [i for i in md_issues if i.startswith(fixable_keys)]
    non_fixable = [i for i in md_issues if not i.startswith(fixable_keys)]
    if non_fixable:
        return "NEEDS_REVIEW", flags + [f"schema:{len(non_fixable)}"]
    if fixable:
        return "SCHEMA_FIXABLE", flags + [f"fix:{len(fixable)}"]

    return "READY", flags


# === Output-Generierung ===

def write_jsonl(records: list[DraftRecord], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def write_classification_lists(records: list[DraftRecord],
                                outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    # Per-Klassifikation
    by_cls: dict[str, list[str]] = {}
    for r in records:
        by_cls.setdefault(r.classification, []).append(r.stem)
    for cls, stems in by_cls.items():
        (outdir / f"{cls.lower()}.txt").write_text(
            "\n".join(sorted(stems)) + "\n", encoding="utf-8")
    # Sammel-Liste für Re-Run
    rerun_classes = {"BROKEN", "STUB", "INCONSISTENT_CRITICAL",
                     "NEEDS_REVIEW", "ORPHAN", "INCOMPLETE_ASSEMBLY",
                     "META_ONLY", "EMPTY"}
    rerun = sorted(r.stem for r in records
                   if r.classification in rerun_classes)
    (outdir / "needs_rerun.txt").write_text(
        "\n".join(rerun) + "\n", encoding="utf-8")


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    idx = min(len(values) - 1, int(len(values) * p))
    return values[idx]


def write_report(records: list[DraftRecord], path: Path) -> None:
    L: list[str] = []

    L.append("# Draft-Inventory Report")
    L.append("")
    L.append(f"**Lauf:** `{datetime.now().isoformat(timespec='seconds')}`  ")
    L.append(f"**Drafts:** `{DRAFTS_DIR}`  ")
    L.append(f"**Stems erfasst:** {len(records)}")
    L.append("")

    # 1. Klassifikation
    L.append("## 1. Klassifikation")
    L.append("")
    descriptions = {
        "READY": "✅ Vault-ready",
        "SCHEMA_FIXABLE": "🔧 Deterministisch fixbar (category, doc_role, slug-Umlaute)",
        "INCONSISTENT_MINOR": "⚠️ md↔json-Drift in unkritischen Feldern (Doppelarbeit-Pattern)",
        "INCONSISTENT_CRITICAL": "🚩 Diff in title/type/summary/slug — manueller Review",
        "STUB": f"📉 Body < {MIN_BODY_WORDS} Wörter",
        "BROKEN": "💥 Parse-Fehler in YAML oder JSON",
        "ORPHAN": "👤 Nur eine Quelle (md ODER json ODER body.md)",
        "INCOMPLETE_ASSEMBLY": "🧩 body+json da, aber Assembly fehlt",
        "META_ONLY": "🪦 Nur Meta-Files, kein Content (Run-Artefakt)",
        "EMPTY": "⚫ Stem ohne irgendeinen File-Bezug",
        "NEEDS_REVIEW": "❓ Schema-Issues nicht trivial fixbar",
    }
    cls_counter = Counter(r.classification for r in records)
    L.append("| Klassifikation | Anzahl | Bedeutung |")
    L.append("|---|---:|---|")
    for cls, count in cls_counter.most_common():
        L.append(f"| `{cls}` | {count} | {descriptions.get(cls, '—')} |")
    L.append("")

    # 2. Routing
    L.append("## 2. Routing-Verteilung")
    L.append("")
    L.append("| Routing | Anzahl |")
    L.append("|---|---:|")
    for routing, count in Counter(r.routing for r in records).most_common():
        L.append(f"| `{routing}` | {count} |")
    L.append("")

    # 3. Body-Metriken (Quantile)
    L.append("## 3. Body-Metriken")
    L.append("")
    L.append("| Metrik | Min | Median | p90 | Max |")
    L.append("|---|---:|---:|---:|---:|")
    for label, attr in [("Wörter", "body_words"),
                        ("Headings", "body_headings"),
                        ("Code-Blöcke", "body_code_blocks"),
                        ("Tabellen", "body_tables"),
                        ("Wikilinks", "body_wikilinks"),
                        ("Offene Fragen", "body_open_questions")]:
        vals = sorted(getattr(r, attr) for r in records)
        if vals:
            L.append(f"| {label} | {vals[0]} "
                     f"| {_percentile(vals, 0.5)} "
                     f"| {_percentile(vals, 0.9)} "
                     f"| {vals[-1]} |")
    L.append("")

    # 3a. Body-Buckets
    L.append("### 3a. Body-Größen-Verteilung")
    L.append("")
    stub = sum(1 for r in records if r.body_words < MIN_BODY_WORDS)
    short = sum(1 for r in records
                if MIN_BODY_WORDS <= r.body_words < 150)
    medium = sum(1 for r in records
                 if 150 <= r.body_words < RICH_BODY_WORDS)
    rich = sum(1 for r in records if r.body_words >= RICH_BODY_WORDS)
    L.append(f"- Stub (`< {MIN_BODY_WORDS}`): **{stub}**")
    L.append(f"- Kurz (`{MIN_BODY_WORDS}–149`): {short}")
    L.append(f"- Mittel (`150–{RICH_BODY_WORDS - 1}`): {medium}")
    L.append(f"- Substantiell (`≥ {RICH_BODY_WORDS}`): {rich}")
    L.append("")

    # 4. Frontmatter-Qualität
    L.append("## 4. Frontmatter-Qualität")
    L.append("")
    L.append("| Befund | Anzahl |")
    L.append("|---|---:|")
    L.append(f"| `summary` zu kurz (< {MIN_SUMMARY_WORDS}) | "
             f"{sum(1 for r in records if r.summary_too_short)} |")
    L.append(f"| `summary` zu lang (> {MAX_SUMMARY_WORDS}) | "
             f"{sum(1 for r in records if r.summary_too_long)} |")
    L.append(f"| `tags > {MAX_TAGS}` | "
             f"{sum(1 for r in records if r.tags_too_many)} |")
    L.append(f"| Ohne Provenance | "
             f"{sum(1 for r in records if r.fm_source and not r.has_provenance)} |")
    L.append(f"| `confidence: low` | "
             f"{sum(1 for r in records if r.confidence == 'low')} |")
    L.append(f"| Titel-Sprache EN | "
             f"{sum(1 for r in records if r.title_lang_guess == 'en')} |")
    L.append("")

    # 5. Schema-Issues
    L.append("## 5. Schema-Issues")
    L.append("")
    issue_counter: Counter[tuple[str, str]] = Counter()
    for r in records:
        for i in r.md_schema_issues:
            issue_counter[("md", i.split(":")[0])] += 1
        for i in r.json_schema_issues:
            issue_counter[("json", i.split(":")[0])] += 1
    L.append("| Quelle | Issue-Typ | Anzahl |")
    L.append("|---|---|---:|")
    for (src, issue), count in issue_counter.most_common():
        L.append(f"| {src} | `{issue}` | {count} |")
    L.append("")

    # 6. Diffs md ↔ json
    L.append("## 6. md ↔ json Diffs pro Feld")
    L.append("")
    diff_counter: Counter[str] = Counter()
    for r in records:
        for fld in r.diff_fields_critical + r.diff_fields_minor + r.diff_fields_other:
            diff_counter[fld] += 1
    L.append("| Feld | Anzahl | Kategorie |")
    L.append("|---|---:|---|")
    for fld, count in diff_counter.most_common():
        cat = ("critical" if fld in CRITICAL_DIFF_FIELDS
               else "minor" if fld in MINOR_DIFF_FIELDS
               else "other")
        L.append(f"| `{fld}` | {count} | {cat} |")
    L.append("")

    # 7. Flag-Häufigkeit
    L.append("## 7. Flag-Häufigkeit")
    L.append("")
    flag_counter: Counter[str] = Counter()
    for r in records:
        for f in r.flags:
            flag_counter[f.split(":")[0]] += 1
    L.append("| Flag | Anzahl |")
    L.append("|---|---:|")
    for flag, count in flag_counter.most_common():
        L.append(f"| `{flag}` | {count} |")
    L.append("")

    # 8. Slug-Listen pro Klassifikation
    L.append("## 8. Slugs pro Klassifikation")
    L.append("")
    order = ["READY", "SCHEMA_FIXABLE", "INCONSISTENT_MINOR",
             "INCONSISTENT_CRITICAL", "STUB", "BROKEN",
             "ORPHAN", "INCOMPLETE_ASSEMBLY",
             "META_ONLY", "EMPTY", "NEEDS_REVIEW"]
    for cls in order:
        stems = sorted(r.stem for r in records if r.classification == cls)
        if not stems:
            continue
        L.append(f"### {cls} ({len(stems)})")
        L.append("")
        for s in stems:
            L.append(f"- `{s}`")
        L.append("")

    path.write_text("\n".join(L), encoding="utf-8")


# === Main ===

def main() -> int:
    if not DRAFTS_DIR.exists():
        print(f"FEHLER: {DRAFTS_DIR} existiert nicht.", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files_by_stem = discover_files()
    records = [build_record(stem, fs)
               for stem, fs in sorted(files_by_stem.items())]

    write_jsonl(records, INVENTORY_JSONL)
    write_classification_lists(records, CLASSIFICATION_DIR)
    write_report(records, INVENTORY_REPORT)

    # Konsolen-Summary
    cls_counter = Counter(r.classification for r in records)
    routing_counter = Counter(r.routing for r in records)

    print()
    print("=== Draft-Inventory ===")
    print(f"Drafts:   {DRAFTS_DIR}")
    print(f"Stems:    {len(records)}")
    print()
    print("Routing:")
    for routing, c in routing_counter.most_common():
        print(f"  {routing:14} {c:4}")
    print()
    print("Klassifikation:")
    for cls, c in cls_counter.most_common():
        print(f"  {cls:24} {c:4}")
    print()
    print(f"JSONL:    {INVENTORY_JSONL}")
    print(f"Report:   {INVENTORY_REPORT}")
    print(f"Listen:   {CLASSIFICATION_DIR}/")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
