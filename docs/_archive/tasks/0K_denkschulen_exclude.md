---
title: Block 0.K — denkschulen aus Mainstream-Pipeline exkludieren
slug: 0k-denkschulen-exclude
status: done
created: 2026-05-29
updated: 2026-05-29
---

# Block 0.K — denkschulen exkludieren

## Problem

Gate-1-Re-Run (Block 0.J) ergab 4/6 Kriterien erfüllt. Die zwei Fehlschläge haben dieselbe Ursache:

- `denkschulen_ueberblick_und_einfuehrung.md` (15.770 Wörter) dominiert `C_cluster-0000` mit 171 Docs
- Similarity-Threshold 0.65 zieht das gesamte Book-Content in einen Mega-Cluster
- Konsequenz: Cluster-Karte unbrauchbar für Phase 8 — alle 171 Docs landen in einem Batch

Das File ist ein Lehr-Überblick über Denkschulen und konzeptionell kein integraler Teil des persönlichen Wissenskorpus. Exklusion ist die sauberste Lösung.

**Nicht betroffen:**
- `denkschulen_der_gegenwart.md` (583 Wörter) — bleibt im Korpus
- `denkschulen_und_konzepte.md` (1.419 Wörter) — bleibt im Korpus

## Scope

| Schritt | Beschreibung |
|---|---|
| 0K.1 | Aufgabe dokumentieren (`docs/tasks/0K_denkschulen_exclude.md`) |
| 0K.2 | File nach `_excluded/` verschieben (Phase 1 skippt `_*`-Prefix) |
| 0K.3 | Re-Run `--from-phase 1 --force` |
| 0K.4 | Reports generieren |
| 0K.5 | Verifikation: alle 6 Gate-1-Kriterien prüfen |
| 0K.6 | Commit |
| 0K.7 | PROJECT_STATUS + GATE_1_review aktualisieren |

## Exklusions-Mechanismus

Phase 1 (`phase_1_inventory.py`) überspringt bereits Pfade, die auf `_*`-Prefix matchen (konfiguriert via `exclude_patterns`). Verschieben nach `data/01_corpus_input/_excluded/` reicht — kein Code-Eingriff notwendig.

## Erwartete Ergebnisse nach Re-Run

| Kriterium | Ziel | Nach 0.J | Erwartung 0.K |
|---|---|---|---|
| Unsortierte Segmente | < 40 % | 19.0 % ✅ | ≤ 19 % (leicht besser) |
| 1.0-Similarity-Kanten | < 100 | 15 ✅ | 0 (alle aus denkschulen) |
| Mikrocluster | < 20 | 8 ✅ | ≤ 8 |
| Cluster ≥ 3 Docs | ≥ 50 | 9 ❌ | deutlich besser (ohne Mega-Cluster) |
| Mega-File-Mikrocluster weg | ja | ❌ | ✅ (C_cluster-0000 fällt weg) |
| Ø Wörter/Segment | 200–400 | ~203 ✅ | unverändert |

## Ergebnis

Commit: `feat(corpus): denkschulen aus mainstream-pipeline exkludiert (block 0.k)`

Nachher: Gate-1 vollständig erfüllt → Freigabe für Block 8.A (Phase-8-Smoke-Test).
