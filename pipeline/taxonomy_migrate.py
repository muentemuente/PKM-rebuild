"""Taxonomie-Migration — Vault-Mutation bei ``category``/``tag``-Rename.

Hält die SSoT (``config/``-YAMLs) und den bestehenden Vault konsistent, wenn eine
Kategorie oder ein Tag umbenannt wird. Reicht über das reine Anlegen
(``scripts/manage_vocab`` add-category/add-tag) hinaus, weil bei einem Rename
**Bestandsdaten** mitgezogen werden müssen:

* ``rename_category``: SSoT-Key + Vault-Ordner-Move + ``category``-Frontmatter
  (Vault-``.md`` und Draft-``.md``/``.frontmatter.json``) + ``_index.md``-Regen
  + Validierung (Frontmatter gegen ``FrontmatterDraft``, Wikilinks auflösbar, §10).
* ``rename_tag``: SSoT (Tag → Synonym auf den neuen Namen) + ``tags``-Frontmatter.

Alle Funktionen sind **pfad-parametrisiert** (``vault_dir``/``drafts_dir``/
``categories_path``/``tag_vocab_path``) — Migrationen laufen in Tests nur gegen
Fixtures, nie blind gegen ``data``/``output``. ``dry_run=True`` plant ohne Schreiben.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from pipeline import _paths, taxonomy
from pipeline.phase_9_vault_build import _INDEX_EXCLUDED_FOLDERS, _Article, _render_index
from pipeline.schemas import FrontmatterDraft

log = structlog.get_logger()

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FM_DELIM = "---\n"


@dataclass
class MigrationResult:
    """Ergebnis einer Migration (auch für ``--dry-run``-Reporting)."""

    kind: str  # "category" | "tag"
    old: str
    new: str
    dry_run: bool
    folder_from: str | None = None
    folder_to: str | None = None
    files_frontmatter: int = 0  # Vault-.md mit geändertem Feld
    drafts_frontmatter: int = 0  # Draft-.md/.json mit geändertem Feld
    indexes_regenerated: int = 0
    changed: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.validation_errors


# === Frontmatter-Helfer (line-/block-basiert, minimal-diff) ===================


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """``.md``-Text → ``(frontmatter_yaml, body)``. ``None`` ohne ``---``-Block."""
    if not text.startswith(_FM_DELIM):
        return None, text
    m = re.search(r"\n---\s*\n", text[4:])
    if not m:
        return None, text
    return text[4 : 4 + m.start()], text[4 + m.end() :]


def _read_fm(path: Path) -> dict[str, Any] | None:
    """Frontmatter-Dict einer ``.md`` (oder ``None`` bei fehlendem/kaputtem Block)."""
    fm_text, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
    if fm_text is None:
        return None
    data = yaml.safe_load(fm_text)
    return data if isinstance(data, dict) else None


def _has_field_value(path: Path, field_name: str, value: str) -> bool:
    """True wenn die ``.md`` ein Frontmatter mit ``field_name == value`` hat."""
    return (_read_fm(path) or {}).get(field_name) == value


def _is_content_md(path: Path) -> bool:
    """Echte Artikel-/Draft-``.md`` (kein ``_index.md``, kein ``*.body.md``)."""
    return path.name != "_index.md" and not path.name.endswith(".body.md")


def _category_hits(old_dir: Path, drafts_dir: Path, old: str) -> tuple[list[Path], list[Path]]:
    """``(vault_hits, draft_hits)`` — ``.md`` mit ``category == old``."""
    vault_src = old_dir.glob("*.md") if old_dir.is_dir() else []
    vault_hits = [
        p for p in vault_src if _is_content_md(p) and _has_field_value(p, "category", old)
    ]
    draft_src = drafts_dir.glob("*.md") if drafts_dir.is_dir() else []
    draft_hits = [
        p for p in draft_src if _is_content_md(p) and _has_field_value(p, "category", old)
    ]
    return vault_hits, draft_hits


def _tag_hits(files: list[Path], old: str) -> list[Path]:
    """``.md`` aus ``files``, deren ``tags``-Liste ``old`` enthält."""
    out: list[Path] = []
    for p in files:
        if not _is_content_md(p):
            continue
        tags = (_read_fm(p) or {}).get("tags")
        if isinstance(tags, list) and old in tags:
            out.append(p)
    return out


def _set_md_category(path: Path, new_value: str) -> bool:
    """Setzt die ``category:``-Zeile im ersten Frontmatter-Block. True wenn geändert."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return False
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return False
    for i in range(1, end):
        if re.match(r"^category:\s", lines[i]) or lines[i].rstrip("\n") == "category:":
            newline = f"category: {new_value}\n"
            if lines[i] != newline:
                lines[i] = newline
                path.write_text("".join(lines), encoding="utf-8")
                return True
            return False
    return False


def _set_json_field(path: Path, key: str, value: object) -> bool:
    """Setzt ``key`` in einer ``.frontmatter.json`` (2-Space-Indent). True wenn geändert."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get(key) == value:
        return False
    data[key] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _replace_md_tag(path: Path, old: str, new: str) -> bool:
    """Ersetzt einen Tag in der ``tags``-Liste (block oder inline) per Frontmatter-Reparse."""
    fm_text, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    if fm_text is None:
        return False
    data = yaml.safe_load(fm_text)
    if not isinstance(data, dict):
        return False
    tags = data.get("tags")
    if not isinstance(tags, list) or old not in tags:
        return False
    new_tags: list[str] = []
    for t in tags:
        repl = new if t == old else t
        if repl not in new_tags:
            new_tags.append(repl)
    # Frontmatter-Block neu serialisieren (nur der YAML-Teil), Body unverändert.
    data["tags"] = new_tags
    new_fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).rstrip("\n")
    path.write_text(f"---\n{new_fm}\n---\n{body}", encoding="utf-8")
    return True


# === Vault-Index-Regen (reuse phase_9._render_index) ==========================


def _regenerate_index(folder_dir: Path, folder_name: str) -> bool:
    """Schreibt ``_index.md`` für einen Ordner neu (aus den enthaltenen ``.md``). True wenn geschrieben."""
    if folder_name in _INDEX_EXCLUDED_FOLDERS:
        return False
    articles: list[_Article] = []
    for p in sorted(folder_dir.glob("*.md")):
        if p.name == "_index.md":
            continue
        data = _read_fm(p)
        if data is None:
            continue
        articles.append(
            _Article(stem=p.stem, data=data, body="", folder=folder_name, final_slug=p.stem)
        )
    (folder_dir / "_index.md").write_text(_render_index(folder_name, articles), encoding="utf-8")
    return True


# === Validierung (Frontmatter + Wikilinks, §10) ===============================


def _validate_vault(vault_dir: Path) -> list[str]:
    """Validiert alle Vault-``.md``: Frontmatter gegen Schema + Wikilink-Auflösbarkeit (§10)."""
    errors: list[str] = []
    md_files = [p for p in vault_dir.rglob("*.md") if p.name != "_index.md"]
    known_slugs = {p.stem for p in md_files}
    known_slugs |= {f"CK_{p.stem}" for p in md_files}
    for p in md_files:
        data = _read_fm(p)
        if data is None:
            errors.append(f"{p.name}: kein parsebares Frontmatter")
            continue
        try:
            FrontmatterDraft.model_validate(data)
        except Exception as e:  # pragma: no cover - Fehlertext variiert
            first = str(e).splitlines()[0]
            errors.append(f"{p.name}: schema_invalid ({first})")
        # related-Wikilinks müssen auflösbar sein (§10)
        for target in data.get("related") or []:
            ref = str(target).strip().strip("[]")
            base = ref.split("|")[0].split("#")[0].strip()
            if base and base not in known_slugs:
                errors.append(f"{p.name}: related-Wikilink unauflösbar: {base!r}")
    return errors


# === category rename ==========================================================


def rename_category(
    old: str,
    new: str,
    *,
    categories_path: Path | None = None,
    vault_dir: Path | None = None,
    drafts_dir: Path | None = None,
    dry_run: bool = False,
) -> MigrationResult:
    """Benennt eine ``category`` um und zieht SSoT + Vault + Drafts nach.

    Reiner Rename: ``new`` darf noch nicht existieren (kein Merge). Der Ordner
    behält seine ``NN``-Nummer, nur der Anzeigename folgt ``new``.
    """
    categories_path = categories_path or _paths.CATEGORIES_FILE
    vault_dir = vault_dir or _paths.OUTPUT
    drafts_dir = drafts_dir or _paths.DRAFTS

    if not _SLUG_RE.match(new):
        raise ValueError(f"ungültiger category-Slug: {new!r}")
    mapping = taxonomy.load_category_to_folder(categories_path)
    if old not in mapping:
        raise ValueError(f"category {old!r} existiert nicht")
    if new in mapping:
        raise ValueError(f"category {new!r} existiert bereits (Merge ist nicht unterstützt)")

    old_folder = mapping[old]
    num = old_folder[:2] if old_folder[:2].isdigit() else f"{len(mapping):02d}"
    new_folder = f"{num}_{taxonomy.folder_display_name(new)}"

    res = MigrationResult(
        kind="category",
        old=old,
        new=new,
        dry_run=dry_run,
        folder_from=old_folder,
        folder_to=new_folder,
    )

    # Betroffene Dateien zählen (Plan)
    old_dir = vault_dir / old_folder
    vault_hits, draft_hits = _category_hits(old_dir, drafts_dir, old)
    res.files_frontmatter = len(vault_hits)
    res.drafts_frontmatter = len(draft_hits)

    if dry_run:
        res.changed = [
            f"config/categories.yaml: {old} → {new} ({new_folder})",
            f"vault-move: {old_folder}/ → {new_folder}/ ({len(vault_hits)} Artikel)",
            f"drafts: {len(draft_hits)} category-Felder",
            f"_index.md regen: {new_folder}/",
        ]
        return res

    _apply_category_rename(
        res,
        mapping,
        old,
        new,
        old_dir,
        new_folder,
        categories_path,
        vault_dir,
        drafts_dir,
        draft_hits,
    )
    res.validation_errors = _validate_vault(vault_dir)
    return res


def _apply_category_rename(
    res: MigrationResult,
    mapping: dict[str, str],
    old: str,
    new: str,
    old_dir: Path,
    new_folder: str,
    categories_path: Path,
    vault_dir: Path,
    drafts_dir: Path,
    draft_hits: list[Path],
) -> None:
    """Schreibender Teil von :func:`rename_category` (SSoT + Move + Frontmatter + Index)."""
    # 1. SSoT: Mapping-Key umbenennen (Reihenfolge erhalten), Ordnerwert aktualisieren
    new_mapping = {
        (new if k == old else k): (new_folder if k == old else v) for k, v in mapping.items()
    }
    taxonomy.write_category_mapping(new_mapping, categories_path)
    res.changed.append("config/categories.yaml")

    # 2. Vault-Ordner umziehen + category-Frontmatter setzen
    if old_dir.is_dir():
        new_dir = vault_dir / new_folder
        if new_dir.exists():
            raise FileExistsError(f"Zielordner existiert bereits: {new_dir}")
        shutil.move(str(old_dir), str(new_dir))
        res.changed.append(f"vault-move:{old_dir.name}→{new_folder}")
        for p in new_dir.glob("*.md"):
            if _is_content_md(p) and _has_field_value(p, "category", old):
                _set_md_category(p, new)

    # 3. Drafts (flach: .md + .frontmatter.json)
    for p in draft_hits:
        _set_md_category(p, new)
        j = drafts_dir / f"{p.stem}.frontmatter.json"
        if j.exists():
            _set_json_field(j, "category", new)

    # 4. Facade neu laden + Index regenerieren
    taxonomy.reload()
    new_dir = vault_dir / new_folder
    if new_dir.is_dir() and _regenerate_index(new_dir, new_folder):
        res.indexes_regenerated = 1
        res.changed.append(f"_index.md:{new_folder}")


# === tag rename ===============================================================


def rename_tag(
    old: str,
    new: str,
    *,
    tag_vocab_path: Path | None = None,
    vault_dir: Path | None = None,
    drafts_dir: Path | None = None,
    dry_run: bool = False,
) -> MigrationResult:
    """Benennt einen Tag um: SSoT (alter Name → Synonym auf ``new``) + ``tags``-Frontmatter."""
    tag_vocab_path = tag_vocab_path or _paths.TAG_VOCABULARY_FILE
    vault_dir = vault_dir or _paths.OUTPUT
    drafts_dir = drafts_dir or _paths.DRAFTS

    if not _SLUG_RE.match(new):
        raise ValueError(f"ungültiger Tag: {new!r}")
    data = yaml.safe_load(tag_vocab_path.read_text(encoding="utf-8")) or {}
    sections: dict[str, list[str]] = data.get("sections") or {}
    vocab = {t for tags in sections.values() for t in (tags or [])}
    if old not in vocab:
        raise ValueError(f"Tag {old!r} existiert nicht im Vokabular")

    res = MigrationResult(kind="tag", old=old, new=new, dry_run=dry_run)
    vault_hits = _tag_hits(list(vault_dir.rglob("*.md")) if vault_dir.is_dir() else [], old)
    draft_hits = _tag_hits(list(drafts_dir.glob("*.md")) if drafts_dir.is_dir() else [], old)
    res.files_frontmatter = len(vault_hits)
    res.drafts_frontmatter = len(draft_hits)

    if dry_run:
        res.changed = [
            f"config/tag_vocabulary.yaml: '{old}' → Synonym auf '{new}'",
            f"vault: {len(vault_hits)} tags-Listen",
            f"drafts: {len(draft_hits)} tags-Listen",
        ]
        return res

    _rewrite_tag_vocab(data, sections, old, new, tag_vocab_path)
    res.changed.append("config/tag_vocabulary.yaml")
    for p in vault_hits + draft_hits:
        _replace_md_tag(p, old, new)
    for p in draft_hits:
        _replace_json_tag(drafts_dir / f"{p.stem}.frontmatter.json", old, new)
    res.changed.append(f"vault+drafts: {len(vault_hits) + len(draft_hits)} tags-Listen")

    taxonomy.reload()
    res.validation_errors = _validate_vault(vault_dir)
    return res


def _rewrite_tag_vocab(
    data: dict[str, Any], sections: dict[str, list[str]], old: str, new: str, path: Path
) -> None:
    """SSoT-Schreiben: ``old`` aus Sektionen entfernen, ``new`` sicherstellen, Synonym setzen."""
    for sec, tags in sections.items():
        sections[sec] = [t for t in (tags or []) if t != old]
    if new not in {t for tags in sections.values() for t in tags}:
        target_sec = next((s for s, t in sections.items() if new in (t or [])), None)
        target_sec = target_sec or next(iter(sections))
        sections[target_sec] = sorted({*sections[target_sec], new})
    syn = data.get("synonyms") or {}
    syn[old] = new
    data["synonyms"] = dict(sorted(syn.items()))
    data["sections"] = sections
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _replace_json_tag(json_path: Path, old: str, new: str) -> None:
    """Ersetzt ``old`` durch ``new`` in der ``tags``-Liste einer ``.frontmatter.json`` (dedup)."""
    if not json_path.exists():
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    tags = data.get("tags")
    if not isinstance(tags, list) or old not in tags:
        return
    seen: list[str] = []
    for t in tags:
        repl = new if t == old else t
        if repl not in seen:
            seen.append(repl)
    _set_json_field(json_path, "tags", seen)
