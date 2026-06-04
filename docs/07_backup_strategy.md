---
title: PKM-rebuild Backup-Strategie
slug: 07-backup-strategy
status: stable
created: 2026-05-25
updated: 2026-06-04
---

# Backup-Strategie

Vault und Korpus liegen außerhalb des Git-Repos (Entscheidung B6). Ohne ein eigenes Backup-Konzept gäbe es keine Wiederherstellungs-Option bei Datenverlust. Dieses Dokument definiert das Konzept.

---

## 1. Geltungsbereich

Geschützt werden:

| Daten | Pfad | Priorität |
|---|---|---|
| Korpus-Original | `~/projects/aktiv/PKM_rebuild/data/01_corpus_input/` | **kritisch** (read-only, nicht reproduzierbar) |
| Vault | `~/projects/aktiv/PKM_rebuild/data/04_vault/` | **kritisch** (manuelle Reviews verloren) |
| Pipeline-Outputs | `~/projects/aktiv/PKM_rebuild/data/02_pipeline_output/` | mittel (reproduzierbar, aber teuer) |
| Drafts | `~/projects/aktiv/PKM_rebuild/data/03_drafts/` | mittel (Qwen-Lauf wäre wiederholbar) |
| Code & Doku | `~/projects/aktiv/PKM-rebuild/` (Git-Repo) | abgedeckt durch Git + GitHub |

---

## 2. Backup-Ebenen (Defense in Depth)

Mehrere unabhängige Ebenen — wenn eine fällt, fängt die nächste auf.

### 2.1 Ebene 1 — Time Machine (Pflicht, immer aktiv)

| Aspekt | Wert |
|---|---|
| Tool | macOS Time Machine |
| Ziel | externe USB/Thunderbolt-SSD oder Time Capsule |
| Frequenz | stündlich (default) |
| Aufbewahrung | letzte 24h stündlich, letzte Woche täglich, danach wöchentlich |
| Status-Check | `tmutil latestbackup` |

**Setup-Voraussetzung:** Time Machine ist aktiviert und das Backup-Volume ist mindestens 2× so groß wie das Source-Volume.

**Schwäche:** Lokal — bei physischem Verlust (Diebstahl, Wasser, Feuer) ist das Backup ebenfalls weg.

---

### 2.2 Ebene 2 — Externe SSD (manuell, wöchentlich)

| Aspekt | Wert |
|---|---|
| Tool | `rsync` über Script |
| Ziel | separate externe SSD (nicht die Time-Machine-SSD) |
| Frequenz | wöchentlich, manuell ausgelöst |
| Inhalt | nur kritische Daten (Korpus + Vault) |
| Verschlüsselung | empfohlen (APFS encrypted) |

**Script-Skelett** in `scripts/backup_vault.sh` (in Phase 0 erstellen):
```bash
#!/usr/bin/env bash
set -euo pipefail

SOURCE="${HOME}/projects/aktiv/PKM_rebuild/data"
TARGET="/Volumes/PKM-Backup/PKM_rebuild_$(date +%Y-%m-%d)"

rsync -avh --delete \
  --exclude="02_pipeline_output/embeddings.parquet" \
  --exclude="02_pipeline_output/pipeline.log" \
  "${SOURCE}/" "${TARGET}/"

echo "✓ Backup nach ${TARGET}"
```

**Schwäche:** Manuell — wird vergessen. Kompensiert durch Ebene 3.

---

### 2.3 Ebene 3 — Cloud-Snapshot (zusätzlich, optional)

Eine Off-Site-Kopie für den Worst Case.

| Option | Pro | Contra |
|---|---|---|
| iCloud Drive (verschlüsselter Ordner) | nativ in macOS, automatisch | proprietär, Apple-Lock-in |
| Backblaze B2 + `rclone` | günstig (~6 USD/TB/Monat), unabhängig | manuelles Setup |
| Verschlüsselte tar.gz auf E-Mail (z.B. Proton) | extrem einfach für kleine Datenmenge | nur für Korpus, nicht für Vault |
| Privates GitHub-Repo (nur Vault, NICHT Korpus) | bekannte Infrastruktur, Versionierung gratis | bricht die „Vault nicht in Git"-Regel |

**Empfehlung:** iCloud Drive mit verschlüsseltem Ordner für ersten Aufschlag (geringster Setup-Aufwand), später Backblaze B2 wenn Datenmenge wächst.

**Entscheidung wird in Phase 0 getroffen.**

---

## 3. Pre-Pipeline-Snapshot (Phase 0)

Vor jedem Pipeline-Erstlauf (und vor jedem `--force`-Lauf, der Outputs überschreibt) wird ein expliziter Snapshot erzeugt.

### Script-Skelett `scripts/snapshot.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
SNAPSHOT_DIR="${DATA_ROOT}/backups/snapshot_${TIMESTAMP}"

mkdir -p "${SNAPSHOT_DIR}"

# Korpus immer mitnehmen (sollte sich nie ändern, aber sicher ist sicher)
tar -czf "${SNAPSHOT_DIR}/corpus_input.tar.gz" -C "${DATA_ROOT}/data" "01_corpus_input"

# Vault wenn vorhanden
if [[ -d "${DATA_ROOT}/data/04_vault" ]]; then
  tar -czf "${SNAPSHOT_DIR}/vault.tar.gz" -C "${DATA_ROOT}/data" "04_vault"
fi

# Pipeline-State falls vorhanden
if [[ -f "${DATA_ROOT}/data/02_pipeline_output/pipeline_state.json" ]]; then
  cp "${DATA_ROOT}/data/02_pipeline_output/pipeline_state.json" "${SNAPSHOT_DIR}/"
fi

echo "✓ Snapshot nach ${SNAPSHOT_DIR}"
ls -lah "${SNAPSHOT_DIR}"
```

**Aufruf:**
```bash
bash scripts/snapshot.sh
```

**Aufbewahrung:** lokal in `~/projects/aktiv/PKM_rebuild/backups/`. Nach 30 Tagen alte Snapshots manuell aufräumen.

### Backup-Verzeichnis-Konventionen (real in Gebrauch)

In `~/projects/aktiv/PKM_rebuild/backups/` haben sich folgende Präfixe etabliert:

| Präfix | Zweck | Erzeuger |
|---|---|---|
| `snapshot_<ts>/` | Pre-Pipeline-/`--force`-Snapshot (Korpus + Vault) | `scripts/snapshot.sh` |
| `pre_phase9_<ts>/` | gezielter Draft-Snapshot vor Phase 9 | manuell / Hardening-Runs |
| `archive_<ts>/` | **archive-before-delete** — regenerierbare Outputs (Triage-Batches, phase8_logs, `.DS_Store`) werden hierher verschoben, nie hart gelöscht | Cleanup-Runs |
| `phase8_<batch>_<ts>/` | vom Runner verdrängte Drafts vor Re-Synthese | `phase8_runner.py` |
| `cleanup_<ts>/`, `hidden_<ts>/` | ältere manuelle Aufräum-Snapshots | manuell |

**Regel `archive-before-delete`:** Inhalte unter `data/` werden vor dem Entfernen nach `backups/archive_<datum>/` verschoben, niemals hart gelöscht. OS-Junk außerhalb `data/` (z.B. Repo-`.DS_Store`) ist davon ausgenommen.

---

## 4. Wiederherstellungs-Drill (Pflicht in Phase 0)

Backup ohne getesteten Restore ist kein Backup.

**Test-Prozedur** (einmalig in Phase 0, danach jährlich):

1. Auf einem temporären Pfad `${HOME}/tmp/restore-test/` aus dem Backup wiederherstellen
2. Stichproben-Vergleich (10 zufällige Files via `diff`)
3. Frontmatter-Validierung auf den wiederhergestellten Files (Pydantic)
4. Temporäres Verzeichnis löschen

**Wenn fehlschlägt:** Backup-Konfiguration überprüfen, bevor produktive Arbeit fortgesetzt wird.

---

## 5. Backup-Status-Check

Vor jedem Phase-Start (besonders vor Phase 8 und 9, die viel Output erzeugen):

```bash
# Time Machine — letzter Backup
tmutil latestbackup

# Externe SSD — letzter manueller Backup
ls -lt ~/projects/aktiv/PKM_rebuild/backups/ | head -5

# Vault-Größe als Sanity-Check
du -sh ~/projects/aktiv/PKM_rebuild/data/04_vault/ 2>/dev/null || echo "noch kein Vault"
```

---

## 6. Recovery-Szenarien

### 6.1 Versehentliches Löschen einer einzelnen Datei

1. Time Machine öffnen
2. Im entsprechenden Ordner navigieren
3. Datei wiederherstellen
4. Aufwand: Minuten

### 6.2 Vault korrumpiert oder gelöscht

1. Letzten Snapshot aus `~/projects/aktiv/PKM_rebuild/backups/` identifizieren
2. `tar -xzf snapshot_<datum>/vault.tar.gz -C ~/projects/aktiv/PKM_rebuild/data/`
3. Frontmatter-Validierung laufen lassen
4. Aufwand: 10–30 Minuten

### 6.3 Gesamtes Daten-Verzeichnis verloren (z.B. Festplatten-Crash)

1. Hardware-Problem lösen (neuer Mac oder neue SSD)
2. Time Machine: kompletten Restore
3. Falls Time Machine ebenfalls weg: Ebene 2 (externe SSD)
4. Falls auch weg: Ebene 3 (Cloud)
5. Aufwand: Stunden (Time Machine), evtl. Tage (Cloud-Download)

### 6.4 Korpus-Original verändert (sollte unmöglich sein wegen Read-Only)

Sanity-Check: SHA-256 des Korpus mit dem im Snapshot vergleichen:
```bash
# Beim Snapshot wurde gespeichert:
cat ~/projects/aktiv/PKM_rebuild/backups/snapshot_<datum>/corpus_input.sha256

# Aktueller Hash:
find ~/projects/aktiv/PKM_rebuild/data/01_corpus_input -type f -name "*.md" \
  -exec sha256sum {} \; | sort | sha256sum
```

Bei Abweichung: aus Snapshot wiederherstellen.

---

## 7. Aktualisierungs-Routine

Dieses Dokument wird gepflegt:
- bei Änderung der Backup-Tools (z.B. Wechsel auf andere Cloud)
- nach Recovery-Drill (Erkenntnisse einarbeiten)
- bei Speicher-Knappheit (Aufbewahrungs-Strategie anpassen)

---

## 8. Akzeptanzkriterien (für DoD)

Aus `docs/01_strategy.md` Sektion 3 — Backup-Block:

- [ ] Time Machine aktiv und für Korpus + Vault gesnapshottet (verifiziert mit `tmutil latestbackup`)
- [ ] Vault-Snapshot auf zweitem Medium (externe SSD oder Cloud, jüngster Snapshot < 7 Tage alt)
- [ ] Korpus-Originale unverändert gegenüber Pre-Pipeline-Snapshot (SHA-256 Vergleich)
- [ ] Recovery-Drill erfolgreich durchgeführt (einmalig in Phase 0)

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
