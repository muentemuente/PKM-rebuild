---
title: PHASE_09 — vault-build
slug: phase-09-vault-build
type: phase-reflection
status: draft
phase_number: 09
phase_name: "Vault-Aufbau"
session_started: "2026-06-04 23:30"
session_ended: "2026-06-05 07:00"
duration_minutes: 90
created: "2026-06-05"
updated: "2026-06-05"
---

# Phase 9: Vault-Aufbau

Reflexionsdokument nach Abschluss der Phase. Pflicht laut `docs/01_strategy.md` Sektion 8 (Lernziele).

---

## 1. Was war geplant?

Task `docs/tasks/9.A_vault_build.md`: den Stub `build-vault` implementieren, testen, real ausführen.

- Erwartete Outputs: `pipeline/phase_9_vault_build.py` + CLI `build-vault`, Tests, 180 Vault-Files in `data/04_vault/<NN_Cluster>/<slug>.md`, `_index.md` pro genutztem Ordner.
- Akzeptanzkriterien (Spec/Task): valides Frontmatter, alle Wikilinks auflösbar, keine SHA-Dups, `15_Gedanken` leer, idempotent, Tests + ruff grün, `pipeline status` ohne Stub.
- Geschätzte Dauer: 4–6 h (Phasen-Budget). Tatsächlich ~1,5 h.

---

## 2. Was ist tatsächlich passiert?

### 2.1 Outputs

| Erwartet | Tatsächlich | Bemerkung |
|---|---|---|
| Builder-Modul | `pipeline/phase_9_vault_build.py` (412 Z.) | mypy-clean |
| CLI-Befehl | `build-vault` (`--dry-run`/`--force`) | war in Spec §4 vorgesehen |
| 180 Vault-Files | 180 geschrieben (`write_stats: written=180`) | 15 genutzte Ordner |
| `_index.md` | 15 (= genutzte Ordner) | regenerierbar, deterministisch |
| Tests | 12 neu (alle 371 grün) | synthetische Fixtures |

### 2.2 Akzeptanzkriterien — Status

- [x] 180 Files in korrekten `<NN_Cluster>/`-Ordnern
- [x] jedes File valides Frontmatter (Pydantic, 0 Fails über die 180)
- [x] alle Wikilinks auflösbar (0 dangling nach E4-Drop)
- [x] `_index.md` pro genutztem Cluster
- [x] keine SHA-256-Duplikate (0)
- [x] `15_Gedanken/` leer
- [x] Builder-Tests grün, ruff sauber
- [x] Builder idempotent (2. Lauf `--force` byte-identisch)
- [x] `pipeline status`: Phase 9 implementiert

### 2.3 Dauer

- Tatsächliche Arbeit: ~90 min
- Abweichung von Schätzung: deutlich unter Budget (Task war eng spezifiziert, Daten sauber aus Phase 8)

---

## 3. Probleme & Blocker

- **Mapping-Quelle missverständlich spezifiziert.** Task verlangte Import des `category→Ordner`-Mappings aus `scripts/apply_category_mapping.py`. Dieses Skript liefert aber nur Ist-`category`→canonical (bereits auf Drafts angewandt), **nicht** canonical→`NN_Ordner`.
  - Lösung: neue Konstante `CATEGORY_TO_FOLDER` (18 Einträge) im Pipeline-Modul, SSoT-Verweis auf `vault_standard` Appendix A. Kein Drift-Risiko, da Mapping vorher nirgends als Code existierte.
  - Zeit: ~20 min Recherche (Proposal-Datei, reale `category`-Werte, Doc-Tabelle gegenchecken).
- **Erwartungswert „9 dangling Links" war falsch.** Ground Truth: 8 (1 Target `gestaltgesetze-ui-ux` löst auf). Per Checkpoint §3 als Anomalie gemeldet, mit Ursache — User gab GO.
  - Lehre: „Reports ≠ Ground Truth" galt diesmal auch für den Task-Text selbst.
- **`_index.md` zunächst nicht idempotent** (Wall-Clock `generated:`-Feld). Entfernt → rein inhalts-abgeleitet.
- **`00_Meta` enthält 11 kuratierte Human-Files.** Risiko: Bulk-Delete/Overwrite. Design entsprechend defensiv: nur selbst-produzierte Files schreiben, archive-before-delete nur bei echter Kollision. Files blieben unangetastet (0 Archive).

### 3.1 Ungelöste Probleme (→ TODO)

- [ ] `00_Meta/_index.md` listet nur den 1 Build-Artikel (`taxonomie.md`), nicht die 11 kuratierten Standards. Spec Z419 sagt „alle Files im Cluster". 1-Ordner-Kosmetik, Entscheidung in Review-Gate 3.
- [ ] `unsortiert/` (8 Files) + 8 gedroppte Links brauchen manuelle Nachpflege.

---

## 4. Was wurde gelernt?

### 4.1 Technisch
- Slug-Eindeutigkeit muss **vault-weit** sein (Obsidian linkt per Dateiname), nicht pro Ordner — sonst Link-Ambiguität. Reale Kollision `aspect-ratio` (2× über verschiedene Ordner) → `aspect-ratio_2`.
- Idempotenz erfordert deterministische Serialisierung (YAML `sort_keys=False`, feste Feldreihenfolge aus dem Pydantic-Modell, `width` hoch gegen Zeilenumbruch-Drift, **keine** Zeitstempel im Content).

### 4.2 Workflow / Methodik
- Vor dem ersten Codezeichen die reale Datenlage zählen (Body-Naming, `related`-Targets, Kollisionen) zahlte sich aus — die meisten „Überraschungen" waren so vorab bekannt.
- Checkpoint-Disziplin (STOP bei Drop≠9/2) hat funktioniert: Abweichung gemeldet statt still durchgezogen.

### 4.3 Über Claude Code / Qwen / Tooling
- Kein Qwen in dieser Phase (reine Python-Arbeit). mypy-strict hat im Repo vorbestehende `schemas.py`-Fehler — neue Module trotzdem clean gehalten.

---

## 5. Was würde ich nächstes Mal anders machen?

- Task-Annahmen mit Zahlen (erwartete Drops, Mapping-Quelle) **vor** Implementierung gegen Ground Truth prüfen — diesmal gut gelaufen, als Standard verankern.
- Bei „bestehendes X wiederverwenden"-Anweisungen zuerst verifizieren, dass X das Gesuchte überhaupt enthält.

---

## 6. Token-Verbrauch (Claude Code)

| Wert | Schätzung |
|---|---|
| Anzahl Sessions | 1 |
| Geschätzte Input-Tokens | mittel (mehrere Doku-/Code-Reads) |
| Geschätzte Output-Tokens | mittel (1 Modul + Tests + Reports) |
| 5h-Limit erreicht? | nein |
| Weekly-Cap-Druck? | nein |

---

## 7. Memory-/Hardware-Beobachtungen

Nicht relevant — kein Qwen-/Embedding-Lauf in dieser Phase.

---

## 8. Folgende TODOs / offene Fragen

- [ ] Push `main` → `origin/main` (steht aus, braucht OK).
- [ ] Review-Gate 3: Mensch reviewt Vault inhaltlich (App-Chat).
- [ ] `00_Meta/_index`-Scope entscheiden (s. 3.1).
- [ ] `unsortiert/` + gedroppte Links nachpflegen.
- [ ] Phase 10 (Kontroll-Berichte) — nächste Phase.

---

## 9. Cross-Reference

| Bereich | Verweis |
|---|---|
| Task | `docs/tasks/9.A_vault_build.md` |
| Spec für diese Phase | `docs/02_pipeline_spec.md` §Phase 9 |
| Vorherige Reflexion | `docs/learnings/PHASE_08_synthesis.md` |
| Vault-Standard | `docs/03_vault_standard.md` (Appendix A — Category-Mapping) |
| Code | `pipeline/phase_9_vault_build.py`, Commit `e4e3c87` / Merge `493b2f0` |

---

## 10. Gesamtbewertung der Phase

**Lief gut wenn:** Datenlage vorab gezählt, Task-Annahmen gegen Ground Truth geprüft, defensives Schreiben (kuratierte Files geschützt) — sauber unter Budget, alle DoD grün.
**Lief schlecht wenn:** man der Task-Spezifikation (Mapping-Quelle, „9 Drops") blind gefolgt wäre.

---

## Änderungs-Log

- 2026-06-05 — Initial-Bearbeitung nach Phasen-Ende (Builder gemerged nach main)
