#!/usr/bin/env python3
"""
apply_tag_map.py — wendet das kuratierte Tag-Vokabular auf einen Ziel-Baum an.

Zweck:
  Letzter Verarbeitungsschritt vor dem Obsidian-Umzug. Pro .md im Ziel:
    1. tags lesen (YAML-Frontmatter)
    2. remap anwenden (Synonym -> Survivor)
    3. drop-Tags entfernen
    4. deduplizieren, Reihenfolge stabil
    5. nur Tags aus dem Vokabular behalten (tag-system.md)
  Nur das tags-Feld wird angefasst. Restliches Frontmatter + Body bleiben
  byte-identisch (gezielte Block-Ersetzung, kein YAML-Roundtrip).

Sicherheit:
  - DRY-RUN ist Default. Schreiben nur mit --apply.
  - --apply legt VORHER einen tar.gz-Snapshot des Ziels an (backup-before-write).
  - Idempotent: zweiter Lauf erzeugt keine weiteren Änderungen.

Aufruf:
  python3 scripts/apply_tag_map.py                 # dry-run auf 04_vault
  python3 scripts/apply_tag_map.py --apply         # schreibt + Backup
  python3 scripts/apply_tag_map.py --target 03_drafts

Exit:
  0 = nichts zu tun ODER apply erfolgreich
  1 = Änderungen ausstehend (dry-run) ODER Vokabular-Verstoß nach remap
  2 = Setup-Fehler (Pfade, fehlende Map/Vocab, Dependencies)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FEHLER: pyyaml fehlt. pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
REPO_ROOT = Path.home() / "projects" / "aktiv" / "PKM-rebuild"
BACKUP_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "backups"

FM_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
# tags-Block: ab 'tags:' bis zur nächsten Top-Level-Key-Zeile oder FM-Ende
TAGS_BLOCK_RE = re.compile(
    r"(?m)^tags:[ \t]*(?:\n(?:[ \t]+.*(?:\n|$)|[ \t]*-[ \t].*(?:\n|$))*|.*\n)"
)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def load_map(path: Path) -> tuple[set[str], dict[str, str], set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    vocab = {nfc(t) for t in data.get("vocabulary", [])}
    remap = {nfc(k): nfc(v) for k, v in data.get("remap", {}).items()}
    drop = {nfc(t) for t in data.get("drop", [])}
    return vocab, remap, drop


def load_vocab_md(path: Path) -> set[str]:
    """Vokabular aus tag-system.md ziehen (Zeilen wie '- `tag`')."""
    txt = path.read_text(encoding="utf-8")
    return {nfc(m) for m in re.findall(r"^\s*-\s+`([a-z0-9][a-z0-9-]*)`", txt, re.M)}


def extract_tags(fm_text: str) -> list[str] | None:
    """tags-Liste aus Frontmatter-Text lesen (inline oder block)."""
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or "tags" not in data:
        return None
    t = data["tags"]
    if t is None:
        return []
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [str(x) for x in t]
    return None


def transform(tags: list[str], vocab, remap, drop) -> tuple[list[str], list[str]]:
    """Returnt (neue_tags, verworfene_unbekannte)."""
    out: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        t = nfc(raw.strip().strip('"').strip("'"))
        if not t or t in drop:
            continue
        t = remap.get(t, t)
        if t in vocab:
            if t not in seen:
                seen.add(t)
                out.append(t)
        else:
            unknown.append(t)
    return out, unknown


def render_tags_block(tags: list[str]) -> str:
    if not tags:
        return "tags: []\n"
    lines = ["tags:"]
    lines += [f"  - {t}" for t in tags]
    return "\n".join(lines) + "\n"


def process_file(path: Path, vocab, remap, drop):
    """Returnt dict mit before/after/unknown/changed/error."""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return {"error": "no_frontmatter"}
    fm = m.group(1)
    before = extract_tags(fm)
    if before is None:
        return {"error": "no_tags_or_parse"}
    after, unknown = transform(before, vocab, remap, drop)
    changed = [nfc(x) for x in before] != after

    new_text = None
    if changed:
        block = render_tags_block(after)
        if TAGS_BLOCK_RE.search(fm):
            new_fm = TAGS_BLOCK_RE.sub(block, fm, count=1)
        else:  # tags fehlten als Block -> ans Ende des FM
            new_fm = fm + block
        new_text = f"---\n{new_fm}---\n" + text[m.end():]
    return {
        "before": before, "after": after, "unknown": unknown,
        "changed": changed, "new_text": new_text, "error": None,
    }


def iter_targets(target_dir: Path):
    for p in sorted(target_dir.rglob("*.md")):
        if p.name == "_index.md":
            continue
        if "00_Meta" in p.parts:
            continue
        if "_hold" in p.parts:
            continue
        yield p


def make_backup(target_dir: Path) -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"pre_tagapply_{target_dir.name}_{ts}.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(target_dir, arcname=target_dir.name)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="04_vault",
                    help="Unterordner in data/ (default 04_vault)")
    ap.add_argument("--map", default=str(REPO_ROOT / "scripts" / "tag_merge_map.json"))
    ap.add_argument("--vocab", default=None,
                    help="tag-system.md (default: <target>/00_Meta/tag-system.md)")
    ap.add_argument("--apply", action="store_true", help="schreibt + Backup (sonst dry-run)")
    args = ap.parse_args()

    target_dir = DATA_ROOT / args.target
    if not target_dir.exists():
        print(f"FEHLER: {target_dir} fehlt.", file=sys.stderr)
        return 2

    map_path = Path(args.map)
    if not map_path.exists():
        print(f"FEHLER: Merge-Map fehlt: {map_path}", file=sys.stderr)
        return 2
    vocab_json, remap, drop = load_map(map_path)

    vocab_md_path = Path(args.vocab) if args.vocab else target_dir / "00_Meta" / "tag-system.md"
    vocab = vocab_json
    if vocab_md_path.exists():
        vmd = load_vocab_md(vocab_md_path)
        if vmd and vmd != vocab_json:
            only_md, only_json = vmd - vocab_json, vocab_json - vmd
            print(f"WARNUNG: tag-system.md ≠ map.vocabulary  "
                  f"(nur_md={len(only_md)}, nur_json={len(only_json)})", file=sys.stderr)
        vocab = vmd or vocab_json
    else:
        print(f"WARNUNG: {vocab_md_path} fehlt, nutze map.vocabulary als Whitelist.", file=sys.stderr)

    changed_files: list[tuple[Path, dict]] = []
    unknown_counter: Counter[str] = Counter()
    errors: list[tuple[Path, str]] = []
    n = 0
    for p in iter_targets(target_dir):
        n += 1
        r = process_file(p, vocab, remap, drop)
        if r.get("error"):
            errors.append((p, r["error"]))
            continue
        for u in r["unknown"]:
            unknown_counter[u] += 1
        if r["changed"]:
            changed_files.append((p, r))

    # Report
    print("\n=== apply_tag_map ===")
    print(f"Ziel:            {target_dir}")
    print(f"Modus:           {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Files gescannt:  {n}")
    print(f"Mit Änderungen:  {len(changed_files)}")
    print(f"Parse-Fehler:    {len(errors)}")
    print(f"Vokabular:       {len(vocab)} Tags")
    if unknown_counter:
        print(f"\nUnbekannt nach remap (NICHT im Vokabular, würden entfernt): "
              f"{len(unknown_counter)}")
        for t, c in unknown_counter.most_common(20):
            print(f"  {t}: {c}")

    for p, r in changed_files[:30]:
        print(f"\n  {p.relative_to(target_dir)}")
        print(f"    - {sorted(set(nfc(x) for x in r['before']))}")
        print(f"    + {r['after']}")
    if len(changed_files) > 30:
        print(f"\n  … {len(changed_files)-30} weitere")

    if errors:
        print("\nFEHLER-Files:")
        for p, e in errors:
            print(f"  {e}: {p.relative_to(target_dir)}")

    if args.apply and changed_files:
        bak = make_backup(target_dir)
        print(f"\nBackup: {bak}")
        for p, r in changed_files:
            p.write_text(r["new_text"], encoding="utf-8")
        print(f"Geschrieben: {len(changed_files)} Files")
        return 0

    if changed_files:
        print("\nDRY-RUN — nichts geschrieben. Mit --apply ausführen.")
        return 1
    print("\nNichts zu tun (idempotent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
