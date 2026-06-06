# TASK — Vollständiger Projektstand-Audit (read-only)

**Zweck:** Verifizierten Ist-Stand des gesamten `~/projects`-Baums erstellen, mit Fokus auf das PKM-rebuild-Doppelverzeichnis (`PKM-rebuild` = Git-Repo, `PKM_rebuild` = Daten/Vault). Output = **ein** Markdown-Report. Keine Annahmen aus Doku — nur reale Filesystem-/Git-Fakten.

## Arbeitsregeln (verbindlich)
- **Read-only.** Keine Datei ändern/löschen/verschieben. Einzige Schreiboperation: der Report.
- `$HOME` statt `~` in allen Variablen-Assignments.
- Jeden Block-Output **an den Report anhängen** (`>> "$REPORT" 2>&1`), nie `| head` mitten im Pipe (SIGPIPE-Risiko).
- Autonom durchlaufen, **kein** STOP. Am Ende: `ℹ STATUS` mit 10-Zeilen-Summary zurück in den App-Chat.
- Wenn ein Pfad/Skript fehlt: Fehler in den Report schreiben, weiterlaufen.

## Setup
```bash
REPO="$HOME/projects/aktiv/PKM-rebuild"
DATA="$HOME/projects/aktiv/PKM_rebuild/data"
VAULT="$DATA/04_vault"
DRAFTS="$DATA/03_drafts"
TS=$(date +%Y%m%d_%H%M)
REPORT="$REPO/docs/STATE_AUDIT_${TS}.md"
mkdir -p "$REPO/docs"
echo "# Projektstand-Audit $TS" > "$REPORT"
echo "" >> "$REPORT"
```

---

## Block A — projects-Gesamtüberblick (Doppelungen/Waisen finden)
```bash
echo "## A. ~/projects Gesamtstruktur" >> "$REPORT"
echo '```' >> "$REPORT"
find "$HOME/projects" -maxdepth 2 -type d 2>/dev/null | sort >> "$REPORT"
echo '```' >> "$REPORT"

echo "### A.1 Verzeichnisgrößen (Top-Level je aktiv/)" >> "$REPORT"
echo '```' >> "$REPORT"
du -sh "$HOME/projects"/*/* 2>/dev/null | sort -rh >> "$REPORT"
echo '```' >> "$REPORT"

echo "### A.2 Namensähnliche Ordner (Bindestrich vs Unterstrich etc.)" >> "$REPORT"
echo '```' >> "$REPORT"
find "$HOME/projects" -maxdepth 3 -type d \( -iname '*pkm*' -o -iname '*rebuild*' \) 2>/dev/null | sort >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block B — Git-Repo (`PKM-rebuild`)
```bash
echo "## B. Git-Repo PKM-rebuild" >> "$REPORT"
echo '```' >> "$REPORT"
git -C "$REPO" status >> "$REPORT" 2>&1
echo "--- letzte 8 Commits ---" >> "$REPORT"
git -C "$REPO" log --oneline -8 >> "$REPORT" 2>&1
echo "--- Branches ---" >> "$REPORT"
git -C "$REPO" branch -a >> "$REPORT" 2>&1
echo "--- untracked/ignored Stichprobe ---" >> "$REPORT"
git -C "$REPO" status --ignored --short >> "$REPORT" 2>&1
echo '```' >> "$REPORT"

echo "### B.1 Repo-Struktur (2 Ebenen)" >> "$REPORT"
echo '```' >> "$REPORT"
find "$REPO" -maxdepth 2 -not -path '*/.git/*' 2>/dev/null | sort >> "$REPORT"
echo '```' >> "$REPORT"

echo "### B.2 scripts/ + Tests + Lint" >> "$REPORT"
echo '```' >> "$REPORT"
ls -la "$REPO/scripts" >> "$REPORT" 2>&1
cd "$REPO" && mise exec -- pytest -q >> "$REPORT" 2>&1 || echo "PYTEST_FEHLER (s.o.)" >> "$REPORT"
cd "$REPO" && ruff check . >> "$REPORT" 2>&1 || echo "RUFF_FEHLER (s.o.)" >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block C — Daten (`PKM_rebuild/data`)
```bash
echo "## C. Daten PKM_rebuild" >> "$REPORT"
echo '```' >> "$REPORT"
find "$DATA" -maxdepth 1 2>/dev/null | sort >> "$REPORT"
echo "--- Counts ---" >> "$REPORT"
echo "corpus_input .md:        $(find "$DATA/01_corpus_input" -name '*.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo "corpus _excluded:        $(find "$DATA/01_corpus_input/_excluded" -name '*.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo "drafts .md (ohne body):  $(find "$DRAFTS" -maxdepth 1 -name '*.md' ! -name '*.body.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo "drafts .body.md:         $(find "$DRAFTS" -maxdepth 1 -name '*.body.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo "drafts .frontmatter.json:$(find "$DRAFTS" -maxdepth 1 -name '*.frontmatter.json' 2>/dev/null | wc -l)" >> "$REPORT"
echo "drafts _hold/:           $(find "$DRAFTS/_hold" -name '*.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo '```' >> "$REPORT"

echo "### C.1 Backups" >> "$REPORT"
echo '```' >> "$REPORT"
ls -lt "$HOME/projects/aktiv/PKM_rebuild/backups" 2>/dev/null | sed -n '1,10p' >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block D — Vault-Tiefenanalyse
```bash
echo "## D. Vault" >> "$REPORT"
echo "### D.1 Cluster-Ordner + Counts" >> "$REPORT"
echo '```' >> "$REPORT"
for d in "$VAULT"/*/; do
  n=$(find "$d" -maxdepth 1 -name '*.md' ! -name '_index.md' 2>/dev/null | wc -l)
  idx=$([ -f "$d/_index.md" ] && echo "idx:ja" || echo "idx:NEIN")
  printf "%-50s files:%4s  %s\n" "$(basename "$d")" "$n" "$idx" >> "$REPORT"
done
echo "--- Totale ---" >> "$REPORT"
echo "Artikel (.md ohne _index): $(find "$VAULT" -name '*.md' ! -name '_index.md' -mindepth 2 2>/dev/null | wc -l)" >> "$REPORT"
echo "_index.md:                 $(find "$VAULT" -name '_index.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo "00_Meta .md:               $(find "$VAULT/00_Meta" -name '*.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo "alle .md gesamt:           $(find "$VAULT" -name '*.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo '```' >> "$REPORT"

echo "### D.2 Standard-Abweichungen (Ordnernamen)" >> "$REPORT"
echo '```' >> "$REPORT"
echo "Erwartet laut Vault-Standard §4: unsortiert/ OHNE Präfix, _attic/, 15_Gedanken/." >> "$REPORT"
echo "Gefundene Sonderordner:" >> "$REPORT"
find "$VAULT" -maxdepth 1 -type d \( -iname '*unsortiert*' -o -iname '_attic' -o -iname '*gedanken*' \) 2>/dev/null >> "$REPORT"
echo '```' >> "$REPORT"

echo "### D.3 SHA-256-Duplikate (DoD-Pflicht: 0)" >> "$REPORT"
echo '```' >> "$REPORT"
find "$VAULT" -name '*.md' ! -name '_index.md' -exec shasum -a 256 {} \; 2>/dev/null \
  | awk '{print $1}' | sort | uniq -d > /tmp/vault_dups.txt
echo "Duplikat-Hashes: $(wc -l < /tmp/vault_dups.txt)" >> "$REPORT"
cat /tmp/vault_dups.txt >> "$REPORT"
echo '```' >> "$REPORT"

echo "### D.4 Slug-Kollisionen (gleicher Dateiname in mehreren Clustern)" >> "$REPORT"
echo '```' >> "$REPORT"
find "$VAULT" -name '*.md' ! -name '_index.md' -mindepth 2 -exec basename {} \; 2>/dev/null \
  | sort | uniq -d >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block E — Konsistenz (Skripte)
```bash
echo "## E. Konsistenz-Skripte" >> "$REPORT"
echo "### E.1 check_frontmatter.py (gegen DRAFTS)" >> "$REPORT"
echo '```' >> "$REPORT"
cd "$REPO" && python3 scripts/check_frontmatter.py >> "$REPORT" 2>&1 || echo "EXIT!=0 (Issues vorhanden)" >> "$REPORT"
echo '```' >> "$REPORT"

echo "### E.2 pkm_triage.py (letzte 20 Zeilen)" >> "$REPORT"
echo '```' >> "$REPORT"
cd "$REPO" && python3 scripts/pkm_triage.py > /tmp/triage.txt 2>&1 || true
tail -20 /tmp/triage.txt >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block F — Tag-Stand (Bereinigung angewandt?)
```bash
echo "## F. Tag-Stand" >> "$REPORT"
echo '```' >> "$REPORT"
echo "tag-system.md im Vault?  $([ -f "$VAULT/00_Meta/tag-system.md" ] && echo JA || echo NEIN)" >> "$REPORT"
echo "tag_merge_map.json da?   $(find "$HOME/projects/aktiv/PKM-rebuild" "$DATA" -name 'tag_merge_map.json' 2>/dev/null | head -1)" >> "$REPORT"
echo "" >> "$REPORT"
echo "--- Distinct Tags im gebauten Vault (alle category-Cluster) ---" >> "$REPORT"
grep -rhoE '^\s*-\s+"?[a-z0-9][a-z0-9-]+"?' "$VAULT"/*/*.md 2>/dev/null \
  | grep -vE 'sources_docs|source_chunks|child_concepts|doc_role|related|used_in' \
  > /tmp/rawtags.txt || true
echo "(Heuristik — manuell gegenprüfen) Tag-Zeilen erfasst: $(wc -l < /tmp/rawtags.txt)" >> "$REPORT"
echo '```' >> "$REPORT"
echo "Hinweis: F ist heuristisch. Maßgeblich ist, ob ein Tag-Apply-Lauf dokumentiert ist (Commit/Log). Falls unklar → in STATUS als OFFEN markieren." >> "$REPORT"
```

## Block G — DoD-Abgleich (Strategy §3)
```bash
echo "## G. DoD-Schnellabgleich" >> "$REPORT"
echo '```' >> "$REPORT"
echo "[ ] Vault existiert + strukturiert:        $([ -d "$VAULT" ] && echo JA || echo NEIN)" >> "$REPORT"
echo "[ ] _index.md pro genutztem Cluster:       siehe D.1 (idx-Spalte)" >> "$REPORT"
echo "[ ] Keine SHA-256-Duplikate:               siehe D.3" >> "$REPORT"
echo "[ ] Frontmatter valide:                    siehe E.1" >> "$REPORT"
echo "[ ] Triage konsistent:                     siehe E.2" >> "$REPORT"
echo "[ ] Tests grün + ruff clean:               siehe B.2" >> "$REPORT"
echo "[ ] reports/ (corpus/duplicate/cluster):   $(find "$DATA/02_pipeline_output" -name '*_report.md' 2>/dev/null | wc -l) gefunden" >> "$REPORT"
echo "[ ] Tag-Vokabular angewandt:               siehe F" >> "$REPORT"
echo '```' >> "$REPORT"
```

## Abschluss
```bash
echo "" >> "$REPORT"
echo "Report: $REPORT"
echo "Zeilen: $(wc -l < "$REPORT")"
```

**ℹ STATUS an App-Chat (CC ausgeben):** max. 10 Zeilen —
1. Vault-Counts (Artikel / `_index` / 00_Meta / gesamt) + ob 205 erklärt
2. SHA-256-Dups + Slug-Kollisionen (D.3/D.4)
3. `17_unsortiert`-Anomalie bestätigt? (D.2)
4. check_frontmatter Exit + Triage-Endzeilen
5. pytest/ruff Ergebnis
6. Tag-Bereinigung: angewandt / offen / unklar
7. DoD-Lücken aus G
8. Report-Pfad

**Kein** weiteres Vorgehen einleiten — Audit endet hier, Entscheidungen zurück im App-Chat.
