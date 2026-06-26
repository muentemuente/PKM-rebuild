"""WP4 — Vault-Audit/Repair-Tooling (read-only Audit · Safe-Repair · Review-Patch).

Zielt auf den **produktiven** Obsidian-Vault (``_paths.BRAIN_VAULT``). Drei Modi:

* :func:`audit_vault` — read-only Befund-Report über alle Content-Files
  (``_attic``/``_index``/``00_Meta``/Templates ausgenommen). Implementiert die
  neun Detektionsregeln aus dem WP4-Spec.
* :func:`repair_text` — deterministische, **verlustfreie**, idempotente Safe-Tier-
  Fixes auf einem File-Text: ``**``-Heading entbolden, Junk-Heading entfernen,
  Setext-Bruch entkoppeln, PUA-Wrapper bereinigen, genuin unclosed Code-Fence
  schließen, Code-Fences bei eindeutiger Heuristik taggen. Schutzbereiche
  (Frontmatter, Code-Inhalt, Wikilinks/Embeds) bleiben unberührt.
* :func:`review_patches` — Unified-Diff-Vorschläge für **Review-Tier**-Fälle, die
  nie auto-angewendet werden: verlustbehaftete ``turn…``-Token-Leaks (keine
  rekonstruierbare URL → B-2) und URL-Mashup-Rekonstruktion (an der URL/Prosa-Grenze
  **nicht** deterministisch — CANARY-Belege ``figma.com:``, ``affinity.serif.com/-Setup``).
  Fences ohne erkennbare Sprache bleiben Audit-Findings.

Das Modul ist **non-mutating gegenüber dem Vault**: alle öffentlichen Funktionen
lesen und liefern Datenstrukturen bzw. neuen Text zurück. Das Schreiben (3-State
``raw``→``work``→``export``) ist Sache des Aufrufers (CLI/WP4-Teil-B).

Wiederverwendet die Taxonomie-Facade (:mod:`pipeline.taxonomy`, WP1-SSoT) für die
Frontmatter-Enums und folgt dem 3-State-/Schutzbereich-Muster aus
:mod:`pipeline.format_vault` (WP3a).
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
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
#: Inline-Code-Span (Backtick-delimitiert, einzeilig) — Wikilinks darin sind Syntax-Demo.
_INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
_SETEXT_RE = re.compile(r"^(={3,}|-{3,})\s*$")
#: Box-Drawing/Bullet-Glyphen → markiert ASCII-Diagramme/Trees (kein md/text-Tag).
_BOXDRAW_RE = re.compile(r"[─│┌┐└┘├┤┬┴┼╔╗╚╝═║╠╣╦╩╬•◦▪▶►]")

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
        # Inline-Code maskieren: `` `[[Beispiel]]` `` ist Syntax-Demo, kein echter Link.
        scan_text = _INLINE_CODE_RE.sub("", bl.text)
        for m in _WIKILINK_RE.finditer(scan_text):
            # ``[[N]](url)`` = Markdown-Link mit Klammer-Text, kein Wikilink (z. B. Zitate).
            if scan_text[m.end() : m.end() + 1] == "(":
                continue
            base = _link_target_base(m.group(2))
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


def _fence_block(lines: list[str], open_idx: int) -> str:
    """Liefert den Inhalt eines Fences (Zeilen nach ``open_idx`` bis zum nächsten Fence)."""
    block: list[str] = []
    for raw in lines[open_idx + 1 :]:
        if _FENCE_RE.match(raw):
            break
        block.append(raw)
    return "\n".join(block)


def detect_fence_lang(lines: list[str], open_idx: int) -> str | None:
    """Heuristische Sprach-Erkennung für einen untagged Fence (ab ``open_idx``).

    Liefert nur bei **eindeutigem** Signal eine Sprache, sonst ``None`` (→ Review).
    Reihenfolge spezifisch→generisch; ``text`` nur als bewusster Prosa-Fallback.
    """
    content = _fence_block(lines, open_idx)
    if not content.strip():
        return None
    for detector in (
        _is_python,
        _is_bash,
        _is_sql,
        _is_json,
        _is_toml,
        _is_yaml,
        _is_html,
        _is_regex,
        _is_md,
        _is_text,
    ):
        lang = detector(content)
        if lang:
            return lang
    return None


def _is_python(c: str) -> str | None:
    if re.search(r"^\s*(def |class |import |from .+ import |return\b)|print\(", c, re.MULTILINE):
        return "python"
    return None


def _is_bash(c: str) -> str | None:
    """Shell: Prompt/Tool-Token am Zeilenanfang. **Kein** bares ``$VAR`` (fängt sonst JS ``$0``)."""
    tools = (
        r"\$ |sudo |apt |apt-get |pip |pip3 |brew |cd |ls |git |export |echo |chmod |chown |"
        r"mkdir |source |deactivate\b|npm |yarn |pnpm |npx |docker |kubectl |cargo |curl |wget |"
        r"ssh |scp |rsync |tar |grep |sed |awk |systemctl "
    )
    if re.search(r"(?m)^\s*(" + tools + r")", c):
        return "bash"
    if re.search(r"(?m)^\$\{\w+", c):  # ${VAR} mit Klammer (nicht JS $0/$1)
        return "bash"
    if re.search(r"^#!.*/(ba|z)?sh\b", c, re.MULTILINE):
        return "bash"
    return None


def _is_sql(c: str) -> str | None:
    """SQL: ``SELECT … FROM`` oder eindeutige DDL/DML-Anweisung (mehrteilig, prosa-fest)."""
    if re.search(r"\bSELECT\b.+\bFROM\b", c, re.IGNORECASE | re.DOTALL):
        return "sql"
    if re.search(
        r"(?im)^\s*(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|"
        r"CREATE\s+(TABLE|DATABASE|INDEX)|ALTER\s+TABLE|DROP\s+(TABLE|DATABASE))\b",
        c,
    ):
        return "sql"
    return None


def _is_html(c: str) -> str | None:
    """HTML/XML: Schließ-Tag ``</tag>`` **und** passender Öffner im Block."""
    if re.search(r"</[a-zA-Z][\w-]*>", c) and re.search(r"<[a-zA-Z][\w-]*(\s[^>]*)?>", c):
        return "html"
    return None


def _is_regex(c: str) -> str | None:
    if re.match(r"^\s*/.*/[a-z]*\s*(#|$)", c, re.MULTILINE) or re.search(r"\\[dDwWsSbB]|\\\[", c):
        return "regex"
    return None


def _is_json(c: str) -> str | None:
    stripped = c.strip()
    if stripped[:1] in "{[" and re.search(r'"\s*:\s*', stripped):
        return "json"
    return None


def _is_toml(c: str) -> str | None:
    if re.search(r"^\[[\w.\-]+\]\s*$", c, re.MULTILINE) and re.search(
        r"^[\w.\-]+ = ", c, re.MULTILINE
    ):
        return "toml"
    return None


def _is_yaml(c: str) -> str | None:
    keyed = re.findall(r"^[ \t]*[\w.\-]+:( .+)?$", c, re.MULTILINE)
    code_like = re.search(r"[{}=]|^\s*(def |class )", c, re.MULTILINE)
    if len(keyed) >= 2 and not code_like:
        return "yaml"
    return None


def _is_md(c: str) -> str | None:
    """Markdown: GFM-Tabellen-Separator ODER mehrheitlich Listen-Items (Bullets/nummeriert)."""
    if _BOXDRAW_RE.search(c):  # ASCII-Diagramm/Tree → kein md
        return None
    if re.search(r"^\|[\s:\-|]+\|\s*$", c, re.MULTILINE):  # GFM-Tabellen-Separator
        return "md"
    nonblank = [ln for ln in c.splitlines() if ln.strip()]
    if not nonblank:
        return None
    # yaml-artig (``key:`` + Listen) ist kein md
    if re.search(r"(?m)^\s*[\w.\-]+:\s*$", c) and re.search(r"(?m)^\s*[-*+]\s", c):
        return None
    # Listen-Items sind das starke Signal; ATX-``#`` NICHT zählen (fängt Code-Kommentare).
    markers = sum(1 for ln in nonblank if re.match(r"^\s{0,3}(\d+\.\s+\S|[-*+]\s+\S)", ln))
    if markers >= 2 and markers >= len(nonblank) / 2:
        return "md"
    return None


def _is_text(c: str) -> str | None:
    """Prosa-Fallback: nur wenn keine Code-/Struktur-/Diagramm-Signale und natürlichsprachlich."""
    if _BOXDRAW_RE.search(c):  # ASCII-Diagramm/Tree → keine Prosa
        return None
    if re.search(r"[{}<>=$/\\|]|\b(def|class|import|function|var|const)\b", c):
        return None
    lines = [ln for ln in c.splitlines() if ln.strip()]
    if not lines:
        return None
    proselike = sum(1 for ln in lines if len(ln.split()) >= 4 and re.search(r"[A-Za-zÄÖÜäöüß]", ln))
    return "text" if proselike >= max(1, len(lines) // 2) else None


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


# Genehmigte Doc-Count-Baseline (G6) — die *einzige* Quelle dieser Zahlen.
# Semantik: (content, attic) = (Audit-Content-Menge `len(index.audit_files)`,
# `_attic`-Artikel). Verifiziert gegen den Live-Vault am 2026-06-21 (165 / 6).
# Die Audit-Content-Menge schließt _index.md/00_Meta/_assets/_attic + funktionale
# Templates aus (s. build_index). Erweiterung des Vaults = bewusste Baseline-Pflege hier.
DOC_COUNT_BASELINE: tuple[int, int] = (165, 6)


def doc_count(index: VaultIndex, vault_dir: Path) -> dict[str, int]:
    """Regel 6 — gültige Content-.md (Audit-Menge) + ``_attic``-Zähler."""
    attic = vault_dir / "_attic"
    attic_count = (
        sum(1 for p in attic.rglob("*.md") if p.name != "_index.md") if attic.is_dir() else 0
    )
    return {"content": len(index.audit_files), "attic": attic_count}


def content_by_cluster(index: VaultIndex) -> dict[str, int]:
    """Audit-Content-Files je Top-Level-Cluster — lokalisiert Count-Drift im Reconcile."""
    out: dict[str, int] = {}
    for rel in index.audit_files:
        cluster = rel.split("/", 1)[0] if "/" in rel else "(root)"
        out[cluster] = out.get(cluster, 0) + 1
    return out


def reconcile_doc_count(
    counts: dict[str, int],
    baseline: tuple[int, int] = DOC_COUNT_BASELINE,
    *,
    by_cluster: dict[str, int] | None = None,
) -> list[Finding]:
    """Reconcile ``content``/``attic`` gegen die :data:`DOC_COUNT_BASELINE`.

    Liefert ein ``PASS``-Finding bei exakter Übereinstimmung, sonst je Abweichung ein
    ``warning``-Finding mit Delta. Weicht ``content`` ab und ist ``by_cluster`` gegeben,
    wird die Pro-Cluster-Verteilung zur Lokalisierung angehängt.
    """
    base_content, base_attic = baseline
    dc, da = counts["content"], counts["attic"]
    if dc == base_content and da == base_attic:
        return [
            Finding(
                "doc-count",
                "info",
                "",
                None,
                f"PASS: content {dc}/{base_content}, _attic {da}/{base_attic}",
            )
        ]
    out: list[Finding] = []
    if dc != base_content:
        msg = f"Abweichung content: {dc} ≠ Baseline {base_content} (Δ{dc - base_content:+d})"
        if by_cluster:
            dist = ", ".join(f"{k}:{v}" for k, v in sorted(by_cluster.items()))
            msg += f" — Cluster: {dist}"
        out.append(Finding("doc-count", "warning", "", None, msg))
    if da != base_attic:
        out.append(
            Finding(
                "doc-count",
                "warning",
                "",
                None,
                f"Abweichung _attic: {da} ≠ Baseline {base_attic} (Δ{da - base_attic:+d})",
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


# === WP-N1: Deterministische NB-Report-Suite (read-only Detektoren) ===========
# Fünf rein deterministische Detektoren (NB-1/2/6/7/12/14). Sie LESEN Vault-Notes
# und emittieren Findings — kein Vault-Write, kein Qwen, kein Schema-Feld. Confidence
# wird in die Message kodiert (``[confidence=…]``), da :class:`Finding` kein eigenes
# Feld trägt (minimaler Diff). Toggles + Schwellen leben in :class:`NBReportConfig`.


@dataclass(frozen=True)
class NBReportConfig:
    """Schwellen + Toggles der NB-Report-Suite (Defaults = Spec WP-N1)."""

    # Regelgruppen-Toggles (Near-Dup + Akronyme bewusst default AUS).
    fragment: bool = True
    dup: bool = True
    gap: bool = True
    stale: bool = True
    boilerplate: bool = True
    near_dup: bool = False
    acronyms: bool = False
    # Schwellen.
    fragment_min_words: int = 30
    dup_min_words: int = 12
    dup_near_threshold: float = 0.95
    stale_age_days: int = 365
    stale_year_gap: int = 2
    boilerplate_link_run: int = 3
    # Staleness-Bezugszeitpunkt (None → ``date.today()`` zur Laufzeit; Tests setzen fix).
    now: date | None = None
    # Embedding-Parameter für den optionalen Near-Dup-Pfad.
    embed_model: str = "sentence-transformers/all-mpnet-base-v2"
    embed_device: str = "auto"
    embed_batch: int = 32


#: Platzhalter-/Lücken-Marker (außerhalb Code/Inline-Code).
_GAP_MARKER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b|\?\?\?|[<\[](?:\.\.\.|…)[>\]]")
#: Text-Referenz ohne auflösbares Ziel (numerierte/relative Verweise).
_GAP_TEXTREF_RE = re.compile(r"\bsiehe\s+(oben|unten|abschnitt\s+\d+|kapitel\s+\d+)\b", re.IGNORECASE)
#: Staleness-Textmarker: „Stand …/as of …" gefolgt von einer Jahreszahl.
_STALE_MARKER_RE = re.compile(r"\b(?:Stand|as of)\b[^\n]{0,24}?(\d{4})", re.IGNORECASE)
#: Consent/Cookie-Phrasen (hochspezifisch → Einzel-Signal genügt).
_CONSENT_RE = re.compile(
    r"verwendet cookies|cookie-einstellung|cookies? (?:zu )?akzeptier|nutzung von cookies",
    re.IGNORECASE,
)
#: CTA-Floskeln (schwaches Signal → braucht ein zweites).
_CTA_RE = re.compile(
    r"\b(click here|weiterlesen|mehr erfahren|jetzt teilen|hier klicken)\b", re.IGNORECASE
)
#: Eine Zeile, die NUR ein Link/Wikilink ist (optional Bullet) — für Link-Run-Cluster.
_LINK_ONLY_RE = re.compile(
    r"^[-*]?\s*(?:!?\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\)|https?://\S+)\s*$"
)
#: Undefiniertes All-Caps-Akronym (optional, hohes FP-Risiko → default AUS).
_ACRONYM_RE = re.compile(r"\b([A-ZÄÖÜ]{3,})\b")


def _is_table_line(raw: str) -> bool:
    """``True`` für Markdown-Tabellenzeilen (beginnen mit ``|``)."""
    return raw.lstrip().startswith("|")


def _prose_paragraphs(text: str) -> list[tuple[str, int]]:
    """Prosa-Absätze (Leerzeilen-getrennt) als ``(joined_text, start_line)``.

    Code-Fences und Tabellenzeilen werden ausgeschlossen (FP-Schutz für NB-1/NB-2).
    """
    out: list[tuple[str, int]] = []
    buf: list[str] = []
    buf_start = 0
    for bl in iter_body(text):
        is_break = bl.in_fence or _is_table_line(bl.text) or not bl.text.strip()
        if is_break:
            if buf:
                out.append((" ".join(buf), buf_start))
                buf = []
            continue
        if not buf:
            buf_start = bl.lineno
        buf.append(bl.text.strip())
    if buf:
        out.append((" ".join(buf), buf_start))
    return out


def _norm_paragraph(p: str) -> str:
    """Normalisiert einen Absatz für den Exakt-Dup-Vergleich (kein Lowercasing)."""
    collapsed = re.sub(r"\s+", " ", p).strip()
    return collapsed.strip(" \t.,;:!?\"'")


def _confidence(msg: str, level: str) -> str:
    """Hängt den Confidence-Tag an einen Befundtext (Finding hat kein eigenes Feld)."""
    return f"{msg} [confidence={level}]"


def check_fragment(
    relpath: str, text: str, fm: dict[str, Any] | None, cfg: NBReportConfig
) -> list[Finding]:
    """NB-14 — Fragment: sehr kurz, ohne Headings, mit unvollständigem Frontmatter.

    ``type: gedanke`` ist absichtlich kurz und wird **nie** geflaggt.
    """
    if not cfg.fragment:
        return []
    if fm and fm.get("type") == "gedanke":
        return []
    _, body, _ = split_frontmatter(text)
    word_count = len(body.split())
    if word_count >= cfg.fragment_min_words:
        return []
    has_heading = any(
        _HEADING_RE.match(bl.text) for bl in iter_body(text) if not bl.in_fence
    )
    if has_heading:
        return []
    fm = fm or {}
    title_empty = not str(fm.get("title") or "").strip()
    summary_empty = not str(fm.get("summary") or "").strip()
    if not (title_empty or summary_empty):
        return []
    lacks = "title" if title_empty else "summary"
    return [
        Finding(
            "nb14-fragment",
            "info",
            relpath,
            1,
            _confidence(
                f"Fragment-Verdacht: {word_count} Wörter, keine Headings, {lacks} leer", "high"
            ),
        )
    ]


def check_dup_paragraph(relpath: str, text: str, cfg: NBReportConfig) -> list[Finding]:
    """NB-1 — innerhalb derselben Note wiederholte Absätze (exakt; optional near)."""
    if not cfg.dup:
        return []
    paras = [
        (norm, line, raw)
        for raw, line in _prose_paragraphs(text)
        if len((norm := _norm_paragraph(raw)).split()) > cfg.dup_min_words
    ]
    out: list[Finding] = []
    seen: dict[str, int] = {}
    reported: set[str] = set()
    for norm, line, _raw in paras:
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if h in seen and h not in reported:
            snippet = norm[:60] + ("…" if len(norm) > 60 else "")
            out.append(
                Finding(
                    "nb1-dup-paragraph",
                    "info",
                    relpath,
                    line,
                    _confidence(
                        f"Absatz wiederholt (zuerst Zeile {seen[h]}): {snippet!r}", "high"
                    ),
                )
            )
            reported.add(h)
        seen.setdefault(h, line)
    if cfg.near_dup:
        out += _check_near_dup(relpath, paras, reported, cfg)
    return out


def _check_near_dup(
    relpath: str,
    paras: list[tuple[str, int, str]],
    exact_hashes: set[str],
    cfg: NBReportConfig,
) -> list[Finding]:
    """Optionaler Near-Dup-Pfad (Embedding-Cosine ≥ Schwelle); Default AUS."""
    texts = [norm for norm, _l, _r in paras]
    if len(texts) < 2:
        return []
    from pipeline import redundancy_scan

    sim = redundancy_scan.embed_similarity(
        texts, model_name=cfg.embed_model, device=cfg.embed_device, batch_size=cfg.embed_batch
    )
    out: list[Finding] = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if float(sim[i][j]) >= cfg.dup_near_threshold:
                # Exakte Dubletten (oben gemeldet) hier nicht doppelt aufführen.
                if texts[i] == texts[j]:
                    continue
                line = paras[j][1]
                out.append(
                    Finding(
                        "nb1-near-dup",
                        "info",
                        relpath,
                        line,
                        _confidence(
                            f"Absatz semantisch ~ Zeile {paras[i][1]} "
                            f"(cos {float(sim[i][j]):.3f})",
                            "medium",
                        ),
                    )
                )
    return out


def check_gap_markers(relpath: str, text: str, cfg: NBReportConfig) -> list[Finding]:
    """NB-6/7 — Struktur-Lücken: Platzhalter-Marker, leere Sektionen, Textrefs."""
    if not cfg.gap:
        return []
    out: list[Finding] = []
    lines = iter_body(text)
    for bl in lines:
        if bl.in_fence:
            continue
        scan = _INLINE_CODE_RE.sub("", bl.text)
        for m in _GAP_MARKER_RE.finditer(scan):
            out.append(
                Finding(
                    "nb67-gap-marker",
                    "info",
                    relpath,
                    bl.lineno,
                    _confidence(f"Lücken-Marker: {m.group(0)!r}", "high"),
                )
            )
        ref = _GAP_TEXTREF_RE.search(scan)
        if ref:
            out.append(
                Finding(
                    "nb67-gap-marker",
                    "info",
                    relpath,
                    bl.lineno,
                    _confidence(f"Textreferenz ohne Wikilink-Ziel: {ref.group(0)!r}", "high"),
                )
            )
    out += _check_empty_sections(relpath, lines)
    if cfg.acronyms:
        out += _check_acronyms(relpath, lines)
    return out


def _check_empty_sections(relpath: str, lines: list[BodyLine]) -> list[Finding]:
    """Heading, dem direkt das nächste Heading oder EOF folgt (kein Inhalt)."""
    out: list[Finding] = []
    heading_idx = [
        i for i, bl in enumerate(lines) if not bl.in_fence and _HEADING_RE.match(bl.text)
    ]
    for k, i in enumerate(heading_idx):
        next_i = heading_idx[k + 1] if k + 1 < len(heading_idx) else len(lines)
        has_content = any(lines[j].text.strip() for j in range(i + 1, next_i))
        if not has_content:
            htext = _HEADING_RE.match(lines[i].text).group(2)  # type: ignore[union-attr]
            out.append(
                Finding(
                    "nb67-gap-marker",
                    "info",
                    relpath,
                    lines[i].lineno,
                    _confidence(f"leere Sektion: {htext!r}", "high"),
                )
            )
    return out


def _check_acronyms(relpath: str, lines: list[BodyLine]) -> list[Finding]:
    """Optional (Default AUS): All-Caps-Akronyme ohne Klammer-Definition. Niedrige Confidence."""
    out: list[Finding] = []
    seen: set[str] = set()
    for bl in lines:
        if bl.in_fence:
            continue
        scan = _INLINE_CODE_RE.sub("", bl.text)
        for m in _ACRONYM_RE.finditer(scan):
            token = m.group(1)
            if token in seen:
                continue
            # Definition in Klammern in derselben Zeile → nicht undefiniert.
            if re.search(rf"\(\s*{re.escape(token)}\s*\)", scan):
                continue
            seen.add(token)
            out.append(
                Finding(
                    "nb67-acronym",
                    "info",
                    relpath,
                    bl.lineno,
                    _confidence(f"undefiniertes Akronym: {token!r}", "low"),
                )
            )
    return out


def check_staleness(
    relpath: str, text: str, fm: dict[str, Any] | None, cfg: NBReportConfig
) -> list[Finding]:
    """NB-12 — Aktualitäts-**Proxy** (kein semantisches Veraltungs-Urteil)."""
    if not cfg.stale:
        return []
    out: list[Finding] = []
    now = cfg.now or date.today()
    fm = fm or {}
    ref = _as_date(fm.get("updated")) or _as_date(fm.get("created"))
    if ref is not None and (now - ref).days > cfg.stale_age_days:
        out.append(
            Finding(
                "nb12-stale-age",
                "info",
                relpath,
                1,
                _confidence(
                    f"Aktualitäts-Proxy (keine semantische Veraltung): "
                    f"{(now - ref).days} Tage seit {ref.isoformat()}",
                    "medium",
                ),
            )
        )
    cutoff = now.year - cfg.stale_year_gap
    for bl in iter_body(text):
        if bl.in_fence:
            continue
        for m in _STALE_MARKER_RE.finditer(bl.text):
            year = int(m.group(1))
            if year < cutoff:
                out.append(
                    Finding(
                        "nb12-stale-marker",
                        "info",
                        relpath,
                        bl.lineno,
                        _confidence(
                            f"Aktualitäts-Proxy (Textmarker): {m.group(0)!r} (Jahr {year})",
                            "medium",
                        ),
                    )
                )
    return out


def _as_date(value: Any) -> date | None:
    """Robuste Datum-Extraktion aus Frontmatter-Werten (date/datetime/ISO-String)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def check_boilerplate(relpath: str, text: str, cfg: NBReportConfig) -> list[Finding]:
    """NB-2 — Navi/Werbung/Consent **detect-only** (nie strippen).

    FP-Guard: Befund nur bei ≥2 korrelierenden Signaltypen ODER einem hochspezifischen
    Consent-Muster. Jeder Befund nennt Snippet + Muster-ID.
    """
    if not cfg.boilerplate:
        return []
    body_lines = [bl for bl in iter_body(text) if not bl.in_fence]
    signals: list[tuple[str, int, str, str]] = []  # (pattern_id, line, snippet, confidence)

    for bl in body_lines:
        cm = _CONSENT_RE.search(bl.text)
        if cm:
            signals.append(("consent", bl.lineno, cm.group(0), "medium"))
        ct = _CTA_RE.search(bl.text)
        if ct:
            signals.append(("cta", bl.lineno, ct.group(0), "low"))
        if _is_nav_line(bl.text):
            signals.append(("nav", bl.lineno, bl.text.strip()[:50], "low"))

    # Link-Run: ≥ N aufeinanderfolgende reine Link-Zeilen.
    run_start = 0
    run_len = 0
    for bl in body_lines:
        if _LINK_ONLY_RE.match(bl.text.strip()):
            if run_len == 0:
                run_start = bl.lineno
            run_len += 1
        else:
            if run_len >= cfg.boilerplate_link_run:
                signals.append(("link-run", run_start, f"{run_len} Link-Zeilen", "low"))
            run_len = 0
    if run_len >= cfg.boilerplate_link_run:
        signals.append(("link-run", run_start, f"{run_len} Link-Zeilen", "low"))

    has_consent = any(s[0] == "consent" for s in signals)
    distinct_types = {s[0] for s in signals}
    if not has_consent and len(distinct_types) < 2:
        return []  # FP-Guard: einzelnes schwaches Signal → unterdrücken
    return [
        Finding(
            "nb2-boilerplate",
            "info",
            relpath,
            line,
            _confidence(f"Boilerplate-Verdacht [{pid}]: {snippet!r}", conf),
        )
        for pid, line, snippet, conf in signals
    ]


def _is_nav_line(raw: str) -> bool:
    """Menü-/Nav-Zeile: Pipe-getrennte Kurzlabels (``Start | Über | Kontakt``)."""
    s = raw.strip()
    if _is_table_line(s) or s.count("|") < 2:
        return False
    segments = [seg.strip() for seg in s.split("|") if seg.strip()]
    if len(segments) < 3 or len(segments) > 6:
        return False
    # Kurzlabels (≤ 20 Zeichen) statt Prosa-mit-Pipes → Nav-typisch.
    return all(len(seg) <= 20 for seg in segments)


def check_nb_report_suite(
    relpath: str, text: str, fm: dict[str, Any] | None, cfg: NBReportConfig
) -> list[Finding]:
    """Bündelt die fünf NB-Detektoren für eine einzelne Note (read-only)."""
    out: list[Finding] = []
    out += check_fragment(relpath, text, fm, cfg)
    out += check_dup_paragraph(relpath, text, cfg)
    out += check_gap_markers(relpath, text, cfg)
    out += check_staleness(relpath, text, fm, cfg)
    out += check_boilerplate(relpath, text, cfg)
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
    baseline: tuple[int, int] = DOC_COUNT_BASELINE,
    candidates_md: Path | None = None,
    nb_config: NBReportConfig | None = None,
) -> list[Finding]:
    """Führt alle Detektionsregeln read-only über den Vault aus (9 WP4 + NB-Suite).

    Args:
        vault_dir: Wurzel des produktiven Vaults.
        baseline: Handover-Doc-Count ``(content_main, attic)`` zum Reconcile.
        candidates_md: Pfad zu ``synthesis_candidates.md`` (Regel 8); ``None`` = skip.
        nb_config: Schwellen/Toggles der deterministischen NB-Report-Suite
            (WP-N1, read-only); ``None`` → :class:`NBReportConfig`-Defaults.

    Returns:
        Sortierte Liste aller :class:`Finding` (Datei-Befunde + Vault-Ebene).
    """
    index = build_index(vault_dir)
    nb_cfg = nb_config or NBReportConfig()
    out: list[Finding] = []
    for rel, text in index.audit_files.items():
        fm = index.frontmatter.get(rel)
        out += check_frontmatter(rel, fm, index.parse_errors.get(rel))
        out += check_wikilinks(rel, text, index)
        out += check_headings(rel, text)
        out += check_fences(rel, text)
        out += check_corruption(rel, text)
        out += check_nb_report_suite(rel, text, fm, nb_cfg)
    # Regel 9 — Quarantäne (nicht-parsebar, isoliert melden statt stillem Skip)
    for rel, err in index.parse_errors.items():
        if rel not in index.audit_files:
            out.append(Finding("quarantine", "error", rel, None, f"nicht parsebar: {err}"))
    out += check_alias_collisions(index)
    out += reconcile_doc_count(
        doc_count(index, vault_dir), baseline, by_cluster=content_by_cluster(index)
    )
    if candidates_md is not None:
        out += read_cross_link_candidates(candidates_md)
    return out


def audit_build_output(vault_dir: Path) -> dict[str, int]:
    """Read-only Post-Build-Audit über das frisch gebaute ``output/`` (S3/G4).

    Fokus-Verifikation des Build-Ergebnisses — **keine** Mutation, **kein** Doc-Count-
    Reconcile (für den Staging-Build irrelevant). Reuse der bestehenden Engine
    (:func:`build_index`, :func:`repair_text`, :func:`check_wikilinks`).

    Returns:
        Zähler-Dict:

        * ``safe_tier_rest`` — Files, in denen :func:`repair_text` noch Safe-Tier-Fixes
          fände (bei korrektem repair-on-build erwartet **0** — der Beleg für den
          sauberen Build).
        * ``parse_errors`` — Files mit nicht-parsebarem Frontmatter.
        * ``dangling`` — unauflösbare (echt-defekte) Wikilinks im Body.
    """
    index = build_index(vault_dir)
    safe_tier_rest = 0
    dangling = 0
    for rel, text in index.audit_files.items():
        _, actions = repair_text(text)
        if actions:
            safe_tier_rest += 1
        dangling += sum(1 for f in check_wikilinks(rel, text, index) if f.rule == "wikilink")
    return {
        "safe_tier_rest": safe_tier_rest,
        "parse_errors": len(index.parse_errors),
        "dangling": dangling,
    }


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


_URL_MASH_RECON_RE = re.compile(r"\burl(\S+?)(https?://[^\s)\]]+)")
_JUNK_HEADING_TEXTS = frozenset({"unbenannt", "untitled", ""})


def _scan_states(parts: list[str]) -> list[tuple[bool, bool]]:
    """Pro Zeile ``(in_frontmatter, in_fence)``. Fence-Marker-Zeilen zählen als ``in_fence``."""
    states: list[tuple[bool, bool]] = []
    in_fm = bool(parts) and parts[0] == "---"
    fm_closed = not in_fm
    in_fence = False
    marker = ""
    for i, raw in enumerate(parts):
        if in_fm and not fm_closed:
            states.append((True, False))
            if i > 0 and raw.strip() == "---":
                fm_closed = True
            continue
        fence = _FENCE_RE.match(raw)
        if fence and not in_fence:
            in_fence, marker = True, fence.group(1)
            states.append((False, True))
        elif fence and in_fence and raw.strip().startswith(marker):
            in_fence = False
            states.append((False, True))
        else:
            states.append((False, in_fence))
    return states


def _clean_pua(text: str) -> tuple[str, int]:
    """Entfernt PUA-Wrapper-Zeichen ``\\ue200``/``\\ue201`` (verlustfrei). Idempotent."""
    return _PUA_RE.subn("", text)


def _fix_setext(text: str) -> tuple[str, int]:
    """Entkoppelt ``Prosa\\n---``-Setext-False-Breaks (Leerzeile davor). Idempotent, fence-aware."""
    parts = text.split("\n")
    states = _scan_states(parts)
    out: list[str] = []
    n = 0
    for i, raw in enumerate(parts):
        in_fm, in_fence = states[i]
        if not in_fm and not in_fence and i > 0 and _SETEXT_RE.match(raw):
            prev_fm, prev_fence = states[i - 1]
            prev = parts[i - 1]
            if not prev_fm and not prev_fence and prev.strip() and not _HEADING_RE.match(prev):
                out.append("")
                n += 1
        out.append(raw)
    return "\n".join(out), n


def _remove_junk_headings(text: str) -> tuple[str, int]:
    """Entfernt eindeutige Junk-/Platzhalter-Headings (``# Unbenannt``, leer). Idempotent."""
    parts = text.split("\n")
    states = _scan_states(parts)
    out: list[str] = []
    n = 0
    for i, raw in enumerate(parts):
        in_fm, in_fence = states[i]
        heading = _HEADING_RE.match(raw)
        if (
            not in_fm
            and not in_fence
            and heading
            and heading.group(2).strip().lower() in _JUNK_HEADING_TEXTS
        ):
            n += 1
            continue
        out.append(raw)
    return "\n".join(out), n


def _reconstruct_url_mash(text: str) -> tuple[str, int]:
    """Review-Tier: ``url<Text>https://<url>``-Mashup → ``[Text](url)``.

    **Kein Safe-Auto** — die URL/Prosa-Grenze ist nicht trennscharf (``[^\\s)\\]]+``
    greift Trailing-``:``/``,`` mit, verschluckt angehängte Prosa wie ``/-Setup``).
    Daher als Vorschlag über :func:`review_patches`, nicht in :func:`repair_text`.
    """
    return _URL_MASH_RECON_RE.subn(lambda m: f"[{m.group(1)}]({m.group(2)})", text)


def _tag_fences(text: str) -> tuple[str, int]:
    """Taggt untagged Code-Fences bei **eindeutiger** Sprach-Heuristik. Idempotent, fm-aware."""
    parts = text.split("\n")
    states = _scan_states(parts)
    out: list[str] = []
    n = 0
    in_fence = False
    marker = ""
    for i, raw in enumerate(parts):
        in_fm = states[i][0]
        fence = _FENCE_RE.match(raw)
        if not in_fm and fence and not in_fence:
            in_fence, marker = True, fence.group(1)
            if not fence.group(2).strip():
                lang = detect_fence_lang(parts, i)
                if lang:
                    out.append(f"{marker}{lang}")
                    n += 1
                    continue
        elif not in_fm and fence and in_fence and raw.strip().startswith(marker):
            in_fence = False
        out.append(raw)
    return "\n".join(out), n


def _close_unclosed_fences(text: str) -> tuple[str, int]:
    """Schließt eine **genuin unclosed** Code-Fence deterministisch + verlustfrei.

    Erkennung über die line-start-Fence-State-Machine (`_FENCE_RE`): nur wenn sie am
    Body-Ende noch ``in_fence`` ist, existiert eine echt offene Fence (inline-``` in Prosa
    triggert nicht, da nicht zeilenanfang-matchend). Schließ-Position: schließende
    Marker-Zeile (gleicher Marker) **vor der ersten** Leerzeile / ATX-Heading nach der
    Open-Zeile, sonst am EOF. Idempotent (nach Close endet die Maschine balanciert).
    """
    fm_text, body, _ = split_frontmatter(text)
    parts = body.split("\n")
    in_fence = False
    marker = ""
    open_idx = -1
    for i, raw in enumerate(parts):
        fence = _FENCE_RE.match(raw)
        if fence and not in_fence:
            in_fence, marker, open_idx = True, fence.group(1), i
        elif fence and in_fence and raw.strip().startswith(marker):
            in_fence = False
    if not in_fence:
        return text, 0
    close_at = len(parts)
    for j in range(open_idx + 1, len(parts)):
        if parts[j].strip() == "" or _HEADING_RE.match(parts[j]):
            close_at = j
            break
    parts.insert(close_at, marker)
    new_body = "\n".join(parts)
    if fm_text is None:
        return new_body, 1
    return f"---\n{fm_text}\n---\n{new_body}", 1


#: Safe-Tier-Ops (deterministisch, verlustfrei, idempotent) — Reihenfolge fix.
#: URL-Mashup-Rekonstruktion ist hier **nicht** enthalten: an der URL/Prosa-Grenze
#: nicht deterministisch (CANARY-Befund A-2.1) → :func:`review_patches`.
_SAFE_OPS: tuple[tuple[Any, str], ...] = (
    (_debold_headings, "`**`-Heading(s) entboldet"),
    (_remove_junk_headings, "Junk-Heading(s) entfernt"),
    (_fix_setext, "Setext-Bruch/-Brüche entkoppelt"),
    (_clean_pua, "PUA-Wrapper bereinigt"),
    (_close_unclosed_fences, "unclosed Fence(s) geschlossen"),
    (_tag_fences, "Fence(s) sprach-getaggt"),
)


def repair_text(text: str) -> tuple[str, list[str]]:
    """Wendet alle Safe-Tier-Fixes idempotent + verlustfrei an.

    Safe-Tier = entbolden · Junk-Heading entfernen · Setext entkoppeln ·
    PUA-Wrapper bereinigen · unclosed Fence schließen · Fence-Tagging (high-conf,
    inkl. bash/sql/html/md-Listen seit v2).
    **Nicht** enthalten (verlustbehaftet/nicht-deterministisch → :func:`review_patches`):
    ``turn…``-Token-Strip, URL-Mashup-Rekonstruktion.

    Returns:
        ``(neuer_text, [aktions-logs])``. Bei ``[]`` war nichts zu tun.
    """
    actions: list[str] = []
    for op, label in _SAFE_OPS:
        text, count = op(text)
        if count:
            actions.append(f"{count} {label}")
    return text, actions


def _strip_turn_tokens(text: str) -> tuple[str, int]:
    """Review-Tier: entfernt ``turn\\d+(view|search)\\d+``-Leaks (verlustbehaftet → kein Auto)."""
    return _TOKEN_LEAK_RE.subn("", text)


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


#: Review-Tier-Ops (verlustbehaftet ODER nicht-deterministisch → nie Safe-Auto).
_REVIEW_OPS: tuple[Any, ...] = (_strip_turn_tokens, _reconstruct_url_mash)


def review_patches(relpath: str, text: str) -> list[str]:
    """Erzeugt Unified-Diff-Vorschläge für **Review-Tier**-Fälle (kein Auto-Write).

    Review-Tier (menschlich zu prüfen, nie auto-appliziert):

    * ``turn…``-Token-Strips (B-2) — verlustbehaftet, echte URL nicht rekonstruierbar.
    * URL-Mashup-Rekonstruktion (``url<Text>https://<url>`` → ``[Text](url)``) — an
      der URL/Prosa-Grenze **nicht** deterministisch (CANARY A-2.1: ``figma.com:``
      schluckt den Doppelpunkt, ``affinity.serif.com/-Setup`` verschluckt Prosa).

    Safe-Fixes laufen über :func:`repair_text` / ``vault-repair``; Fences ohne
    erkennbare Sprache bleiben reine Audit-Findings (kein deterministischer Patch).
    """
    suggested = text
    total = 0
    for op in _REVIEW_OPS:
        suggested, count = op(suggested)
        total += count
    if total == 0 or suggested == text:
        return []
    diff = difflib.unified_diff(
        text.splitlines(keepends=True),
        suggested.splitlines(keepends=True),
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
    lines.append(
        f"**{len(findings)} Befunde** — {sev['error']} error · {sev['warning']} warning · {sev['info']} info"
    )
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
