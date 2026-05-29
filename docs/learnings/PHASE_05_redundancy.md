---
title: Reflexion Phase 5 — Redundanz-Erkennung
slug: phase-05-redundancy
phase_id: 5
phase_status: draft
status: draft
created: 2026-05-28
updated: 2026-05-29
---

# Phase 5 — Redundanz-Erkennung

## 1. Was wurde gemacht

Commit `d9cb420` (feat: implement Phase 5 — Redundanz-Erkennung). Zwei-stufige Duplikat-Erkennung: (1) SHA-256 auf normalisiertem Body-Text für exakte Duplikate, (2) TF-IDF Cosine-Similarity auf Segment-Ebene für nahe Duplikate. Konfigurierbare Schwellwerte (`threshold`, `ngram_range`, `max_features`, `min_df`). Ergebnis: 0 exakte Duplikat-Gruppen, 1.031 nahe-Duplikat-Kanten (642 davon Similarity = 1.0 auf Segment-Ebene).

- Output: `exact_duplicates.json` (leer — 0 Gruppen), `near_duplicate_edges.jsonl` (1.031 Kanten)
- TF-IDF-Threshold: 0.72 (aus Config)
- 642 Kanten mit Similarity 1.0: Segmente identischer Chunks in verschiedenen Dokumenten

## 2. Output-Größen

| Datei | Größe | Zeilen |
|---|---|---|
| `exact_duplicates.json` | 2 B | 1 (leere Liste) |
| `near_duplicate_edges.jsonl` | 133 KB | 1.031 |
| `near_duplicate_edges.jsonl.meta.json` | 501 B | 1 |

## 3. Code-Stats

- Modul: `pipeline/phase_5_redundancy.py` (LOC: 331)
- Tests: 19 (`tests/test_phase_5_redundancy.py`)
- Mypy-Fehler: 0

## 4. Beobachtete Auffälligkeiten

- 0 exakte Duplikate auf Dokument-Ebene trotz 642 Segment-Kanten mit Sim=1.0: Dokumente haben unterschiedliche Frontmatter oder Rahmensätze, aber gleiche Abschnitt-Chunks
- Niedriger Test-Count (19) im Vergleich zu Phasen 3-4 — TF-IDF-Logik ist extern (scikit-learn), Tests fokussieren auf Integration und Threshold-Logik
- `min_df=1` in Config: auch einmalige Terme werden im Vokabular behalten — bei kleinem Korpus (203 Docs) sinnvoll
- `exact_duplicates.json` mit 2 Byte (leere Liste) — Corner-Case für Phase-10-Report: "keine Duplikate" muss explizit ausgegeben werden, nicht als Fehler behandelt werden

**Gate-1-Befund + Nach-Re-Run (2026-05-29):**
- Vorher: 642 Kanten mit Sim=1.0 — Ursache: Phase-4 Mini-Segmente (Heading-Echo erzeugt identische Token-Mengen)
- Phase-4-Fix behebt Ursache: Nach Re-Run nur noch **31 Kanten gesamt, 15 mit Sim=1.0**
- Alle verbleibenden 1.0-Kanten stammen aus `denkschulen_ueberblick_und_einfuehrung.md` — wird in Block 0.K exkludiert
- `similarity_threshold`-Änderung (0.85→0.65, `546c121`) betrifft Phase 6 (Clustering), nicht den TF-IDF-Threshold hier
- **TF-IDF-Threshold + `min_df` blieben in Block 0.J/0.K unverändert** — Heading-Echo in Phase 4 war alleinige Ursache der 642 Sim=1.0-Kanten, nicht die Threshold-Parameter
- **Block-0.K-Endstand:** Nach denkschulen-Exklusion: **0 Kanten Sim=1.0**, 0 Kanten gesamt ✅

## 5. Lessons

> [!todo] Inhaltliche Reflexion in App-Session 0H.4

## 6. Verknüpfung

- Strategy: `docs/01_strategy.md` Phase 5
- Spec: `docs/02_pipeline_spec.md` Phase 5

## Änderungs-Log

- 2026-05-28 — Skelett generiert (Block 0.H.3)
- 2026-05-29 — Gate-1-Befund + Nach-Re-Run-Zahlen ergänzt (Sektion 4)
- 2026-05-29 — TF-IDF-unverändert-Notiz + Block-0.K-Endstand ergänzt (Block 0.J.8)
