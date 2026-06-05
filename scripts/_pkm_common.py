#!/usr/bin/env python3
"""_pkm_common.py — Geteilte Enums, Konstanten und Helfer für die PKM-Skripte.

Single Source of Truth für die Skripte (`draft_inventory.py`, `pkm_triage.py`,
`check_frontmatter.py`, `apply_category_mapping.py`, `phase8_runner.py`), um die
früher mehrfach duplizierten Enums/Helfer (Drift-Risiko, E1 musste 3x nachgezogen
werden) zu zentralisieren.

Die Enums werden, wo möglich, direkt aus den Pipeline-Pydantic-Schemas
(`pipeline.schemas.FrontmatterDraft`) bzw. dem Vault-Mapping
(`pipeline.phase_9_vault_build.CATEGORY_TO_FOLDER`) abgeleitet — die Pipeline
bleibt kanonisch, dieses Modul spiegelt sie nur. `tests/test_pkm_common.py`
bewacht die Konsistenz gegen Drift.

Bewusst NICHT zentralisiert: `check_schema`, `compare_*` und `normalize_for_*`.
Diese divergieren zwischen den Skripten im Output-Kontrakt (Issue-String-Format,
Feld-Coverage, Return-Typ) — Vereinheitlichung wäre eine Verhaltensänderung, kein
reines Refactor. Sie referenzieren aber jetzt die geteilten Enums/Feld-Sets hier,
womit das eigentliche Enum-Drift-Risiko beseitigt ist.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, get_args

# Repo-Root auf den Pfad legen, damit `pipeline` importierbar ist, auch wenn ein
# Skript als `python3 scripts/foo.py` läuft (sys.path[0] = scripts/).
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import yaml  # noqa: E402
from pipeline.schemas import FrontmatterDraft  # noqa: E402

# === Enums (aus pipeline.schemas abgeleitet — Drift unmöglich) ================

_FIELDS = FrontmatterDraft.model_fields
ALLOWED_TYPE: set[str] = set(get_args(_FIELDS["type"].annotation))
ALLOWED_STATUS: set[str] = set(get_args(_FIELDS["status"].annotation))
ALLOWED_REVIEW: set[str] = set(get_args(_FIELDS["review_status"].annotation))
ALLOWED_CONFIDENCE: set[str] = set(get_args(_FIELDS["confidence"].annotation))

# `category` und `doc_role` sind im Schema freie Strings (keine Literals).
# ALLOWED_CATEGORIES wird gegen pipeline.phase_9_vault_build.CATEGORY_TO_FOLDER
# getestet (tests/test_pkm_common.py); ALLOWED_DOC_ROLE ist skript-kanonisch.
ALLOWED_CATEGORIES: set[str] = {
    "meta", "grundlagen", "webentwicklung", "betriebssysteme",
    "protokolle-und-standards", "dateitypen-und-konfiguration",
    "methoden-und-prozesse", "best-practices", "cheatsheets",
    "ki-und-semantische-systeme", "datenarchitektur-und-datenbanken",
    "dokumentenverarbeitung-und-extraktion",
    "wissensmodellierung-und-knowledge-graphs",
    "visualisierung-reporting-und-design-systeme",
    "automatisierung-scripting-und-pipelines",
    "gedanken", "kunst-kultur", "unsortiert",
}
ALLOWED_DOC_ROLE: set[str] = {
    "manual", "how-to", "best-practice", "workflow",
    "explanation", "reference", "cheatsheet", "wiki",
}

# === Feld-Sets ================================================================

REQUIRED_FIELDS: set[str] = {
    "title", "slug", "summary",
    "type", "doc_role", "category",
    "sources_docs", "source_chunks",
    "status", "review_status", "confidence",
    "doc_version", "created", "updated",
    "last_synthesized", "prompt_version",
}
# Diff-Klassifikation: kritisch = semantischer Drift (Halluzinations-Verdacht)
CRITICAL_DIFF_FIELDS: set[str] = {"title", "type", "summary", "slug"}
# Minor = erwartbare LLM-Drift / Timestamps
MINOR_DIFF_FIELDS: set[str] = {
    "tags", "aliases", "category", "doc_role", "confidence",
    "subcategory", "created", "updated", "last_synthesized",
    "status", "review_status",
}

# === Schwellwerte =============================================================

MIN_BODY_WORDS = 50  # darunter = STUB
MIN_SUMMARY_WORDS = 8
MAX_SUMMARY_WORDS = 60
MAX_TAGS = 10

# === Regexes / Zeichen ========================================================

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
UMLAUT_CHARS = ("ä", "ö", "ü", "ß")
UMLAUT_MAP = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}

HEADING_RE = re.compile(r"^(#{1,6})\s+\S", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)
TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
QUESTION_RE = re.compile(r"^>\s*\[!question\]", re.MULTILINE | re.IGNORECASE)

# Kanonische CK-Slug-Ableitung — Composed-Umlaut-Tabelle + 60-Cap (Pipeline-Spiegel)
_CK_UMLAUT_TABLE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)
_CK_SPECIAL_RE = re.compile(r"[^a-z0-9]+")
CK_SLUG_CAP = 60


# === Pure Helfer (identisch in allen Skripten) ================================


def split_md(text: str) -> tuple[str | None, str]:
    """Teilt .md-Text in (frontmatter_yaml, body). None wenn kein `---`-Block."""
    if not text.startswith(("---\n", "---\r\n")):
        return None, text
    rest = text[4:]
    end = re.search(r"\n---\s*\n", rest)
    if not end:
        return None, text
    return rest[: end.start()], rest[end.end() :]


def parse_yaml_text(text: str) -> tuple[dict | None, str | None]:
    """YAML-Frontmatter-Text → (dict | None, error | None)."""
    if not text or not text.strip():
        return None, "empty"
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, f"yaml_error: {type(e).__name__}"
    if not isinstance(data, dict):
        return None, "not_dict"
    return data, None


def parse_json_file(path: Path) -> tuple[dict | None, str | None]:
    """JSON-Datei → (dict | None, error | None)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"json_error: {type(e).__name__}"
    if not isinstance(data, dict):
        return None, "not_dict"
    return data, None


def compute_body_metrics(body: str) -> dict[str, int]:
    """Body-Metriken (Superset: deckt Bedarf aller Skripte; Extra-Keys werden ignoriert)."""
    if not body or not body.strip():
        return dict(
            words=0, chars=0, headings=0, code_blocks=0,
            tables=0, wikilinks=0, open_questions=0,
        )
    return {
        "words": len(body.split()),
        "chars": len(body),
        "headings": len(HEADING_RE.findall(body)),
        "code_blocks": len(CODE_FENCE_RE.findall(body)) // 2,
        "tables": len(TABLE_SEP_RE.findall(body)),
        "wikilinks": len(WIKILINK_RE.findall(body)),
        "open_questions": len(QUESTION_RE.findall(body)),
    }


# === Slug-Werkzeuge ===========================================================


def normalize_to_slug(name: str) -> str:
    """Korpus-/Dateiname → kanonischer Slug (NFC-Fix für macOS-NFD, Umlaut-Map)."""
    s = unicodedata.normalize("NFC", name).lower()
    for o, r in UMLAUT_MAP.items():
        s = s.replace(o, r)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def draft_stem_to_slug(stem: str) -> str:
    """Draft-Stem `CK_foo` → Slug `foo`. Kein `CK_`-Prefix → unverändert."""
    return stem[3:] if stem.startswith("CK_") else stem


def canonical_ck_slug(name: str) -> str:
    """Repliziert die Pipeline-Slug-Ableitung für CK-Dateinamen.

    NFC-Komposition (macOS-NFD-Fix), Umlaut-Map, NFKD-Akzent-Strip, lowercase,
    Sonderzeichen→Bindestrich, 60-Cap. Single Source of Truth bleibt die
    Pipeline; ``tests/test_phase8_runner.py`` bewacht die Übereinstimmung.
    """
    s = unicodedata.normalize("NFC", name).translate(_CK_UMLAUT_TABLE)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = _CK_SPECIAL_RE.sub("-", s).strip("-")
    return s[:CK_SLUG_CAP].strip("-") or "concept"


# Alias: phase8_runner nutzte `normalize_slug` (identische Logik zu normalize_to_slug)
normalize_slug = normalize_to_slug


def _normalize_for_diff(v: Any) -> Any:
    """Normalisiert Werte für Diff. None / [] / '' sind als 'leer' äquivalent."""
    if v is None:
        return None
    if isinstance(v, list):
        return tuple(v) if v else None
    if isinstance(v, str) and not v:
        return None
    return v
