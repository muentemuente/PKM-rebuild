"""WP3b — Indentierte Code-Beispiele → gefencte Blöcke (deterministisch, verifiziert).

Die WP3a-Formatierung (``mdformat``) korrumpiert eine Teilmenge des Vaults: 4-Space-
indentierte Code-/Konfig-**Beispiele** (häufig direkt nach Listen-Items) werden von
mdformat de-indentiert, wodurch enthaltene ``# …``-Zeilen zu **echten Headings**
zerfallen (``unsafe``: ``heading-text verändert``). Dieses Modul behebt die Ursache,
indem solche indentierten Beispiel-Regionen **vor** der Formatierung in einen Code-
Fence gelegt werden — danach hält mdformat den Inhalt verbatim und die Datei wird
``safe``.

**Scope (bewusst eng):** ausschließlich *indented → fenced* (Transform T1). Andere
mdformat-Korruptions-Mechanismen (col-0-``---``-Beispiel-Frontmatter, versehentliche
Setext-Headings ``Prosa\\n---``, Meta-Markdown) werden NICHT auto-konvertiert, sondern
als ``flagged`` mit Mechanismus ausgewiesen (Owner-Review).

**Fences sind bar** (``` ohne Sprach-Tag) — ein Auto-Sprach-Tag wäre eine Inhalts-
Annahme. Sprach-Vorschläge liefert :func:`suggest_language` separat als Review-Liste.

**Sicherheits-Gate (D4):** Eine Datei gilt nur als ``convertible``, wenn die Konversion

1. **textverlustfrei** ist (Multiset der Nicht-Leer-Inhaltszeilen unverändert, nur
   ``` ``` ``-Zeilen kommen hinzu),
2. nach der Konversion **kein emergentes Heading** mehr erzeugt (``format_file`` ∈
   ``{safe, unchanged}``), und
3. **idempotent** ist (zweiter Formatlauf = ``unchanged``).

Andernfalls: ``flagged`` mit Grund. Das Modul ist **non-mutating** gegenüber dem
Vault (#3); es liefert Konversions-Texte + Reports für den Dry-Run.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from pipeline.format_vault import format_file, format_markdown

log = structlog.get_logger()

# WP3b-Scope: die 14 Kat-B-Files (von den 18 WP3a-`unsafe`-LEAVE).
#   ausgeschlossen — Kat A (Heading-Sonderzeichen, eigener Mini-Task):
#     01_Grundlagen/nlp-pkm-grundlagen.md, 01_Grundlagen/themenstraenge-debatten.md,
#     14_…/python-introduction.md
#   ausgeschlossen — Git-Trio (Track B, wird dort archiviert/gemerged):
#     14_…/git-setup-and-concepts.md
KAT_B_FILES: tuple[str, ...] = (
    "00_Meta/artikel-template-grundlagen.md",
    "00_Meta/artikel-template-kompaktreferenz.md",
    "01_Grundlagen/artikel-formatierung.md",
    "01_Grundlagen/konfigurationsformate-yaml-toml-frontmatter.md",
    "01_Grundlagen/markdown-syntax.md",
    "01_Grundlagen/moderne-datenokosysteme-und-protokolle.md",
    "05_Dateitypen-und-Konfiguration/csv-parquet-formats.md",
    "05_Dateitypen-und-Konfiguration/hierarchische-formate-json-xml.md",
    "09_KI-und-Semantische-Systeme/claude-agenten-uebersicht.md",
    "09_KI-und-Semantische-Systeme/thinkstation-pgx-roadmap.md",
    "10_Datenarchitektur-und-Datenbanken/datenbank-design-und-projektorganisation.md",
    "10_Datenarchitektur-und-Datenbanken/metadata-processor-pipeline.md",
    "10_Datenarchitektur-und-Datenbanken/sql-grundlagen-sqlite-abfragen.md",
    "10_Datenarchitektur-und-Datenbanken/vector-databases-embeddings.md",
)

_FM_RE = re.compile(r"^---\n.*?\n---\n", re.S)
_FENCE_OPEN_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})")
# Eine „indentierte" Zeile: mind. 4 führende Spaces (Tabs werden nicht als Code-Indent
# gewertet — der Vault nutzt durchgängig Spaces; ein Tab wäre ein eigener Review-Fall).
_INDENT_RE = re.compile(r"^ {4}")
# Listen-Marker am Zeilenanfang (nach De-Indent): `-`/`*`/`+`/`1.`/`1)` + Space.
_LIST_MARKER_RE = re.compile(r"^([-*+]|\d+[.)])\s")


# === Sprach-Heuristik (nur Vorschlag, nie auto-angewandt) =====================


def suggest_language(code: str) -> str:
    """Schlägt einen Sprach-Tag für einen de-indentierten Code-Block vor (Heuristik).

    Returns einen Tag (``sql``/``yaml``/``toml``/``json``/``xml``/``csv``/``bash``/
    ``python``) oder ``""`` bei Unsicherheit. Rein für die Review-Liste — der
    geschriebene Fence bleibt bar.
    """
    text = code.strip()
    low = text.lower()
    if re.search(r"\b(select|insert into|update|delete from|create table)\b", low):
        return "sql"
    if re.search(r"^\s*\[[^\]]+\]\s*$", text, re.M) and "=" in text:
        return "toml"
    if re.search(r"^\s*<\?xml|^\s*<[a-zA-Z]", text):
        return "xml"
    if text.startswith("{") or re.search(r'"\w+":\s', text):
        return "json"
    if re.search(r"\b(def |import |print\(|class )\b", text):
        return "python"
    # `#` ist sprach-übergreifend ein Kommentar (yaml/toml/python/…) → KEIN bash-Signal;
    # nur `$`-Prompt oder konkrete Shell-Kommandos zählen.
    if re.search(r"^\s*\$\s|\b(cd|ls|git|pbcopy|ssh-keygen|chmod|mkdir)\b", text, re.M):
        return "bash"
    if re.search(r"^\s*[\w-]+:\s", text, re.M) or re.search(r"^\s*-\s", text, re.M):
        return "yaml"
    if re.search(r"^[^,\n]+,[^,\n]+,", text, re.M):
        return "csv"
    return ""


# === Transform T1: indented → fenced ==========================================


@dataclass
class Block:
    """Eine konvertierte indentierte Region (für Report + Sprach-Vorschlag)."""

    body_line: int  # 1-basierte Zeile im Body (nach Frontmatter), wo der Fence beginnt
    base_indent: int  # entfernter gemeinsamer Indent
    lang_suggestion: str
    preview: str  # erste nicht-leere Inhaltszeile (gekürzt)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Trennt führenden ``---``-Frontmatter-Block vom Body."""
    m = _FM_RE.match(text)
    return (text[: m.end()], text[m.end() :]) if m else ("", text)


def convert_indented(text: str) -> tuple[str, list[Block]]:
    """Wrappt maximale Runs ≥4-Space-indentierter Zeilen in bare ``` ``` ``-Fences.

    Echte (bereits gefencte) Code-Blöcke und der Frontmatter bleiben unangetastet.
    De-indentiert jede Region um ihren gemeinsamen Mindest-Indent (Relativ-Indent
    bleibt erhalten). Returns ``(konvertierter_text, blocks)``.
    """
    head, body = _split_frontmatter(text)
    lines = body.split("\n")
    out: list[str] = []
    blocks: list[Block] = []
    i = 0
    in_fence = False
    fence_marker = ""
    while i < len(lines):
        ln = lines[i]
        fm = _FENCE_OPEN_RE.match(ln)
        if not in_fence and fm:
            in_fence, fence_marker = True, fm.group(2)[0]
            out.append(ln)
            i += 1
            continue
        if in_fence:
            out.append(ln)
            if re.match(rf"^[ \t]*{re.escape(fence_marker)}{{3,}}[ \t]*$", ln):
                in_fence = False
            i += 1
            continue

        prev_blank = (not out) or out[-1].strip() == ""
        if prev_blank and _INDENT_RE.match(ln) and ln.strip():
            region, j = _collect_region(lines, i)
            indents = [len(x) - len(x.lstrip(" ")) for x in region if x.strip()]
            base = min(indents)
            dedented = [x[base:] if x.strip() else "" for x in region]
            preview = next((d for d in dedented if d.strip()), "")
            # Verschachtelte Listen (`    - text`, `    1. text`) sind KEIN Code — sie
            # werden von mdformat ohnehin sicher (2-Space) normalisiert. Nur als Code
            # behandeln, wenn die erste Inhaltszeile kein Listen-Marker ist.
            if _LIST_MARKER_RE.match(preview):
                out.extend(region)
                i = j
                continue
            # List-aware Platzierung: liegt die Region im Scope eines Listen-Items
            # (nächste Nicht-Leer-Zeile davor ist ein Marker), wird der Fence auf dessen
            # Content-Indent gesetzt, damit der Block IN der Liste bleibt — sonst zerfällt
            # z. B. eine geordnete Liste in 1./1./1. Sonst Spalte 0.
            pad = " " * _governing_indent(out)
            blocks.append(
                Block(
                    body_line=len(out) + 1,
                    base_indent=base,
                    lang_suggestion=suggest_language("\n".join(dedented)),
                    preview=preview[:60],
                )
            )
            out.append(f"{pad}```")
            out.extend(f"{pad}{d}" if d.strip() else "" for d in dedented)
            out.append(f"{pad}```")
            i = j
            continue

        out.append(ln)
        i += 1
    return head + "\n".join(out), blocks


_LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])(\s+)\S")


def _governing_indent(emitted: list[str]) -> int:
    """Content-Indent des regierenden Listen-Items für eine folgende indentierte Region.

    Geht in den bereits emittierten Zeilen über Leerzeilen zurück; ist die letzte
    Nicht-Leer-Zeile ein Listen-Marker, ist der Content-Indent = Marker-Präfixlänge
    (führende Spaces + Marker + Spaces). Sonst 0 (Top-Level → Fence auf Spalte 0).
    """
    for ln in reversed(emitted):
        if ln.strip() == "":
            continue
        m = _LIST_ITEM_RE.match(ln)
        if m:
            return len(m.group(1)) + len(m.group(2)) + len(m.group(3))
        return 0
    return 0


def _collect_region(lines: list[str], start: int) -> tuple[list[str], int]:
    """Sammelt eine indentierte Region ab ``start``: indentierte Zeilen + eingebettete
    Leerzeilen, solange danach wieder eine indentierte Zeile folgt. Returns
    ``(region_lines, next_index)``."""
    region: list[str] = []
    j = start
    while j < len(lines):
        if lines[j].strip() == "":
            k = j + 1
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            if k < len(lines) and _INDENT_RE.match(lines[k]) and lines[k].strip():
                region.append(lines[j])
                j += 1
                continue
            break
        if _INDENT_RE.match(lines[j]):
            region.append(lines[j])
            j += 1
            continue
        break
    return region, j


# === Verifikations-Gate =======================================================

_OK_TIERS = {"safe", "unchanged"}


def _content_lines(text: str) -> list[str]:
    """Nicht-leere Zeilen ohne reine ``` ``` ``-Fence-Zeilen, gestripped, sortiert —
    für den Textverlust-Check (Konversion darf nur Fences hinzufügen + de-indentieren)."""
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s or re.fullmatch(r"`{3,}|~{3,}", s):
            continue
        out.append(s)
    return sorted(out)


@dataclass
class FileOutcome:
    """Ergebnis der Konversions-Prüfung einer Datei."""

    relpath: str
    status: str  # convertible | flagged | noop
    reasons: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    converted: str = ""  # nur indented→fenced (vor Formatierung)
    final: str = ""  # converted danach mdformat-formatiert (= work-copy)


def mechanism_hint(original: str) -> str:
    """Grober Mechanismus-Hinweis für ``flagged`` Files (Review-Report), heuristisch.

    Erkennt billig die im Vault auftretenden Nicht-T1-Korruptionen, damit das Review
    pro Datei den richtigen manuellen Fix wählt. Keine Mutation, keine Garantie.
    """
    _, body = _split_frontmatter(original)
    # col-0 Beispiel-Frontmatter: ein ---…---Block im Body, dessen Inhalt YAML-ähnlich
    # ist (≥1 `key:`-Zeile). Vor dem Setext-Check, da dessen schließendes `---` sonst
    # fälschlich als Setext-Unterstrich gilt.
    for m in re.finditer(r"(?ms)^---[ \t]*\n(.*?)\n---[ \t]*$", body):
        if re.search(r"(?m)^[ \t]*[\w-]+:", m.group(1)):
            return "col-0 Beispiel-Frontmatter (`---`-Block) — manuell in ```yaml umschließen"
    # versehentliches Setext-Heading: lose Prosa-Zeile direkt gefolgt von ---
    if re.search(r"(?m)^(?!---|===|\s*$).+\n---[ \t]*$", body):
        return "Setext-Heading (`Prosa`+`---`) — Leerzeile vor `---` einfügen"
    return "anderer Mechanismus — manuell prüfen"


def evaluate_file(original: str, relpath: str) -> FileOutcome:
    """Wendet T1 an + prüft das Sicherheits-Gate. Mutiert nichts."""
    converted, blocks = convert_indented(original)
    if not blocks:
        # Keine indentierte Region gefunden → anderer Mechanismus.
        return FileOutcome(relpath, "flagged", ["kein indented-Code-Block erkannt"], [])

    reasons: list[str] = []
    if _content_lines(original) != _content_lines(converted):
        reasons.append("textverlust/-änderung durch konversion")

    conv_res = format_file(converted, relpath)
    if conv_res.tier not in _OK_TIERS:
        reasons.append(f"konversion bleibt {conv_res.tier} ({', '.join(conv_res.reasons)})")

    final, _ = format_markdown(converted)
    if format_file(final, relpath).tier != "unchanged":
        reasons.append("nicht idempotent (2. formatlauf ändert)")

    status = "flagged" if reasons else "convertible"
    return FileOutcome(relpath, status, reasons, blocks, converted, final)


# === Scan / Reports / Work-Copies (3-State, non-mutating ggü. #3) ==============


def scan_files(vault_dir: Path, relpaths: tuple[str, ...] | list[str]) -> list[FileOutcome]:
    """Wertet alle ``relpaths`` (raw, read-only) durch das Gate aus. Mutiert nichts."""
    outcomes: list[FileOutcome] = []
    for rel in relpaths:
        p = vault_dir / rel
        if not p.is_file():
            outcomes.append(FileOutcome(rel, "flagged", ["datei fehlt"], []))
            continue
        outcomes.append(evaluate_file(p.read_text(encoding="utf-8"), rel))
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1
    log.info("fence_indented_scan_done", vault=str(vault_dir), **counts)
    return outcomes


def write_work(work_dir: Path, vault_dir: Path, outcomes: list[FileOutcome]) -> None:
    """Schreibt für ``convertible`` die formatierte Arbeitskopie (``final``) + einen
    Unified-Diff (raw→final) nach ``work_dir``. Für ``flagged`` nur einen ``.flag``-
    Hinweis. Der Vault (#3) bleibt unangetastet (Export ist separat, Gate-3)."""
    for o in outcomes:
        target = work_dir / o.relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        if o.status == "convertible":
            target.write_text(o.final, encoding="utf-8")
            original = (vault_dir / o.relpath).read_text(encoding="utf-8")
            diff = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    o.final.splitlines(keepends=True),
                    fromfile=f"a/{o.relpath}",
                    tofile=f"b/{o.relpath}",
                    n=2,
                )
            )
            (work_dir / (o.relpath + ".diff")).write_text(diff, encoding="utf-8")
        else:
            (work_dir / (o.relpath + ".flag")).write_text(
                "\n".join(o.reasons) + "\n", encoding="utf-8"
            )


def render_report(outcomes: list[FileOutcome], vault_dir: Path) -> str:
    """``fence_indented_report.md`` — Konvertierbare + geflaggte Files mit Begründung."""
    conv = [o for o in outcomes if o.status == "convertible"]
    flag = [o for o in outcomes if o.status == "flagged"]
    lines = [
        "# WP3b — Indented→Fenced Report (Dry-Run, non-mutating)",
        "",
        f"- Vault (raw, read-only): `{vault_dir}`",
        f"- Files im Scope: **{len(outcomes)}** · convertible **{len(conv)}** · flagged **{len(flag)}**",
        "",
        "> `convertible` = indented Beispiel-Region in bare ``` gelegt; danach `safe` + "
        "idempotent + textverlustfrei (Gate). `flagged` = anderer Mechanismus → manueller "
        "Review, NICHT auto-konvertiert.",
        "",
        f"## Convertible — {len(conv)}",
        "",
    ]
    for o in conv:
        langs = ", ".join(f"`{b.lang_suggestion or '?'}`" for b in o.blocks)
        lines.append(f"- `{o.relpath}` — {len(o.blocks)} Block(e); Sprach-Vorschlag: {langs}")
    lines += ["", f"## Flagged (Review) — {len(flag)}", ""]
    for o in flag:
        # Persistent-unsafe trotz Block ⇒ Meta-Markdown; sonst Mechanismus-Hinweis.
        if o.blocks:
            hint = "weitere `#`-Beispiele/Meta-Markdown — manuell prüfen"
        else:
            original = (vault_dir / o.relpath).read_text(encoding="utf-8")
            hint = mechanism_hint(original)
        lines.append(f"- `{o.relpath}` — {hint}  _(Gate: {'; '.join(o.reasons)})_")
    return "\n".join(lines) + "\n"


def render_language_suggestions(outcomes: list[FileOutcome]) -> str:
    """``language_tag_suggestions.md`` — separate Liste; Fences bleiben bar (nicht auto)."""
    lines = [
        "# WP3b — Sprach-Tag-Vorschläge (separat, NICHT auto-angewandt)",
        "",
        "> Die konvertierten Fences sind bewusst **bar** (` ``` `). Diese Vorschläge sind "
        "rein heuristisch; ein Tag wird erst nach menschlicher Bestätigung gesetzt.",
        "",
    ]
    for o in outcomes:
        if o.status != "convertible":
            continue
        lines.append(f"## `{o.relpath}`")
        for b in o.blocks:
            tag = b.lang_suggestion or "?"
            lines.append(f"- Body-Zeile ~{b.body_line}: `{tag}` — `{b.preview}`")
        lines.append("")
    return "\n".join(lines) + "\n"
