# TASK — PKM-rebuild: Projekt-Abschluss (autonom, ein Durchlauf)

**Auftrag (autorisiert):** Projekt heute vollständig abschließen. Ergebnis: verschiebbarer Vault, saubere Doku inkl. aller Entscheidungen, aufgeräumtes Repo, Re-Run-fähig für neue Files. **Finaler Merge nach `main` ist freigegeben.** Architektur-Entscheidungen unten sind gelockt — ausführen, nicht hinterfragen.

## Arbeitsregeln
- Autonom durcharbeiten. `$HOME`/absolute Pfade. **STOP nur bei echtem Blocker** (Verify-Gate rot / Datenverlust-Risiko) — dann sauberer Abbruch mit Rollback-Hinweis.
- Block 0 legt einen Rollback-Snapshot an. Bei hartem Fehler: abbrechen, Snapshot nennen.
- Verify-Gates (⛔) müssen grün sein, sonst Abbruch.
- Keine Zwischen-Erklärungen; am Ende **ein** `ℹ STATUS` (≤12 Zeilen).

## Gelockte Entscheidungen (Senior Architect)
1. Tag-Apply auf `04_vault` (kein Rebuild — Vault verifiziert korrekt).
2. `_index.md` nach Apply regenerieren; Vault-Frontmatter validieren.
3. Skip-Draft `befriffssammlung-tags-taxonomie-referenz` migrieren: Slug → `begriffssammlung-…`; Ziel aus `category` (∈16) mit Präfix, sonst `17_unsortiert`.
4. Vokabular 149 (`configuration` rein, `setup` raus, `ci`→`corporate-identity`, `design` behalten, `backup` deferred).
5. Drafts + Intermediates archivieren (tar), dann entfernen. Stale Backups/Diagnose-Reports/Fragmente löschen.
6. Finaler Merge nach `main` + push.

---

## Block 0 — Preflight, Rollback-Snapshot, Branch
```bash
set -euo pipefail
REPO="$HOME/projects/aktiv/PKM-rebuild"
DATA="$HOME/projects/aktiv/PKM_rebuild/data"
VAULT="$DATA/04_vault"
BK="$HOME/projects/aktiv/PKM_rebuild/backups"
TS=$(date +%Y%m%d_%H%M%S)
cd "$REPO"
git status --short
mkdir -p "$BK"
tar -czf "$BK/ROLLBACK_$TS.tar.gz" -C "$DATA" 04_vault 03_drafts 2>/dev/null
echo "ROLLBACK: $BK/ROLLBACK_$TS.tar.gz"
git checkout -b "finalize-$TS"
```

## Block 1 — Artefakte schreiben
```bash
cd "$REPO"
cat > scripts/apply_tag_map.py <<'APPLYEOF'
#!/usr/bin/env python3
"""
apply_tag_map.py — wendet das kuratierte Tag-Vokabular auf einen Ziel-Baum an.

Zweck:
  Letzter Verarbeitungsschritt vor dem Obsidian-Umzug. Pro .md im Ziel:
    1. tags lesen (YAML-Frontmatter)
    2. remap anwenden (Synonym -> Survivor)
    3. drop-Tags entfernen
    4. deduplizieren, Reihenfolge stabil
    5. nur Tags aus dem Vokabular behalten (tag-system.md)
  Nur das tags-Feld wird angefasst. Restliches Frontmatter + Body bleiben
  byte-identisch (gezielte Block-Ersetzung, kein YAML-Roundtrip).

Sicherheit:
  - DRY-RUN ist Default. Schreiben nur mit --apply.
  - --apply legt VORHER einen tar.gz-Snapshot des Ziels an (backup-before-write).
  - Idempotent: zweiter Lauf erzeugt keine weiteren Änderungen.

Aufruf:
  python3 scripts/apply_tag_map.py                 # dry-run auf 04_vault
  python3 scripts/apply_tag_map.py --apply         # schreibt + Backup
  python3 scripts/apply_tag_map.py --target 03_drafts

Exit:
  0 = nichts zu tun ODER apply erfolgreich
  1 = Änderungen ausstehend (dry-run) ODER Vokabular-Verstoß nach remap
  2 = Setup-Fehler (Pfade, fehlende Map/Vocab, Dependencies)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FEHLER: pyyaml fehlt. pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
REPO_ROOT = Path.home() / "projects" / "aktiv" / "PKM-rebuild"
BACKUP_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "backups"

FM_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
# tags-Block: ab 'tags:' bis zur nächsten Top-Level-Key-Zeile oder FM-Ende
TAGS_BLOCK_RE = re.compile(
    r"(?m)^tags:[ \t]*(?:\n(?:[ \t]+.*(?:\n|$)|[ \t]*-[ \t].*(?:\n|$))*|.*\n)"
)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def load_map(path: Path) -> tuple[set[str], dict[str, str], set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    vocab = {nfc(t) for t in data.get("vocabulary", [])}
    remap = {nfc(k): nfc(v) for k, v in data.get("remap", {}).items()}
    drop = {nfc(t) for t in data.get("drop", [])}
    return vocab, remap, drop


def load_vocab_md(path: Path) -> set[str]:
    """Vokabular aus tag-system.md ziehen (Zeilen wie '- `tag`')."""
    txt = path.read_text(encoding="utf-8")
    return {nfc(m) for m in re.findall(r"^\s*-\s+`([a-z0-9][a-z0-9-]*)`", txt, re.M)}


def extract_tags(fm_text: str) -> list[str] | None:
    """tags-Liste aus Frontmatter-Text lesen (inline oder block)."""
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or "tags" not in data:
        return None
    t = data["tags"]
    if t is None:
        return []
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [str(x) for x in t]
    return None


def transform(tags: list[str], vocab, remap, drop) -> tuple[list[str], list[str]]:
    """Returnt (neue_tags, verworfene_unbekannte)."""
    out: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        t = nfc(raw.strip().strip('"').strip("'"))
        if not t or t in drop:
            continue
        t = remap.get(t, t)
        if t in vocab:
            if t not in seen:
                seen.add(t)
                out.append(t)
        else:
            unknown.append(t)
    return out, unknown


def render_tags_block(tags: list[str]) -> str:
    if not tags:
        return "tags: []\n"
    lines = ["tags:"]
    lines += [f"  - {t}" for t in tags]
    return "\n".join(lines) + "\n"


def process_file(path: Path, vocab, remap, drop):
    """Returnt dict mit before/after/unknown/changed/error."""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return {"error": "no_frontmatter"}
    fm = m.group(1)
    before = extract_tags(fm)
    if before is None:
        return {"error": "no_tags_or_parse"}
    after, unknown = transform(before, vocab, remap, drop)
    changed = [nfc(x) for x in before] != after

    new_text = None
    if changed:
        block = render_tags_block(after)
        if TAGS_BLOCK_RE.search(fm):
            new_fm = TAGS_BLOCK_RE.sub(block, fm, count=1)
        else:  # tags fehlten als Block -> ans Ende des FM
            new_fm = fm + block
        new_text = f"---\n{new_fm}---\n" + text[m.end():]
    return {
        "before": before, "after": after, "unknown": unknown,
        "changed": changed, "new_text": new_text, "error": None,
    }


def iter_targets(target_dir: Path):
    for p in sorted(target_dir.rglob("*.md")):
        if p.name == "_index.md":
            continue
        if "00_Meta" in p.parts:
            continue
        if "_hold" in p.parts:
            continue
        yield p


def make_backup(target_dir: Path) -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"pre_tagapply_{target_dir.name}_{ts}.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(target_dir, arcname=target_dir.name)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="04_vault",
                    help="Unterordner in data/ (default 04_vault)")
    ap.add_argument("--map", default=str(REPO_ROOT / "scripts" / "tag_merge_map.json"))
    ap.add_argument("--vocab", default=None,
                    help="tag-system.md (default: <target>/00_Meta/tag-system.md)")
    ap.add_argument("--apply", action="store_true", help="schreibt + Backup (sonst dry-run)")
    args = ap.parse_args()

    target_dir = DATA_ROOT / args.target
    if not target_dir.exists():
        print(f"FEHLER: {target_dir} fehlt.", file=sys.stderr)
        return 2

    map_path = Path(args.map)
    if not map_path.exists():
        print(f"FEHLER: Merge-Map fehlt: {map_path}", file=sys.stderr)
        return 2
    vocab_json, remap, drop = load_map(map_path)

    vocab_md_path = Path(args.vocab) if args.vocab else target_dir / "00_Meta" / "tag-system.md"
    vocab = vocab_json
    if vocab_md_path.exists():
        vmd = load_vocab_md(vocab_md_path)
        if vmd and vmd != vocab_json:
            only_md, only_json = vmd - vocab_json, vocab_json - vmd
            print(f"WARNUNG: tag-system.md ≠ map.vocabulary  "
                  f"(nur_md={len(only_md)}, nur_json={len(only_json)})", file=sys.stderr)
        vocab = vmd or vocab_json
    else:
        print(f"WARNUNG: {vocab_md_path} fehlt, nutze map.vocabulary als Whitelist.", file=sys.stderr)

    changed_files: list[tuple[Path, dict]] = []
    unknown_counter: Counter[str] = Counter()
    errors: list[tuple[Path, str]] = []
    n = 0
    for p in iter_targets(target_dir):
        n += 1
        r = process_file(p, vocab, remap, drop)
        if r.get("error"):
            errors.append((p, r["error"]))
            continue
        for u in r["unknown"]:
            unknown_counter[u] += 1
        if r["changed"]:
            changed_files.append((p, r))

    # Report
    print("\n=== apply_tag_map ===")
    print(f"Ziel:            {target_dir}")
    print(f"Modus:           {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Files gescannt:  {n}")
    print(f"Mit Änderungen:  {len(changed_files)}")
    print(f"Parse-Fehler:    {len(errors)}")
    print(f"Vokabular:       {len(vocab)} Tags")
    if unknown_counter:
        print(f"\nUnbekannt nach remap (NICHT im Vokabular, würden entfernt): "
              f"{len(unknown_counter)}")
        for t, c in unknown_counter.most_common(20):
            print(f"  {t}: {c}")

    for p, r in changed_files[:30]:
        print(f"\n  {p.relative_to(target_dir)}")
        print(f"    - {sorted(set(nfc(x) for x in r['before']))}")
        print(f"    + {r['after']}")
    if len(changed_files) > 30:
        print(f"\n  … {len(changed_files)-30} weitere")

    if errors:
        print("\nFEHLER-Files:")
        for p, e in errors:
            print(f"  {e}: {p.relative_to(target_dir)}")

    if args.apply and changed_files:
        bak = make_backup(target_dir)
        print(f"\nBackup: {bak}")
        for p, r in changed_files:
            p.write_text(r["new_text"], encoding="utf-8")
        print(f"Geschrieben: {len(changed_files)} Files")
        return 0

    if changed_files:
        print("\nDRY-RUN — nichts geschrieben. Mit --apply ausführen.")
        return 1
    print("\nNichts zu tun (idempotent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
APPLYEOF
cat > scripts/tag_merge_map.json <<'MAPEOF'
{
  "generated": "2026-06-06",
  "vocabulary": [
    "accessibility",
    "api",
    "architecture",
    "art-history",
    "aspect-ratio",
    "auth",
    "automation",
    "bash",
    "cartography",
    "cheatsheet",
    "chmod",
    "claude",
    "cli",
    "cognitive-load",
    "color-theory",
    "computer-vision",
    "configuration",
    "corporate-identity",
    "crm",
    "css",
    "csv",
    "data-analysis",
    "data-formats",
    "data-processing",
    "data-quality",
    "data-visualization",
    "debugging",
    "deduplication",
    "design",
    "design-psychology",
    "design-systems",
    "developer-tools",
    "devops",
    "diagrams",
    "display",
    "documentation",
    "duplicate-detection",
    "ecommerce",
    "embeddings",
    "excel",
    "exif",
    "exiftool",
    "file-management",
    "folder-structure",
    "formatting",
    "frontend",
    "frontmatter",
    "gestalt-principles",
    "git",
    "github",
    "gitignore",
    "governance",
    "graphic-design",
    "graphql",
    "graphviz",
    "gui",
    "hd",
    "homebrew",
    "http",
    "image-formats",
    "image-processing",
    "imagemagick",
    "information-architecture",
    "iptc",
    "javascript",
    "json",
    "knowledge-management",
    "layout",
    "llm",
    "machine-learning",
    "macos",
    "markdown",
    "mermaid",
    "metadata",
    "navigation",
    "ner",
    "networking",
    "nlp",
    "obsidian",
    "ocr",
    "ontology",
    "open-source",
    "pandas",
    "pandoc",
    "parquet",
    "pattern-matching",
    "personal-branding",
    "perspective-drawing",
    "philosophy",
    "pipeline",
    "pixel-density",
    "pkm",
    "plantuml",
    "printing",
    "product-data",
    "programming",
    "project-management",
    "project-structure",
    "prompt-engineering",
    "psychology",
    "python",
    "rag",
    "readme",
    "reference",
    "regex",
    "renaissance",
    "research",
    "resolution",
    "responsive-design",
    "rest",
    "scripting",
    "security",
    "semantic-search",
    "shell",
    "shortcuts",
    "software-architecture",
    "software-development",
    "sql",
    "sqlite",
    "ssh",
    "standards",
    "strings",
    "syntax",
    "taxonomy",
    "technical-writing",
    "templates",
    "terminal",
    "text-processing",
    "toml",
    "topic-modeling",
    "troubleshooting",
    "typography",
    "ui-ux",
    "unix-philosophy",
    "usb",
    "variables",
    "vault-standard",
    "vector-database",
    "virtual-environment",
    "visual-hierarchy",
    "visualization",
    "vscode",
    "web-development",
    "web-scraping",
    "webp",
    "workflow",
    "xmp",
    "yaml",
    "zsh"
  ],
  "vocabulary_size": 149,
  "drop": [
    "ai-prompts",
    "ai-workflow",
    "aktivieren",
    "analyse",
    "anzeigen",
    "apis",
    "architektur",
    "artikel",
    "attributes",
    "ausfuehren",
    "automatisch",
    "backup",
    "batch",
    "best-practices",
    "bilder",
    "cinema",
    "cleaning",
    "cnn",
    "code",
    "collaboration",
    "comprehensive",
    "conventions",
    "conversion",
    "daten",
    "datenbank",
    "design-tokens",
    "digital-collage",
    "dokumente",
    "epistemology",
    "erp-integration",
    "erste",
    "fazit",
    "file",
    "finden",
    "folge",
    "format",
    "formats",
    "functions",
    "funktioniert",
    "grpc",
    "gut",
    "haeufige",
    "hierarchie",
    "hinzufuegen",
    "inhaltsverzeichnis",
    "installation",
    "installieren",
    "integration",
    "iterm2",
    "konfiguration",
    "kurzdefinition",
    "laden",
    "language",
    "links",
    "maintenance",
    "management",
    "mehrere",
    "meta",
    "metadaten",
    "moegliche",
    "multiple",
    "name",
    "normalization",
    "nutrition",
    "on-premise-ai",
    "optional",
    "organization",
    "output",
    "personal",
    "phasen",
    "philosophie",
    "political-economy",
    "pro",
    "projekt",
    "pruefen",
    "quality",
    "quick",
    "readability",
    "regeln",
    "report",
    "request",
    "request-response",
    "search",
    "server",
    "setzen",
    "speichern",
    "standard",
    "start",
    "starten",
    "status",
    "structure",
    "suchen",
    "system",
    "tags",
    "techniken",
    "testen",
    "testing",
    "themen",
    "tipps",
    "titel",
    "top",
    "typische",
    "ui",
    "use-cases",
    "vergleich",
    "version-control",
    "vs",
    "webserver",
    "websockets",
    "weiterfuehrende",
    "windows",
    "workflows",
    "xml",
    "zentrale",
    "ziel"
  ],
  "remap": {
    "api-design": "api",
    "authentication": "auth",
    "ci": "corporate-identity",
    "command-line": "cli",
    "commands": "cli",
    "composition": "design",
    "data": "data-processing",
    "data-cleaning": "data-quality",
    "data-extraction": "data-processing",
    "data-integration": "data-processing",
    "data-structures": "data-formats",
    "data-transfer": "data-processing",
    "data-types": "data-formats",
    "data-validation": "data-quality",
    "design-principles": "design",
    "design-system": "design-systems",
    "development-environment": "developer-tools",
    "development-workflow": "developer-tools",
    "frontend-development": "frontend",
    "gestalt-psychology": "gestalt-principles",
    "gestaltgesetze": "gestalt-principles",
    "information-design": "information-architecture",
    "keyboard-shortcuts": "shortcuts",
    "layout-design": "layout",
    "mixed": "perspective-drawing",
    "mixed-perspective": "perspective-drawing",
    "named-entity-recognition": "ner",
    "perspective": "perspective-drawing",
    "productivity": "workflow",
    "project": "project-management",
    "project-planning": "project-management",
    "project-specification": "project-structure",
    "script": "scripting",
    "scripts": "scripting",
    "tag": "taxonomy",
    "tagging": "taxonomy",
    "template": "templates",
    "text-mining": "text-processing",
    "ui-design": "ui-ux",
    "ux-design": "ui-ux",
    "visual-perception": "visual-hierarchy",
    "vs-code": "vscode",
    "web": "web-development",
    "web-design": "web-development",
    "workflow-automation": "automation",
    "workflow-optimization": "workflow"
  },
  "note": "Anwendung auf Draft-Frontmatter: jeden tag durch remap[tag] ersetzen; tags in 'drop' entfernen; resultierende Liste deduplizieren + nur 'vocabulary' behalten."
}
MAPEOF
cat > scripts/rebuild_indices.py <<'REIDXEOF'
#!/usr/bin/env python3
"""rebuild_indices.py — _index.md pro Cluster-Ordner neu schreiben (nach Tag-Apply)."""
import re, sys, unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
import yaml
VAULT = Path.home()/"projects"/"aktiv"/"PKM_rebuild"/"data"/"04_vault"
FM = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
def fm(p):
    m = FM.match(p.read_text(encoding="utf-8"))
    if not m: return {}
    try: return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError: return {}
n=0
for d in sorted(VAULT.iterdir()):
    if not d.is_dir() or d.name=="00_Meta": continue
    arts=[p for p in sorted(d.glob("*.md")) if p.name!="_index.md"]
    if not arts: continue
    tagc=Counter(); rows=[]
    for p in arts:
        f=fm(p)
        rows.append((f.get("title",p.stem), f.get("slug",p.stem), f.get("status","draft")))
        for t in (f.get("tags") or []): tagc[t]+=1
    L=[f"# {d.name}","",f"Cluster-Index. Automatisch generiert {date.today().isoformat()}.","",
       f"**Artikel:** {len(arts)}","","## Artikel","","| Titel | Slug | Status |","|---|---|---|"]
    for ti,sl,st in sorted(rows): L.append(f"| {ti} | `{sl}` | {st} |")
    L+=["","## Tag-Häufigkeiten",""]
    if tagc:
        L+=["| Tag | Anzahl |","|---|--:|"]
        for t,c in tagc.most_common(): L.append(f"| `{t}` | {c} |")
    else: L.append("_keine_")
    L.append("")
    (d/"_index.md").write_text("\n".join(L),encoding="utf-8"); n+=1
print(f"_index.md regeneriert: {n}")
REIDXEOF
cat > scripts/validate_vault.py <<'VALEOF'
#!/usr/bin/env python3
"""validate_vault.py — Pflichtfelder/Enums/Category/Slug + Vokabular im gebauten Vault."""
import re, sys, unicodedata
from pathlib import Path
import yaml
VAULT = Path.home()/"projects"/"aktiv"/"PKM_rebuild"/"data"/"04_vault"
FM = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CATS={"meta","grundlagen","webentwicklung","betriebssysteme","protokolle-und-standards",
 "dateitypen-und-konfiguration","methoden-und-prozesse","best-practices","cheatsheets",
 "ki-und-semantische-systeme","datenarchitektur-und-datenbanken","dokumentenverarbeitung-und-extraktion",
 "wissensmodellierung-und-knowledge-graphs","visualisierung-reporting-und-design-systeme",
 "automatisierung-scripting-und-pipelines","gedanken","kunst-kultur","unsortiert"}
TYPE={"process-document","knowledge-article","compact-reference","gedanke"}
STATUS={"draft","review","stable","deprecated"}; REV={"ai_drafted","human_reviewed","verified"}
CONF={"low","medium","high"}
REQ={"title","slug","summary","type","doc_role","category","sources_docs","source_chunks",
 "status","review_status","confidence","doc_version","created","updated"}
vs=set()
ts=VAULT/"00_Meta"/"tag-system.md"
if ts.exists():
    vs={m for m in re.findall(r"^\s*-\s+`([a-z0-9][a-z0-9-]*)`", ts.read_text(encoding="utf-8"), re.M)}
issues=0; files=0
for p in VAULT.rglob("*.md"):
    if p.name=="_index.md" or "00_Meta" in p.parts: continue
    files+=1
    m=FM.match(p.read_text(encoding="utf-8"))
    if not m: print(f"  no_frontmatter: {p.relative_to(VAULT)}"); issues+=1; continue
    try: d=yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e: print(f"  yaml_error {p.name}: {e}"); issues+=1; continue
    miss=REQ-set(d)
    if miss: print(f"  {p.name}: fehlende Felder {sorted(miss)}"); issues+=1
    if d.get("type") not in TYPE: print(f"  {p.name}: type={d.get('type')}"); issues+=1
    if d.get("category") not in CATS: print(f"  {p.name}: category={d.get('category')}"); issues+=1
    sl=d.get("slug","")
    if not isinstance(sl,str) or not SLUG.match(sl): print(f"  {p.name}: slug={sl}"); issues+=1
    if vs:
        bad=[t for t in (d.get("tags") or []) if t not in vs]
        if bad: print(f"  {p.name}: tags außerhalb Vokabular {bad}"); issues+=1
print(f"validate_vault: {files} Files, {issues} Issues")
sys.exit(1 if issues else 0)
VALEOF
mkdir -p "$VAULT/00_Meta"
cat > "$VAULT/00_Meta/tag-system.md" <<'TAGSYSEOF'
---
title: Tag-System (kontrolliertes Vokabular)
slug: tag-system
status: stable
created: 2026-06-06
updated: 2026-06-06
---

# Tag-System — kontrolliertes Vokabular

Verbindliches Tag-Vokabular für den Vault. Quelle: `docs/03_vault_standard.md` §7.

## Regeln

- Nur Tags aus diesem Vokabular verwenden. Erweiterung braucht Begründung + Eintrag hier.
- Klein geschrieben, Englisch (Tech-Standard), Bindestrich-getrennt.
- Max. 5–10 Tags pro Artikel.
- Kategorien **nicht** als Tags duplizieren (Ordnernamen ≠ Tags).
- Synonyme vermeiden — Survivor-Tag laut Merge-Map nutzen.

## Vokabular

### Sprachen & Code

- `css`
- `javascript`
- `pandas`
- `programming`
- `python`
- `strings`
- `syntax`
- `variables`

### Terminal, Shell & Scripting

- `bash`
- `chmod`
- `cli`
- `homebrew`
- `macos`
- `scripting`
- `shell`
- `terminal`
- `unix-philosophy`
- `zsh`

### Git & Versionierung

- `git`
- `github`
- `gitignore`
- `ssh`

### Web & APIs

- `api`
- `frontend`
- `graphql`
- `http`
- `networking`
- `responsive-design`
- `rest`
- `web-development`
- `web-scraping`

### Daten & Formate

- `configuration`
- `csv`
- `data-analysis`
- `data-formats`
- `data-processing`
- `data-quality`
- `data-visualization`
- `json`
- `parquet`
- `toml`
- `webp`
- `yaml`

### Datenbanken

- `sql`
- `sqlite`
- `vector-database`

### KI, NLP & semantische Systeme

- `claude`
- `computer-vision`
- `embeddings`
- `llm`
- `machine-learning`
- `ner`
- `nlp`
- `ocr`
- `ontology`
- `prompt-engineering`
- `rag`
- `semantic-search`
- `topic-modeling`

### Dokumentenverarbeitung & Extraktion

- `deduplication`
- `duplicate-detection`
- `pandoc`
- `pattern-matching`
- `regex`
- `text-processing`

### Bild & Metadaten

- `aspect-ratio`
- `display`
- `exif`
- `exiftool`
- `hd`
- `image-formats`
- `image-processing`
- `imagemagick`
- `iptc`
- `pixel-density`
- `printing`
- `resolution`
- `xmp`

### Design, UX & Visuelles

- `accessibility`
- `cartography`
- `cognitive-load`
- `color-theory`
- `corporate-identity`
- `design`
- `design-psychology`
- `design-systems`
- `gestalt-principles`
- `graphic-design`
- `information-architecture`
- `layout`
- `perspective-drawing`
- `typography`
- `ui-ux`
- `visual-hierarchy`

### Diagramme & Visualisierung

- `diagrams`
- `graphviz`
- `mermaid`
- `plantuml`
- `visualization`

### Wissensmanagement & PKM

- `frontmatter`
- `knowledge-management`
- `markdown`
- `metadata`
- `obsidian`
- `pkm`
- `taxonomy`

### Methoden, Projekte & Prozesse

- `automation`
- `developer-tools`
- `devops`
- `file-management`
- `folder-structure`
- `open-source`
- `pipeline`
- `project-management`
- `project-structure`
- `research`
- `software-architecture`
- `software-development`
- `standards`
- `virtual-environment`
- `vscode`
- `workflow`

### Dokumentation & Standards

- `cheatsheet`
- `documentation`
- `formatting`
- `readme`
- `reference`
- `technical-writing`
- `templates`
- `vault-standard`

### Sicherheit & System

- `auth`
- `debugging`
- `gui`
- `navigation`
- `security`
- `shortcuts`
- `troubleshooting`
- `usb`

### Kunst, Kultur & Geistes

- `architecture`
- `art-history`
- `governance`
- `philosophy`
- `psychology`
- `renaissance`

### Business & Produkt

- `crm`
- `ecommerce`
- `excel`
- `personal-branding`
- `product-data`

## Statistik

- Tags gesamt: **149**
- Herkunft: 100 % aus existierendem Frontmatter (Sektion A)
- Themenbereiche: 17
- Abgeleitet aus 306 Kandidaten (3-stufiges Review).

> Frequenzangaben + vollständiges Merge-Mapping (Alt→Neu) siehe `tag_merge_map.json`.
TAGSYSEOF
[ -f "$VAULT/tag-system.md" ] && rm -f "$VAULT/tag-system.md" || true
ruff check scripts/apply_tag_map.py scripts/rebuild_indices.py scripts/validate_vault.py || true
```

## Block 2 — Skip-Draft migrieren
```bash
cd "$REPO"
DATA="$DATA" VAULT="$VAULT" python3 - <<'MIGEOF'

import os, re, shutil, unicodedata
from pathlib import Path
import yaml
DATA=Path(os.environ["DATA"]); VAULT=Path(os.environ["VAULT"]); DR=DATA/"03_drafts"
FM=re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
PREFIX={"meta":"00_Meta","grundlagen":"01_Grundlagen","webentwicklung":"02_Webentwicklung",
 "betriebssysteme":"03_Betriebssysteme","protokolle-und-standards":"04_Protokolle-und-Standards",
 "dateitypen-und-konfiguration":"05_Dateitypen-und-Konfiguration","methoden-und-prozesse":"06_Methoden-und-Prozesse",
 "best-practices":"07_Best-Practices","cheatsheets":"08_Cheatsheets","ki-und-semantische-systeme":"09_KI-und-Semantische-Systeme",
 "datenarchitektur-und-datenbanken":"10_Datenarchitektur-und-Datenbanken","dokumentenverarbeitung-und-extraktion":"11_Dokumentenverarbeitung-und-Extraktion",
 "wissensmodellierung-und-knowledge-graphs":"12_Wissensmodellierung-und-Knowledge-Graphs","visualisierung-reporting-und-design-systeme":"13_Visualisierung-Reporting-und-Design-Systeme",
 "automatisierung-scripting-und-pipelines":"14_Automatisierung-Scripting-und-Pipelines","gedanken":"15_Gedanken","kunst-kultur":"16_Kunst-Kultur"}
cands=[p for p in DR.glob("*.md") if "befriffssammlung" in p.name.lower() and not p.name.endswith(".body.md")]
if not cands:
    print("MIGRATE: kein befriffssammlung-Draft gefunden (evtl. bereits migriert) - skip"); raise SystemExit(0)
src=cands[0]; text=src.read_text(encoding="utf-8"); m=FM.match(text)
if not m: print("MIGRATE: kein Frontmatter - manueller Eingriff noetig"); raise SystemExit(0)
fm=yaml.safe_load(m.group(1)) or {}
cat=fm.get("category"); folder=PREFIX.get(cat,"17_unsortiert")
newslug=re.sub("befriffssammlung","begriffssammlung",str(fm.get("slug",src.stem)))
text=re.sub(r"(?m)^slug:.*$", f"slug: {newslug}", text, count=1)
dest=VAULT/folder/f"{newslug}.md"; dest.parent.mkdir(parents=True, exist_ok=True)
if dest.exists(): print(f"MIGRATE: {dest.name} existiert bereits - skip"); raise SystemExit(0)
dest.write_text(text, encoding="utf-8")
print(f"MIGRATE: {src.name} -> {folder}/{dest.name} (category={cat or 'fehlt->unsortiert'})")
MIGEOF
```

## Block 3 — Tag-Apply auf Vault (⛔ Gate)
```bash
cd "$REPO"
python3 scripts/apply_tag_map.py > /tmp/tag_dry.txt 2>&1 || true
tail -5 /tmp/tag_dry.txt
python3 scripts/apply_tag_map.py --apply > /tmp/tag_apply.txt 2>&1
tail -3 /tmp/tag_apply.txt
LEFT=$(grep -rlE "[\"' -](best-practices|meta|format|setup|funktioniert|installation)[\"',]" "$VAULT"/*/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "drop-Tags-Reste: $LEFT"
[ "$LEFT" = "0" ] || { echo "GATE3 ROT: drop-Tags verblieben"; exit 1; }
```

## Block 4 — Indizes + Vault-Validierung (⛔ Gate)
```bash
cd "$REPO"
python3 scripts/rebuild_indices.py
python3 scripts/validate_vault.py > /tmp/val.txt 2>&1 || { tail -30 /tmp/val.txt; echo "GATE4 ROT: Validierung"; exit 1; }
tail -3 /tmp/val.txt
DUP=$(find "$VAULT" -name '*.md' ! -name '_index.md' -exec shasum -a 256 {} \; 2>/dev/null | awk '{print $1}' | sort | uniq -d | wc -l | tr -d ' ')
echo "SHA256-Duplikate: $DUP"; [ "$DUP" = "0" ] || { echo "GATE4 ROT: Duplikate"; exit 1; }
```

## Block 5 — Projekt-Doku
```bash
cd "$REPO"
mkdir -p docs/learnings
cat > docs/learnings/FINALISIERUNG_2026-06-06.md <<'DECEOF'
---
title: Finalisierung & Entscheidungen 2026-06-06
slug: finalisierung-2026-06-06
status: stable
created: 2026-06-06
updated: 2026-06-06
---

# Finalisierung PKM-rebuild — Entscheidungen 2026-06-06

Abschluss Phase 9/10. Alle an diesem Tag getroffenen Entscheidungen, gelockt.

## Tag-Vokabular

- Kontrolliertes Vokabular: **149 Tags**, Quelle `04_vault/00_Meta/tag-system.md`.
- Abgeleitet aus 306 Kandidaten über 3 Review-Stufen (Inventar → x-Markierung → Tier-Analyse).
- Reduktionsprinzip: Frequenz-Schwelle (≥5 Kern, 3–4 Querschnitt, 2 Fachbegriff selektiv) statt Bauchgefühl.

### Einzelentscheidungen
| Tag | Entscheidung | Grund |
|---|---|---|
| `configuration` | aufgenommen | wiederkehrendes Querschnitts-Thema; NICHT auf `devops` gemappt (semantisch verschieden) |
| `setup` | verworfen | prozess-/dokumenttyp-nah; Semantik trägt `doc_role` (how-to/manual), nicht Tags |
| `ci` | → `corporate-identity` | Belege = Corporate Identity, Kollision mit CI/CD vermieden |
| `design` | behalten | Survivor für `design-principles`/`composition` |
| `backup` | verworfen, später nachrüstbar | aktuell kein Anlass |
| `meta`, `best-practices` | verworfen | Kategorie-Slug = Tag verboten (Vault-Standard §7) |

- 46 Synonym-Remaps + 115 Drops, vollständig in `scripts/tag_merge_map.json`.

## Konventionen

- `17_unsortiert` mit Nummern-Präfix ist **gewollt** (Abweichung von §4-Default bewusst).
- Tag-Apply läuft auf den gebauten Vault (`04_vault`), Drafts sind ab Phase 9 Wegwerf-Intermediate.
- Tags optional pro Datei; Klassifikation zusätzlich über `category`/`subcategory`/`doc_role`.
- Vault-Slug aus Titel abgeleitet (≠ `CK_`-Dateiname) — Provenance-Abgleich über `sources_docs`, nicht Dateiname.

## Build-/Migrations-Befunde

- Vault = frischer Build aus 180 Drafts (Provenance-Jaccard 99,4 %), kein Altbestand.
- 1 Draft (`befriffssammlung-tags-taxonomie-referenz`, Slug-Tippfehler) nachträglich migriert; Slug korrigiert zu `begriffssammlung-tags-taxonomie-referenz`.
- Triage-Match-Bug (zählt über Dateiname statt Provenance → meldete 27 statt 179) → Post-Project-Backlog.

## DoD

- Vault strukturiert, valides Frontmatter, 0 SHA-256-Duplikate, 0 Slug-Kollisionen, alle Wikilinks auflösbar, `_index.md` pro Cluster, Tests grün, ruff clean.
DECEOF
cat > docs/RUNBOOK_new_files.md <<'RUNEOF'
---
title: Runbook — Neue Files in den Vault
slug: runbook-new-files
status: stable
created: 2026-06-06
updated: 2026-06-06
---

# Runbook — Neue Files verarbeiten und in den Vault bringen

Standard-Ablauf für neue Markdown-Files nach Projektabschluss. Idempotent, wiederholbar.

## 1. Files ablegen
Neue `.md` nach `data/01_corpus_input/` kopieren.

## 2. Pipeline laufen lassen
```bash
cd $HOME/projects/aktiv/PKM-rebuild
python -m pipeline run            # Phasen 1–8: Inventar → Synthese → Drafts
```
Ergebnis: neue Drafts in `data/03_drafts/`.

## 3. Drafts reviewen
Frontmatter-Konsistenz prüfen:
```bash
python3 scripts/check_frontmatter.py
```
Inhaltlicher Review der neuen Drafts (Stufe ≥2).

## 4. In den Vault bauen
```bash
python -m pipeline build-vault    # baut/ergänzt 04_vault aus Drafts
```

## 5. Tags vereinheitlichen
```bash
python3 scripts/apply_tag_map.py            # Dry-Run
python3 scripts/apply_tag_map.py --apply    # mit Auto-Backup
```
Neue, sinnvolle Tags außerhalb des Vokabulars erscheinen im Dry-Run als „Unbekannt".
Soll einer bleiben: erst in `00_Meta/tag-system.md` + `scripts/tag_merge_map.json` aufnehmen, dann applien.

## 6. Indizes aktualisieren + validieren
```bash
python3 scripts/rebuild_indices.py
python3 scripts/validate_vault.py
```

## Makefile-Kurzbefehle
```bash
make add-files     # = build-vault + apply --apply + reindex + validate
make tag-apply     # nur Tag-Map anwenden
make reindex       # _index.md neu
make validate      # Vault-Frontmatter prüfen
```
RUNEOF
if [ -f Makefile ]; then cat >> Makefile <<'MAKEEOF'

# --- Abschluss-Targets (2026-06-06) ---
tag-apply:
	@python3 scripts/apply_tag_map.py --apply

reindex:
	@python3 scripts/rebuild_indices.py

validate:
	@python3 scripts/validate_vault.py

add-files:
	@python -m pipeline build-vault && python3 scripts/apply_tag_map.py --apply && python3 scripts/rebuild_indices.py && python3 scripts/validate_vault.py
MAKEEOF
fi
[ -f docs/PROJECT_STATUS.md ] && printf "\n## 2026-06-06 — ABGESCHLOSSEN\nVault gebaut + tag-bereinigt (149er Vokabular), Doku final, Repo aufgeraeumt, Re-Run-Runbook vorhanden. DoD erfuellt.\n" >> docs/PROJECT_STATUS.md || true
sed -i.bak 's/\*\*Phase:\*\*.*/\*\*Phase:\*\* abgeschlossen (2026-06-06)/' README.md 2>/dev/null && rm -f README.md.bak || true
```

## Block 6 — Aufräumen Repo + Daten
```bash
cd "$REPO"
TS2=$(date +%Y%m%d_%H%M%S)
tar -czf "$BK/archive_drafts_$TS2.tar.gz" -C "$DATA" 03_drafts 2>/dev/null && rm -rf "$DATA/03_drafts"
if [ -d "$DATA/02_pipeline_output" ]; then
  tar -czf "$BK/archive_pipeline_output_$TS2.tar.gz" -C "$DATA" 02_pipeline_output 2>/dev/null
  find "$DATA/02_pipeline_output" -maxdepth 1 -type d \( -name 'batches' -o -name 'qwen' -o -name 'phase8_logs' -o -name 'triage' \) -exec rm -rf {} + 2>/dev/null || true
  find "$DATA/02_pipeline_output" -maxdepth 1 -name '*.log' -delete 2>/dev/null || true
fi
find docs -maxdepth 2 \( -name 'STATE_AUDIT_*.md' -o -name 'SLUG_DIFF_*.md' \) -delete 2>/dev/null || true
rm -f docs/PHASE9_GO.md docs/PRE_PHASE9_HARDENING.md 2>/dev/null || true
find "$BK" -maxdepth 1 -type d \( -name 'snapshot_*' -o -name 'pre_*' -o -name 'archive_2*' \) -exec rm -rf {} + 2>/dev/null || true
find "$BK" -maxdepth 1 -name 'pre_tagapply_*.tar.gz' ! -newermt "$(date +%Y-%m-%d)" -delete 2>/dev/null || true
ls -1 "$BK"
```

## Block 7 — Final-Verify (⛔ Gate)
```bash
cd "$REPO"
mise exec -- pytest -q > /tmp/pt.txt 2>&1 || { tail -20 /tmp/pt.txt; echo "GATE7 ROT: pytest"; exit 1; }
tail -1 /tmp/pt.txt
ruff check . > /tmp/rf.txt 2>&1 || { cat /tmp/rf.txt; echo "GATE7 ROT: ruff"; exit 1; }
echo "ruff ok"
echo "Vault-Artikel: $(find "$VAULT" -name '*.md' ! -name '_index.md' -mindepth 2 | wc -l)"
echo "_index.md:     $(find "$VAULT" -name '_index.md' | wc -l)"
echo "tag-system.md: $([ -f "$VAULT/00_Meta/tag-system.md" ] && echo ja || echo NEIN)"
```

## Block 8 — Commit + Merge main
```bash
cd "$REPO"
git add -A
git commit -m "feat: Projekt-Abschluss - Tag-Vokabular (149) angewandt, Vault finalisiert, Doku+Runbook, Repo aufgeraeumt"
git checkout main
git merge --no-ff -m "Merge: Projekt-Abschluss PKM-rebuild" "finalize-$TS"
git push origin main
git branch -d "finalize-$TS"
git status --short && git log --oneline -3
```

## Abschluss — `ℹ STATUS` (≤12 Zeilen)
1. Tag-Apply: geänderte Files + drop-Reste (=0)
2. Skip-Draft migriert: Ziel-Ordner + neuer Slug
3. Vault: Artikel / `_index` / tag-system.md
4. validate_vault Issues (=0) · SHA256-Dups (=0)
5. pytest / ruff
6. Aufräumen: Archive erstellt, Backups eingedampft (Liste)
7. Git: main gemergt + gepusht, clean
8. **Vault verschiebbereit** — Move-Befehl: `mv "$VAULT" "<Obsidian-Zielpfad>"`
9. Rollback-Snapshot-Pfad

**Projekt abgeschlossen. Keine weitere Aktion.**
