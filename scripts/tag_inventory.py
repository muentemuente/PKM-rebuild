#!/usr/bin/env python3
"""Tag-Inventar-Heuristik für Block 0.G.

Scannt alle Markdown-Files in corpus_input und extrahiert:
  A) Frontmatter-Tags (höchste Vertrauenswürdigkeit)
  B) H1/H2-Heading-Tokens (mittlere Vertrauenswürdigkeit)
  C) Dateinamen-Tokens (Hinweis-Charakter)

Normalisierung: lowercase, Umlaute → ASCII, Bindestriche
Mindestfrequenz: ≥ 2 Files (Stop-Wörter + Einzel-Belege gefiltert)

Ausgabe: data/02_pipeline_output/tag_inventory.md

Verwendung:
  python scripts/tag_inventory.py
  python scripts/tag_inventory.py --corpus-dir /pfad/zum/korpus
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

# === Konfiguration ==============================================================

_REPO_ROOT = Path(__file__).parent.parent
_DEFAULT_CORPUS = Path.home() / "projects/aktiv/PKM_rebuild/data/01_corpus_input"
_DEFAULT_OUTPUT = Path.home() / "projects/aktiv/PKM_rebuild/data/02_pipeline_output/tag_inventory.md"

# Stopwörter DE + EN (Häufigste, kein Themen-Informationsgehalt)
_STOP_WORDS: frozenset[str] = frozenset(
    [
        # Deutsch
        "der", "die", "das", "ein", "eine", "einer", "eines", "einem", "einen",
        "und", "oder", "mit", "von", "fuer", "auf", "zu", "an", "in", "ist",
        "sind", "war", "waren", "wird", "werden", "wurde", "haben", "hat",
        "wie", "was", "wann", "wo", "wer", "warum", "ich", "du", "er", "sie",
        "es", "wir", "ihr", "bei", "aus", "nach", "durch", "ueber", "unter",
        "vor", "seit", "ohne", "um", "als", "dass", "wenn", "aber", "auch",
        "noch", "dann", "nur", "nicht", "so", "sehr", "mehr", "alle", "kein",
        "keine", "kann", "muss", "soll", "will", "gibt", "hier", "dort",
        "jede", "jeder", "jedes", "man", "viele", "wenige", "welche", "welcher",
        "welches", "einem", "zum", "zur", "im", "am", "dem", "den", "des",
        "sich", "diese", "dieser", "dieses", "diesen", "einem", "einer",
        "verschiedene", "verschiedener", "verschiedenes", "verschiedenen",
        "neue", "neuer", "neues", "neuen", "bereits", "dabei", "damit",
        "dazu", "dafuer", "daher", "darum", "dabei", "daraus", "davon",
        "hierfuer", "hierbei", "hierzu", "hiermit",
        # Häufige deutsche Section-Heading-Wörter (keine nützlichen Tags)
        "zusammenfassung", "uebersicht", "einfuehrung", "einleitung", "grundlagen",
        "grundlage", "beispiele", "beispiel", "anwendung", "anwendungen", "erlaeuterung",
        "erlaeuterungen", "erklaerung", "erklaerungen", "beschreibung", "beschreibungen",
        "eigenschaften", "eigenschaft", "merkmale", "merkmal", "vorteile", "vorteil",
        "nachteile", "nachteil", "aufbau", "struktur", "strukturen", "konzept", "konzepte",
        "inhalt", "inhalte", "umsetzung", "anleitung", "anleitungen", "vorgehen",
        "schritte", "schritt", "methode", "methoden", "ansatz", "ansaetze",
        "erstellen", "erzeugen", "nutzen", "nutzung", "verwendung", "verwenden",
        "fehler", "fehlerbehebung", "problem", "probleme", "loesung", "loesungen",
        "ressourcen", "ressource", "quellen", "quelle", "referenz", "referenzen",
        "checkliste", "checklisten", "todo", "aufgaben", "aufgabe",
        "werkzeuge", "werkzeug", "tools", "tool",
        "praktische", "praktisch", "praktisches",
        "wichtig", "wichtige", "wichtiger", "wichtiges",
        "allgemein", "allgemeine", "allgemeines", "allgemeiner",
        "weitere", "weiteres", "weiterer", "weiteren",
        "aktuell", "aktuelle", "aktuelles", "aktueller",
        "einfach", "einfache", "einfaches", "einfacher",
        "verschiedene", "verschieden",
        "notizen", "notiz", "hinweis", "hinweise",
        "definition", "definitionen", "begriffe", "begriff",
        "text", "texte", "inhalt", "inhalte",
        "dateien", "datei", "ordner", "verzeichnis", "verzeichnisse",
        "seite", "seiten", "abschnitt", "abschnitte", "kapitel",
        "liste", "listen", "tabelle", "tabellen",
        "wert", "werte", "werten", "werts",
        "typ", "typen", "types", "type",
        "art", "arten",
        "weg", "wege",
        "teil", "teile",
        "punkt", "punkte",
        # Englisch (Section-Heading-Wörter)
        "overview", "introduction", "summary", "basics", "advanced",
        "examples", "usage", "notes", "references", "resources",
        "tips", "tricks", "hints", "best", "practices", "guide",
        "tutorial", "howto", "setup", "configuration", "options",
        "details", "description", "explanation", "properties",
        "methods", "features", "advantages", "disadvantages",
        "steps", "checklist", "todos", "requirements",
        # Englisch
        "the", "a", "an", "and", "or", "with", "of", "for", "on", "to", "in",
        "is", "are", "was", "were", "have", "has", "how", "what", "when",
        "where", "who", "why", "at", "from", "by", "about", "as", "that",
        "this", "these", "those", "if", "but", "also", "not", "only", "all",
        "no", "none", "more", "less", "many", "few", "here", "there", "each",
        "can", "must", "should", "will", "do", "does", "did", "be", "get",
        "set", "use", "via", "per", "my", "your", "our", "its", "their",
        "new", "old", "first", "last", "some", "any", "both", "between",
        "into", "through", "during", "before", "after", "above", "below",
        "up", "down", "out", "off", "over", "under", "then", "once",
        "other", "another", "such", "own", "same", "than", "just", "now",
        "while", "within", "without", "whether", "which", "who", "whom",
        "whose", "very", "so", "too", "most", "much", "well",
        # Einzel-Zeichen + Zahlen-Tokens
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    ]
)

# Tokens kürzer als 2 Zeichen werden verworfen (1-Zeichen-Tokens nutzlos)
_MIN_TOKEN_LEN = 2


# === Normalisierung =============================================================


def normalize_token(token: str) -> str:
    """Normalisiert ein Token: lowercase, Umlaute → ASCII, nur Buchstaben/Bindestriche."""
    token = token.lower()
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        token = token.replace(old, new)
    # Nur alphanumerische Zeichen und Bindestriche behalten
    token = re.sub(r"[^\w-]", "", token, flags=re.ASCII)
    # Unterstriche → Bindestriche
    token = token.replace("_", "-")
    # Mehrfache Bindestriche bereinigen
    token = re.sub(r"-+", "-", token).strip("-")
    return token


def is_valid_token(token: str) -> bool:
    """Prüft ob ein Token nützlich ist (Länge, kein Stop-Wort, kein reines Datum)."""
    if len(token) < _MIN_TOKEN_LEN:
        return False
    if token in _STOP_WORDS:
        return False
    # Reine Zahlen-Tokens verwerfen
    if re.fullmatch(r"\d+", token):
        return False
    # Sehr lange Tokens (>40 Zeichen) sind oft Pfade oder Hashes
    if len(token) > 40:
        return False
    return True


# === Extraktion =================================================================


def extract_frontmatter_tags(content: str) -> list[str]:
    """Extrahiert `tags`-Feld aus YAML-Frontmatter."""
    if not content.startswith("---"):
        return []
    end = content.find("\n---\n", 3)
    if end == -1:
        return []
    fm_text = content[3:end]
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return []
    if not isinstance(fm, dict):
        return []
    tags = fm.get("tags", fm.get("Tags", []))
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
    if not isinstance(tags, list):
        return []
    return [str(t).strip() for t in tags if str(t).strip()]


def extract_heading_tokens(content: str) -> list[str]:
    """Extrahiert Tokens aus H1- und H2-Headings."""
    tokens: list[str] = []
    for match in re.finditer(r"^#{1,2}\s+(.+)$", content, re.MULTILINE):
        heading = match.group(1).strip()
        # Backtick-Code-Spans entfernen
        heading = re.sub(r"`[^`]+`", "", heading)
        # Wörter tokenisieren (Bindestrich als Trennzeichen + Leerzeichen)
        words = re.split(r"[\s\-_/\\|]+", heading)
        tokens.extend(words)
    return tokens


def extract_filename_tokens(filename: str) -> list[str]:
    """Extrahiert Tokens aus dem Dateinamen (ohne Erweiterung)."""
    stem = Path(filename).stem
    # Separatoren: Leerzeichen, Underscore, Bindestrich, Punkt
    tokens = re.split(r"[\s_\-\.]+", stem)
    return tokens


# === Aggregation ================================================================


def build_inventory(
    corpus_dir: Path,
) -> tuple[
    dict[str, list[str]],  # Section A: tag → [files]
    dict[str, list[str]],  # Section B: token → [files]
    dict[str, list[str]],  # Section C: token → [files]
]:
    """Scannt alle Markdown-Files und aggregiert Tag-Kandidaten."""
    section_a: dict[str, list[str]] = defaultdict(list)
    section_b: dict[str, list[str]] = defaultdict(list)
    section_c: dict[str, list[str]] = defaultdict(list)

    md_files = sorted(corpus_dir.glob("*.md"))

    for md_path in md_files:
        filename = md_path.name
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Section A: Frontmatter-Tags
        for raw_tag in extract_frontmatter_tags(content):
            norm = normalize_token(raw_tag)
            if is_valid_token(norm):
                if filename not in section_a[norm]:
                    section_a[norm].append(filename)

        # Section B: Heading-Tokens
        for raw_tok in extract_heading_tokens(content):
            norm = normalize_token(raw_tok)
            if is_valid_token(norm):
                if filename not in section_b[norm]:
                    section_b[norm].append(filename)

        # Section C: Dateinamen-Tokens
        for raw_tok in extract_filename_tokens(filename):
            norm = normalize_token(raw_tok)
            if is_valid_token(norm):
                if filename not in section_c[norm]:
                    section_c[norm].append(filename)

    return dict(section_a), dict(section_b), dict(section_c)


def _filter_min_freq(
    tag_map: dict[str, list[str]], min_freq: int = 2
) -> dict[str, list[str]]:
    """Filtert Tags mit weniger als min_freq Belegen."""
    return {tag: files for tag, files in tag_map.items() if len(files) >= min_freq}


def _sort_by_freq(tag_map: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    """Sortiert absteigend nach Häufigkeit, dann alphabetisch."""
    return sorted(tag_map.items(), key=lambda x: (-len(x[1]), x[0]))


# === Cluster-Vorschlag ==========================================================

# Thematische Cluster-Gruppen (heuristisch, für Ausgabe)
_CLUSTER_HINTS: list[tuple[str, list[str]]] = [
    ("Web / APIs", ["api", "rest", "http", "https", "json", "graphql", "websocket", "cors", "oauth"]),
    ("Frontend / CSS", ["css", "html", "javascript", "typescript", "react", "tailwind", "flexbox", "grid", "sass"]),
    ("Daten / Formate", ["markdown", "yaml", "toml", "frontmatter", "schema", "csv", "xml", "parquet", "jsonl"]),
    ("Git / Deployment", ["git", "github", "deployment", "cicd", "docker", "pipeline", "branch", "commit"]),
    ("Python / Code", ["python", "script", "function", "class", "module", "pytest", "ruff", "mypy", "pydantic"]),
    ("KI / LLM", ["ai", "llm", "qwen", "claude", "embedding", "prompt", "vector", "rag", "model"]),
    ("PKM / Wissen", ["obsidian", "vault", "knowledge", "pkm", "wikilink", "cluster", "tag", "note", "zettelkasten"]),
    ("Design / UX", ["design", "typography", "font", "color", "layout", "ux", "ui", "figma", "system"]),
    ("Automation / Scripts", ["automation", "script", "bash", "zsh", "shell", "cli", "terminal", "hook"]),
    ("Querschnitt", ["security", "performance", "documentation", "best-practice", "workflow", "standard"]),
]


def suggest_clusters(all_tags: set[str]) -> list[tuple[str, list[str]]]:
    """Gruppiert gefundene Tags in thematische Cluster (nur wenn Tag im Inventar)."""
    result: list[tuple[str, list[str]]] = []
    assigned: set[str] = set()
    for cluster_name, hints in _CLUSTER_HINTS:
        matched = [h for h in hints if h in all_tags]
        if matched:
            result.append((cluster_name, matched))
            assigned.update(matched)
    rest = sorted(all_tags - assigned)
    if rest:
        result.append(("Sonstiges", rest))
    return result


# === Ausgabe ====================================================================


def _fmt_table(rows: list[tuple[str, list[str]]], max_files: int = 3) -> str:
    """Formatiert Tag-Tabelle als Markdown."""
    lines = ["| Tag | Häufigkeit | Beleg-Files (max 3) |", "|---|---|---|"]
    for tag, files in rows:
        examples = ", ".join(files[:max_files])
        if len(files) > max_files:
            examples += ", …"
        lines.append(f"| `{tag}` | {len(files)} | {examples} |")
    return "\n".join(lines)


def render_inventory(
    a: dict[str, list[str]],
    b: dict[str, list[str]],
    c: dict[str, list[str]],
    total_files: int,
    min_freq_a: int = 2,
    min_freq_b: int = 8,
    min_freq_c: int = 3,
) -> str:
    """Rendert das Tag-Inventar als Markdown-String.

    Unterschiedliche Min-Freq pro Sektion:
      A (Frontmatter): ≥ 2 — diese Tags wurden bewusst gesetzt
      B (Headings): ≥ 8 — viele Rauschtokens, nur häufige behalten
      C (Dateinamen): ≥ 3 — mittlerer Filter
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    a_filtered = _filter_min_freq(a, min_freq=min_freq_a)
    b_filtered = _filter_min_freq(b, min_freq=min_freq_b)
    c_filtered = _filter_min_freq(c, min_freq=min_freq_c)

    # B: Tags aus A ausschließen (Duplikate), C: Tags aus A+B ausschließen
    b_only = {t: f for t, f in b_filtered.items() if t not in a_filtered}
    c_only = {t: f for t, f in c_filtered.items() if t not in a_filtered and t not in b_filtered}

    all_tags = set(a_filtered) | set(b_only) | set(c_only)
    clusters = suggest_clusters(all_tags)

    a_rows = _sort_by_freq(a_filtered)
    b_rows = _sort_by_freq(b_only)
    c_rows = _sort_by_freq(c_only)

    total_candidates = len(all_tags)
    recommended_size = f"{max(30, min(50, total_candidates))}–{max(40, min(70, total_candidates + 15))}"

    lines = [
        "---",
        "title: Tag-Inventar (heuristisch)",
        "slug: tag-inventory",
        "status: draft",
        f"generated: {now}",
        "---",
        "",
        "# Tag-Inventar (Vorschlag für Vokabular-Kuratierung)",
        "",
        "Automatisch generiert von `scripts/tag_inventory.py`. Basis für Block 0G.2 (manuelle Kuratierung).",
        "",
        "---",
        "",
        f"## Sektion A — Aus existierendem Frontmatter (≥{min_freq_a} Files, höchste Vertrauenswürdigkeit)",
        "",
        _fmt_table(a_rows) if a_rows else "_Keine Tags mit Frontmatter-Belegen gefunden._",
        "",
        "---",
        "",
        f"## Sektion B — Aus H1/H2-Headings (≥{min_freq_b} Files, mittlere Vertrauenswürdigkeit)",
        "",
        _fmt_table(b_rows) if b_rows else "_Keine Heading-Token-Kandidaten gefunden._",
        "",
        "---",
        "",
        f"## Sektion C — Aus Dateinamen (≥{min_freq_c} Files, Hinweis-Charakter)",
        "",
        _fmt_table(c_rows) if c_rows else "_Keine Dateinamen-Token-Kandidaten gefunden._",
        "",
        "---",
        "",
        "## Cluster-Vorschlag (gruppiert nach Themen-Nähe)",
        "",
    ]

    for cluster_name, tags in clusters:
        tags_str = ", ".join(f"`{t}`" for t in sorted(tags))
        lines.append(f"- **{cluster_name}:** {tags_str}")

    lines += [
        "",
        "---",
        "",
        "## Stats",
        "",
        f"- Files gescannt: {total_files}",
        f"- Kandidaten Section A (Frontmatter, ≥{min_freq_a}): {len(a_filtered)}",
        f"- Kandidaten Section B (Headings, ≥{min_freq_b}, exkl. A): {len(b_only)}",
        f"- Kandidaten Section C (Dateinamen, ≥{min_freq_c}, exkl. A+B): {len(c_only)}",
        f"- Kandidaten gesamt: {total_candidates}",
        f"- Empfehlung Vokabular-Größe: {recommended_size}",
        "",
        "---",
        "",
        "> **Nächster Schritt:** Block 0G.2 — Tag-Vokabular kuratieren in App-Session.",
        "> Sektion A hat höchste Priorität. Synonyme zusammenführen. Kategorienamen NICHT als Tags.",
    ]

    return "\n".join(lines)


# === Main =======================================================================


def main() -> None:
    """Einstiegspunkt."""
    parser = argparse.ArgumentParser(
        description="Tag-Inventar aus Korpus generieren (Block 0G.1)"
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=_DEFAULT_CORPUS,
        help=f"Pfad zum Corpus-Input-Verzeichnis (default: {_DEFAULT_CORPUS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Ausgabe-Pfad (default: {_DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    corpus_dir: Path = args.corpus_dir
    output_path: Path = args.output

    if not corpus_dir.exists():
        print(f"Fehler: corpus_dir nicht gefunden: {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    md_files = list(corpus_dir.glob("*.md"))
    total_files = len(md_files)
    if total_files == 0:
        print(f"Warnung: Keine .md-Dateien in {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanne {total_files} Markdown-Files in {corpus_dir}...")
    section_a, section_b, section_c = build_inventory(corpus_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_inventory(section_a, section_b, section_c, total_files)
    output_path.write_text(rendered, encoding="utf-8")

    a_f = _filter_min_freq(section_a)
    b_f = _filter_min_freq(section_b)
    c_f = _filter_min_freq(section_c)
    b_only = {t: f for t, f in b_f.items() if t not in a_f}
    c_only = {t: f for t, f in c_f.items() if t not in a_f and t not in b_f}
    total = len(a_f) + len(b_only) + len(c_only)

    print(f"Fertig: {output_path}")
    print(f"  Sektion A (Frontmatter): {len(a_f)} Tags")
    print(f"  Sektion B (Headings):    {len(b_only)} Tags")
    print(f"  Sektion C (Dateinamen):  {len(c_only)} Tags")
    print(f"  Gesamt:                  {total} Kandidaten")


if __name__ == "__main__":
    main()
