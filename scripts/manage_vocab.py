#!/usr/bin/env python3
"""manage_vocab.py — Vokabular-Pflege für category und Tags (idempotent).

Hält das kontrollierte Vokabular über die verstreuten Stellen hinweg konsistent:

  category:
    - kanonisch:  config/categories.yaml             (Single Source, _paths.CATEGORIES_FILE)
    - abgeleitet: pipeline.phase_9_vault_build.CATEGORY_TO_FOLDER (lädt aus categories.yaml)
                  + scripts/_pkm_common.ALLOWED_CATEGORIES (= set(CATEGORY_TO_FOLDER))
    - physisch:   output/<NN_Folder>/               (Vault-Ordner, _paths.OUTPUT)
    - Doku:       docs/03_vault_standard.md §4 (Ordner-Hierarchie)

  tags:
    - kanonisch:  config/tag_vocabulary.yaml         (Single Source, _paths.TAG_VOCABULARY_FILE)

Neue Kategorien werden ausschließlich in config/categories.yaml angelegt (+ Ordner);
CATEGORY_TO_FOLDER und ALLOWED_CATEGORIES leiten sich daraus ab (Drift unmöglich,
kein Code-Editieren mehr).

Befehle:
  add-category <name>            neue category konsistent anlegen
  add-tag <tag> --reason "..."   neuen Tag ins Kern-Vokabular aufnehmen (mit Begründung)
  list                           aktuelles Vokabular zeigen
  validate                       Drift prüfen (Ordner fehlen? Tags außerhalb Vokabular?)

Aufruf:
  python3 scripts/manage_vocab.py list
  python3 scripts/manage_vocab.py add-category business --dry-run
  python3 scripts/manage_vocab.py add-tag observability --reason "Monitoring/Tracing-Thema"
  python3 scripts/manage_vocab.py validate

Exit-Codes: 0 = ok, 1 = Validierungsfehler/Drift, 2 = Argument-/Setup-Fehler.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths  # noqa: E402
from pipeline.taxonomy import folder_display_name, write_category_mapping  # noqa: E402
from pipeline.vocab import load_tag_vocabulary_yaml  # noqa: E402
from scripts._pkm_common import SLUG_RE, parse_yaml_text, split_md  # noqa: E402

# === Pfade (Defaults; in Tests überschreibbar) — zentral aus pipeline._paths ===
_REPO = _paths.REPO_ROOT
CATEGORIES_PATH = _paths.CATEGORIES_FILE
VAULT_STD_PATH = _REPO / "docs" / "03_vault_standard.md"
VAULT_DIR = _paths.OUTPUT
DRAFTS_DIR = _paths.DRAFTS
# Tag-Vokabular: YAML-Single-Source (config/tag_vocabulary.yaml). Der Parameter
# heißt aus Bestands-Gründen weiter `tag_system_path`; md-Format bleibt als Input
# unterstützt (Bestands-Fixtures).
TAG_SYSTEM_PATH = _paths.TAG_VOCABULARY_FILE

# === category ================================================================


def parse_category_mapping(categories_path: Path = CATEGORIES_PATH) -> dict[str, str]:
    """Liest das category→Ordner-Mapping aus config/categories.yaml (Single Source)."""
    data = yaml.safe_load(categories_path.read_text(encoding="utf-8")) or {}
    return dict(data.get("categories") or {})


def _next_folder_number(mapping: dict[str, str]) -> int:
    """Nächste freie NN_-Nummer (max vorhandene + 1)."""
    nums = [int(v[:2]) for v in mapping.values() if v[:2].isdigit()]
    return (max(nums) + 1) if nums else 0


def add_category(
    name: str,
    *,
    categories_path: Path = CATEGORIES_PATH,
    vault_dir: Path = VAULT_DIR,
    vault_standard_path: Path = VAULT_STD_PATH,
    dry_run: bool = False,
) -> dict[str, object]:
    """Legt eine neue category konsistent an (idempotent).

    Returns: dict mit category, folder, created (bool), already (bool), changed-Liste.
    """
    if not SLUG_RE.match(name):
        raise ValueError(f"ungültiger category-Slug: {name!r} (erlaubt: a-z0-9, Bindestriche)")

    mapping = parse_category_mapping(categories_path)
    if name in mapping:
        return {"category": name, "folder": mapping[name], "already": True, "changed": []}

    num = _next_folder_number(mapping)
    folder = f"{num:02d}_{folder_display_name(name)}"
    changed: list[str] = []

    if dry_run:
        return {
            "category": name,
            "folder": folder,
            "already": False,
            "dry_run": True,
            "changed": [
                "config/categories.yaml",
                "ALLOWED_CATEGORIES (abgeleitet)",
                "vault-folder",
                "doc §4",
            ],
        }

    # 1. config/categories.yaml ergänzen (Single Source; CATEGORY_TO_FOLDER +
    #    ALLOWED_CATEGORIES leiten sich daraus ab). Reihenfolge + Header erhalten.
    mapping[name] = folder
    write_category_mapping(mapping, categories_path)
    changed.append("config/categories.yaml")

    # 2. Vault-Ordner anlegen
    (vault_dir / folder).mkdir(parents=True, exist_ok=True)
    changed.append(f"vault-folder:{folder}")

    # 3. Doku §4 Ordner-Hierarchie (best-effort; Anker: '└── _attic/')
    if vault_standard_path.exists():
        doc = vault_standard_path.read_text(encoding="utf-8")
        anchor = "└── _attic/"
        if f"{folder}/" not in doc and anchor in doc:
            line = f"├── {folder}/                        ← (via manage_vocab)\n"
            doc = doc.replace(anchor, line + anchor, 1)
            doc = _bump_updated(doc)
            vault_standard_path.write_text(doc, encoding="utf-8")
            changed.append("doc:03_vault_standard §4")

    return {"category": name, "folder": folder, "already": False, "changed": changed}


# === tags ====================================================================

_KERN = "## Kern-Vokabular"
_SYNONYM = "## Synonym-Map"
_EXT_HEADER = "### Erweiterungen (manage_vocab)"
_EXT_TABLE = "| Tag | Begründung | Datum |\n|---|---|---|\n"


def parse_tag_vocab(tag_system_path: Path = TAG_SYSTEM_PATH) -> set[str]:
    """Alle kanonischen Tags. YAML-Single-Source oder (Fallback) md-Bereich Kern-Vokabular."""
    if tag_system_path.suffix in (".yaml", ".yml"):
        vocab, _ = load_tag_vocabulary_yaml(tag_system_path)
        return vocab
    content = tag_system_path.read_text(encoding="utf-8")
    kern = content.find(_KERN)
    if kern == -1:
        return set()
    syn = content.find(_SYNONYM, kern)
    section = content[kern:syn] if syn != -1 else content[kern:]
    return set(re.findall(r"`([^`]+)`", section))


# Default-Sektion für governed growth (E1=A): neu aufgenommene Tags ohne explizite
# Themen-Sektion landen hier (legt sich an, falls noch nicht vorhanden).
_DEFAULT_GROWTH_SECTION = "Erweiterungen"


def add_tag(
    tag: str,
    reason: str,
    *,
    tag_system_path: Path = TAG_SYSTEM_PATH,
    section: str = _DEFAULT_GROWTH_SECTION,
    md_doc_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Nimmt einen neuen Tag mit Begründung ins Vokabular auf (idempotent).

    YAML-Pfad (config/tag_vocabulary.yaml) = governed growth (E1=A): schreibt den
    Tag DIREKT ins SSoT (Sektion ``section`` + ``changelog``-Eintrag mit ``reason``)
    und hält das md-Doc ``md_doc_path`` (Default ``_paths.TAG_SYSTEM_DOC``) synchron.
    md-Pfad = Legacy-Verhalten (nur md-Tabelle). ``reason`` ist Pflicht und wird
    persistiert. Re-Add eines vorhandenen Tags = No-op (``already=True``), kein Dup.
    """
    if not SLUG_RE.match(tag):
        raise ValueError(f"ungültiger Tag: {tag!r} (kleingeschrieben, a-z0-9, Bindestriche)")
    if "`" in reason or "|" in reason:
        raise ValueError("Begründung darf kein '`' oder '|' enthalten")
    if not reason.strip():
        raise ValueError("Begründung (--reason) ist Pflicht")

    if tag_system_path.suffix in (".yaml", ".yml"):
        return _add_tag_yaml(
            tag, reason.strip(), tag_system_path, section, md_doc_path, dry_run
        )

    vocab = parse_tag_vocab(tag_system_path)
    if tag in vocab:
        return {"tag": tag, "already": True, "changed": []}
    if dry_run:
        return {"tag": tag, "already": False, "dry_run": True, "changed": ["tag-system.md"]}

    tag_system_path.write_text(
        _append_tag_to_md(tag_system_path.read_text(encoding="utf-8"), tag, reason),
        encoding="utf-8",
    )
    return {"tag": tag, "already": False, "changed": ["tag-system.md"]}


def _add_tag_yaml(
    tag: str,
    reason: str,
    tag_vocab_path: Path,
    section: str,
    md_doc_path: Path | None,
    dry_run: bool,
) -> dict[str, object]:
    """E1=A: Tag direkt ins YAML-SSoT + md-Doc-Sync (siehe add_tag)."""
    vocab, synonyms = load_tag_vocabulary_yaml(tag_vocab_path)
    if tag in vocab:
        return {"tag": tag, "already": True, "changed": []}
    if tag in synonyms:
        raise ValueError(
            f"{tag!r} ist als Synonym/Alias geführt (→ {synonyms[tag]!r}); "
            "kein neuer kanonischer Tag"
        )

    md = md_doc_path or _paths.TAG_SYSTEM_DOC
    md_will_sync = md.exists()
    changed: list[str] = ["config/tag_vocabulary.yaml"]
    if md_will_sync:
        changed.append(md.name)

    if dry_run:
        return {"tag": tag, "already": False, "dry_run": True, "changed": changed,
                "md_synced": md_will_sync}

    text = tag_vocab_path.read_text(encoding="utf-8")
    text = _yaml_insert_tag(text, section, tag)
    text = _yaml_append_changelog(text, tag, reason, date.today().isoformat())
    tag_vocab_path.write_text(text, encoding="utf-8")

    md_synced = False
    if md_will_sync:
        md.write_text(_append_tag_to_md(md.read_text(encoding="utf-8"), tag, reason), encoding="utf-8")
        md_synced = True
    return {"tag": tag, "already": False, "changed": changed, "md_synced": md_synced}


def _find_section_index(lines: list[str], section: str) -> int | None:
    """Index der Sektions-Kopfzeile (2-Space-Indent), quoted oder unquoted."""
    targets = {f"{section}:", f'"{section}":', f"'{section}':"}
    for i, ln in enumerate(lines):
        if ln.startswith("  ") and not ln.startswith("    ") and ln.strip() in targets:
            return i
    return None


def _sections_block_end(lines: list[str]) -> int:
    """Einfügeindex für eine neue Sektion: direkt vor dem ``synonyms``-Block (inkl. Kommentaren)."""
    syn_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("synonyms:")), len(lines)
    )
    k = syn_idx
    while k - 1 >= 0 and (lines[k - 1].lstrip().startswith("#") or lines[k - 1].strip() == ""):
        k -= 1
    return k


def _yaml_insert_tag(text: str, section: str, tag: str) -> str:
    """Fügt ``tag`` (sortiert, dedup) in ``section`` ein; legt die Sektion an, falls nötig."""
    lines = text.splitlines()
    sec_idx = _find_section_index(lines, section)
    if sec_idx is not None:
        j = sec_idx + 1
        item_idxs: list[int] = []
        while j < len(lines) and lines[j].startswith("    - "):
            item_idxs.append(j)
            j += 1
        existing = [lines[k].strip()[2:].strip() for k in item_idxs]
        merged = sorted(set(existing) | {tag})
        rebuilt = [f"    - {t}" for t in merged]
        lines = lines[: sec_idx + 1] + rebuilt + lines[j:]
    else:
        ins = _sections_block_end(lines)
        lines = lines[:ins] + [f"  {section}:", f"    - {tag}", ""] + lines[ins:]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _yaml_append_changelog(text: str, tag: str, reason: str, day: str) -> str:
    """Hängt einen ``changelog``-Eintrag (Tag/Reason/Datum) an — persistiert die Begründung."""
    entry = (
        f"  - tag: {tag}\n"
        f"    reason: {json.dumps(reason, ensure_ascii=False)}\n"
        f"    date: {day}"
    )
    body = text.rstrip("\n")
    if re.search(r"^changelog:", text, re.MULTILINE):
        return body + "\n" + entry + "\n"
    return body + "\n\nchangelog:\n" + entry + "\n"


def _append_tag_to_md(content: str, tag: str, reason: str) -> str:
    """Hängt ``tag`` an die ``### Erweiterungen``-Tabelle in tag-system.md an (md-Sync)."""
    syn = content.find(_SYNONYM)
    if syn == -1:
        raise ValueError("tag-system.md ohne '## Synonym-Map' — unerwartetes Format")
    row = f"| `{tag}` | {reason.strip()} | {date.today().isoformat()} |\n"
    if _EXT_HEADER in content[:syn]:
        insert_at = content.rfind("\n", 0, syn)  # Leerzeile vor Synonym-Map
        block = content[:insert_at] + "\n" + row.rstrip("\n") + content[insert_at:]
    else:
        new_section = f"\n{_EXT_HEADER}\n\n{_EXT_TABLE}{row}\n---\n\n"
        block = content[:syn] + new_section + content[syn:]
    return _bump_updated(block)


# === validate / list =========================================================


def validate(
    *,
    categories_path: Path = CATEGORIES_PATH,
    vault_dir: Path = VAULT_DIR,
    drafts_dir: Path = DRAFTS_DIR,
    tag_system_path: Path = TAG_SYSTEM_PATH,
    vault_standard_path: Path = VAULT_STD_PATH,
) -> dict[str, list[str]]:
    """Prüft Drift. Returns dict mit Listen 'category_issues' und 'tag_issues' (leer = ok)."""
    cat_issues: list[str] = []
    tag_issues: list[str] = []

    mapping = parse_category_mapping(categories_path)
    used_tags, used_categories = _collect_used_tags_and_categories(vault_dir, drafts_dir)

    # category: nur tatsächlich belegte Kategorien (≥1 Artikel) verlangen einen Ordner.
    # Definierte, aber unbenutzte Kategorien sind kein Drift (Ordner wird erst bei
    # Belegung vom Builder angelegt).
    for cat, folder in sorted(mapping.items()):
        if cat in used_categories and not (vault_dir / folder).is_dir():
            cat_issues.append(f"Vault-Ordner fehlt für belegte category '{cat}': {folder}/")

    # category: Doku §4 sollte jeden Ordner führen (Doku-Vollständigkeit, unabhängig von Belegung)
    if vault_standard_path.exists():
        doc = vault_standard_path.read_text(encoding="utf-8")
        for cat, folder in sorted(mapping.items()):
            if f"{folder}/" not in doc:
                cat_issues.append(f"Doku §4 führt Ordner nicht: {folder}/ (category '{cat}')")

    # tags: alle in Vault/Drafts verwendeten Tags müssen im Vokabular sein
    vocab = parse_tag_vocab(tag_system_path)
    for tag in sorted(used_tags - vocab):
        tag_issues.append(f"Tag nicht im Vokabular: '{tag}'")

    return {"category_issues": cat_issues, "tag_issues": tag_issues}


def _collect_used_tags_and_categories(
    vault_dir: Path, drafts_dir: Path
) -> tuple[set[str], set[str]]:
    """Tags + category-Werte aus allen Frontmattern in Vault (ohne _index) + aktiven Drafts."""
    tags_used: set[str] = set()
    cats_used: set[str] = set()
    md_files: list[Path] = []
    if vault_dir.exists():
        md_files += [p for p in vault_dir.rglob("*.md") if p.name != "_index.md"]
    if drafts_dir.exists():
        md_files += [p for p in drafts_dir.glob("*.md") if not p.name.endswith(".body.md")]
    for p in md_files:
        fm_yaml, _ = split_md(p.read_text(encoding="utf-8"))
        if fm_yaml is None:
            continue
        data, _err = parse_yaml_text(fm_yaml)
        if not data:
            continue
        tags = data.get("tags")
        if isinstance(tags, list):
            tags_used.update(str(t) for t in tags)
        cat = data.get("category")
        if isinstance(cat, str) and cat:
            cats_used.add(cat)
    return tags_used, cats_used


def list_vocab(
    *,
    categories_path: Path = CATEGORIES_PATH,
    tag_system_path: Path = TAG_SYSTEM_PATH,
) -> dict[str, Any]:
    """Aktuelles Vokabular als dict (categories: {cat: folder}, tags: sorted list)."""
    mapping = parse_category_mapping(categories_path)
    vocab = parse_tag_vocab(tag_system_path) if tag_system_path.exists() else set()
    return {"categories": mapping, "tags": sorted(vocab)}


# === Helfer ==================================================================


def _bump_updated(doc: str) -> str:
    """Setzt das `updated:`-Frontmatter-Feld auf heute (erste Vorkommnis)."""
    return re.sub(
        r"^updated:.*$",
        f"updated: {date.today().isoformat()}",
        doc,
        count=1,
        flags=re.MULTILINE,
    )


# === CLI =====================================================================


def _cmd_add_category(args: argparse.Namespace) -> int:
    try:
        res = add_category(args.name, dry_run=args.dry_run)
    except ValueError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 2
    changed = res.get("changed") or []
    changed_str = ", ".join(str(c) for c in changed) if isinstance(changed, list) else ""
    if res.get("already"):
        print(f"category '{res['category']}' existiert bereits → {res['folder']} (no-op)")
    elif res.get("dry_run"):
        print(f"[dry-run] würde anlegen: '{res['category']}' → {res['folder']}/")
        print(f"          Stellen: {changed_str}")
    else:
        print(f"category '{res['category']}' → {res['folder']}/ angelegt")
        print(f"  geändert: {changed_str}")
        print("  Hinweis: Appendix-A-Tabelle in 03_vault_standard.md ggf. manuell ergänzen.")
    return 0


def _cmd_add_tag(args: argparse.Namespace) -> int:
    try:
        res = add_tag(args.tag, args.reason, dry_run=args.dry_run)
    except ValueError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 2
    if res.get("already"):
        print(f"Tag '{res['tag']}' ist bereits im Vokabular (no-op)")
    elif res.get("dry_run"):
        print(f"[dry-run] würde Tag '{res['tag']}' aufnehmen")
    else:
        print(f"Tag '{res['tag']}' ins Kern-Vokabular aufgenommen")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    v = list_vocab()
    categories = v["categories"]
    tags = v["tags"]
    assert isinstance(categories, dict)
    assert isinstance(tags, list)
    print("== Kategorien (category → Ordner) ==")
    for cat, folder in categories.items():
        print(f"  {cat:45} {folder}")
    print(f"\n== Tags ({len(tags)}) ==")
    print("  " + " · ".join(tags))
    return 0


def _cmd_validate(_args: argparse.Namespace) -> int:
    vres = validate()
    issues = vres["category_issues"] + vres["tag_issues"]
    if not issues:
        print("✓ Vokabular konsistent (Kategorien + Tags, keine Drift).")
        return 0
    print("⚠️ Drift gefunden:")
    for i in issues:
        print(f"  - {i}")
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vokabular-Pflege (category + tags).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cat = sub.add_parser("add-category", help="neue category anlegen")
    p_cat.add_argument("name")
    p_cat.add_argument("--dry-run", action="store_true")

    p_tag = sub.add_parser("add-tag", help="neuen Tag ins Vokabular aufnehmen")
    p_tag.add_argument("tag")
    p_tag.add_argument("--reason", required=True, help="Begründung (Pflicht, Vault-Standard §7)")
    p_tag.add_argument("--dry-run", action="store_true")

    sub.add_parser("list", help="Vokabular zeigen")
    sub.add_parser("validate", help="Drift prüfen")

    args = ap.parse_args(argv)

    handlers = {
        "add-category": _cmd_add_category,
        "add-tag": _cmd_add_tag,
        "list": _cmd_list,
        "validate": _cmd_validate,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
