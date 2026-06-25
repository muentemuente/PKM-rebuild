---
title: WP4 · T1c — Live-Export vollzogen
slug: wp4-t1c-export
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T1c-export-und-T2a-nlp.md
gate: 4-2a
---

# WP4 · T1c — erster Live-Vault-Export

Owner-Entscheidung umgesetzt: die 5 Projekt-Artefakte liegen in
`00_Meta/_projektdoku/` (nicht in der 00_Meta-Wurzel). Export vom Owner manuell
ausgeführt (`!`-Lauf), da der Harness Schreibzugriff auf `BRAIN_VAULT` per
Deny-Rule sperrt.

- Snapshot (Rollback): `…/archive/backups/wp4_T1_master_20260624_231006/raw/`
- archive-before (Export): `…/archive/backups/wp4_t1c_export_20260624_234500/`

## Live-Stand (verifiziert, read-only)

| Prüfung | Ergebnis |
|---|---|
| 5 Files in `00_Meta/_projektdoku/` | ✅ vorhanden |
| alte Pfade (14_…, 10_…, 01_…) entfernt | ✅ alle 5 Moves vollzogen |
| `00_Meta/_projektdoku/_index.md` | nicht erzeugt (Vault-Standard §4) |
| Live == work-Stage (207 md SHA-256) | ✅ identisch |
| Body-Byte-Test 7 vs Snapshot-raw | ✅ PASS (0 Byte-Änderung) |
| Schutzbereich `_attic/` vs Snapshot | 0 Diffs |
| `15_Gedanken/` | existiert nicht (nicht erzeugt) |
| Synthese-Filter live | gescannt **166** / ausgeschlossen **26**; #1–5 raus (`Ordner 00_Meta`), #6/#7 drin |
| neue broken Wikilinks durch Export | **0** (broken-Target-Set live == snapshot = 167; Baseline = illustrative Tutorial-Links, projektfremd) |
| ruff `pipeline/` | green; keine Code-Änderung |

DoD Teil A erfüllt: Live-Vault trägt alle 7 Korrekturen, 5 in `00_Meta/_projektdoku/`,
0 Body-Änderung, Synthese-Ausschluss live wirksam.
