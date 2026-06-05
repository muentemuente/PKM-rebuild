#!/usr/bin/env python3
"""
apply_category_mapping.py — Wendet das freigegebene R3-Category-Mapping auf Drafts an.

Liest das Mapping aus `r3_category_mapping_proposal.md` (Single Source of Truth, vom
User freigegeben) und schreibt das gemappte `category`-Feld in jeden aktiven Draft:
  - CK_<slug>.frontmatter.json   (JSON, 2-Space-Indent erhalten)
  - CK_<slug>.md                 (category-Zeile im YAML-Frontmatter-Block)

`_hold/` ist ausgenommen (top-level glob). `.meta.json` wird nicht angefasst
(enthält kein category). Idempotent: bereits gemappte Werte werden übersprungen.

Aufruf:
  python3 scripts/apply_category_mapping.py --dry-run   # nur zeigen
  python3 scripts/apply_category_mapping.py             # anwenden

Exit-Codes:
  0 = ok   2 = Setup-Fehler (Pfade/Proposal fehlen)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
DRAFTS = DATA / "03_drafts"
PROPOSAL = DATA / "02_pipeline_output" / "r3_category_mapping_proposal.md"

EMPTY_KEY = "<leer>"


def parse_mapping(path: Path) -> dict[str, str]:
    """Liest die Mapping-Tabelle (| Ist | Count | -> Vault | Sicherheit |)."""
    mapping: dict[str, str] = {}
    in_table = False
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("| Ist-"):
            in_table = True
            continue
        if in_table:
            if not ln.startswith("|"):
                break  # Tabellenende
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) != 4 or cells[0].startswith("---"):
                continue
            ist, _count, target, _conf = cells
            ist = ist.strip("`")
            mapping[ist] = target
    return mapping


def update_json(path: Path, target: str) -> bool:
    """Setzt category in .frontmatter.json. True wenn geaendert."""
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("category") == target:
        return False
    d["category"] = target
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def update_md(path: Path, target: str) -> bool:
    """Setzt category-Zeile im ersten YAML-Frontmatter-Block. True wenn geaendert."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return False
    # Frontmatter-Ende finden
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False
    changed = False
    for i in range(1, end):
        if re.match(r"^category:", lines[i]):
            newline = f"category: {target}\n"
            if lines[i] != newline:
                lines[i] = newline
                changed = True
            break
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def current_category_json(path: Path) -> str:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return (d.get("category") or "").strip() or EMPTY_KEY


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="nur zeigen, nichts schreiben")
    args = ap.parse_args()

    if not PROPOSAL.exists():
        print(f"FEHLER: Proposal fehlt: {PROPOSAL}", file=sys.stderr)
        return 2
    if not DRAFTS.exists():
        print(f"FEHLER: Drafts fehlen: {DRAFTS}", file=sys.stderr)
        return 2

    mapping = parse_mapping(PROPOSAL)
    print(f"Mapping-Eintraege: {len(mapping)}")

    transitions: Counter[tuple[str, str]] = Counter()
    n_changed = 0
    n_skipped_same = 0
    n_unmapped = 0
    unmapped_cats: set[str] = set()

    for fj in sorted(DRAFTS.glob("CK_*.frontmatter.json")):  # top-level, _hold aus
        slug_core = fj.name[len("CK_"):-len(".frontmatter.json")]
        cur = current_category_json(fj)
        if cur not in mapping:
            n_unmapped += 1
            unmapped_cats.add(cur)
            continue
        target = mapping[cur]
        cur_real = cur if cur != EMPTY_KEY else ""
        if cur_real == target:
            n_skipped_same += 1
            continue
        transitions[(cur, target)] += 1
        if args.dry_run:
            n_changed += 1
            continue
        ch_j = update_json(fj, target)
        md = DRAFTS / f"CK_{slug_core}.md"
        ch_m = update_md(md, target) if md.exists() else False
        if ch_j or ch_m:
            n_changed += 1

    mode = "DRY-RUN" if args.dry_run else "ANGEWANDT"
    print(f"\n=== {mode} ===")
    print(f"Drafts geaendert:        {n_changed}")
    print(f"Schon korrekt (skip):    {n_skipped_same}")
    print(f"Nicht im Mapping (skip): {n_unmapped}  {sorted(unmapped_cats) if unmapped_cats else ''}")
    print(f"\nTop-Transitionen (alt -> neu):")
    for (a, b), n in transitions.most_common(20):
        print(f"  {n:3}  {a:32} -> {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
