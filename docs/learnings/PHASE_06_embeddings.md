---
title: Reflexion Phase 6 — Embeddings + Cluster-Vorbereitung
slug: phase-06-embeddings
phase_id: 6
phase_status: draft
status: draft
created: 2026-05-28
updated: 2026-05-29
---

# Phase 6 — Embeddings + Cluster-Vorbereitung

## 1. Was wurde gemacht

Commit `74de985` (feat: implement Phase 6 — Embeddings + Cluster-Vorbereitung). Alle 5.368 Segmente werden mit `paraphrase-multilingual-mpnet-base-v2` (768-dim, MPS-Device auf M5) eingebettet und als Parquet gespeichert. Cluster-Bildung via Cosine-Similarity-Matrix + DBSCAN-ähnlichem Ansatz: 71 Named Cluster + 1 `C_unsortiert` mit 4.877 Segmenten. Laufzeit: im Rahmen der Performance-Erwartungen (5-15 min).

- Output: `embeddings.parquet` (16 MB), `cluster_proposals.json` (72 Cluster)
- Embedding-Modell: `paraphrase-multilingual-mpnet-base-v2` (korrektes DE-Modell, nach Korrektur aus Block 0.D)
- `C_unsortiert` enthält 4.877/5.368 Segmente (90.8%) — auffällig hoher Anteil

## 2. Output-Größen

| Datei | Größe | Zeilen/Einträge |
|---|---|---|
| `embeddings.parquet` | 16 MB | 5.368 Embeddings |
| `cluster_proposals.json` | 260 KB | 72 Cluster |
| `cluster_proposals.json.meta.json` | 500 B | 1 |

## 3. Code-Stats

- Modul: `pipeline/phase_6_embeddings.py` (LOC: 393)
- Tests: 23 (`tests/test_phase_6_embeddings.py`)
- Mypy-Fehler: 5
  - `:27, :28` — `Library stubs not installed for "scipy.sparse[.csgraph]"` (`[import-untyped]`)
  - `:127, :136` — `Call to untyped function "write_table"/"read_table"` in PyArrow (`[no-untyped-call]`)
  - `:156` — `Returning Any from function declared to return "ndarray[...]"` (`[no-any-return]`)

## 4. Beobachtete Auffälligkeiten

- **4.877 unsortierte Segmente (90.8%) ist kritischer Befund**: Cluster-Schwellwert (`similarity_threshold` oder `min_cluster_size`) ist wahrscheinlich zu eng. Gate-1-Review (0H.2) muss entscheiden ob Re-Run mit anderen Parametern.
- Mypy-Fehler kommen ausschließlich von externen Libraries ohne Stubs (scipy, PyArrow) — keine eigenen Code-Fehler
- `scipy-stubs`-Hinweis von mypy vorhanden: `python3 -m pip install scipy-stubs` würde 2 Fehler beheben
- Cluster `C_cluster-0000` mit 107 Segmenten aus 59 Docs ist mit Abstand größter Named Cluster
- 39 von 71 Named Clustern sind Mikrocluster (<3 Docs) — weitere Indikation für zu enge Clustering-Parameter

**Gate-1-Entscheidung + Nach-Re-Run (2026-05-29):**
- `546c121` — `similarity_threshold: 0.85 → 0.65`: zu enges Clustering war Mitursache für 90.8% unsortierte Segmente
- Hauptursache war aber Phase-4 (Mini-Segmente): Nach Phase-4-Fix deutlich weniger Segmente (1.581 statt 5.368)
- Ergebnis: **300 unsortiert / 1.581 = 19.0%** ✅ (Ziel < 40%), Mikrocluster: 39 → 8 ✅
- Problem: `C_cluster-0000` zieht 171 Docs in einen Cluster — `denkschulen_ueberblick` dominiert durch Book-Segmente, wird in Block 0.K exkludiert
- **Threshold-Iteration Block 0.J/0.K:** `0.85` → 0 echte Cluster (alles unsortiert), `0.65` → Mega-Cluster C_cluster-0000, Test `0.75` (`22a40d6`) → 85.9 % unsortiert (zu schlecht), revert auf `0.65` (`12178f4`)
- **Befund:** Mega-Cluster-Problem bei diesem Korpus mit agglomerativem Clustering nicht durch Threshold lösbar — zu breit gestreute Dokumentensammlung ohne natürliche Cluster-Grenzen → Block 0.L (Strategie-Entscheidung A–D)
- **Block-0.K-Endstand (threshold=0.65):** 26.1 % unsortiert (310/1.187), Mikrocluster: 10, `C_cluster-0000` mit 168 Docs (807 Segmente)

## 5. Lessons

> [!todo] Inhaltliche Reflexion in App-Session 0H.4

## 6. Verknüpfung

- Strategy: `docs/01_strategy.md` Phase 6
- Spec: `docs/02_pipeline_spec.md` Phase 6

## Änderungs-Log

- 2026-05-28 — Skelett generiert (Block 0.H.3)
- 2026-05-29 — Gate-1-Entscheidung + Nach-Re-Run-Zahlen ergänzt (Sektion 4)
- 2026-05-29 — Threshold-Iteration + Mega-Cluster-Befund + Block-0.K-Endstand ergänzt (Block 0.J.8)
