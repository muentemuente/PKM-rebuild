# Anweisung an Claude Code — Phase 8 Resume nach Crash

**Lies dies einmal komplett. Dann arbeite ohne Rückfragen.**

---

## Was schief lief (kurz)

| | |
|---|---|
| Batch 001 | ✅ 10/10 (~116 min) |
| Batch 002 | ❌ 2/10 — `\| head -20` killte stdout-Pipe der Pipeline mid-flight (SIGPIPE) |
| Batch 003–009 | ⏸ nie gestartet, Loop war im Crash der Helper-Scripts gefangen |
| State | RERUN_LM=70, FRESH_RUN=106 (8 Batch-02-Reste landeten dort), Hidden=12 |

## Ursachen

1. zsh-eval bricht bei Leerzeichen in Dateinamen
2. Pipeline-stdout in `| head` / `| tee` → SIGPIPE killt Pipeline
3. Loop ohne State-File, kein Resume nach Crash
4. structlog nie initialisiert → kein File-Log → keine Recovery-Info
5. Backup-Pfad inkonsistent (Batch 002 ging nach `/tmp/`)

---

## Was du jetzt tust

### Vorbedingung

`scripts/phase8_runner.py` muss existieren (vom User bereitgestellt). Lies das **nicht** komplett — es ist self-contained und ersetzt deine bisherigen Loop-Scripts. Du musst nur die CLI-Oberfläche kennen:

```
python3 scripts/phase8_runner.py --source {rerun|fresh} [--from N] [--to N] [--single N] [--dry-run]
```

State-Files unter `data/02_pipeline_output/phase8_logs/state_batch_NNN.json`.
Logs unter `data/02_pipeline_output/phase8_logs/batch_NNN/<slug>.log`.

### Block A — Aufräumen (2 min)

```bash
DATA=~/projects/aktiv/PKM_rebuild/data
BAK=~/projects/aktiv/PKM_rebuild/backups/cleanup_$(date +%Y%m%d_%H%M)
mkdir -p "$BAK"

# 1. Hidden Meta-Files (12 Stück) sichern + weg
mv "$DATA/03_drafts/".CK_*.meta.json "$BAK/" 2>/dev/null
ls -A "$DATA/03_drafts/".CK_*.meta.json 2>/dev/null && echo "FEHLER" || echo "✓ hidden weg"

# 2. Veraltete Triage-Batches weg (008, 009 — stammen aus älterer Triage)
rm -f "$DATA/02_pipeline_output/triage/rerun_batches/batch_00"[89]".md"

# 3. Triage neu erstellen (mit korrektem State)
cd ~/projects/aktiv/PKM-rebuild
python3 scripts/pkm_triage.py
```

**Erwartung nach Block A:**
- Hidden Files: 0
- RERUN_LM zwischen 65 und 75
- FRESH_RUN zwischen 100 und 115
- Stop bei größerer Abweichung.

### Block B — Smoke-Test (1 Slug, ~10 min)

```bash
# Aus dem ersten Batch den 1. Slug nehmen
caffeinate python3 scripts/phase8_runner.py --source rerun --single 1 --dry-run | head -3
# Wenn parsing ok: 1. Slug live verarbeiten
# (Dry-Run zeigt: parse-fähig?)
```

Wenn Dry-Run zwei `DRY:`-Zeilen liefert: weiter.

```bash
caffeinate python3 scripts/phase8_runner.py --source rerun --single 1
```

**Akzeptanz:**
- `state_batch_001.json` enthält done- oder failed-Liste
- Andere Drafts (außer den Batch-Slugs) sind nicht touched: `stat -f "%m %N" $DATA/03_drafts/*.md > /tmp/before_b.txt` vor dem Lauf, danach diff
- Per-Slug-Log unter `phase8_logs/batch_001/<slug>.log`

Wenn alle 10 Slugs des Batches OK: weiter Block C. Sonst STOP.

### Block C — RERUN_LM komplett (autonom, ~10–14 h)

```bash
caffeinate python3 scripts/phase8_runner.py --source rerun > /tmp/phase8_run.log 2>&1 &
PID=$!
echo "PID=$PID"
```

Runner ist crash-tolerant: Einzel-Slug-Fail blockiert nicht den Rest. Bricht den Batch ab nach 5 consecutive failures (Stop-Bedingung).

**Was du NICHT tust während Block C:**
- ❌ Live-Log mit `tail -f` lesen (Token-Verschwendung)
- ❌ Per-Slug-Logs lesen, außer ein Batch ist abgebrochen
- ❌ Pipeline-Source anschauen
- ❌ Reports/Doku schreiben

**Was du tust:**
- 1× pro Stunde checken: `ps -p $PID` läuft noch?
- Wenn fertig: `tail -25 /tmp/phase8_run.log` → SUMMARY-Tabelle

### Block D — FRESH_RUN komplett (autonom, ~16–22 h)

Nur wenn Block C ≤ 5 unprocessed Slugs hinterlässt. Triage neu:

```bash
python3 scripts/pkm_triage.py | tail -15
caffeinate python3 scripts/phase8_runner.py --source fresh > /tmp/phase8_fresh.log 2>&1 &
```

### Block E — Final-Check

```bash
python3 scripts/pkm_triage.py
```

Akzeptanz:
- RERUN_LM ≤ 3
- FRESH_RUN ≤ 3
- Hidden Files: 0

Verbleibender Rest → Slug-Liste an User, manuell triagieren.

---

## Token-Effizienz: Regeln

| Regel | Statt | Stattdessen |
|---|---|---|
| 1 | Pipeline-Source lesen | Per-Slug-Log lesen (`phase8_logs/batch_NNN/<slug>.log`) |
| 2 | Alle Batch-Files lesen | State-File reicht (`state_batch_NNN.json`) |
| 3 | `cat <log>` voll | `tail -50` oder `grep ERROR` |
| 4 | Reports schreiben | Nur SUMMARY-Tabelle nach Block C/D/E |
| 5 | Bash-Helper neu schreiben | Runner nutzen, ist sufficient |
| 6 | Code-Walk durch Pipeline | Smoke-Test verifiziert ausreichend |
| 7 | Status alle 5 min checken | 1× pro Stunde |
| 8 | Output mit `\| head` filtern | Direkt in Datei: `> file 2>&1`, dann `head file` |
| 9 | jq über alle JSONLs | Filtern auf einzelnen Slug |
| 10 | Doku-Files anlegen | Erst NACH Block E |

---

## Stop-Bedingungen während Block C/D

Sofort STOP + User-Bericht:

- Memory-Pressure rot in Activity Monitor
- Pipeline-Crash mit Python-Traceback (kein Pipeline-Logic-Fail)
- ≥3 Batches abgebrochen (Aborted=yes in SUMMARY)
- `phase8_runner.py` selbst crasht (Exit 130 = SIGINT/SIGTERM = OK)

Nicht stoppen bei:

- Einzelner Slug failt (Runner handhabt das)
- Memory-Pressure gelb (normal bei Qwen 27B)
- Lange Laufzeit (1 Slug × 10 min ist normal)

---

## Recovery wenn Runner unterbrochen

Einfach nochmal starten:

```bash
caffeinate python3 scripts/phase8_runner.py --source rerun
```

State-Files springen automatisch zum nächsten unverarbeiteten Slug. Idempotent.

---

## Block-Ende-Berichte (einmal pro Block, knapp)

Format:

```
Block <X> fertig
  Total: <n>   Done: <n>   Failed: <n>   Aborted: <ja/nein>
  Dauer: <hh:mm>
  Verbleibend RERUN_LM/FRESH_RUN: <triage>
  Nächster Block: <Y>
```
