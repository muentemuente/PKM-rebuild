---
title: PKM-rebuild Backup-Strategie
slug: 07-backup-strategy
status: stable
created: 2026-05-25
updated: 2026-06-14
---

# Backup-Strategie

Das Projekt verteilt sich auf **drei Orte**, von denen zwei außerhalb von Git leben und ohne eigenes Backup-Konzept unwiederbringlich wären. Dieses Dokument definiert, was wie gesichert und wie wiederhergestellt wird.

> **Status (2026-06-14):** 3-Orte-Konzept aktiv. `scripts/snapshot.sh` + `scripts/restore.sh` (✅ pkm-pipeline-Recovery) und **neu** `scripts/backup_vault.sh` / `make backup-vault` (✅ expliziter Vault-Snapshot, schließt die #3-Lücke). Recovery-Drill bestanden (Archiv-Hash + Voll-Manifest, Stichproben-`diff`). **Offen (menschlich, kein Pipeline-Blocker):** Time-Machine-Verifikation und Off-Volume-Kopie auf 2. Medium (externe SSD / Cloud) — siehe §6.

---

## 1. Die drei Orte

| # | Ort | Pfad | Git? | Priorität | Reproduzierbar? |
|---|---|---|---|---|---|
| **#1** | Code & Doku | `~/projects/aktiv/PKM-rebuild/` | ✅ Git + GitHub | abgedeckt durch Git | — |
| **#2** | Pipeline-Daten | `~/projects/aktiv/pkm-pipeline/` (`input/ work/ drafts/ output/ review/ archive/`) | ❌ gitignored | mittel | teilweise (Qwen-Lauf wiederholbar, Reviews nicht) |
| **#3** | Produktiver Vault | `~/Zentrale/09_Brain-Vault/` (`$PKM_VAULT_ROOT`) | ❌ extern | **kritisch** | **nein** — Endprodukt mit manuellen Reviews |

Daten-Root #2 ist über `PKM_PIPELINE_ROOT` überschreibbar (`pipeline/_paths.py`), der Vault #3 über `PKM_VAULT_ROOT` bzw. `PKM_BRAIN_VAULT`.

---

## 2. Backup-Ebenen (Defense in Depth)

Drei unabhängige Ebenen — fällt eine, fängt die nächste auf.

### Ebene 1 — Time Machine (alles, Off-Volume, Pflicht)

| Aspekt | Wert |
|---|---|
| Tool | macOS Time Machine |
| Abdeckung | **alle drei Orte** (Home-Verzeichnis komplett) |
| Ziel | externe USB/Thunderbolt-SSD oder Time Capsule (Off-Volume) |
| Frequenz | stündlich (default) |
| Status-Check | `tmutil latestbackup` |
| Schwäche | bei physischem Verlust (Diebstahl/Feuer) lokal ebenfalls weg → Ebene 3 |

### Ebene 2 — explizite Snapshots (gezielt, vor riskanten Aktionen)

Punktuelle, verifizierbare tar+SHA-Snapshots — unabhängig von Time Machine und sofort restore-getestet.

| Ziel | Tool / Befehl | Sichert | Wann |
|---|---|---|---|
| **#3 Vault** | `make backup-vault` (`scripts/backup_vault.sh`) | `09_Brain-Vault/` komplett | vor riskanten Vault-Aktionen; regelmäßig (Endprodukt!) |
| **#2 Pipeline** | `make snapshot` (`scripts/snapshot.sh`) | `input/ work/ drafts/ output/ review/` | vor `--force`-Läufen / größeren Eingriffen |

Beide schreiben standardmäßig nach `pkm-pipeline/archive/backups/`:
- `vault_<ts>.tar.gz` + `.sha256` + `.manifest.sha256`
- `snapshot_<ts>/<label>.tar.gz` (+ Hashes/Manifeste je Ordner)

`make backup-vault TARGET=/Volumes/PKM-Backup` legt den Vault-Snapshot stattdessen auf ein **externes Medium** (Off-Volume-Kopie, deckt Ebene-3-Bedarf für #3 teilweise ab).

### Ebene 3 — Off-Site (optional, Worst Case)

Eine Off-Site-Kopie für Diebstahl/Feuer. Optionen: iCloud Drive (verschlüsselter Ordner, nativ), Backblaze B2 + `rclone` (günstig, unabhängig), oder `make backup-vault TARGET=…` auf ein wechselndes externes Medium. **Entscheidung offen** (siehe §6).

---

## 3. Was wofür zuständig ist

```
#1 Repo (PKM-rebuild)        → Git + GitHub (push)                     [vorhanden]
#2 pkm-pipeline (Daten)      → make snapshot  + Time Machine            [✅]
#3 09_Brain-Vault (Vault)    → make backup-vault + Time Machine         [✅ Lücke geschlossen]
```

Die früher offene **#3-Lücke** (kein Script sicherte den produktiven Vault; nur `publish-assets` schrieb hinein) ist mit `make backup-vault` **geschlossen**: expliziter, restore-getesteter tar+SHA-Snapshot des Endprodukts.

---

## 4. `archive-before-delete` (#2)

Inhalte unter `pkm-pipeline/` werden vor dem Entfernen nach `archive/processed_<ts>/` bzw. `archive/backups/` **verschoben**, nie hart gelöscht. `archive/` selbst wird von `snapshot.sh` ausgespart (= Backup-Ziel, enthält frühere Snapshots). OS-Junk außerhalb der Daten (Repo-`.DS_Store`) ist ausgenommen.

Etablierte Präfixe in `pkm-pipeline/archive/`:

| Präfix | Zweck | Erzeuger |
|---|---|---|
| `processed_<ts>/` | verarbeitete Inputs (+ `_assets/`) nach erfolgreichem Build | `orchestrator._archive_inputs` |
| `backups/snapshot_<ts>/` | Pipeline-Daten-Snapshot (#2) | `scripts/snapshot.sh` |
| `backups/vault_<ts>.tar.gz` | Vault-Snapshot (#3) | `scripts/backup_vault.sh` |
| `backups/*.tar.gz`, `smoke_reset_<ts>/` u.a. | ältere/situative Snapshots | manuell / Cleanup |

---

## 5. Wiederherstellungs-Drills (Pflicht)

Backup ohne getesteten Restore ist kein Backup.

**#2 Pipeline-Daten:**
```bash
make snapshot                                  # erzeugt snapshot_<ts>/
make restore SNAPSHOT=snapshot_<ts>            # entpackt nach ~/tmp/, verifiziert SHA
diff -r ~/projects/aktiv/pkm-pipeline/output ~/tmp/pkm-restore-test_*/output
```
`restore.sh` prüft Archiv-Hash **und** jedes Datei-Hash gegen das Manifest und ist generisch (verarbeitet jedes `*.tar.gz` im Snapshot).

**#3 Vault** (Drill-Prozedur, bestanden am 2026-06-14):
```bash
make backup-vault
tar -xzf pkm-pipeline/archive/backups/vault_<ts>.tar.gz -C "$HOME/tmp/restore-test"
# Archiv-Hash gegen .sha256, Stichproben-diff gegen den Live-Vault,
# Voll-Verifikation gegen .manifest.sha256 → dann tmp löschen.
```

---

## 6. Status-Check & offene Punkte

```bash
tmutil latestbackup                                          # Time Machine
ls -lt ~/projects/aktiv/pkm-pipeline/archive/backups/ | head # letzte Snapshots
du -sh ~/Zentrale/09_Brain-Vault/                            # Vault-Größe (Sanity)
```

**Offen (menschlich):**
- [ ] Time-Machine-Verifikation (früherer Mount-Fehler Code 18)
- [ ] Off-Volume-Kopie des Vaults auf 2. Medium etablieren (`make backup-vault TARGET=…` oder Cloud), jüngster Snapshot < 7 Tage
- [x] Recovery-Drill #2 (snapshot/restore) erfolgreich
- [x] Recovery-Drill #3 (Vault) erfolgreich
- [x] #3-Backup-Lücke geschlossen (`make backup-vault`)

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
- 2026-06-05 — Status-Vermerk (snapshot/restore + Drill erledigt; Time Machine + 2. Medium offen)
- 2026-06-14 — Voll-Rewrite auf 3-Orte-Konzept; `make backup-vault` / `scripts/backup_vault.sh` ergänzt (#3-Lücke geschlossen); Pfade auf `pkm-pipeline/`-Layout; veraltete Script-Skelette entfernt (Doku spiegelt jetzt die realen Skripte)
