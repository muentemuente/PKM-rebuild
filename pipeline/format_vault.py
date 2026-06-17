"""WP3a — Deterministische, idempotente Markdown-Formatierung (mdformat).

Normalisiert „unsaubere" Vault-Files **rein deterministisch** (Whitespace, Blank-
Lines, Listen-Marker, Code-Fences, Tabellen, Frontmatter-Whitespace) — KEIN
Content-Rewrite, KEIN LLM. mdformat ist idempotent-by-design (zweiter Lauf = no-op).

**Obsidian-Schutzbereiche** (NIE verändern):

* Wikilinks ``[[...]]`` und Embeds ``![[...]]`` — mdformat *escaped* sie sonst zu
  ``\\[[...]\\]``; sie werden vor dem Formatieren **maskiert** und danach restauriert.
* Callout-Marker ``> [!note]`` — von mdformat als Blockquote erhalten (Guard).
* Code-Block-**Inhalte** — von mdformat verbatim erhalten (Guard).
* Frontmatter-**Werte** + Key-Reihenfolge — mdformat-frontmatter normalisiert nur
  Whitespace/Quoting (Guard: geparstes Dict muss identisch bleiben).

**Tier-Split (D4):**

* ``unchanged`` — Formatierung ändert nichts.
* ``safe`` — nur deterministische, nicht-semantische Formatierung → auto-anwendbar
  (in die Arbeitskopie ``work/``).
* ``unsafe`` — die Formatierung würde einen Schutzbereich/Heading-Text/Code-Inhalt
  berühren → **nie** auto; wird als Patch-Vorschlag ausgewiesen.

Dieses Modul ist **non-mutating gegenüber dem Vault** (#3): es liest die Originale
(raw) und schreibt Arbeitskopien/Reports nach ``work/`` (#2). Export nach #3 ist ein
separater, Gate-3-pflichtiger Schritt (NICHT hier).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import mdformat
import mistune
import structlog
import yaml

log = structlog.get_logger()

# AST-Parser für repräsentations-agnostische Code-Block-Extraktion (indented + fenced).
_MD_AST = mistune.create_markdown(renderer=None)

_EXTENSIONS = {"gfm", "frontmatter"}

# Wikilinks + Embeds (mit optionalem Alias/Anker): ![[a|b]], [[a#h]], [[a^x]].
_WIKILINK_EMBED_RE = re.compile(r"!?\[\[[^\]\n]*\]\]")
# Fenced Code-Block (``` oder ~~~), Indent-erhaltend.
_FENCE_RE = re.compile(r"(?ms)^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1\2[ \t]*$")
# ATX-Heading (mit optionalen Closing-#).
_ATX_RE = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$")
_CALLOUT_RE = re.compile(r"\[!([A-Za-z][A-Za-z0-9_-]*)\]")
_FM_DELIM = "---\n"

# Maskierungs-Token: rein alphanumerisch → von mdformat als opakes Wort behandelt.
_SENTINEL_BASE = "Xmdfmtprotectx"


# === Schutz/Restore Wikilinks + Embeds ========================================


def _protect_links(text: str) -> tuple[str, list[str], bool]:
    """Maskiert Wikilinks/Embeds. Returns (masked, spans, collision)."""
    if _SENTINEL_BASE in text:
        return text, [], True  # Kollision → Aufrufer behandelt als unsafe
    spans: list[str] = []

    def _repl(m: re.Match[str]) -> str:
        spans.append(m.group(0))
        return f"{_SENTINEL_BASE}{len(spans) - 1:04d}x"

    return _WIKILINK_EMBED_RE.sub(_repl, text), spans, False


def _restore_links(text: str, spans: list[str]) -> str:
    for i, original in enumerate(spans):
        text = text.replace(f"{_SENTINEL_BASE}{i:04d}x", original)
    return text


def _restore_thematic_breaks(text: str) -> str:
    """Setzt mdformats Thematic-Break-Stil (Zeile aus ``_``) auf ``---`` zurück (E1).

    Fence-aware: innerhalb von Code-Blöcken wird nichts verändert. Eine etwaige
    Fehl-Konversion in Code würde ohnehin vom Code-Guard als ``unsafe`` markiert.
    """
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if not in_fence and re.match(r"^(`{3,}|~{3,})", stripped):
            in_fence = True
        elif in_fence and re.fullmatch(r"(`{3,}|~{3,})", stripped):
            in_fence = False
        elif not in_fence and re.fullmatch(r"_{3,}", stripped):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}---")
            continue
        out.append(line)
    return "\n".join(out)


def format_markdown(text: str) -> tuple[str, bool]:
    """Formatiert Markdown deterministisch unter Schutz der Wikilinks/Embeds.

    Returns ``(formatted, ok)``. ``ok=False`` bei Sentinel-Kollision (nicht sicher
    formatierbar) — dann wird der Originaltext unverändert zurückgegeben.
    """
    masked, spans, collision = _protect_links(text)
    if collision:
        return text, False
    formatted = mdformat.text(masked, extensions=_EXTENSIONS)
    formatted = _restore_thematic_breaks(formatted)
    return _restore_links(formatted, spans), True


# === Schutzbereich-Extraktoren (für Guards) ===================================


def _norm_code(content: str) -> str:
    """Code-Inhalt für den Guard normalisieren: Trailing-WS pro Zeile + Trailing-Blanks.

    mdformat strippt Trailing-Whitespace auch in Code-Blöcken (kosmetisch, nicht-
    semantisch). Der Guard soll nur **echte** Inhaltsänderungen als unsafe werten,
    daher wird Trailing-WS vor dem Vergleich ignoriert.
    """
    return "\n".join(line.rstrip() for line in content.split("\n")).rstrip("\n")


def _code_block_contents(text: str) -> list[str]:
    """Normalisierter Code-Inhalt aller Code-Blöcke (indented UND fenced) via mistune-AST.

    Repräsentations-agnostisch: mdformats Konversion indented→fenced (= Code-Fence-
    Normalisierung, laut Spec safe-auto) ändert den Inhalt nicht und löst daher KEIN
    unsafe aus — nur eine echte Änderung am Code-Text tut das.
    """
    out: list[str] = []

    def _walk(tokens: list[dict]) -> None:
        for t in tokens:
            if t.get("type") == "block_code":
                out.append(_norm_code(str(t.get("raw", ""))))
            children = t.get("children")
            if isinstance(children, list):
                _walk(children)

    _walk(_MD_AST(text))
    return sorted(out)


def _strip_code(text: str) -> str:
    return _FENCE_RE.sub("", text)


def _strip_frontmatter(text: str) -> str:
    """Entfernt den führenden ``---``-Frontmatter-Block (damit seine Delimiter nicht
    als Setext-Heading-Unterstrich fehlinterpretiert werden)."""
    if not text.startswith(_FM_DELIM):
        return text
    m = re.search(r"\n---\s*\n", text[4:])
    return text[4 + m.end() :] if m else text


def _heading_texts(text: str) -> list[str]:
    """ATX-Heading-Texte, code-/frontmatter-frei, als sortiertes Multiset.

    Bewusst NUR ATX (`#`): Setext-Erkennung über ``---``/``===``-Zeilen erzeugt
    Fehlalarme (thematische Breaks, Beispiel-Frontmatter/HTML-Kommentare im Body).
    Der Vault verwendet durchgängig ATX; ein echter Heading-Text-Edit durch
    mdformat (das es nicht tut) bliebe so trotzdem erkennbar.
    """
    body = _strip_code(_strip_frontmatter(text))
    # Interner Whitespace im Heading-Text wird kollabiert: mdformat normalisiert
    # `# H  X` → `# H X` (kosmetisch, Heading-Text semantisch unverändert). Echte
    # Text-Änderungen / neu auftauchende Headings bleiben dadurch trotzdem erkennbar.
    return sorted(re.sub(r"\s+", " ", m.group(1).strip()) for m in _ATX_RE.finditer(body))


def _wikilinks(text: str) -> list[str]:
    return sorted(_WIKILINK_EMBED_RE.findall(text))


def _callout_markers(text: str) -> list[str]:
    return sorted(m.group(0) for m in _CALLOUT_RE.finditer(text))


def _frontmatter_dict(text: str) -> object:
    """Geparstes Frontmatter-Dict (oder None). Für semantischen Vergleich."""
    if not text.startswith(_FM_DELIM):
        return None
    m = re.search(r"\n---\s*\n", text[4:])
    if not m:
        return None
    try:
        return yaml.safe_load(text[4 : 4 + m.start()])
    except yaml.YAMLError:
        return "<<unparseable>>"


# === Tier-Klassifikation ======================================================

_TIER_UNCHANGED = "unchanged"
_TIER_SAFE = "safe"
_TIER_UNSAFE = "unsafe"


def classify(original: str, formatted: str, *, format_ok: bool = True) -> tuple[str, list[str]]:
    """Ordnet eine Formatierung einem Tier zu + listet Unsafe-Gründe.

    Unsafe, sobald die Formatierung einen Schutzbereich, Heading-Text oder Code-
    Inhalt verändern würde (oder nicht sicher formatierbar war).
    """
    reasons: list[str] = []
    if not format_ok:
        reasons.append("sentinel-kollision (nicht sicher formatierbar)")
    if _code_block_contents(original) != _code_block_contents(formatted):
        reasons.append("codeblock-inhalt verändert")
    if _heading_texts(original) != _heading_texts(formatted):
        reasons.append("heading-text verändert")
    if _wikilinks(original) != _wikilinks(formatted):
        reasons.append("wikilink/embed verändert")
    if _callout_markers(original) != _callout_markers(formatted):
        reasons.append("callout-marker verändert")
    if _frontmatter_dict(original) != _frontmatter_dict(formatted):
        reasons.append("frontmatter-wert verändert")

    if reasons:
        return _TIER_UNSAFE, reasons
    if formatted == original:
        return _TIER_UNCHANGED, []
    return _TIER_SAFE, []


# === Datei-/Vault-Scan (3-State raw → work) ===================================


@dataclass
class FileResult:
    """Ergebnis der Formatierung einer Datei (Dry-Run-tauglich)."""

    relpath: str
    tier: str
    reasons: list[str] = field(default_factory=list)
    added: int = 0  # geänderte Zeilen (für safe/unsafe)
    removed: int = 0
    diff: str = ""  # unified diff original→formatted


@dataclass
class ScanReport:
    """Aggregat eines Vault-Scans."""

    vault_dir: Path
    work_dir: Path
    results: list[FileResult]

    def by_tier(self, tier: str) -> list[FileResult]:
        return [r for r in self.results if r.tier == tier]

    def counts(self) -> dict[str, int]:
        out = {_TIER_UNCHANGED: 0, _TIER_SAFE: 0, _TIER_UNSAFE: 0}
        for r in self.results:
            out[r.tier] += 1
        return out


def _is_content_md(p: Path) -> bool:
    return p.name != "_index.md" and not p.name.endswith(".body.md")


def format_file(original: str, relpath: str) -> FileResult:
    """Formatiert einen Datei-Inhalt und klassifiziert ihn (rein, ohne IO)."""
    formatted, ok = format_markdown(original)
    tier, reasons = classify(original, formatted, format_ok=ok)
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            formatted.splitlines(keepends=True),
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
            n=2,
        )
    )
    added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))
    return FileResult(
        relpath=relpath,
        tier=tier,
        reasons=reasons,
        added=added,
        removed=removed,
        diff="".join(diff_lines),
    )


def scan_vault(vault_dir: Path, work_dir: Path, *, write_work: bool = True) -> ScanReport:
    """Scannt einen Vault (raw, read-only) und schreibt Arbeitskopien nach ``work_dir``.

    3-State (D4): Original (raw, #3) bleibt unangetastet. Für ``safe`` wird die
    formatierte Fassung in die Arbeitskopie geschrieben (auto-angewandt); für
    ``unsafe``/``unchanged`` wird das Original kopiert + (unsafe) ein ``.patch``
    daneben gelegt. Der **Export** der Arbeitskopie nach #3 ist NICHT Teil hiervon.
    """
    results: list[FileResult] = []
    for p in sorted(vault_dir.rglob("*.md")):
        if not _is_content_md(p):
            continue
        relpath = str(p.relative_to(vault_dir))
        original = p.read_text(encoding="utf-8")
        res = format_file(original, relpath)
        results.append(res)

        if write_work:
            target = work_dir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            if res.tier == _TIER_SAFE:
                formatted, _ = format_markdown(original)
                target.write_text(formatted, encoding="utf-8")
            else:
                # unchanged + unsafe: Arbeitskopie = Original (Safe-by-default),
                # unsafe zusätzlich als Patch-Vorschlag (NIE auto-angewandt).
                target.write_text(original, encoding="utf-8")
                if res.tier == _TIER_UNSAFE and res.diff:
                    (work_dir / (relpath + ".patch")).write_text(res.diff, encoding="utf-8")

    log.info(
        "format_vault_scan_done",
        vault=str(vault_dir),
        **scan_counts(results),
    )
    return ScanReport(vault_dir=vault_dir, work_dir=work_dir, results=results)


def export_formatted(vault_dir: Path, relpaths: list[str]) -> list[tuple[str, str]]:
    """**Gate-3-Mutation**: schreibt die formatierte Fassung NUR von ``safe``-Files
    zurück in den Vault (#3). Re-formatiert aus dem Raw-Original (autoritativ) und
    weigert sich bei ``unsafe``/``unchanged``.

    Returns: Liste ``(relpath, status)`` mit status ∈ {written, skipped-unchanged,
    refused-unsafe, missing}.
    """
    results: list[tuple[str, str]] = []
    for rel in relpaths:
        target = vault_dir / rel
        if not target.is_file():
            results.append((rel, "missing"))
            continue
        original = target.read_text(encoding="utf-8")
        res = format_file(original, rel)
        if res.tier == _TIER_UNSAFE:
            results.append((rel, "refused-unsafe"))
            continue
        if res.tier == _TIER_UNCHANGED:
            results.append((rel, "skipped-unchanged"))
            continue
        formatted, _ = format_markdown(original)
        target.write_text(formatted, encoding="utf-8")
        results.append((rel, "written"))
        log.info("format_vault_exported", relpath=rel)
    return results


def scan_counts(results: list[FileResult]) -> dict[str, int]:
    out = {_TIER_UNCHANGED: 0, _TIER_SAFE: 0, _TIER_UNSAFE: 0}
    for r in results:
        out[r.tier] += 1
    return out


# === Report ===================================================================


def render_diff_report(report: ScanReport, *, examples_per_tier: int = 5) -> str:
    """``diff_report.md`` — Blast-Radius + Beispiel-Diffs je Tier (deterministisch)."""
    c = report.counts()
    total = len(report.results)
    lines = [
        "# Format-Vault Diff-Report (WP3a — deterministisch, Dry-Run)",
        "",
        f"- Vault (raw, read-only): `{report.vault_dir}`",
        f"- Arbeitskopie (work): `{report.work_dir}`",
        f"- Docs gescannt: **{total}**",
        "",
        "| Tier | Files |",
        "|---|---:|",
        f"| unchanged | {c['unchanged']} |",
        f"| safe-auto | {c['safe']} |",
        f"| unsafe (Patch-Vorschlag) | {c['unsafe']} |",
        "",
        "> Schutzbereiche (Wikilinks/Embeds/Callouts/Code-Inhalt/Frontmatter-Werte) sind "
        "per Konstruktion + Guard unverändert; `safe` ist rein deterministische Formatierung. "
        "`unsafe` wird NIE auto-angewandt (nur `.patch`-Vorschlag).",
        "",
    ]
    for tier, label in ((_TIER_SAFE, "Safe-auto"), (_TIER_UNSAFE, "Unsafe (Patch-Vorschlag)")):
        rows = report.by_tier(tier)
        lines += [f"## {label} — {len(rows)} Files", ""]
        if not rows:
            lines += ["_keine_", ""]
            continue
        rows_sorted = sorted(rows, key=lambda r: (-(r.added + r.removed), r.relpath))
        for r in rows_sorted[:examples_per_tier]:
            reason = f" · Gründe: {', '.join(r.reasons)}" if r.reasons else ""
            lines += [
                f"### `{r.relpath}` (+{r.added}/-{r.removed}){reason}",
                "",
                "```diff",
                r.diff.rstrip("\n") or "(kein Diff)",
                "```",
                "",
            ]
    return "\n".join(lines) + "\n"
