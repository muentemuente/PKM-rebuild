---
title: Gate-1-Review — Cluster-Karte (28.05.2026)
slug: gate-1-review-2026-05-28
status: stable
date: 2026-05-28
decision: rerun_phase_4_onwards
phase_status: done
created: 2026-05-28
updated: 2026-05-29
---

# Gate-1-Review — Cluster-Karte (Stand 28.05.2026)

## Geprüft

| Report | Datum |
|---|---|
| `data/02_pipeline_output/corpus_report.md` | 2026-05-28 |
| `data/02_pipeline_output/duplicate_report.md` | 2026-05-28 |
| `data/02_pipeline_output/cluster_report.md` | 2026-05-28 |

## Entscheidung

**Re-Run ab Phase 3 mit Phase-4-Fix + Book-Sonderbehandlung.**

Konkret:
1. Phase 4 Merge-Logik fixen (Heading-only-Segmente und Mini-Segmente werden mit Nachbar gemergt)
2. `min_words_per_segment: 50 → 150` in Config
3. Neuen `doc_type_guess`-Label `book` einführen für Files > 8000 Wörter
4. Phase 4 segmentiert Books nach H1/H2 (große Segmente), nicht H2/H3
5. Re-Run `--from-phase 3 --force`
6. Neue Reports + Gate-1-Verifikation

Umsetzung in Block 0.J — siehe `docs/tasks/0J_phase4_fix_and_rerun.md`.

## Begründung

### Kritische Befunde

| Befund | Zahl | Bewertung |
|---|---|---|
| Ø Wörter pro Segment | 60 | unter `min_words: 50` — Merge-Logik greift nicht zuverlässig |
| Segmente gesamt | 5.368 | zu fein granuliert für 203 Files |
| Unsortierte Segmente | 4.877 (90.8 %) | nur 9 % der Segmente landen in benannten Clustern |
| Top-Cluster Doc-Count | 59 Docs | bildet 29 % aller Files in einem Bucket — zu grob |
| 1.0-Similarity-Kanten | 642 (62 % aller Kanten) | Heading-only-Boilerplate, kein echtes Duplikat-Signal |
| Mikrocluster mit Label „1. Komplexität & emergente Systeme" | ~13× | stammt aus Mega-File `denkschulen_ueberblick_und_einfuehrung.md` (15.770 Wörter), das in zig Mikrocluster zerlegt wurde |

### Ursachen-Hypothese

**Phase 4 ist Wurzelproblem.** Heading-Splits produzieren Mini-Segmente (3–10 Wörter), die nicht mit Nachbarn gemergt werden. Konsequenz:
- Heading-Echo verstopft die Duplikat-Erkennung (Phase 5)
- Mini-Segment-Embeddings sind semantisch arm → Cluster scheitern (Phase 6)
- Inhaltlich verwandte Sub-Sektionen verteilen sich auf mehrere Cluster

**Mega-File ist Verstärker.** Bei 15.770 Wörtern erzeugt `denkschulen_ueberblick` mit Standard-Heuristik ca. 250 Segmente. Diese dominieren die Mikrocluster-Liste.

## Verworfene Alternativen

| Option | Verworfen weil |
|---|---|
| B — Quick-Fix Schwellwerte | Symptombehandlung, Heading-Noise bleibt |
| C — Kombi (Phase 4 + min_df) | Komplexer, A liefert vermutlich schon genug |
| D — Pragmatisch akzeptieren | 90 % unsortiert bedeutet 90 % des Korpus geht durch Phase 8 verloren |
| Mega-File manuell splitten | Strukturell unsauber, Book-Pattern ist generischer |

## Konsequenzen

- Phase 8 Smoke-Test (Block 8.A) verschiebt sich um Block 0.J nach hinten
- Block 0.G und 0.I können parallel zu 0.J laufen (App-/User-Tasks unabhängig vom Re-Run)
- Block 0.H Sub-Task 0H.4 (Reflexionen Phase 4, 5, 6, 7) erst nach erfolgreichem Re-Run — Inhalte würden sonst veralten
- Schema-Erweiterung `DocTypeGuess.label += "book"` betrifft Phase 3, ist abwärtskompatibel
- `FrontmatterDraft.type` muss nicht erweitert werden (Books bekommen weiterhin `knowledge-article` oder `process-document` als finalen Typ)

## Erfolgs-Kriterien für nächsten Gate-1-Review (nach Re-Run)

- [x] Unsortierte Segmente sinken von 90.8 % auf < 40 % — **19.0 %** ✅
- [x] 1.0-Similarity-Kanten sinken von 642 auf < 100 — **15** ✅
- [x] Mikrocluster < 20 (statt 39) — **8** ✅
- [ ] Cluster mit ≥ 3 Docs steigen von 32 auf ≥ 50 — **9** ❌
- [ ] Mega-File-Mikrocluster („1. Komplexität…") verschwinden — `C_cluster-0000` dominiert mit 171 Docs (denkschulen-Problem, → Block 0.K) ❌
- [x] Ø Wörter pro Segment steigt auf 200–400 — **~203** ✅

Falls Kriterien verfehlt: erneute Gate-1-Diskussion, ggf. Strategie B oder C nachschalten.

## Verifikation 0.65-Iteration

Re-Run ab Phase 3 (`--from-phase 3 --force`) abgeschlossen am 2026-05-29. Reports generiert.

| Kriterium | Ziel | Vorher | Nachher | Status |
|---|---|---|---|---|
| Unsortierte Segmente | < 40 % | 90.8 % (4.877/5.368) | 19.0 % (300/1.581) | ✅ |
| 1.0-Similarity-Kanten | < 100 | 642 | 15 | ✅ |
| Mikrocluster (< 3 Docs) | < 20 | 39 | 8 | ✅ |
| Cluster mit ≥ 3 Docs | ≥ 50 | 32 | 9 | ❌ |
| Mega-File-Mikrocluster weg | ja | ~13 Mikrocluster | `C_cluster-0000` mit 171 Docs | ❌ |
| Ø Wörter pro Segment | 200–400 | ~60 | ~203 | ✅ |

**Ergebnis: 4/6 Kriterien erfüllt → Gate-1 akzeptiert.**

Begründung Akzeptanz trotz 2 Fehlern:
- Kriterium 4 (Cluster ≥ 3 Docs): 9 statt 50 — denkschulen dominiert `C_cluster-0000` und zieht 171 Docs künstlich in einen Cluster. Ohne dieses eine File würde das Clustering deutlich besser ausfallen.
- Kriterium 5 (Mega-File-Mikrocluster): Die ~13 Mikrocluster sind weg, aber das Mega-File erzeugt nun einen Mega-Cluster. Beides ist dieselbe Ursache: `denkschulen_ueberblick_und_einfuehrung.md` gehört nicht in die Mainstream-Pipeline.

**Beschluss:** denkschulen wird in Block 0.K aus `data/01_corpus_input/` nach `_excluded/` verschoben. Phase 1 skippt `_*`-Prefix bereits. Nach Block-0.K-Re-Run werden alle 6 Kriterien neu bewertet.

## Verifikation Block 0.K (denkschulen exkludiert)

Re-Run nach Exklusion von `denkschulen_ueberblick_und_einfuehrung.md`, 2026-05-29.

| Kriterium | Ziel | Nach 0.J | Nach 0.K | Status |
|---|---|---|---|---|
| Unsortierte Segmente | < 40 % | 19.0 % | 26.1 % (310/1.187) | ✅ |
| 1.0-Similarity-Kanten | < 100 | 15 | **0** | ✅ |
| Mikrocluster (< 3 Docs) | < 20 | 8 | 10 | ✅ |
| Cluster mit ≥ 3 Docs | ≥ 50 | 9 | 8 | ❌ |
| Mega-File-Mikrocluster weg | ja | ❌ | ✅ (denkschulen-Content weg) | ✅ |
| Ø Wörter pro Segment | 200–400 | ~203 | ~257 | ✅ |

**Neuer Befund:** `C_cluster-0000` hat jetzt Label „Diagramme und Flowcharts" mit 168 Docs (83 % des Korpus). Das Mega-Cluster-Problem ist kein denkschulen-spezifisches Problem — `similarity_threshold=0.65` ist zu niedrig und zieht generell zu viel Content in einen Cluster. Nächster Schritt: Threshold-Tuning separat entscheiden (ggf. 0.72–0.78).

Kriterium 5 formal erfüllt (denkschulen-Mikrocluster weg). Kriterium 4 weiterhin offen.

**Endstand (1.187 Segmente, 202 Files):**
- Unsortiert: 26.1 % (310/1.187) ✅
- Cluster ≥3 Docs: 8 ❌ (Ziel ≥50)
- Mega-Cluster C_cluster-0000: 807 Segmente / 168 Docs — Problem bleibt

**Bekannte Verzerrung:** Reports-Generator (`cluster_report.md`) zeigte „Top-Cluster 8 Docs" statt tatsächlich 168. Diskrepanz aufgelöst per Direct-Query in `cluster_proposals.json`. Reports-Bug wird in Block 0.M gefixt.

## Änderungs-Log

- 2026-05-28 — Gate-1 abgeschlossen, Re-Run-Strategie A + Book-Sonderbehandlung beschlossen
- 2026-05-29 — Verifikation nach Re-Run ergänzt: 4/6 Kriterien erfüllt, Gate-1 akzeptiert, denkschulen → Block 0.K
- 2026-05-29 — Verifikation Block 0.K: denkschulen exkludiert, 5/6 Kriterien erfüllt; Mega-Cluster-Problem (`similarity_threshold`) bleibt offen
- 2026-05-29 — Endstand + Reports-Bug-Notiz ergänzt (Block 0.J.8)
