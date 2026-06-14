"""Review-Gate-System (file-basiert, Zed-Review — kein TUI).

Vier Gates im go-forward-Flow halten alle manuellen Entscheidungen fest:

| Gate     | Frage                              | Entscheidungen                         |
|----------|------------------------------------|----------------------------------------|
| quality  | low-confidence / Validierungsfehler| freigeben · nachbessern · quarantäne   |
| category | unklare/neue Kategorie             | zuweisen · neu · unsortiert            |
| tags     | Tag außerhalb Vokabular            | aufnehmen · mappen · droppen           |
| final    | Publish-Freigabe                   | publish · hold                         |

Round-Trip (file-basiert)::

    Producer (scan_*)  →  review/decisions.jsonl   (maschinell, ein Item pro Zeile)
    pkm review         →  review/decisions.md       (editierbar, gruppiert nach gate→group)
    Mensch editiert decisions.md in Zed (Entscheidung + ggf. Wert eintragen)
    pkm review --apply →  liest decisions.md zurück, wendet je Gate die Wirkung an

`decisions.jsonl` bleibt kanonische Quelle der offenen Punkte; `decisions.md` ist
die menschen-editierbare Sicht. Verwandte Files eines Laufs werden je Gate über
`group` (Themengebiet) gebündelt gezeigt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

from pipeline.config import PipelineConfig
from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER

log = structlog.get_logger()

GATES = ("quality", "category", "tags", "final")

# Erlaubte Entscheidungs-Keywords je Gate (in decisions.md eingetragen).
DECISIONS: dict[str, tuple[str, ...]] = {
    "quality": ("freigeben", "nachbessern", "quarantaene"),
    "category": ("zuweisen", "neu", "unsortiert"),
    "tags": ("aufnehmen", "mappen", "droppen"),
    "final": ("publish", "hold"),
}

_GATE_TITLES = {
    "quality": "Gate A — Qualität (low-confidence / Validierungsfehler)",
    "category": "Gate B — Kategorie (unklar / neu)",
    "tags": "Gate C — Tags (außerhalb Vokabular)",
    "final": "Gate D — Final-Sicht (Publish-Freigabe)",
}

_DECISIONS_JSONL = "decisions.jsonl"
_DECISIONS_MD = "decisions.md"
_STATE_FILE = "state.json"

_LOWER_TOKENS = {"und", "oder", "der", "die", "das", "von", "zu", "mit", "für", "im", "am"}


# === Datenmodell ==============================================================


@dataclass
class DecisionItem:
    """Ein offener Entscheidungspunkt eines Gates.

    doc_id ist der Draft-Stem (`CK_<slug>`). current = Ist-Wert (z. B. die unbekannte
    category bzw. der unbekannte Tag). options = Anzeige-Optionen für den Menschen.
    decision/value werden beim Apply aus decisions.md zurückgelesen.
    """

    doc_id: str
    gate: str
    question: str
    current: str
    options: list[str]
    group: str
    decision: str = ""
    value: str = ""

    @property
    def item_id(self) -> str:
        """Stabile, render-/parse-bare ID (matcht decisions.md ↔ decisions.jsonl)."""
        return f"{self.gate}::{self.doc_id}::{self.current}"


def load_decisions(path: Path) -> list[DecisionItem]:
    """Lädt DecisionItems aus decisions.jsonl (eine Zeile pro Item)."""
    if not path.exists():
        return []
    items: list[DecisionItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        items.append(DecisionItem(**data))
    return items


def save_decisions(path: Path, items: list[DecisionItem]) -> None:
    """Schreibt DecisionItems als JSONL (deterministisch sortiert nach gate, group, doc_id)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(items, key=lambda it: (GATES.index(it.gate), it.group, it.doc_id, it.current))
    with path.open("w", encoding="utf-8") as fh:
        for it in ordered:
            fh.write(json.dumps(asdict(it), ensure_ascii=False) + "\n")


# === Draft-Frontmatter lesen/schreiben =======================================


def _split_md(text: str) -> tuple[dict[str, Any], str]:
    """Teilt .md in (frontmatter_dict, body). Leeres Dict wenn kein `---`-Block."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, text
    return (data if isinstance(data, dict) else {}), body


def read_draft_frontmatter(drafts_dir: Path, stem: str) -> dict[str, Any]:
    """Liest das Frontmatter eines Drafts (`.frontmatter.json` bevorzugt, sonst `.md`)."""
    fm_json = drafts_dir / f"{stem}.frontmatter.json"
    if fm_json.exists():
        try:
            data = json.loads(fm_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    md = drafts_dir / f"{stem}.md"
    if md.exists():
        fm, _ = _split_md(md.read_text(encoding="utf-8"))
        return fm
    return {}


def write_draft_frontmatter(drafts_dir: Path, stem: str, fm: dict[str, Any]) -> None:
    """Schreibt das aktualisierte Frontmatter zurück in `.frontmatter.json` UND `.md`."""
    fm_json = drafts_dir / f"{stem}.frontmatter.json"
    if fm_json.exists():
        fm_json.write_text(json.dumps(fm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = drafts_dir / f"{stem}.md"
    if md.exists():
        _, body = _split_md(md.read_text(encoding="utf-8"))
        dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
        md.write_text(f"---\n{dumped}\n---\n\n{body.lstrip(chr(10))}", encoding="utf-8")


def _move_draft(drafts_dir: Path, stem: str, dest_dir: Path) -> list[str]:
    """Verschiebt alle Draft-Files eines Stems (.md/.body.md/.frontmatter.json) nach dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for suffix in (".md", ".body.md", ".frontmatter.json"):
        src = drafts_dir / f"{stem}{suffix}"
        if src.exists():
            src.rename(dest_dir / src.name)
            moved.append(src.name)
    return moved


# === decisions.md Render / Parse =============================================


def render_decisions_md(items: list[DecisionItem]) -> str:
    """Rendert die editierbare decisions.md (gruppiert nach gate → group)."""
    lines: list[str] = [
        "---",
        "title: Review-Entscheidungen",
        "slug: review-decisions",
        "status: editable",
        "---",
        "",
        "# Review-Entscheidungen",
        "",
        "Trage je Punkt **Entscheidung:** (und ggf. **Wert:**) ein, speichere, dann",
        "`pkm review --apply`. Erlaubte Entscheidungen stehen unter *Optionen*.",
        "",
    ]
    by_gate: dict[str, list[DecisionItem]] = {g: [] for g in GATES}
    for it in items:
        by_gate.setdefault(it.gate, []).append(it)

    for gate in GATES:
        gate_items = by_gate.get(gate) or []
        if not gate_items:
            continue
        lines += [f"## {_GATE_TITLES[gate]}", ""]
        by_group: dict[str, list[DecisionItem]] = {}
        for it in gate_items:
            by_group.setdefault(it.group, []).append(it)
        for group in sorted(by_group):
            lines += [f"### Gruppe: {group}", ""]
            for it in sorted(by_group[group], key=lambda x: (x.doc_id, x.current)):
                lines += [
                    f"<!-- item: {it.item_id} -->",
                    f"- **Datei:** `{it.doc_id}`",
                    f"  - Frage: {it.question}",
                    f"  - Aktuell: `{it.current or '—'}`",
                    f"  - Optionen: {' | '.join(it.options)}",
                    "  - **Entscheidung:** ",
                    "  - **Wert:** ",
                    "",
                ]
    return "\n".join(lines) + "\n"


_ITEM_RE = re.compile(r"<!-- item: (?P<id>.+?) -->")
_DECISION_RE = re.compile(r"\*\*Entscheidung:\*\*[ \t]*(?P<v>.*)")
_VALUE_RE = re.compile(r"\*\*Wert:\*\*[ \t]*(?P<v>.*)")


def parse_decisions_md(text: str) -> dict[str, tuple[str, str]]:
    """Parst die ausgefüllte decisions.md → {item_id: (decision, value)}.

    Robust gegen Reihenfolge: trennt an den `<!-- item: ID -->`-Markern und liest
    je Block die erste Entscheidung-/Wert-Zeile. Leere Entscheidungen werden
    übersprungen (noch nicht bearbeitet).
    """
    result: dict[str, tuple[str, str]] = {}
    blocks = _ITEM_RE.split(text)
    # blocks: [prefix, id1, body1, id2, body2, ...]
    for i in range(1, len(blocks), 2):
        item_id = blocks[i].strip()
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        dm = _DECISION_RE.search(body)
        vm = _VALUE_RE.search(body)
        decision = (dm.group("v").strip() if dm else "").strip("`").strip()
        value = (vm.group("v").strip() if vm else "").strip("`").strip()
        if decision:
            result[item_id] = (decision, value)
    return result


# === Producer: offene Punkte aus den Drafts scannen ==========================


def _draft_stems(drafts_dir: Path) -> list[str]:
    """Aktive Draft-Stems (`CK_<slug>`), sortiert."""
    if not drafts_dir.exists():
        return []
    return sorted(
        p.name[: -len(".md")]
        for p in drafts_dir.glob("*.md")
        if not p.name.endswith(".body.md") and not p.name.startswith(".")
    )


def build_decisions(
    cfg: PipelineConfig, *, skip_doc_ids: Collection[str] = frozenset()
) -> list[DecisionItem]:
    """Scannt die aktiven Drafts und erzeugt offene DecisionItems für alle Gates.

    - quality: Frontmatter validiert NICHT gegen FrontmatterDraft → Gate A.
    - category: `category` ∉ bekannte Kategorien → Gate B.
    - tags: jeder Tag ∉ Vokabular → ein Gate-C-Item.
    - final: Draft ohne offene A/B/C-Punkte → Gate D (Publish-Freigabe).

    Args:
        cfg: PipelineConfig.
        skip_doc_ids: bereits abgeschlossene Drafts (approved/published) — keine
            neuen Items, damit publizierte Docs nicht erneut als Gate D auftauchen.
    """
    from pipeline.schemas import FrontmatterDraft  # lokal: vermeidet Import-Zyklus

    drafts_dir = cfg.paths.drafts
    allowed_cats = set(CATEGORY_TO_FOLDER)
    vocab, _synonyms = _load_vocab(cfg)

    items: list[DecisionItem] = []
    for stem in _draft_stems(drafts_dir):
        if stem in skip_doc_ids:
            continue
        fm = read_draft_frontmatter(drafts_dir, stem)
        category = str(fm.get("category") or "")
        group = category or "unsortiert"

        # Gate A — Validierung
        try:
            FrontmatterDraft.model_validate(fm)
        except Exception as exc:  # ValidationError o.ä.
            items.append(
                DecisionItem(
                    doc_id=stem,
                    gate="quality",
                    question=f"Frontmatter-Validierung fehlgeschlagen ({type(exc).__name__})",
                    current=str(fm.get("confidence") or "?"),
                    options=list(DECISIONS["quality"]),
                    group=group,
                )
            )

        # Gate B — Kategorie
        if category and category not in allowed_cats:
            items.append(
                DecisionItem(
                    doc_id=stem,
                    gate="category",
                    question="Kategorie nicht im kontrollierten Set",
                    current=category,
                    options=[*sorted(allowed_cats)[:6], "…", *DECISIONS["category"]],
                    group=group,
                )
            )

        # Gate C — Tags
        tags = fm.get("tags") or []
        if vocab:
            for tag in tags:
                if tag not in vocab:
                    items.append(
                        DecisionItem(
                            doc_id=stem,
                            gate="tags",
                            question="Tag außerhalb des kontrollierten Vokabulars",
                            current=str(tag),
                            options=list(DECISIONS["tags"]),
                            group=group,
                        )
                    )

        # Gate D — Final: immer ein Publish-Punkt. A/B/C werden beim Apply zuerst
        # angewandt (Gate-Reihenfolge), sodass ein Review-Zyklus genügt.
        items.append(
            DecisionItem(
                doc_id=stem,
                gate="final",
                question="Bereit für Publish nach output/?",
                current=str(fm.get("status") or "draft"),
                options=list(DECISIONS["final"]),
                group=group,
            )
        )
    return items


# === Vokabular- / Kategorie-Helfer ===========================================


def _load_vocab(cfg: PipelineConfig) -> tuple[set[str], dict[str, str | None]]:
    """Lädt (Vokabular, Synonym-Map) aus der konfigurierten vocabulary_file (YAML/MD)."""
    from pipeline.phase_8_synthesis import _parse_tag_system

    path = cfg.tags.vocabulary_file
    if not path.exists():
        return set(), {}
    try:
        return _parse_tag_system(path)
    except FileNotFoundError:
        return set(), {}


def _folder_display_name(slug: str) -> str:
    """category-Slug → Ordner-Anzeigename (Title-Case, kleine Wörter klein)."""
    parts = slug.split("-")
    out = [p if p in _LOWER_TOKENS else p.capitalize() for p in parts]
    if out:
        out[0] = out[0].capitalize()
    return "-".join(out)


def _next_folder_number(mapping: dict[str, str]) -> int:
    """Nächste freie zweistellige Ordner-Nummer (max + 1)."""
    nums = [int(m.group(1)) for v in mapping.values() if (m := re.match(r"(\d+)_", v))]
    return (max(nums) + 1) if nums else 0


def add_category(slug: str, cfg: PipelineConfig) -> dict[str, Any]:
    """Legt eine neue Kategorie an: config/categories.yaml (Single Source) + output-Ordner.

    Idempotent: existiert die Kategorie bereits, wird sie unverändert zurückgegeben.
    config/categories.yaml ist die alleinige Quelle; das Laufzeit-Dict CATEGORY_TO_FOLDER
    wird mitgeführt, damit der Build im selben Prozess die neue Kategorie kennt.
    """
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise ValueError(f"ungültiger category-Slug: {slug!r}")

    cats_file = cfg.paths.config / "categories.yaml"
    data = yaml.safe_load(cats_file.read_text(encoding="utf-8")) or {}
    mapping: dict[str, str] = data.get("categories") or {}

    if slug in mapping:
        return {"category": slug, "folder": mapping[slug], "already": True}

    folder = f"{_next_folder_number(mapping):02d}_{_folder_display_name(slug)}"
    mapping[slug] = folder

    # 1. config/categories.yaml (Single Source) — Reihenfolge erhalten
    data["categories"] = mapping
    _write_categories_yaml(cats_file, mapping)

    # 2. Laufzeit-Dict mitführen (kein Code-Literal mehr — categories.yaml ist Quelle)
    CATEGORY_TO_FOLDER[slug] = folder

    # 3. output/-Ordner
    (cfg.paths.output / folder).mkdir(parents=True, exist_ok=True)

    log.info("review_new_category", category=slug, folder=folder)
    return {"category": slug, "folder": folder, "already": False}


def _write_categories_yaml(path: Path, mapping: dict[str, str]) -> None:
    """Schreibt categories.yaml unter Erhalt des Header-Kommentars."""
    text = path.read_text(encoding="utf-8")
    header_end = text.find("categories:")
    header = text[:header_end] if header_end != -1 else ""
    body = "categories:\n" + "".join(f"  {k}: {v}\n" for k, v in mapping.items())
    path.write_text(header + body, encoding="utf-8")


def _add_tag_to_vocab(cfg: PipelineConfig, tag: str) -> bool:
    """Nimmt einen Tag in config/tag_vocabulary.yaml auf (Abschnitt 'Erweiterungen (review)').

    Minimal-invasiver Text-Splice (analog ``_write_categories_yaml``): die Datei wird als
    Text bearbeitet und ausschließlich um eine ``- <tag>``-Zeile ergänzt. Kommentar-Header,
    Key-Quoting und Struktur der Single-Source bleiben unangetastet (kein
    ``yaml.safe_load`` → ``safe_dump`` Full-Reserialize mehr). ``safe_load`` wird nur noch
    lesend für den Existenz-Check genutzt.

    Returns:
        True, wenn der Tag neu aufgenommen wurde; False, wenn er bereits im Vokabular steht.
    """
    path = cfg.paths.config / "tag_vocabulary.yaml"
    text = path.read_text(encoding="utf-8")

    # Existenz-Check über strukturiertes Laden (rein lesend, schreibt die Datei nicht).
    data = yaml.safe_load(text) or {}
    sections: dict[str, list[str]] = data.get("sections") or {}
    existing = {t for tags in sections.values() for t in (tags or [])}
    if tag in existing:
        return False

    ext = "Erweiterungen (review)"
    new_item = f"    - {tag}"
    lines = text.split("\n")

    # Section-Header (2-Space-Einrückung, quoted oder unquoted) suchen.
    sec_idx = next(
        (
            i
            for i, ln in enumerate(lines)
            if ln.startswith("  ")
            and ln.rstrip().endswith(":")
            and ln.strip().rstrip(":") in (ext, f'"{ext}"')
        ),
        None,
    )

    if sec_idx is not None:
        # Einfügen nach dem letzten Listenelement der Sektion.
        insert_at = sec_idx + 1
        for i in range(sec_idx + 1, len(lines)):
            if lines[i].lstrip().startswith("- "):
                insert_at = i + 1
            elif lines[i].strip() == "":
                continue
            else:
                break
        lines.insert(insert_at, new_item)
    else:
        # Sektion fehlt → direkt vor 'synonyms:' anlegen (über vorausgehende
        # Kommentar-/Leerzeilen hinweg, damit sie noch unter 'sections' landet).
        syn_idx = next((i for i, ln in enumerate(lines) if ln.startswith("synonyms:")), len(lines))
        anchor = syn_idx
        while anchor > 0 and (
            lines[anchor - 1].lstrip().startswith("#") or lines[anchor - 1].strip() == ""
        ):
            anchor -= 1
        lines[anchor:anchor] = [f"  {ext}:", new_item]

    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def _record_tag_merge(cfg: PipelineConfig, alias: str, canonical: str | None) -> None:
    """Hält eine Tag-Entscheidung in config/tag_merge_map.json fest (remap oder drop)."""
    path = cfg.paths.config / "tag_merge_map.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if canonical is None:
        drop = data.setdefault("drop", [])
        if alias not in drop:
            drop.append(alias)
    else:
        data.setdefault("remap", {})[alias] = canonical
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# === Appliers je Gate ========================================================


def _apply_quality(item: DecisionItem, cfg: PipelineConfig) -> str:
    """Gate A: freigeben (no-op) · nachbessern (→ review/needs_human) · quarantaene."""
    drafts = cfg.paths.drafts
    if item.decision == "freigeben":
        return "freigegeben"
    if item.decision == "nachbessern":
        _move_draft(drafts, item.doc_id, cfg.paths.review / "needs_human")
        return "nachbessern → review/needs_human"
    if item.decision == "quarantaene":
        _move_draft(drafts, item.doc_id, cfg.paths.review / "quarantine")
        return "quarantäne → review/quarantine"
    raise ValueError(f"Gate quality: unbekannte Entscheidung {item.decision!r}")


def _apply_category(item: DecisionItem, cfg: PipelineConfig) -> str:
    """Gate B: zuweisen (value=cat) · neu (value=neue cat) · unsortiert."""
    drafts = cfg.paths.drafts
    fm = read_draft_frontmatter(drafts, item.doc_id)
    if item.decision == "zuweisen":
        if item.value not in CATEGORY_TO_FOLDER:
            raise ValueError(f"Gate category: '{item.value}' ist keine bekannte Kategorie")
        fm["category"] = item.value
        write_draft_frontmatter(drafts, item.doc_id, fm)
        return f"category → {item.value}"
    if item.decision == "neu":
        res = add_category(item.value, cfg)
        fm["category"] = item.value
        write_draft_frontmatter(drafts, item.doc_id, fm)
        return f"neue Kategorie {item.value} ({res['folder']})"
    if item.decision == "unsortiert":
        fm["category"] = "unsortiert"
        write_draft_frontmatter(drafts, item.doc_id, fm)
        return "category → unsortiert"
    raise ValueError(f"Gate category: unbekannte Entscheidung {item.decision!r}")


def _apply_tags(item: DecisionItem, cfg: PipelineConfig) -> str:
    """Gate C: aufnehmen (→ vocab) · mappen (value=canonical) · droppen."""
    drafts = cfg.paths.drafts
    fm = read_draft_frontmatter(drafts, item.doc_id)
    tags: list[str] = list(fm.get("tags") or [])
    tag = item.current
    if item.decision == "aufnehmen":
        _add_tag_to_vocab(cfg, tag)
        return f"Tag '{tag}' ins Vokabular aufgenommen"
    if item.decision == "mappen":
        canonical = item.value
        if not canonical:
            raise ValueError("Gate tags 'mappen' braucht **Wert:** (kanonischer Tag)")
        tags = [canonical if t == tag else t for t in tags]
        # Duplikate entfernen, Reihenfolge erhalten
        fm["tags"] = list(dict.fromkeys(tags))
        write_draft_frontmatter(drafts, item.doc_id, fm)
        _record_tag_merge(cfg, tag, canonical)
        return f"Tag '{tag}' → '{canonical}'"
    if item.decision == "droppen":
        fm["tags"] = [t for t in tags if t != tag]
        write_draft_frontmatter(drafts, item.doc_id, fm)
        _record_tag_merge(cfg, tag, None)
        return f"Tag '{tag}' entfernt"
    raise ValueError(f"Gate tags: unbekannte Entscheidung {item.decision!r}")


def _apply_final(item: DecisionItem, cfg: PipelineConfig) -> str:
    """Gate D: publish (state-Flag) · hold."""
    if item.decision not in ("publish", "hold"):
        raise ValueError(f"Gate final: unbekannte Entscheidung {item.decision!r}")
    state_path = cfg.paths.work / _STATE_FILE
    state: dict[str, Any] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    docs = state.setdefault("docs", {})
    docs[item.doc_id] = "approved" if item.decision == "publish" else "hold"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"{item.doc_id} → {docs[item.doc_id]}"


_APPLIERS = {
    "quality": _apply_quality,
    "category": _apply_category,
    "tags": _apply_tags,
    "final": _apply_final,
}


def apply_decision(item: DecisionItem, cfg: PipelineConfig) -> str:
    """Wendet ein einzelnes (entschiedenes) DecisionItem an und gibt eine Wirkungs-Notiz zurück."""
    if item.decision not in DECISIONS[item.gate]:
        raise ValueError(
            f"Gate {item.gate}: Entscheidung {item.decision!r} nicht in {DECISIONS[item.gate]}"
        )
    return _APPLIERS[item.gate](item, cfg)


# === Top-Level: render + apply ===============================================


def render_review(
    cfg: PipelineConfig, *, rebuild: bool = True, skip_doc_ids: Collection[str] = frozenset()
) -> dict[str, Any]:
    """Erzeugt decisions.jsonl (optional neu aus den Drafts) + die editierbare decisions.md.

    Args:
        cfg: PipelineConfig.
        rebuild: Wenn True, werden offene Punkte frisch aus den Drafts gescannt
            (überschreibt decisions.jsonl). Sonst wird die bestehende jsonl genutzt.
        skip_doc_ids: bereits abgeschlossene Drafts (approved/published) auslassen.

    Returns:
        Summary mit Pfaden, Anzahl Items je Gate, Set der offenen doc_ids.
    """
    review_dir = cfg.paths.review
    review_dir.mkdir(parents=True, exist_ok=True)
    jsonl = review_dir / _DECISIONS_JSONL
    md = review_dir / _DECISIONS_MD

    items = build_decisions(cfg, skip_doc_ids=skip_doc_ids) if rebuild else load_decisions(jsonl)
    save_decisions(jsonl, items)
    md.write_text(render_decisions_md(items), encoding="utf-8")

    per_gate = {g: sum(1 for it in items if it.gate == g) for g in GATES}
    open_blocking = {it.doc_id for it in items if it.gate != "final"}
    return {
        "decisions_jsonl": str(jsonl),
        "decisions_md": str(md),
        "total": len(items),
        "per_gate": per_gate,
        "open_doc_ids": sorted({it.doc_id for it in items}),
        "blocking_doc_ids": sorted(open_blocking),
    }


def apply_review(cfg: PipelineConfig) -> dict[str, Any]:
    """Liest die ausgefüllte decisions.md, wendet alle entschiedenen Items an.

    Angewandte Items werden aus decisions.jsonl entfernt; offene bleiben stehen.

    Returns:
        Summary: applied (Liste Wirkungs-Notizen), remaining (offen), errors.
    """
    review_dir = cfg.paths.review
    jsonl = review_dir / _DECISIONS_JSONL
    md = review_dir / _DECISIONS_MD

    items = load_decisions(jsonl)
    filled = parse_decisions_md(md.read_text(encoding="utf-8")) if md.exists() else {}

    applied: list[str] = []
    errors: list[str] = []
    remaining: list[DecisionItem] = []
    for it in items:
        choice = filled.get(it.item_id)
        if not choice:
            remaining.append(it)
            continue
        it.decision, it.value = choice
        try:
            note = apply_decision(it, cfg)
            applied.append(f"[{it.gate}] {it.doc_id}: {note}")
        except Exception as exc:
            errors.append(f"[{it.gate}] {it.doc_id}: {exc}")
            remaining.append(it)

    save_decisions(jsonl, remaining)
    md.write_text(render_decisions_md(remaining), encoding="utf-8")
    return {"applied": applied, "remaining": len(remaining), "errors": errors}
