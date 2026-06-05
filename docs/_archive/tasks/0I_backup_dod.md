---
task_id: 0I
title: Backup-DoD-Aufholung — Time Machine + Zweites Medium
status: open
owner: app + user (Hardware-Entscheidungen)
priority: P1
depends_on: []
created: 2026-05-28
updated: 2026-05-28
estimated_effort: 2–4h
---

# Block 0.I — Backup-DoD-Aufholung

## Kontext

Aus `docs/07_backup_strategy.md` Sektion 8 (DoD-Block):
- **Time Machine:** Mount-Fehler Code 18 (Volume nicht eingehängt) — bekannt seit Block 0.C
- **Zweites Medium:** noch nicht entschieden (externe SSD, iCloud, Backblaze)

Vor Phase-9-Vault-Aufbau zwingend zu erledigen — Vault liegt außerhalb Git, ohne zweites Backup-Medium ist Risiko R5 (Vault-Datenverlust, siehe `docs/01_strategy.md` Sektion 7) ungemindert.

**Block-Charakteristik:** App-/User-Domäne, primär Hardware- und Diagnose-Arbeit. Claude Code unterstützt nur an klar definierten Stellen (Skript-Anpassungen). Block läuft parallel zu 0.F/0.G/0.H als Sidetask.

## Pflicht-Lektüre

1. `docs/07_backup_strategy.md` (komplett)
2. `scripts/snapshot.sh`
3. `scripts/restore.sh`
4. `docs/06b_tool_routing.md`

---

## Task 0I.1 — Time Machine reparieren

**Owner:** User (in Ghostty)

**Diagnose-Schritte:**

```bash
# 1. Externe Volumes auflisten
diskutil list

# 2. Time-Machine-Status
tmutil destinationinfo
tmutil latestbackup

# 3. Manuell mounten falls Volume erkannt aber nicht eingehängt
diskutil mount /dev/diskNsM   # konkrete Disk aus Schritt 1
```

**Wenn Mount weiterhin fehlschlägt:**
- Volume-Format prüfen: muss APFS oder HFS+ sein, nicht NTFS/exFAT
- Permissions prüfen: macOS-Festplattenvollzugriff für Backupd-Daemon
- Alternatives Volume probieren
- Notlösung: Time-Machine-Disk neu formatieren (mit Datenverlust der alten Snapshots)

**Wenn nicht reparierbar:** als bekannte Schwäche dokumentieren, Schwerpunkt verlagern auf Ebene 2 + 3 (externe SSD, Cloud).

**Akzeptanzkriterium:**
- `tmutil latestbackup` zeigt aktuelles Backup (≤24h alt)  
  ODER:
- Ergebnis dokumentiert als „TM nicht verfügbar, kompensiert durch X"

### 🛑 App-Checkpoint nach 0I.1

In App-Konversation einfügen:

```
Block: 0.I
Erledigt: 0I.1 (Time-Machine-Diagnose)
Status: <repariert / nicht reparierbar, Begründung>
Nächster Schritt: 0I.2 (zweites Medium wählen)
Frage an App: Optionen für zweites Medium diskutieren
```

---

## Task 0I.2 — Zweites Medium wählen (App)

**Owner:** App-Konversation + User

**Entscheidungs-Grundlage:** `docs/07_backup_strategy.md` Sektion 2.3

**Optionen:**

| Option | Aufwand | Kosten | Off-Site | Verschlüsselung |
|---|---|---|---|---|
| Externe SSD (`rsync` weekly) | mittel | einmalig 50–200 € | nein | APFS encrypted |
| iCloud Drive (verschlüsselter Ordner) | gering | 0–3 €/Monat | ja | ja (Apple-Side) |
| Backblaze B2 + `rclone` | hoch (Setup) | ~6 USD/TB/Monat | ja | client-side via `rclone crypt` |
| Privates GitHub-Repo (nur Vault) | gering | 0 € | ja | nein direkt — bricht „Vault nicht in Git"-Regel |

**Diskussion in App:**
- Datenvolumen-Schätzung (Vault wird voraussichtlich <100 MB)
- Reise-Verhalten (off-site-Wichtigkeit)
- Vertrauen in Anbieter
- Vorhandenes Hardware

**Entscheidungs-Output:** kurze Notiz in `docs/learnings/backup_decision_<datum>.md` mit gewählter Option + Begründung.

---

## Task 0I.3 — Initial-Backup auf zweitem Medium

**Owner:** je nach gewähltem Medium

**Wenn externe SSD:**

```bash
# Existierendes snapshot.sh nutzen, evtl. Skript-Anpassung
bash scripts/snapshot.sh

# Snapshot manuell auf SSD kopieren
SNAPSHOT_DIR=~/projects/aktiv/PKM_rebuild/backups/snapshot_$(date +%Y-%m-%d_%H%M)
cp -R "$SNAPSHOT_DIR" /Volumes/PKM-Backup/
```

**Wenn iCloud:**

- Verschlüsselten Ordner anlegen in iCloud Drive
- Snapshot dorthin kopieren (manuell oder via Skript)
- Sync verifizieren

**Wenn Backblaze:**

- `rclone config` für B2 + crypt-Layer
- `rclone copy snapshot_dir b2-crypt:pkm-backup/`

### ℹ STATUS für CC (falls Skript-Anpassung nötig)

Wenn Skript-Anpassung an `snapshot.sh` notwendig (z.B. für `--target` Parameter):

- **Owner:** CC nach User-Auftrag
- **Akzeptanz:** Skript erlaubt Target-Pfad als Argument, Default bleibt aktueller Backup-Pfad
- **Test:** `tests/test_snapshot_script.py` mit Mock-Filesystem

---

## Task 0I.4 — Recovery-Drill auf zweitem Medium

**Owner:** User (in Ghostty)

**Workflow analog `docs/07_backup_strategy.md` Sektion 4:**

1. Temp-Verzeichnis `~/tmp/restore-test-2nd-medium/`
2. Aus dem zweiten Medium wiederherstellen:
   ```bash
   bash scripts/restore.sh <snapshot_path_on_2nd_medium> ~/tmp/restore-test-2nd-medium/
   ```
3. Stichproben-Vergleich: `diff -r ~/projects/aktiv/PKM_rebuild/data/01_corpus_input/ ~/tmp/restore-test-2nd-medium/01_corpus_input/ | head -20`
4. Frontmatter-Validierung auf 5 zufälligen Vault-Files (wenn Vault existiert):
   ```bash
   python -m pipeline validate --files ~/tmp/restore-test-2nd-medium/04_vault/*.md
   ```
   (Hinweis: `validate`-CLI muss existieren — siehe Block 0.F Out-of-Scope)
5. Temp-Verzeichnis löschen

**Akzeptanzkriterium:**
- `diff -r` Exit-Code 0 (oder dokumentierte erwartete Differenzen)
- Wenn `validate`-CLI noch nicht existiert: Manuelle YAML-Frontmatter-Stichprobe statt automatisierter Validierung

### 🛑 App-Checkpoint nach 0I.4 — Block-Abschluss

```
Block: 0.I ABGESCHLOSSEN
Erledigt: 0I.1, 0I.2, 0I.3, 0I.4
Zweites Medium: <Option>
Recovery-Drill: erfolgreich
Time Machine: <Status>
Nächster Schritt: keiner in 0.I; weiter mit 8.A wenn 0.F + 0.G + 0.H ebenfalls done
Frage an App: keine
```

---

## Definition of Done für Block 0.I

- [ ] 0I.1: Time-Machine-Status geklärt (repariert ODER dokumentiert als „nicht verfügbar")
- [ ] 0I.2: Zweites Medium entschieden, in `backup_decision_<datum>.md` dokumentiert
- [ ] 0I.3: Initial-Snapshot auf zweitem Medium vorhanden
- [ ] 0I.4: Recovery-Drill erfolgreich auf zweitem Medium
- [ ] `docs/07_backup_strategy.md` Sektion 8 DoD-Checkliste abgehakt
- [ ] `status` im Frontmatter dieses Files auf `done`

## Out-of-Scope für 0.I

- Automatisierte Cron-/Launchd-Backups (kann später, ist kein Phase-9-Blocker)
- `validate`-CLI-Implementierung (separater Task)

---

## Änderungs-Log

- 2026-05-28 — Initial-Version
