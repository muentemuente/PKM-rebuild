---
title: PKM-rebuild Phase 0 — Setup & Sicherung
slug: phase-00-setup
status: living-document
created: 2026-05-27
updated: 2026-05-27
phase: 0
phase_status: in_progress
last_block_completed: 0.D
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
| 0.D | LM Studio + Qwen Hardware-Test (Memory, Tokens/sek, Health-Check) | ✅ abgeschlossen (mit Pipeline-Spec-Korrekturbedarf) |
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

## 4. Block 0.D — Hardware-Test Ergebnisse

### 4.1 Setup-Realität

| Aspekt | Annahme (Persona / Spec) | Realität |
|---|---|---|
| Modell | Qwen 3.6 27B 4-bit | ✅ läuft |
| Modell-ID | `qwen-3.6-27b` | `qwen/qwen3.6-27b` (Präfix beachten) |
| Kontext-Fenster | mind. 128K | **~50K** (Hard Limit auf 32 GB RAM) |
| RAM-Verbrauch | 26–28 GB | 28 GB belegt, 0.08 GB Free, kein Swap |
| Memory-Pressure | grün/gelb erwartet | **grün** stabil |
| Inference-Speed | nicht spezifiziert | **7.45 t/s** stabil über Test-Lauf |
| Embedding-Modell | `paraphrase-multilingual-mpnet-base-v2` | aktuell `nomic-embed-text-v1.5` geladen — falsches Modell für DE |

### 4.2 Reasoning-Modell-Charakteristik (kritisch)

Qwen 3.6 27B ist ein **Reasoning-Modell** (denkt vor Antwort, ähnlich o1).

**Beobachtete Ratios:**
- Test 1 (kurze Tech-Frage): 948 Reasoning / 90 Content = **91 % Reasoning-Overhead**
- Test 3 (kurzer JSON): 311 Reasoning / 23 Content = **93 % Reasoning-Overhead**

**Konsequenz:** `max_tokens` muss in der Pipeline-Config mindestens **10× die geplante Content-Größe** sein. Bei `max_tokens: 300` (initialer Test) wurde die Antwort vor dem eigentlichen Content abgeschnitten (`finish_reason: "length"`).

### 4.3 Token-Budget-Hochrechnung (Phase 8 realistisch)

Mit 7.45 t/s und 10× Reasoning-Overhead:

| Stage | Content-Output (Spec) | + Reasoning | Zeit pro Cluster |
|---|---|---|---|
| 1 (Cluster-Analyse) | 2K–8K | 20K–80K | 3–12 min |
| 2 (Merge) | 1K–4K | 10K–40K | 2–6 min |
| 3 (Synthese) | 3K–10K | 30K–100K | 6–15 min |
| 4 (Frontmatter) | 1K–3K | 10K–30K | 2–4 min |
| **Pro Cluster (4 Stages)** | | | **13–37 min** |

Bei ~20 erwarteten Clustern: Phase 8 = **4–12 Stunden** Inferenz. Deckt sich grob mit Strategy-Schätzung (8–30h+), nur jetzt mit echten Daten.

### 4.4 Test-Auffälligkeit: `response_format: json_object`

Bei Test 2 (`response_format: {"type": "json_object"}` in der API-Payload) blieb der Request hängen ohne Antwort. Beim Wiederholen ohne dieses Feld lief der gleiche Inhalts-Test durch. **Ursache unklar.** Mögliche Hypothesen:
- LM-Studio-Bug mit `response_format` und Reasoning-Modell
- Schema-Validierung internal blockiert Reasoning-Stream
- Mein Prompt war zu komplex für 50K-Kontext + Reasoning-Tokens

**Konsequenz:** Pipeline darf nicht auf `response_format` setzen. Stattdessen JSON-Output im Prompt erzwingen + Python-seitig parsen + Retry-Loop (siehe Spec Sektion 9 „Failure-Handling").

### 4.5 Korrekturbedarf in Projekt-Doku

Folgende Stellen müssen vor Phase 8 angepasst werden:

| Datei | Stelle | Was ändern |
|---|---|---|
| `00_persona_muente.md` | Sektion 6 (Kontext-Setting) | „mind. 128K" → „~49152 (50K) auf dieser Hardware" |
| `02_pipeline_spec.md` | Sektion 3 (Config) | `context_window: 131072` → `49152`, `model: "qwen-3.6-27b"` → `"qwen/qwen3.6-27b"`, `json_mode: true` → `false` |
| `02_pipeline_spec.md` | Sektion 9 (Token-Budget) | Reasoning-Overhead 10× hinzufügen |
| `02_pipeline_spec.md` | Sektion 12 (Performance) | Stage-Zeiten aktualisieren auf 7.5 t/s + Reasoning |
| `04_qwen_prompts.md` | Sektion 9 (Token-Budget) | Output-Tokens × 10 für Reasoning |
| `04_qwen_prompts.md` | Sektion 7 Stage 1 (Constraints) | „100K Input" → „35K Input" (Output-Raum für Reasoning) |
| `04_qwen_prompts.md` | Generell | Hinweis auf Reasoning-Charakter ergänzen |

**Diese Korrekturen sind Block 0.E Pflichtaufgabe, vor Phase 1-Start.**

### 4.6 Strategisch nicht jetzt entschieden

- Embedding-Modell-Wechsel auf `paraphrase-multilingual-mpnet-base-v2` — geschieht in Pipeline Phase 6, nicht in LM Studio
- Kleineres Reasoning-freies Modell als Alternative (z.B. Llama-3.1-70B Nicht-Reasoning) — wird erst evaluiert, wenn Qwen Quality in Phase 8 nicht genügt

---

## 5. Lessons Learned

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

## 6. Offene Punkte (nicht für Phase 0, aber zu erledigen)

**Backup / Sicherheit (aus Block 0.C):**
- [ ] Time Machine Backup-Volume wieder mounten, `tmutil latestbackup` erfolgreich
- [ ] Externe SSD oder Cloud-Option für Ebene-3-Backup entscheiden + einrichten
- [ ] `pkm-import` Helper in `~/.zshrc.local` anlegen (Handover Sektion 12.2)
- [ ] Ghostty Festplattenvollzugriff sauber lösen (Quarantäne + mehrere Versionen prüfen)
- [ ] `snapshot.sh` um Skip-Logik für leere Verzeichnisse erweitern (kosmetisch)
- [ ] `preflight.sh` dokumentieren oder entfernen (steht im Repo, Zweck aus Handover nicht ersichtlich)

**Pipeline / Modell (aus Block 0.D):**
- [ ] Embedding-Modell-Wechsel: `nomic-embed-text-v1.5` → `paraphrase-multilingual-mpnet-base-v2` (geschieht in Pipeline Phase 6)
- [ ] `response_format: json_object`-Issue weiter untersuchen oder dauerhaft umgehen (siehe Sektion 4.4)
- [ ] Alternativ-Modell-Liste pflegen falls Qwen-Quality in Phase 8 enttäuscht (z.B. Llama-3.1-70B non-reasoning)

---

## 7. Reflexion — Arbeitsweise

Wird nach Block 0.E final gefüllt. Stichworte für Erinnerung:

- ADHS-Schutz funktioniert: kleinteilige Schritte (5.1 → 5.6) verhindern Drift
- Output-Vergleich gegen Erwartung war goldwert (Script-Versions-Falle erkannt)
- `present_files`-Workflow ist aktuell fragil — macOS-Security + Browser-Cache + alte Versionen in Downloads sind zusammen ein Stolperdraht
- Token-Verbrauch in dieser Session: nicht gemessen, gefühlt moderat (kein File-Upload-Massendump)

---

## 8. Nächste Aktionen

1. Block 0.E starten: Doku-Korrekturen aus Sektion 4.5 umsetzen (Persona + Pipeline-Spec + Qwen-Prompts)
2. Erstes Phase-Skeleton (`pipeline/phase_1_inventory.py` Stub mit Pydantic-Schema)
3. `PHASE_00_setup.md` finalisieren: `phase_status: done`, Reflexion in Sektion 7 ausfüllen

---

## Änderungs-Log

- 2026-05-27 — Initial-Version, Status nach Abschluss Block 0.C
- 2026-05-27 — Block 0.D ergänzt: Hardware-Test, Reasoning-Modell-Charakteristik, Korrekturbedarf in Pipeline-Doku
