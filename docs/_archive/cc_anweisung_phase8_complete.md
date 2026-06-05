# Anweisung an Claude Code — Phase 8: Vollständiges File-Archiv

**Datum:** 2026-06-01
**Branch-Empfehlung:** `phase8/complete-archive` (für eventuelle Code-Änderungen am Pipeline)
**Geltungsbereich:** alle Operationen bis alle 201 Korpus-Slugs einen sauber verarbeiteten Draft haben

---

## 1. Ziel

Vollständiges File-Archiv aufbauen: für **jeden** der 201 Korpus-Slugs aus `data/01_corpus_input/` existiert am Ende ein konsistenter Draft-Triple (`CK_<slug>.md` + `CK_<slug>.frontmatter.json`, ggf. `CK_<slug>.body.md`) in `data/03_drafts/`.

**Definition „vollständig":** `pkm_triage.py` meldet 0 Slugs in `RERUN_LM` und 0 in `FRESH_RUN`. Optimierung des Inhalts (Tag-Konsolidierung, category-Mapping, Vault-Aufbau) ist explizit NACH dieser Aufgabe — nicht jetzt.

---

## 2. Was bereits passiert ist (Kontext)

- Triage-Lauf am 2026-06-01 18:21 zeigt:
  - 103 Drafts matched (1 READY_TO_MIGRATE, 13 POSTPROCESS, 89 RERUN_LM)
  - 0 Orphans nach Cleanup
  - 98 FRESH_RUN (Korpus-Files ohne Draft)
  - 106 Hidden Files (`.CK_*.meta.json`) übersprungen
- Skip-Bug-Fix liegt auf Branch `fix/phase8-resume-dedup` (Zeile ~885 in `pipeline/phase_8_synthesis.py` + `max_tokens_stage3: 16000` in `pipeline/pipeline.config.yaml`). **Noch nicht auf main.**

---

## 3. Arbeitsvereinbarung (gilt zusätzlich zu `0N`)

- **Default autonom.** Block-Ende-Bericht nach jedem nummerierten Block.
- **STOP-Punkte** sind unten pro Block markiert. Keine STOPs aus eigenem Ermessen einlegen.
- **NIE stoppen** für: Branch-Commits, Snapshots, Tests, Pipeline-Läufe ohne `--force`, Hidden-File-Archivierung.
- **Wach halten** mit `caffeinate` für alle LM-Studio-Läufe (Block 5+).
- **Was NICHT in den Run gehört:** READY_TO_MIGRATE (1) + POSTPROCESS (13) + Excluded (1) + Orphan-Stems (0). Hidden Files (106) sind separat zu behandeln (Block 2).

---

## 4. Vor-Bedingungen prüfen (Pre-Flight)

Bevor irgendein Block beginnt:

```bash
cd ~/projects/aktiv/PKM-rebuild
git status                                          # muss clean sein
git branch --show-current                           # aktuellen Stand notieren
ls ~/projects/aktiv/PKM_rebuild/data/03_drafts/ | wc -l    # Soll: 309 (103+99+103+4 Edge) oder ähnlich
ls -A ~/projects/aktiv/PKM_rebuild/data/03_drafts/.CK_*.meta.json 2>/dev/null | wc -l    # Soll: 106
python3 scripts/pkm_triage.py | tail -15            # Soll: RERUN_LM=89, FRESH_RUN=98
```

Wenn diese Zahlen abweichen: **STOP, Bericht an User.** Sonst weiter.

---

## Block 1 — Skip-Bug-Fix auf main mergen

**Ziel:** Sicherstellen, dass die Skip-Logik bei wiederholten Pipeline-Läufen nicht wieder Doppelarbeit auslöst.

### Schritte

1. Branch `fix/phase8-resume-dedup` auschecken, Diff gegen main prüfen
2. Tests laufen lassen:
   ```bash
   pytest -v
   ruff check . && ruff format --check .
   ```
3. Wenn grün: PR-Beschreibung erstellen (Format: Conventional Commit, `fix(pipeline): skip-logic also checks frontmatter.meta.json existence`)
4. **STOP — User-Freigabe für main-Merge.**

### Akzeptanz

- [ ] Tests grün
- [ ] Lint clean
- [ ] User hat Merge auf main freigegeben

---

## Block 2 — Hidden Files archivieren

**Ziel:** Die 106 hängengebliebenen `.CK_*.meta.json` aus `03_drafts/` entfernen, sodass die Skip-Logik nicht durch leftover Bookkeeping verwirrt wird.

### Schritte

```bash
DATA=~/projects/aktiv/PKM_rebuild/data
BACKUP=~/projects/aktiv/PKM_rebuild/backups/hidden_meta_$(date +%Y%m%d_%H%M)
mkdir -p "$BACKUP"

# Stichprobe vor dem Verschieben sichern (Beleg)
ls -la "$DATA/03_drafts/.CK_"*.meta.json | head -5 > "$BACKUP/_inventory_before.txt"

# Verschieben (nicht löschen — defensive)
mv "$DATA/03_drafts/".CK_*.meta.json "$BACKUP/"

# Verifizieren
ls -A "$DATA/03_drafts/".CK_*.meta.json 2>/dev/null && echo "FEHLER: noch hidden meta da" && exit 1
echo "✓ Hidden Files archiviert nach $BACKUP"
ls "$BACKUP" | wc -l
```

### Akzeptanz

- [ ] `ls .CK_*.meta.json` in `03_drafts/` liefert nichts
- [ ] Backup-Verzeichnis enthält 106 Files

Kein STOP. Weiter zu Block 3.

---

## Block 3 — Triage-Baseline neu erstellen

**Ziel:** Nach Cleanup verifizieren, dass die Triage immer noch dieselbe Verteilung liefert (sanity check).

### Schritte

```bash
python3 scripts/pkm_triage.py
```

### Akzeptanz

- [ ] `Hidden Files: 0`
- [ ] `RERUN_LM: 89`
- [ ] `FRESH_RUN: 98`
- [ ] `READY_TO_MIGRATE: 1`, `POSTPROCESS: 13`, `Orphans: 0`

Bei Abweichung > 2 Slugs in irgendeiner Kategorie: **STOP, Bericht.** Sonst weiter.

---

## Block 4 — Smoke-Test mit 1 Slug aus RERUN_LM

**Ziel:** Verifizieren, dass die Pipeline mit gepatchter Skip-Logik korrekt auf einen einzelnen Slug läuft, ohne andere Drafts zu touchen.

### Schritte

1. Korpus-Pfad des ersten Slugs aus Batch 1 extrahieren:
   ```bash
   BATCH=~/projects/aktiv/PKM_rebuild/data/02_pipeline_output/triage/rerun_batches/batch_001.md
   FIRST_CORPUS=$(grep -oE '`/[^`]+\.md`' "$BATCH" | head -1 | tr -d '`')
   echo "Test-Slug: $FIRST_CORPUS"
   ```

2. mtime der **anderen** Drafts (nicht des Test-Slugs) vor dem Lauf speichern:
   ```bash
   stat -f "%m %N" ~/projects/aktiv/PKM_rebuild/data/03_drafts/*.md > /tmp/before.txt
   ```

3. Vorhandene Draft-Files des Test-Slugs aus `03_drafts/` entfernen (sonst greift Skip):
   ```bash
   SLUG=$(basename "$FIRST_CORPUS" .md | tr '_' '-' | tr 'A-Z' 'a-z')
   # Behutsam — erst listen, dann mv
   ls ~/projects/aktiv/PKM_rebuild/data/03_drafts/CK_${SLUG}.* 2>/dev/null
   BACKUP=~/projects/aktiv/PKM_rebuild/backups/smoketest_$(date +%Y%m%d_%H%M)
   mkdir -p "$BACKUP"
   mv ~/projects/aktiv/PKM_rebuild/data/03_drafts/CK_${SLUG}.* "$BACKUP/" 2>/dev/null
   ```

4. Pipeline auf **genau diesem einen File** laufen lassen:
   ```bash
   caffeinate python -m pipeline run --phase 8 --file "$FIRST_CORPUS"
   ```
   (Falls die CLI keinen `--file`-Filter unterstützt: ad-hoc-Workaround dokumentieren — andere Korpus-Files mit `chmod -r` temporär unlesbar machen ist NICHT erlaubt. Stattdessen: CLI erweitern.)

5. Verifikation:
   ```bash
   # Test-Slug-Files neu erzeugt?
   ls -la ~/projects/aktiv/PKM_rebuild/data/03_drafts/CK_${SLUG}.*
   # Andere Drafts UNBERÜHRT?
   stat -f "%m %N" ~/projects/aktiv/PKM_rebuild/data/03_drafts/*.md > /tmp/after.txt
   diff /tmp/before.txt /tmp/after.txt
   ```

6. **STOP — User-Eval.** Bericht enthalten:
   - Welcher Slug wurde verarbeitet?
   - Wie viele andere Drafts wurden touched? (Erwartung: **0**)
   - Wie ist die Output-Qualität (body-Wörter, frontmatter-Felder, Konsistenz)?

### Akzeptanz

- [ ] `diff /tmp/before.txt /tmp/after.txt` ist leer (keine fremden Drafts touched)
- [ ] Neuer Draft hat valides Frontmatter + Body
- [ ] User hat Output-Qualität bestätigt → freigegeben für Block 5

**Bei Doppelarbeit-Symptom (andere Drafts touched): STOP, Skip-Logik weiter debuggen.**

---

## Block 5 — RERUN_LM Batches 2 bis 9

**Ziel:** Die verbliebenen 88 RERUN_LM-Slugs in 8 Batches durchlaufen, autonom, mit Block-Ende-Bericht.

### Pro Batch (Loop):

```bash
for n in 002 003 004 005 006 007 008 009; do
  BATCH=~/projects/aktiv/PKM_rebuild/data/02_pipeline_output/triage/rerun_batches/batch_${n}.md

  # Korpus-Pfade aus dem Batch-File extrahieren
  CORPUS_FILES=$(grep -oE '`/[^`]+\.md`' "$BATCH" | tr -d '`')

  # Bestehende Drafts dieser Slugs sichern + entfernen (sonst skip)
  BACKUP=~/projects/aktiv/PKM_rebuild/backups/rerun_${n}_$(date +%Y%m%d_%H%M)
  mkdir -p "$BACKUP"
  for f in $CORPUS_FILES; do
    SLUG=$(basename "$f" .md | iconv -f utf-8 -t ascii//translit | tr '_' '-' | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9-]//g')
    mv ~/projects/aktiv/PKM_rebuild/data/03_drafts/CK_${SLUG}.* "$BACKUP/" 2>/dev/null
  done

  # Pipeline auf diese Files
  caffeinate python -m pipeline run --phase 8 --files $CORPUS_FILES

  # Validierung nach jedem Batch
  python3 scripts/draft_inventory.py | tee /tmp/inventory_${n}.txt

  # Block-Ende-Bericht
  echo "=== Batch ${n} fertig ==="
  echo "Verarbeitete Slugs: $(echo "$CORPUS_FILES" | wc -w)"
  grep -E "(READY|INCONSISTENT|BROKEN|STUB)" /tmp/inventory_${n}.txt
done
```

### Stopp-Bedingungen während Block 5

- **Pipeline-Crash** (return code != 0) → STOP, Bericht
- **Memory-Pressure rot** in Activity Monitor → STOP, manuell
- **3 aufeinanderfolgende BROKEN-Outputs** → STOP, Prompt prüfen
- **Sonst:** durchlaufen lassen. Nach Batch 9: Block-Ende-Bericht, dann Block 6.

### Akzeptanz Block 5

- [ ] 88 Slugs (Batches 2–9) verarbeitet
- [ ] Jeder Batch hat ein eigenes Backup-Verzeichnis (Vorher-Zustand)
- [ ] Inventory nach jedem Batch dokumentiert

---

## Block 6 — Triage Re-Check nach RERUN_LM

```bash
python3 scripts/pkm_triage.py
```

### Akzeptanz

- [ ] `RERUN_LM` ist deutlich kleiner als 89 (idealerweise 0, realistisch < 10)
- [ ] `FRESH_RUN` ist immer noch 98 (unverändert)
- [ ] Keine neuen Hidden Files

Verbleibende RERUN_LM-Slugs (falls > 0): in `rerun_residual.txt` listen, **STOP, Bericht.** Sonst weiter zu Block 7.

---

## Block 7 — FRESH_RUN Batches 1 bis 10

**Ziel:** Die 98 Korpus-Slugs ohne Draft erstmalig durch Stage 3 (Pro-Doc-Veredelung oder Passthrough) + Stage 4 laufen lassen.

### Vorbedingung

- Routing-Logik aus Option B greift automatisch (Code ist auf main, siehe `0L`)
- Neue Drafts werden in `03_drafts/` erstellt

### Pro Batch (Loop):

```bash
for n in 001 002 003 004 005 006 007 008 009 010; do
  BATCH=~/projects/aktiv/PKM_rebuild/data/02_pipeline_output/triage/fresh_run_batches/batch_${n}.md
  CORPUS_FILES=$(grep -oE '`/[^`]+\.md`' "$BATCH" | tr -d '`')

  caffeinate python -m pipeline run --phase 8 --files $CORPUS_FILES

  python3 scripts/draft_inventory.py | tee /tmp/fresh_${n}.txt
  echo "=== Fresh Batch ${n} fertig ==="
done
```

### Stopp-Bedingungen

- Identisch zu Block 5
- Plus: **wenn mehr als 20 % der Outputs in einem Batch als STUB klassifiziert werden** (Body zu kurz) → STOP, Prompt/Modell debuggen

### Akzeptanz

- [ ] 98 neue Drafts erzeugt
- [ ] Triage zeigt `FRESH_RUN: 0`

---

## Block 8 — Final-Verifikation

```bash
python3 scripts/pkm_triage.py
```

### Akzeptanz

- [ ] `RERUN_LM: 0`
- [ ] `FRESH_RUN: 0`
- [ ] `Hidden Files: 0`
- [ ] `READY_TO_MIGRATE + POSTPROCESS ≥ 200` (alle Korpus-Slugs außer `_excluded` haben Drafts)
- [ ] `Orphan-Drafts: 0`

Bei Vollständigkeit: **STOP, Bericht an User.** Aufgabe abgeschlossen.

---

## 5. Was NICHT geschehen darf

- ❌ POSTPROCESS-Skript jetzt schreiben (kommt nach Block 8)
- ❌ Tags konsolidieren, category-Mapping, slug-Umlaut-Fix (alles Optimierung — danach)
- ❌ Vault-Aufbau (Phase 9 — danach)
- ❌ READY_TO_MIGRATE in den Vault übernehmen (danach)
- ❌ Pipeline-Code-Refactoring außerhalb Skip-Bug-Fix
- ❌ Mehrere Batches **parallel** starten — sequentiell, sonst Memory-Crash

---

## 6. Recovery bei Crash mitten im Block

```bash
# Wo ist der aktuelle Stand?
python3 scripts/pkm_triage.py
# Welcher Batch lief zuletzt? (mtime-Sortierung in 03_drafts)
ls -lt ~/projects/aktiv/PKM_rebuild/data/03_drafts/*.frontmatter.json | head -10
# Inventory neu erstellen, dann ab dem nächsten unverarbeiteten Batch fortsetzen
```

Kein Branch-Reset. Keine Daten-Wiederherstellung aus Backup, außer der vorherige Lauf hat sichtbar Drafts korrumpiert (Diff gegen Backup zeigt Body-Verlust).

---

## 7. Block-Ende-Bericht-Template

```
=== Block <N> abgeschlossen ===
Dauer:                <hh:mm>
Verarbeitete Slugs:   <Anzahl>
Erfolgreich:          <Anzahl>
BROKEN:               <Anzahl, Slugs auflisten>
STUB:                 <Anzahl, Slugs auflisten>
Drafts touched (unerwartet): <Anzahl, sollte 0 sein>
Memory-Pressure-Peaks: <max-Wert während Lauf>
Backup-Verzeichnis:   <Pfad>
Nächster Block:       <N+1>
```
