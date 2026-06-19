"""WP4 — Vault-Audit/Repair-Tooling (read-only Audit · Safe-Repair · Review-Patch).

Zielt auf den **produktiven** Obsidian-Vault (``_paths.BRAIN_VAULT``). Drei Modi:

* :func:`audit_vault` — read-only Befund-Report über alle Content-Files
  (``_attic``/``_index``/``00_Meta``/Templates ausgenommen). Implementiert die
  neun Detektionsregeln aus dem WP4-Spec.
* :func:`repair_text` — deterministische, idempotente Safe-Tier-Fixes auf einem
  einzelnen File-Text (``**``-Heading entbolden, geleakte Tokens/Mashups
  bereinigen, eindeutig erkennbare Code-Fences taggen). Schutzbereiche
  (Frontmatter, Code-Inhalt, Wikilinks/Embeds) bleiben unberührt.
* :func:`review_patches` — Unified-Diff-Vorschläge für **Unsafe**-Fälle, die nie
  auto-angewendet werden (Fence ohne erkennbare Sprache, Setext-Bruch,
  Junk-Heading).

Das Modul ist **non-mutating gegenüber dem Vault**: alle öffentlichen Funktionen
lesen und liefern Datenstrukturen bzw. neuen Text zurück. Das Schreiben (3-State
``raw``→``work``→``export``) ist Sache des Aufrufers (CLI/WP4-Teil-B).

Wiederverwendet die Taxonomie-Facade (:mod:`pipeline.taxonomy`, WP1-SSoT) für die
Frontmatter-Enums und folgt dem 3-State-/Schutzbereich-Muster aus
:mod:`pipeline.format_vault` (WP3a).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pipeline import taxonomy

# === Konstanten ===============================================================

#: Pflichtfelder im Vault-Frontmatter (Spiegel von ``scripts/_pkm_common``/WP1).
REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "slug",
        "summary",
        "type",
        "doc_role",
        "category",
        "sources_docs",
        "source_chunks",
        "status",
        "review_status",
        "confidence",
        "doc_version",
        "created",
        "updated",
    }
)

#: Verzeichnis-Namen, die vom Audit ausgenommen sind (vault-relativ, erste Ebene).
EXCLUDE_DIRS: frozenset[str] = frozenset({"_attic", "_assets", "00_Meta"})

#: Datei-Stems funktionaler Templates (dauerhafte unfenced/format-Ausnahme).
TEMPLATE_STEMS: frozenset[str] = frozenset(
    {
        "artikel-template-grundlagen",
        "artikel-template-kompaktreferenz",
        "artikel-template-prozessdokument",
        "artikel-formatierung",
    }
)

#: Heading-Marker, unter denen Stub-Wikilinks als *intendiert* gelten (kein Defekt).
STUB_SECTION_MARKERS: tuple[str, ...] = (
    "verwandte themen",
    "folge-notiz",
    "weiterführend",
    "siehe auch",
    "detailnotiz",
)

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_WIKILINK_RE = re.compile(r"(!?)\[\[([^\]]+)\]\]")
_SETEXT_RE = re.compile(r"^(={3,}|-{3,})\s*$")

_TOKEN_LEAK_RE = re.compile(r"turn\d+(?:view|search)\d+")
_PUA_RE = re.compile("[\ue200-\ue201]")
_URL_MASH_RE = re.compile(r"<[^>\n]+>https?://")
_CYRILLIC_RE = re.compile("[\u0400-\u04ff]")


# === Datenmodell ==============================================================


@dataclass(frozen=True)
class Finding:
    """Ein einzelner Audit-Befund.

    Args:
        rule: Regel-Kennung (z. B. ``"frontmatter"``, ``"wikilink"``).
        severity: ``"error"`` | ``"warning"`` | ``"info"``.
        relpath: Vault-relativer Pfad; ``""`` für Vault-Ebenen-Befunde.
        line: 1-basierte Zeilennummer oder ``None``.
        message: Menschlich lesbarer Befundtext.
        fixable: ``True`` wenn ein Safe-Tier-Repair existiert.
    """

    rule: str
    severity: str
    relpath: str
    line: int | None
    message: str
    fixable: bool = False


@dataclass
class VaultIndex:
    """Read-only-Index über den Vault (für Auflösbarkeits- und Kollisionsregeln)."""

    audit_files: dict[str, str] = field(default_factory=dict)
    frontmatter: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    parse_errors: dict[str, str] = field(default_factory=dict)
    target_stems: set[str] = field(default_factory=set)
    alias_to_paths: dict[str, list[str]] = field(default_factory=dict)


# === Frontmatter-Helfer =======================================================


def split_frontmatter(text: str) -> tuple[str | None, str, int]:
    """Teilt ``text`` in (Frontmatter-YAML | None, Body, Body-Start-Zeile 1-basiert)."""
    if not text.startswith(("---\n", "---\r\n")):
        return None, text, 1
    rest = text[text.index("\n") + 1 :]
    match = re.search(r"\n---[ \t]*\n", rest)
    if not match:
        return None, text, 1
    fm = rest[: match.start()]
    body = rest[match.end() :]
    body_start = text[: len(text) - len(body)].count("\n") + 1
    return fm, body, body_start


def parse_frontmatter(fm_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """YAML-Frontmatter-Text → ``(dict | None, fehler | None)``."""
    if not fm_text.strip():
        return None, "empty"
    try:
        data: Any = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        return None, f"yaml_error: {type(exc).__name__}"
    if not isinstance(data, dict):
        return None, "not_dict"
    return data, None


def is_content_md(path: Path, vault_dir: Path) -> bool:
    """``True`` wenn ``path`` eine zu auditierende Content-Datei ist."""
    if path.suffix != ".md" or path.name == "_index.md":
        return False
    rel_parts = path.relative_to(vault_dir).parts
    if any(part in EXCLUDE_DIRS for part in rel_parts):
        return False
    return path.stem not in TEMPLATE_STEMS


# === Body-Iteration (fence-/frontmatter-aware) ================================


@dataclass(frozen=True)
class BodyLine:
    """Eine Body-Zeile mit Kontext (1-basierte Zeilennummer, Fence-/Heading-Status)."""

    lineno: int
    text: str
    in_fence: bool
    fence_lang: str | None
    section: str


def iter_body(text: str) -> list[BodyLine]:
    """Zerlegt ``text`` in Body-Zeilen mit Fence-/Heading-Kontext (Frontmatter übersprungen)."""
    _, body, start = split_frontmatter(text)
    out: list[BodyLine] = []
    in_fence = False
    fence_marker = ""
    fence_lang: str | None = None
    section = ""
    for offset, raw in enumerate(body.splitlines()):
        lineno = start + offset
        fence = _FENCE_RE.match(raw)
        if fence and not in_fence:
            in_fence = True
            fence_marker = fence.group(1)
            fence_lang = fence.group(2).strip() or None
        elif fence and in_fence and raw.strip().startswith(fence_marker):
            out.append(BodyLine(lineno, raw, True, fence_lang, section))
            in_fence = False
            fence_lang = None
            continue
        elif not in_fence:
            heading = _HEADING_RE.match(raw)
            if heading:
                section = heading.group(2).strip().lower()
        out.append(BodyLine(lineno, raw, in_fence, fence_lang, section))
    return out


# === Regel 1: Frontmatter ↔ SSoT =============================================


def check_frontmatter(relpath: str, fm: dict[str, Any] | None, error: str | None) -> list[Finding]:
    """Regel 1 — Pflichtfelder, Enums, ``slug``-Konformität gegen die WP1-Taxonomie."""
    if fm is None:
        return [
            Finding("frontmatter", "error", relpath, 1, f"kein parsebares Frontmatter ({error})")
        ]
    out: list[Finding] = []
    missing = REQUIRED_FIELDS - set(fm)
    if missing:
        out.append(
            Finding(
                "frontmatter", "error", relpath, 1, f"fehlende Pflichtfelder: {sorted(missing)}"
            )
        )
    for fld in ("type", "status", "review_status", "confidence"):
        value = fm.get(fld)
        allowed = taxonomy.allowed_values(fld)
        if value is not None and allowed and value not in allowed:
            out.append(
                Finding("frontmatter", "error", relpath, 1, f"{fld}={value!r} nicht im Vokabular")
            )
    category = fm.get("category")
    if category is not None and category not in taxonomy.ALLOWED_CATEGORIES:
        out.append(
            Finding(
                "frontmatter", "warning", relpath, 1, f"category={category!r} unbekannt (→ Routing)"
            )
        )
    slug = fm.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        out.append(Finding("frontmatter", "error", relpath, 1, f"slug ungültig: {slug!r}"))
    elif slug != Path(relpath).stem:
        out.append(
            Finding(
                "frontmatter",
                "warning",
                relpath,
                1,
                f"slug {slug!r} ≠ Dateiname {Path(relpath).stem!r}",
            )
        )
    return out


# === Regel 2: Wikilink-Auflösbarkeit + Dangling-Klassifikation ===============


def _link_target_base(raw_target: str) -> str:
    """Reduziert ein Wikilink-Ziel auf den File-Basisteil (ohne ``|``/``#``/``^``)."""
    return raw_target.split("|", 1)[0].split("#", 1)[0].split("^", 1)[0].strip()


def _resolves(base: str, index: VaultIndex) -> bool:
    """``True`` wenn ``base`` auf eine Vault-Datei (Stem) oder einen Alias auflöst."""
    if not base:
        return True  # reiner Heading-/Block-Link im selben Doc
    if base in index.target_stems:
        return True
    return base.lower() in index.alias_to_paths


def check_wikilinks(relpath: str, text: str, index: VaultIndex) -> list[Finding]:
    """Regel 2 — unauflösbare Wikilinks; klassifiziert intendierte Stubs vs. echt-defekt."""
    out: list[Finding] = []
    for bl in iter_body(text):
        if bl.in_fence:
            continue  # Links in Code-Blöcken sind intendiert (Beispiel)
        for _embed, raw_target in _WIKILINK_RE.findall(bl.text):
            base = _link_target_base(raw_target)
            if _resolves(base, index):
                continue
            is_stub = any(marker in bl.section for marker in STUB_SECTION_MARKERS)
            if is_stub:
                out.append(
                    Finding(
                        "wikilink-stub",
                        "info",
                        relpath,
                        bl.lineno,
                        f"Stub-Link [[{base}]] (intendiert)",
                    )
                )
            else:
                out.append(
                    Finding("wikilink", "warning", relpath, bl.lineno, f"defekter Link [[{base}]]")
                )
    return out


# === Regel 3: Heading-Defekte =================================================


def check_headings(relpath: str, text: str) -> list[Finding]:
    """Regel 3 — ``**``-im-Heading, Junk-Heading, literales ``\\n``, Setext-Bruch."""
    out: list[Finding] = []
    lines = iter_body(text)
    for i, bl in enumerate(lines):
        if bl.in_fence:
            continue
        heading = _HEADING_RE.match(bl.text)
        if heading:
            out.extend(_heading_findings(relpath, bl.lineno, heading.group(2)))
        elif _SETEXT_RE.match(bl.text) and i > 0:
            prev = lines[i - 1]
            if not prev.in_fence and prev.text.strip() and not _HEADING_RE.match(prev.text):
                out.append(
                    Finding(
                        "heading-setext",
                        "warning",
                        relpath,
                        bl.lineno,
                        "Setext-Bruch (Prosa→Heading)",
                        True,
                    )
                )
    return out


def _heading_findings(relpath: str, lineno: int, htext: str) -> list[Finding]:
    """Befunde für einen einzelnen Heading-Text (``**``/Junk/literales ``\\n``)."""
    out: list[Finding] = []
    if "**" in htext:
        out.append(
            Finding("heading-bold", "warning", relpath, lineno, f"`**` im Heading: {htext!r}", True)
        )
    if "\\n" in htext:
        out.append(
            Finding(
                "heading-newline",
                "warning",
                relpath,
                lineno,
                f"literales \\n im Heading: {htext!r}",
                True,
            )
        )
    if htext.strip().lower() in ("unbenannt", "untitled", ""):
        out.append(Finding("heading-junk", "warning", relpath, lineno, f"Junk-Heading: {htext!r}"))
    return out


# === Regel 4: Code-Fences ohne Sprach-Tag =====================================


def check_fences(relpath: str, text: str) -> list[Finding]:
    """Regel 4 — öffnende Code-Fences ohne Sprach-Tag."""
    out: list[Finding] = []
    _, body, start = split_frontmatter(text)
    in_fence = False
    marker = ""
    for offset, raw in enumerate(body.splitlines()):
        fence = _FENCE_RE.match(raw)
        if not fence:
            continue
        if not in_fence:
            in_fence = True
            marker = fence.group(1)
            if not fence.group(2).strip():
                lang = detect_fence_lang(body.splitlines(), offset)
                out.append(
                    Finding(
                        "fence-untagged",
                        "warning",
                        relpath,
                        start + offset,
                        f"Fence ohne Sprach-Tag (→ {lang or '?'})",
                        lang is not None,
                    )
                )
        elif raw.strip().startswith(marker):
            in_fence = False
    return out


def detect_fence_lang(lines: list[str], open_idx: int) -> str | None:
    """Heuristische Sprach-Erkennung für einen untagged Fence (ab ``open_idx``).

    Liefert nur bei **eindeutigem** Signal eine Sprache, sonst ``None`` (→ Review).
    """
    block: list[str] = []
    for raw in lines[open_idx + 1 :]:
        if _FENCE_RE.match(raw):
            break
        block.append(raw)
    content = "\n".join(block)
    if not content.strip():
        return None
    if re.search(r"\b(def|import|print\()|^\s*(class|return)\b", content, re.MULTILINE):
        return "python"
    if re.search(r"(^|\n)\s*(\$ |sudo |apt |pip |brew |cd |ls |git )", content):
        return "bash"
    if re.match(r"^\s*[/(].*[/)]\s*(#|$)", content) or re.search(r"\\[dbsw]|\[\^?\\?\]", content):
        return "regex"
    return None


# === Regel 5: Korruptions-Scan ================================================


def check_corruption(relpath: str, text: str) -> list[Finding]:
    """Regel 5 — geleakte Tokens, PUA-Spans, URL-Mashups, fremdsprachige Kontamination."""
    out: list[Finding] = []
    for offset, raw in enumerate(text.splitlines(), start=1):
        if _TOKEN_LEAK_RE.search(raw):
            out.append(
                Finding(
                    "corruption-token",
                    "error",
                    relpath,
                    offset,
                    "Klartext-Token (turn…view/search…)",
                    True,
                )
            )
        if _PUA_RE.search(raw):
            out.append(
                Finding(
                    "corruption-pua", "error", relpath, offset, "PUA-Span (\\ue200-\\ue201)", True
                )
            )
        if _URL_MASH_RE.search(raw):
            out.append(
                Finding(
                    "corruption-urlmash", "warning", relpath, offset, "URL-Mashup (<Text>https://)"
                )
            )
        if _CYRILLIC_RE.search(raw):
            out.append(
                Finding(
                    "corruption-script",
                    "warning",
                    relpath,
                    offset,
                    "fremdsprachige Kontamination (Kyrillisch)",
                )
            )
    return out


# === Regel 7: Alias-Kollisionen ===============================================


def check_alias_collisions(index: VaultIndex) -> list[Finding]:
    """Regel 7 — Aliase, die vault-weit an mehr als einem Dokument hängen."""
    out: list[Finding] = []
    for alias, paths in sorted(index.alias_to_paths.items()):
        if len(paths) > 1:
            out.append(
                Finding(
                    "alias-collision",
                    "warning",
                    "",
                    None,
                    f"Alias {alias!r} an {len(paths)} Docs: {sorted(paths)}",
                )
            )
    return out


# === Regel 6: Doc-Count-Metrik ================================================


def doc_count(index: VaultIndex, vault_dir: Path) -> dict[str, int]:
    """Regel 6 — gültige Content-.md (Audit-Menge) + ``_attic``-Zähler."""
    attic = vault_dir / "_attic"
    attic_count = (
        sum(1 for p in attic.rglob("*.md") if p.name != "_index.md") if attic.is_dir() else 0
    )
    return {"content": len(index.audit_files), "attic": attic_count}


def reconcile_doc_count(counts: dict[str, int], baseline: tuple[int, int]) -> list[Finding]:
    """Vergleicht ``content``/``attic`` gegen eine Handover-Baseline (z. B. 194/6)."""
    base_content, base_attic = baseline
    out: list[Finding] = []
    if counts["attic"] != base_attic:
        out.append(
            Finding(
                "doc-count", "info", "", None, f"_attic {counts['attic']} ≠ Baseline {base_attic}"
            )
        )
    out.append(
        Finding(
            "doc-count",
            "info",
            "",
            None,
            f"Content-Files (Audit-Menge): {counts['content']} (Baseline-Main {base_content} inkl. _index/Meta)",
        )
    )
    return out


# === Regel 8: Cross-Link-Kandidaten ===========================================


def read_cross_link_candidates(candidates_md: Path) -> list[Finding]:
    """Regel 8 — listet Synthese-/Cross-Link-Kandidaten aus ``work/synthesis_candidates.md``."""
    if not candidates_md.is_file():
        return [
            Finding("cross-link", "info", "", None, f"keine Kandidaten-Datei: {candidates_md.name}")
        ]
    out: list[Finding] = []
    for line in candidates_md.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^## (SC_\d+)", line)
        if match:
            out.append(
                Finding(
                    "cross-link", "info", "", None, f"{match.group(1)} — Anwendung = WP4 Teil B"
                )
            )
    return out


# === Vault-Index-Aufbau + Audit-Orchestrierung ================================


def build_index(vault_dir: Path) -> VaultIndex:
    """Baut den read-only :class:`VaultIndex` über den gesamten Vault auf.

    ``target_stems``/``alias_to_paths`` umfassen **alle** ``.md`` (inkl. ``_attic``/
    Templates), da Obsidian dorthin auflöst; ``audit_files`` nur die Content-Menge.
    """
    index = VaultIndex()
    for path in sorted(vault_dir.rglob("*.md")):
        rel = path.relative_to(vault_dir).as_posix()
        index.target_stems.add(path.stem)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            index.parse_errors[rel] = f"read_error: {type(exc).__name__}"
            continue
        fm_text, _, _ = split_frontmatter(text)
        fm, err = parse_frontmatter(fm_text) if fm_text is not None else (None, "no_frontmatter")
        for alias in _aliases_of(fm):
            index.alias_to_paths.setdefault(alias.lower(), []).append(rel)
        if is_content_md(path, vault_dir):
            index.audit_files[rel] = text
            index.frontmatter[rel] = fm
            if fm is None:
                index.parse_errors[rel] = err or "unparsable"
    return index


def _aliases_of(fm: dict[str, Any] | None) -> list[str]:
    """Extrahiert die String-Aliase aus einem Frontmatter-Dict (robust gegen Typen)."""
    if not fm:
        return []
    raw = fm.get("aliases")
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, str)]


def audit_vault(
    vault_dir: Path,
    *,
    baseline: tuple[int, int] = (194, 6),
    candidates_md: Path | None = None,
) -> list[Finding]:
    """Führt alle neun Detektionsregeln read-only über den Vault aus.

    Args:
        vault_dir: Wurzel des produktiven Vaults.
        baseline: Handover-Doc-Count ``(content_main, attic)`` zum Reconcile.
        candidates_md: Pfad zu ``synthesis_candidates.md`` (Regel 8); ``None`` = skip.

    Returns:
        Sortierte Liste aller :class:`Finding` (Datei-Befunde + Vault-Ebene).
    """
    index = build_index(vault_dir)
    out: list[Finding] = []
    for rel, text in index.audit_files.items():
        fm = index.frontmatter.get(rel)
        out += check_frontmatter(rel, fm, index.parse_errors.get(rel))
        out += check_wikilinks(rel, text, index)
        out += check_headings(rel, text)
        out += check_fences(rel, text)
        out += check_corruption(rel, text)
    # Regel 9 — Quarantäne (nicht-parsebar, isoliert melden statt stillem Skip)
    for rel, err in index.parse_errors.items():
        if rel not in index.audit_files:
            out.append(Finding("quarantine", "error", rel, None, f"nicht parsebar: {err}"))
    out += check_alias_collisions(index)
    out += reconcile_doc_count(doc_count(index, vault_dir), baseline)
    if candidates_md is not None:
        out += read_cross_link_candidates(candidates_md)
    return out


# === Repair (Safe-Tier, idempotent) ==========================================


def _debold_headings(text: str) -> tuple[str, int]:
    """Entfernt ``**``-Marker aus Heading-Texten (Body, außerhalb Fences). Idempotent.

    Arbeitet auf ``text.split("\\n")`` (verlustfrei invers zu ``"\\n".join``), damit
    Trailing-Newline und Zeilenstruktur exakt erhalten bleiben.
    """
    parts = text.split("\n")
    n = 0
    in_frontmatter = bool(parts) and parts[0] == "---"
    fm_closed = not in_frontmatter
    in_fence = False
    marker = ""
    for i, raw in enumerate(parts):
        if in_frontmatter and not fm_closed:
            if i > 0 and raw.strip() == "---":
                fm_closed = True
            continue
        fence = _FENCE_RE.match(raw)
        if fence and not in_fence:
            in_fence, marker = True, fence.group(1)
            continue
        if fence and in_fence and raw.strip().startswith(marker):
            in_fence = False
            continue
        heading = _HEADING_RE.match(raw)
        if heading and not in_fence and "**" in heading.group(2):
            parts[i] = f"{heading.group(1)} {heading.group(2).replace('**', '')}"
            n += 1
    return "\n".join(parts), n


def _clean_tokens(text: str) -> tuple[str, int]:
    """Entfernt geleakte Klartext-Tokens und PUA-Spans (gesamtes Dokument). Idempotent."""
    cleaned, n1 = _TOKEN_LEAK_RE.subn("", text)
    cleaned, n2 = _PUA_RE.subn("", cleaned)
    return cleaned, n1 + n2


def repair_text(text: str) -> tuple[str, list[str]]:
    """Wendet alle Safe-Tier-Fixes idempotent an.

    Returns:
        ``(neuer_text, [aktions-logs])``. Bei ``[]`` war nichts zu tun.
    """
    actions: list[str] = []
    text, n_bold = _debold_headings(text)
    if n_bold:
        actions.append(f"{n_bold} `**`-Heading(s) entboldet")
    text, n_tok = _clean_tokens(text)
    if n_tok:
        actions.append(f"{n_tok} geleakte Token/PUA bereinigt")
    return text, actions


# === Repair: bidirektionale related: (für WP4 Teil B) ========================


def _set_related(fm_text: str, targets: list[str]) -> str:
    """Ersetzt/ergänzt den ``related:``-Block im Frontmatter-Text (Slug-Liste).

    Zeilenbasiert: ersetzt die ``related:``-Key-Zeile samt folgender ``- item``-Liste
    (deckt sowohl ``related: []`` als auch die Block-Form ab); hängt sonst an.
    """
    lines = fm_text.split("\n")
    block = ["related:"] + [f"  - {t}" for t in targets]
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        if not replaced and re.match(r"^related:", lines[i]):
            i += 1
            while i < len(lines) and re.match(r"^[ \t]*-[ \t]*\S", lines[i]):
                i += 1
            out.extend(block)
            replaced = True
            continue
        out.append(lines[i])
        i += 1
    if not replaced:
        out.extend(block)
    return "\n".join(out)


def add_bidirectional_related(
    files: dict[str, str], pairs: list[tuple[str, str]]
) -> dict[str, str]:
    """Stellt für jedes ``(slug_a, slug_b)``-Paar bidirektionale ``related:``-Links her.

    Args:
        files: ``relpath → text`` der betroffenen Files (Slugs = Stems).
        pairs: freigegebene Cross-Link-Paare (Slug-Ebene).

    Returns:
        ``relpath → neuer_text`` nur für tatsächlich geänderte Files (idempotent).
    """
    by_slug = {Path(rel).stem: rel for rel in files}
    wanted: dict[str, set[str]] = {}
    for a, b in pairs:
        if a in by_slug and b in by_slug:
            wanted.setdefault(a, set()).add(b)
            wanted.setdefault(b, set()).add(a)
    changed: dict[str, str] = {}
    for slug, neighbours in wanted.items():
        rel = by_slug[slug]
        text = files[rel]
        fm_text, body, _ = split_frontmatter(text)
        if fm_text is None:
            continue
        existing = set(_related_of(fm_text))
        merged = sorted(existing | neighbours)
        if merged == sorted(existing):
            continue
        new_fm = _set_related(fm_text, merged)
        changed[rel] = f"---\n{new_fm.rstrip(chr(10))}\n---\n{body}"
    return changed


def _related_of(fm_text: str) -> list[str]:
    """Liest die ``related:``-Slug-Liste aus einem Frontmatter-Text."""
    data, _ = parse_frontmatter(fm_text)
    if not data:
        return []
    raw = data.get("related")
    return [r for r in raw if isinstance(r, str)] if isinstance(raw, list) else []


# === Review-Modus (Unified-Diff-Patches, kein Auto-Write) =====================


def review_patches(relpath: str, text: str) -> list[str]:
    """Erzeugt Unified-Diff-Vorschläge für Unsafe-Fälle (kein Auto-Write).

    Deckt aktuell ab: Safe-Tier-Vorschau (entbolden/token-clean) als Patch. Fälle
    ohne deterministische Lösung (Fence ohne erkennbare Sprache, Junk-Heading)
    bleiben Befund-only und erscheinen nicht als Patch.
    """
    repaired, _actions = repair_text(text)
    if repaired == text:
        return []
    diff = difflib.unified_diff(
        text.splitlines(keepends=True),
        repaired.splitlines(keepends=True),
        fromfile=f"a/{relpath}",
        tofile=f"b/{relpath}",
    )
    return list(diff)


# === Report-Rendering =========================================================


def count_by_rule(findings: list[Finding]) -> dict[str, int]:
    """Aggregiert Befunde nach Regel-Kennung (für die Übersichtstabelle)."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.rule] = counts.get(finding.rule, 0) + 1
    return counts


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    """Aggregiert Befunde nach Severity (``error``/``warning``/``info``)."""
    counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def render_report(findings: list[Finding]) -> str:
    """Rendert die Befunde als Markdown-Report (gruppiert nach Datei, Vault-Ebene zuletzt)."""
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.relpath, []).append(finding)
    lines = ["# Vault-Audit-Report", ""]
    sev = count_by_severity(findings)
    lines.append(f"**{len(findings)} Befunde** — {sev['error']} error · {sev['warning']} warning · {sev['info']} info")
    lines.append("")
    for relpath in sorted(by_file, key=lambda r: (r == "", r)):
        title = relpath or "(Vault-Ebene)"
        lines.append(f"## {title}")
        for finding in by_file[relpath]:
            loc = f":{finding.line}" if finding.line else ""
            fix = " [fixable]" if finding.fixable else ""
            lines.append(f"- `{finding.rule}` ({finding.severity}){loc}: {finding.message}{fix}")
        lines.append("")
    return "\n".join(lines)
