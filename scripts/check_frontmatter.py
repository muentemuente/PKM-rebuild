#!/usr/bin/env python3
"""
check_frontmatter.py — Validierung aller Frontmatter in data/03_drafts/

Zweck:
  Diagnostiziert den Inkonsistenz-Zustand zwischen embedded YAML (.md, Mai 30)
  und .frontmatter.json (Mai 31, nach Doppelarbeit-Vorfall).

Prüft pro Slug:
  1. Parseability (YAML in .md, JSON in .frontmatter.json)
  2. Schema-Konformität (Pflichtfelder, Enums, Slug-Format, Umlaute)
  3. category gegen die 16 erlaubten Vault-Ordner
  4. Konsistenz embedded YAML ↔ .frontmatter.json (Feld-für-Feld)

Output:
  - Konsolen-Summary
  - Markdown-Report unter data/02_pipeline_output/frontmatter_check_report.md

Read-only. Modifiziert keine Drafts.

Aufruf:
  python3 scripts/check_frontmatter.py

Exit-Codes:
  0 = alles sauber
  1 = Inkonsistenzen oder Schema-Issues gefunden
  2 = Setup-Fehler (Pfade, Dependencies)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("FEHLER: pyyaml fehlt. Installation: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# === Konfiguration ===
DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
DRAFTS_DIR = DATA_ROOT / "03_drafts"
OUTPUT_DIR = DATA_ROOT / "02_pipeline_output"
REPORT_FILE = OUTPUT_DIR / "frontmatter_check_report.md"

# 16 erlaubte category-Werte (Ordnernamen ohne Nummern-Präfix, plus unsortiert)
ALLOWED_CATEGORIES = {
    "meta",
    "grundlagen",
    "webentwicklung",
    "betriebssysteme",
    "protokolle-und-standards",
    "dateitypen-und-konfiguration",
    "methoden-und-prozesse",
    "best-practices",
    "cheatsheets",
    "ki-und-semantische-systeme",
    "datenarchitektur-und-datenbanken",
    "dokumentenverarbeitung-und-extraktion",
    "wissensmodellierung-und-knowledge-graphs",
    "visualisierung-reporting-und-design-systeme",
    "automatisierung-scripting-und-pipelines",
    "gedanken",
    "kunst-kultur",
    "unsortiert",
}

# Enums aus Vault-Standard (docs/03_vault_standard.md Sektion 3)
ALLOWED_TYPE = {"process-document", "knowledge-article", "compact-reference"}
ALLOWED_DOC_ROLE = {
    "manual", "how-to", "best-practice", "workflow",
    "explanation", "reference", "cheatsheet", "wiki",
}
ALLOWED_STATUS = {"draft", "review", "stable", "deprecated"}
ALLOWED_REVIEW = {"ai_drafted", "human_reviewed", "verified"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}

# Pflichtfelder (Vault-Standard Sektion 3 "Pflicht")
REQUIRED_FIELDS = {
    "title", "slug", "summary",
    "type", "doc_role", "category",
    "sources_docs", "source_chunks",
    "status", "review_status", "confidence",
    "doc_version", "created", "updated",
    "last_synthesized", "prompt_version",
}

# Felder, die für Inkonsistenz-Check (.md vs .json) entscheidend sind
COMPARE_FIELDS = [
    "title", "slug", "summary",
    "type", "doc_role", "category", "subcategory",
    "tags", "aliases",
    "sources_docs", "source_chunks",
    "confidence", "review_status", "status",
    "created", "updated", "last_synthesized",
]

# Slug-Pattern: nur kleinbuchstaben, ziffern, bindestriche
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
UMLAUT_PAIRS = [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]


# === Hilfsfunktionen ===

def extract_yaml_from_md(md_path: Path) -> tuple[dict | None, str | None]:
    """YAML-Frontmatter aus .md extrahieren. Returnt (dict, error_or_None)."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception as e:
        return None, f"read_error: {e}"

    # Frontmatter muss mit --- in erster Zeile starten
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None, "no_frontmatter_start"

    # Zweiten ---  als Ende suchen
    end_match = re.search(r"\n---\s*\n", text[4:])
    if not end_match:
        return None, "unterminated_frontmatter"

    yaml_text = text[4:4 + end_match.start()]
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return None, f"yaml_parse_error: {e}"

    if not isinstance(data, dict):
        return None, "yaml_not_dict"
    return data, None


def load_json(path: Path) -> tuple[dict | None, str | None]:
    """JSON-Frontmatter laden. Returnt (dict, error_or_None)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"json_error: {e}"

    if not isinstance(data, dict):
        return None, "json_not_dict"
    return data, None


def check_schema(fm: dict) -> list[str]:
    """Frontmatter gegen Schema prüfen. Returnt Liste von Issue-Strings."""
    issues: list[str] = []

    # Pflichtfelder
    missing = REQUIRED_FIELDS - set(fm.keys())
    if missing:
        issues.append(f"fehlende_pflichtfelder: {sorted(missing)}")

    # Enum-Checks
    t = fm.get("type")
    if t is not None and t not in ALLOWED_TYPE:
        issues.append(f"invalid_type: {t!r}")

    roles = fm.get("doc_role")
    if roles is not None:
        if not isinstance(roles, list):
            issues.append(f"doc_role_not_list: {type(roles).__name__}")
        else:
            invalid = set(roles) - ALLOWED_DOC_ROLE
            if invalid:
                issues.append(f"invalid_doc_role: {sorted(invalid)}")

    for field, allowed in [
        ("status", ALLOWED_STATUS),
        ("review_status", ALLOWED_REVIEW),
        ("confidence", ALLOWED_CONFIDENCE),
    ]:
        v = fm.get(field)
        if v is not None and v not in allowed:
            issues.append(f"invalid_{field}: {v!r}")

    # category gegen 16 Vault-Ordner
    cat = fm.get("category")
    if cat is not None and cat not in ALLOWED_CATEGORIES:
        issues.append(f"unknown_category: {cat!r}")

    # Slug-Format + Umlaute
    slug = fm.get("slug")
    if slug is not None:
        if not isinstance(slug, str):
            issues.append(f"slug_not_str: {type(slug).__name__}")
        else:
            for orig, expected in UMLAUT_PAIRS:
                if orig in slug:
                    issues.append(f"umlaut_in_slug: {orig!r} (erwartet {expected!r}) in {slug!r}")
            if not SLUG_RE.match(slug):
                issues.append(f"invalid_slug_format: {slug!r}")

    # Listen-Felder
    for field in ("sources_docs", "source_chunks", "tags", "aliases",
                  "related", "child_concepts", "merged_from", "used_in"):
        if field in fm and fm[field] is not None and not isinstance(fm[field], list):
            issues.append(f"{field}_not_list: {type(fm[field]).__name__}")

    return issues


def normalize_for_compare(value: Any) -> Any:
    """Normalisiert Werte für Vergleich (None vs [] etc.)."""
    if value is None:
        return None
    if isinstance(value, list):
        return tuple(value)  # für hashbaren Vergleich
    return value


def compare_fm(yaml_fm: dict, json_fm: dict) -> list[dict]:
    """Feld-für-Feld-Diff. Returnt Liste von {field, md_value, json_value}."""
    diffs = []
    for field in COMPARE_FIELDS:
        y = normalize_for_compare(yaml_fm.get(field))
        j = normalize_for_compare(json_fm.get(field))
        if y != j:
            diffs.append({
                "field": field,
                "md_value": yaml_fm.get(field),
                "json_value": json_fm.get(field),
            })
    return diffs


def format_value(v: Any) -> str:
    """Kompakte Darstellung für Report."""
    if v is None:
        return "*(null)*"
    if isinstance(v, list):
        if not v:
            return "`[]`"
        return "`" + repr(v) + "`"
    if isinstance(v, str):
        if len(v) > 80:
            return "`" + repr(v[:77] + "...") + "`"
        return "`" + repr(v) + "`"
    return f"`{v!r}`"


# === Main ===
#

def main() -> int:
    if not DRAFTS_DIR.exists():
        print(f"FEHLER: {DRAFTS_DIR} existiert nicht.", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Finale .md-Drafts: alles *.md außer *.body.md
    md_files = sorted(
        p for p in DRAFTS_DIR.glob("*.md")
        if not p.name.endswith(".body.md")
    )
    json_files = sorted(DRAFTS_DIR.glob("*.frontmatter.json"))

    md_by_stem = {p.stem: p for p in md_files}
    json_by_stem = {
        p.name.removesuffix(".frontmatter.json"): p
        for p in json_files
    }

    all_stems = sorted(set(md_by_stem) | set(json_by_stem))

    counters: Counter[str] = Counter()
    issue_counter: Counter[tuple[str, str]] = Counter()
    diff_field_counter: Counter[str] = Counter()
    results: list[dict] = []

    for stem in all_stems:
        record: dict[str, Any] = {
            "stem": stem,
            "has_md": stem in md_by_stem,
            "has_json": stem in json_by_stem,
            "md_issues": [],
            "json_issues": [],
            "diffs": [],
        }

        yaml_fm: dict | None = None
        json_fm: dict | None = None

        if record["has_md"]:
            yaml_fm, err = extract_yaml_from_md(md_by_stem[stem])
            if err:
                record["md_issues"].append(f"parse_error: {err}")
                counters["md_parse_error"] += 1
                issue_counter[("md", "parse_error")] += 1
            elif yaml_fm:
                schema_issues = check_schema(yaml_fm)
                record["md_issues"].extend(schema_issues)
                for issue in schema_issues:
                    issue_counter[("md", issue.split(":")[0])] += 1

        if record["has_json"]:
            json_fm, err = load_json(json_by_stem[stem])
            if err:
                record["json_issues"].append(f"parse_error: {err}")
                counters["json_parse_error"] += 1
                issue_counter[("json", "parse_error")] += 1
            elif json_fm:
                schema_issues = check_schema(json_fm)
                record["json_issues"].extend(schema_issues)
                for issue in schema_issues:
                    issue_counter[("json", issue.split(":")[0])] += 1

        if yaml_fm is not None and json_fm is not None:
            record["diffs"] = compare_fm(yaml_fm, json_fm)
            if record["diffs"]:
                counters["inconsistent_pairs"] += 1
                for d in record["diffs"]:
                    diff_field_counter[d["field"]] += 1
            else:
                counters["consistent_pairs"] += 1

        if not record["has_md"]:
            counters["missing_md"] += 1
        if not record["has_json"]:
            counters["missing_json"] += 1
        if record["md_issues"]:
            counters["md_with_issues"] += 1
        if record["json_issues"]:
            counters["json_with_issues"] += 1

        results.append(record)

    # === Report-Markdown bauen ===
    L: list[str] = []
    L.append("# Frontmatter-Check-Report")
    L.append("")
    L.append(f"**Lauf:** `{datetime.now().isoformat(timespec='seconds')}`  ")
    L.append(f"**Drafts:** `{DRAFTS_DIR}`")
    L.append("")
    L.append("## Übersicht")
    L.append("")
    L.append("| Metrik | Wert |")
    L.append("|---|---:|")
    L.append(f"| Stems gesamt (md ∪ json) | {len(all_stems)} |")
    L.append(f"| `.md` mit YAML | {len(md_files)} |")
    L.append(f"| `.frontmatter.json` | {len(json_files)} |")
    L.append(f"| ✅ Konsistente Paare | {counters['consistent_pairs']} |")
    L.append(f"| ⚠️ Inkonsistente Paare | **{counters['inconsistent_pairs']}** |")
    L.append(f"| `.md` ohne `.json` | {counters['missing_json']} |")
    L.append(f"| `.json` ohne `.md` | {counters['missing_md']} |")
    L.append(f"| YAML-Parse-Fehler | {counters['md_parse_error']} |")
    L.append(f"| JSON-Parse-Fehler | {counters['json_parse_error']} |")
    L.append(f"| `.md` mit Schema-Issues | {counters['md_with_issues']} |")
    L.append(f"| `.json` mit Schema-Issues | {counters['json_with_issues']} |")
    L.append("")

    if issue_counter:
        L.append("## Schema-Issue-Häufigkeit")
        L.append("")
        L.append("| Quelle | Issue-Typ | Anzahl |")
        L.append("|---|---|---:|")
        for (src, issue), count in issue_counter.most_common():
            L.append(f"| {src} | `{issue}` | {count} |")
        L.append("")

    if diff_field_counter:
        L.append("## Inkonsistenz-Häufigkeit pro Feld")
        L.append("")
        L.append("| Feld | Inkonsistente Paare |")
        L.append("|---|---:|")
        for field, count in diff_field_counter.most_common():
            L.append(f"| `{field}` | {count} |")
        L.append("")

    # Per-File-Details
    files_with_issues = [
        r for r in results
        if r["md_issues"] or r["json_issues"] or r["diffs"]
        or not r["has_md"] or not r["has_json"]
    ]
    if files_with_issues:
        L.append(f"## Details pro Datei mit Issues ({len(files_with_issues)})")
        L.append("")
        for r in files_with_issues:
            L.append(f"### `{r['stem']}`")
            L.append("")
            L.append(f"- `.md`: {'✓' if r['has_md'] else '✗ FEHLT'}  |  "
                     f"`.frontmatter.json`: {'✓' if r['has_json'] else '✗ FEHLT'}")
            if r["md_issues"]:
                L.append("- **`.md`-Issues:**")
                for i in r["md_issues"]:
                    L.append(f"  - {i}")
            if r["json_issues"]:
                L.append("- **`.json`-Issues:**")
                for i in r["json_issues"]:
                    L.append(f"  - {i}")
            if r["diffs"]:
                L.append("- **Diffs (`.md` ↔ `.json`):**")
                for d in r["diffs"]:
                    L.append(f"  - `{d['field']}`")
                    L.append(f"    - md:   {format_value(d['md_value'])}")
                    L.append(f"    - json: {format_value(d['json_value'])}")
            L.append("")

    REPORT_FILE.write_text("\n".join(L), encoding="utf-8")

    # === Konsolen-Summary ===
    print()
    print("=== Frontmatter-Check ===")
    print(f"Drafts:           {DRAFTS_DIR}")
    print(f"Stems gesamt:     {len(all_stems)}")
    print(f"  .md / .json:    {len(md_files)} / {len(json_files)}")
    print(f"  konsistent:     {counters['consistent_pairs']}")
    print(f"  INKONSISTENT:   {counters['inconsistent_pairs']}")
    print(f"  ohne .json:     {counters['missing_json']}")
    print(f"  ohne .md:       {counters['missing_md']}")
    print(f"Schema-Issues:    md={counters['md_with_issues']}  json={counters['json_with_issues']}")
    print(f"Parse-Fehler:     md={counters['md_parse_error']}  json={counters['json_parse_error']}")
    print(f"Report:           {REPORT_FILE}")
    print()

    has_issues = (
        counters["inconsistent_pairs"] > 0
        or counters["md_parse_error"] > 0
        or counters["json_parse_error"] > 0
        or counters["md_with_issues"] > 0
        or counters["json_with_issues"] > 0
    )
    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
