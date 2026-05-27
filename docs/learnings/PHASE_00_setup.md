---
title: PKM-rebuild Phase 0 — Setup & Sicherung
slug: phase-00-setup
status: living-document
created: 2026-05-27
updated: 2026-05-27
phase: 0
phase_status: in_progress
---

# Phase 0 — Setup & Sicherung

Reflexion zur Setup-Phase. Wird inkrementell ergänzt: jetzt nach Block 0.C, finalisiert nach 0.E.

---

## 1. Phasen-Übersicht

| Block | Inhalt | Status |
|---|---|---|
| 0.A | Foundation: Git, pyproject.toml, mise, pytest, ruff, mypy | ✅ abgeschlossen |
| 0.B | GitHub: Repo public, LICENSE, Topics | ✅ abgeschlossen |
| 0.C | Backup-Setup: snapshot.sh, restore.sh, Recovery-Drill | ✅ abgeschlossen (mit offenen DoD-Punkten) |
| 0.D | LM Studio + Qwen Hardware-Test (Memory, Tokens/sek, Health-Check) | 🔜 anstehend |
| 0.E | Phase-Skeleton (`pipeline/phase_1_inventory.py` Stub) + Reflexion finalisieren | 🔜 anstehend |

---

## 2. DoD-Backup-Block — Status

Bezug: `docs/01_strategy.md` Sektion 3, `docs/07_backup_strategy.md` Sektion 8.

| Kriterium | Status | Notiz |
|---|---|---|
| Time Machine aktiv für Korpus + Vault | ❌ offen | Destination konfiguriert ("TimeMaschine M5"), aber Mount-Fehler (Code 18). Volume nicht eingehängt. |
| Vault-Snapshot auf zweitem Medium (< 7 Tage alt) | ❌ offen | Kein externes Medium entschieden (Optionen: externe SSD, iCloud, Backblaze) |
| Korpus-Originale unverändert (SHA-256-Vergleich) | ✅ Mechanismus bereit | Manifest-Schema implementiert. Anwendung nach Korpus-Import. |
| Recovery-Drill erfolgreich | ✅ erledigt | Snapshot + Restore + 3-Datei-Verifikation + `diff -r` grün, Exit-Code 0 |

**Konsequenz für Phase 0:** Block 0.C technisch abgeschlossen. DoD-Block bleibt **nicht abgehakt** in `01_strategy.md`, bis TM + zweites Medium gelöst sind. Kein Blocker für Phase 1, aber Pflicht vor Phase 8/9 (Qwen-Synthese + Vault-Aufbau erzeugen kritische, nicht-reproduzierbare Daten).

---

## 3. Tech-Stand (Snapshot Block 0.C)

| Bereich | Wert |
|---|---|
| Letzter Commit | `6d62fa5` — `feat: replace snapshot/restore scripts with manifest-verified version` |
| Branch | `main`, synchron mit `origin/main` |
| Scripts im Repo | `scripts/preflight.sh`, `scripts/snapshot.sh`, `scripts/restore.sh` |
| Korpus-Quelle (lokalisiert, nicht kopiert) | `/Users/muente/Zentrale/09_Brain_Vault_original/`, 203 `.md`-Files, flaches Layout |
| Daten-Verzeichnis | `~/projects/aktiv/PKM_rebuild/data/{01..04}/` angelegt, leer |
| Snapshot-Verzeichnis | `~/projects/aktiv/PKM_rebuild/backups/` mit Drill-Snapshot vom 2026-05-27_1114 |

---

## 4. Lessons Learned

### 4.1 Script-Versionierungs-Falle

**Beobachtung:** Beim Import per `cp ~/Downloads/snapshot.sh scripts/` lag eine ältere Version aus einem früheren Block-0.C-Versuch in `~/Downloads/`. Erster Recovery-Drill lief mit altem Script (keine Manifests, anderer Output-Stil). Wurde erst durch Output-Vergleich erkannt.

**Konsequenz:**
- Vor jedem Datei-Import die heruntergeladene Quelle verifizieren (`shasum -a 256` gegen erwarteten Hash)
- Bei Verdacht: `head -5` auf Header-Identität prüfen
- `present_files`-Downloads von Claude haben **kein** intrinsisches Datum-Suffix — Browser hängt `(1)`, `(2)` an, falls Datei schon existierte. Ohne Suffix wird die alte Version überschrieben — gut. Aber: wenn beim Klick auf Download die alte Version aus dem Cache erneut kommt (Browser-Caching), bleibt sie alt.

**Verbesserung künftig:** Helper-Funktion `pkm-import` (siehe Handover 12.2) ergänzen um Hash-Check oder mindestens `head -5`-Echo der importierten Datei.

### 4.2 macOS-Quarantäne + Festplattenvollzugriff

**Beobachtung:** Trotz Ghostty mit Festplattenvollzugriff schlugen `cp ~/Downloads/*.sh` und `xattr -d com.apple.quarantine` mit `Operation not permitted` fehl.

**Diagnose offen:**
- Möglichkeit 1: Ghostty wurde nicht vollständig neu gestartet, Berechtigung nicht greifend
- Möglichkeit 2: Mehrere Ghostty.app-Installationen, falsche autorisiert
- Möglichkeit 3: Quarantäne-Flag spezifisch geschützt (TCC-Subsystem über App-Sandbox)

**Workaround:** Finder-Drag-and-Drop (`⌘+Option`-Ziehen für Verschieben + Überschreiben). Funktioniert, weil Finder vom TCC anders behandelt wird als CLI-Tools.

**TODO:** vor Phase 1 sauber lösen — `mdfind` für Ghostty-Versions-Check, einmaliger Full-Restart, ggf. Berechtigung neu setzen. Sonst wiederholt sich das Problem bei jedem `present_files`.

### 4.3 Leere Manifests (Edge-Case)

**Beobachtung:** `vault.manifest.sha256` und `drafts.manifest.sha256` sind 0 Byte groß, weil die Verzeichnisse zwar existieren, aber leer sind. `snapshot.sh` archiviert sie trotzdem als `.tar.gz` (jeweils 348 B Overhead). `restore.sh` meldet `✓ 0 Dateien verifiziert` — funktional korrekt, aber redundant.

**Konsequenz:** In Phase 0 irrelevant (kostet 700 B). Bei produktivem Lauf: in `make_archive` zusätzlich `find ... -mindepth 1 | head -1` prüfen und früh `return 0`. **Notiert für spätere Verbesserung**, nicht jetzt.

### 4.4 Time-Machine-Volume nicht greifbar

**Beobachtung:** `tmutil destinationinfo` zeigt konfigurierte Destination, aber `tmutil latestbackup` schlägt mit Mount-Fehler fehl. Volume nicht angeschlossen oder anderer Mount-Zustand.

**Konsequenz:** Backup-Ebene 1 (Time Machine) nicht verifizierbar. Block 0.C trotzdem abgeschlossen, weil Snapshot-Mechanik (Ebene 2) unabhängig funktioniert. **TM-Setup ist offener DoD-Punkt**, nicht Phase-0-Blocker.

---

## 5. Offene Punkte (nicht für Phase 0, aber zu erledigen)

- [ ] Time Machine Backup-Volume wieder mounten, `tmutil latestbackup` erfolgreich
- [ ] Externe SSD oder Cloud-Option für Ebene-3-Backup entscheiden + einrichten
- [ ] `pkm-import` Helper in `~/.zshrc.local` anlegen (Handover Sektion 12.2)
- [ ] Ghostty Festplattenvollzugriff sauber lösen (Quarantäne + mehrere Versionen prüfen)
- [ ] `snapshot.sh` um Skip-Logik für leere Verzeichnisse erweitern (kosmetisch)
- [ ] `preflight.sh` dokumentieren oder entfernen (steht im Repo, Zweck aus Handover nicht ersichtlich)

---

## 6. Reflexion — Arbeitsweise

Wird nach Block 0.E final gefüllt. Stichworte für Erinnerung:

- ADHS-Schutz funktioniert: kleinteilige Schritte (5.1 → 5.6) verhindern Drift
- Output-Vergleich gegen Erwartung war goldwert (Script-Versions-Falle erkannt)
- `present_files`-Workflow ist aktuell fragil — macOS-Security + Browser-Cache + alte Versionen in Downloads sind zusammen ein Stolperdraht
- Token-Verbrauch in dieser Session: nicht gemessen, gefühlt moderat (kein File-Upload-Massendump)

---

## 7. Nächste Aktionen

1. Block 0.D starten: LM Studio öffnen, Qwen 3.6 27B 4-bit laden, 128K-Kontext setzen, Memory-Pressure beobachten, Health-Check via `curl http://localhost:1234/v1/models`
2. Erkenntnisse Block 0.D in Sektion 4 ergänzen
3. Block 0.E: erstes Phase-Skeleton (`pipeline/phase_1_inventory.py` Stub), `PHASE_00` finalisieren

---

## Änderungs-Log

- 2026-05-27 — Initial-Version, Status nach Abschluss Block 0.C
