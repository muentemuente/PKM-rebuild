#!/usr/bin/env python3
"""manage_vocab.py — Vokabular-Pflege für category und Tags (idempotent).

Hält das kontrollierte Vokabular über die verstreuten Stellen hinweg konsistent:

  category:
    - kanonisch:  pipeline/phase_9_vault_build.py  → CATEGORY_TO_FOLDER
    - abgeleitet: scripts/_pkm_common.py            → ALLOWED_CATEGORIES (= set(CATEGORY_TO_FOLDER))
    - physisch:   output/<NN_Folder>/               (Vault-Ordner, _paths.OUTPUT)
    - Doku:       docs/03_vault_standard.md §4 (Ordner-Hierarchie)

  tags:
    - kanonisch:  config/tag_vocabulary.yaml         (Single Source, _paths.TAG_VOCABULARY_FILE)

Da `ALLOWED_CATEGORIES` direkt aus `CATEGORY_TO_FOLDER` abgeleitet wird, genügt für
neue Kategorien ein Edit am Dict-Literal + Ordner-Anlage; die Skript-Seite folgt
automatisch (Drift unmöglich).

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
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths  # noqa: E402
from pipeline.vocab import load_tag_vocabulary_yaml  # noqa: E402
from scripts._pkm_common import SLUG_RE, parse_yaml_text, split_md  # noqa: E402

# === Pfade (Defaults; in Tests überschreibbar) — zentral aus pipeline._paths ===
_REPO = _paths.REPO_ROOT
PHASE9_PATH = _REPO / "pipeline" / "phase_9_vault_build.py"
VAULT_STD_PATH = _REPO / "docs" / "03_vault_standard.md"
VAULT_DIR = _paths.OUTPUT
DRAFTS_DIR = _paths.DRAFTS
# Tag-Vokabular: YAML-Single-Source (config/tag_vocabulary.yaml). Der Parameter
# heißt aus Bestands-Gründen weiter `tag_system_path`; md-Format bleibt als Input
# unterstützt (Bestands-Fixtures).
TAG_SYSTEM_PATH = _paths.TAG_VOCABULARY_FILE

# Kleine Wörter, die im Ordner-Anzeigenamen kleingeschrieben bleiben (Stil der Bestands-Ordner)
_LOWER_TOKENS = {"und", "oder", "der", "die", "das", "von", "zu", "mit", "für", "im", "am"}

_DICT_MARKER = "CATEGORY_TO_FOLDER: dict[str, str] = {"
_ENTRY_RE = re.compile(r'"([a-z0-9-]+)":\s*"([^"]+)"')


# === category ================================================================


def parse_category_mapping(phase9_path: Path = PHASE9_PATH) -> dict[str, str]:
    """Liest CATEGORY_TO_FOLDER direkt aus dem Quelltext (category → Ordner)."""
    src = phase9_path.read_text(encoding="utf-8")
    start = src.index(_DICT_MARKER)
    end = src.index("\n}", start)
    block = src[start:end]
    return dict(_ENTRY_RE.findall(block))


def _folder_display_name(slug: str) -> str:
    """Slug → Ordner-Anzeigename im Stil der Bestands-Ordner (Token-Caps, kleine Wörter klein)."""
    parts = []
    for tok in slug.split("-"):
        parts.append(tok if tok in _LOWER_TOKENS else tok.capitalize())
    return "-".join(parts)


def _next_folder_number(mapping: dict[str, str]) -> int:
    """Nächste freie NN_-Nummer (max vorhandene + 1)."""
    nums = [int(v[:2]) for v in mapping.values() if v[:2].isdigit()]
    return (max(nums) + 1) if nums else 0


def add_category(
    name: str,
    *,
    phase9_path: Path = PHASE9_PATH,
    vault_dir: Path = VAULT_DIR,
    vault_standard_path: Path = VAULT_STD_PATH,
    dry_run: bool = False,
) -> dict[str, object]:
    """Legt eine neue category konsistent an (idempotent).

    Returns: dict mit category, folder, created (bool), already (bool), changed-Liste.
    """
    if not SLUG_RE.match(name):
        raise ValueError(f"ungültiger category-Slug: {name!r} (erlaubt: a-z0-9, Bindestriche)")

    mapping = parse_category_mapping(phase9_path)
    if name in mapping:
        return {"category": name, "folder": mapping[name], "already": True, "changed": []}

    num = _next_folder_number(mapping)
    folder = f"{num:02d}_{_folder_display_name(name)}"
    changed: list[str] = []

    if dry_run:
        return {
            "category": name,
            "folder": folder,
            "already": False,
            "dry_run": True,
            "changed": ["CATEGORY_TO_FOLDER", "ALLOWED_CATEGORIES (abgeleitet)", "vault-folder", "doc §4"],
        }

    # 1. CATEGORY_TO_FOLDER-Literal ergänzen (ALLOWED_CATEGORIES folgt automatisch)
    src = phase9_path.read_text(encoding="utf-8")
    start = src.index(_DICT_MARKER)
    close = src.index("\n}", start)  # '\n' direkt vor schließendem '}'
    entry = f'    "{name}": "{folder}",\n'
    src = src[: close + 1] + entry + src[close + 1 :]
    phase9_path.write_text(src, encoding="utf-8")
    changed.append("CATEGORY_TO_FOLDER")

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


def add_tag(
    tag: str,
    reason: str,
    *,
    tag_system_path: Path = TAG_SYSTEM_PATH,
    dry_run: bool = False,
) -> dict[str, object]:
    """Nimmt einen neuen Tag mit Begründung ins Kern-Vokabular auf (idempotent)."""
    if not SLUG_RE.match(tag):
        raise ValueError(f"ungültiger Tag: {tag!r} (kleingeschrieben, a-z0-9, Bindestriche)")
    if "`" in reason or "|" in reason:
        raise ValueError("Begründung darf kein '`' oder '|' enthalten")
    if not reason.strip():
        raise ValueError("Begründung (--reason) ist Pflicht")

    # YAML-Single-Source: das Schreiben neuer Tags ins config/tag_vocabulary.yaml
    # läuft über Gate C (pkm review --apply, WP4). add_tag bleibt auf das md-Format
    # beschränkt (Bestands-Tool); für YAML klar verweisen statt das kuratierte File
    # zu überschreiben.
    if tag_system_path.suffix in (".yaml", ".yml"):
        raise ValueError(
            "Tag-Aufnahme ins YAML-Vokabular läuft über `pkm review` (Gate C). "
            "manage_vocab add-tag unterstützt nur das md-Format."
        )

    vocab = parse_tag_vocab(tag_system_path)
    if tag in vocab:
        return {"tag": tag, "already": True, "changed": []}
    if dry_run:
        return {"tag": tag, "already": False, "dry_run": True, "changed": ["tag-system.md"]}

    content = tag_system_path.read_text(encoding="utf-8")
    syn = content.find(_SYNONYM)
    if syn == -1:
        raise ValueError("tag-system.md ohne '## Synonym-Map' — unerwartetes Format")

    row = f"| `{tag}` | {reason.strip()} | {date.today().isoformat()} |\n"
    if _EXT_HEADER in content[:syn]:
        # Tabelle existiert → Zeile vor ## Synonym-Map anhängen
        insert_at = content.rfind("\n", 0, syn)  # Leerzeile vor Synonym-Map
        block = content[:insert_at] + "\n" + row.rstrip("\n") + content[insert_at:]
    else:
        new_section = f"\n{_EXT_HEADER}\n\n{_EXT_TABLE}{row}\n---\n\n"
        block = content[:syn] + new_section + content[syn:]

    block = _bump_updated(block)
    tag_system_path.write_text(block, encoding="utf-8")
    return {"tag": tag, "already": False, "changed": ["tag-system.md"]}


# === validate / list =========================================================


def validate(
    *,
    phase9_path: Path = PHASE9_PATH,
    vault_dir: Path = VAULT_DIR,
    drafts_dir: Path = DRAFTS_DIR,
    tag_system_path: Path = TAG_SYSTEM_PATH,
    vault_standard_path: Path = VAULT_STD_PATH,
) -> dict[str, list[str]]:
    """Prüft Drift. Returns dict mit Listen 'category_issues' und 'tag_issues' (leer = ok)."""
    cat_issues: list[str] = []
    tag_issues: list[str] = []

    mapping = parse_category_mapping(phase9_path)
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
    phase9_path: Path = PHASE9_PATH,
    tag_system_path: Path = TAG_SYSTEM_PATH,
) -> dict[str, Any]:
    """Aktuelles Vokabular als dict (categories: {cat: folder}, tags: sorted list)."""
    mapping = parse_category_mapping(phase9_path)
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
