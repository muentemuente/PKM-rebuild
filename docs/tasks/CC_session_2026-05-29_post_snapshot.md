---
task_id: SESSION_2026-05-29_post-snapshot
title: CC-Session nach Snapshot — Blocks 0J.8 + 0.M + 0.L-Vorbereitung
status: open
owner: claude_code (3 Blöcke autonom mit App-Checkpoints)
priority: P0
depends_on: [snapshot_2026-05-29_1519]
created: 2026-05-29
updated: 2026-05-29
estimated_effort: 90–120 Min (3 Blöcke à 30 Min, plus Übergänge)
---

# Session-Briefing — durchlaufend autonom bis Strategie-STOP

## Voraussetzungen

- Snapshot `snapshot_2026-05-29_1519` ist vorhanden in `~/projects/aktiv/PKM_rebuild/backups/`
- Letzter committeter Stand: Block 0.J + 0.K Code-Changes gepusht (Mega-Cluster-Diskrepanz aufgelöst, 168 Docs in C_cluster-0000 bestätigt)
- Frische CC-Session (kein Carry-Over aus voriger Session)

## Pflicht-Lektüre (in dieser Reihenfolge)

1. `/CLAUDE.md`
2. `docs/06b_tool_routing.md`
3. `docs/PROJECT_STATUS.md`
4. `docs/learnings/GATE_1_review_2026-05-28.md`
5. `docs/tasks/0J_phase4_fix_and_rerun.md` (für 0J.8-Detail-Spec)
6. `docs/tasks/README.md` (Master-Plan-Stand)

## Sektion 0 — Session-Start (5 Min)

**Sanity-Checks vor Beginn:**

```bash
cd ~/projects/aktiv/PKM-rebuild
git status         # erwartung: clean
git log --oneline -10  # letzte 10 commits sichten
ls ~/projects/aktiv/PKM_rebuild/backups/ | grep 1519  # snapshot da?
python -m pipeline status  # phases 1-10 implementiert
pytest -q --tb=short  # alle tests grün
```

Bei Auffälligkeit STOP, App melden.

---

## Block 0J.8 — Doku-Update Block 0.J + 0.K (~30 Min)

### Kontext

Block 0.J (Phase-4-Fix + Book-Sonderpfad + threshold-Tuning) und Block 0.K (denkschulen-Exklusion) sind code-seitig abgeschlossen. Doku ist nicht synchron.

Spec: `docs/tasks/0J_phase4_fix_and_rerun.md` Task 0J.8 (gilt analog für 0.K).

### Tasks

**0J.8.1 — `docs/PROJECT_STATUS.md`**
- Sektion 1: Phase-3-Hash, Phase-4-Hash, Phase-5-Hash, Phase-6-Hash, Phase-7-Hash auf aktuelle commits aktualisieren
- Sektion 2 Phase 4: Sub-Sektion ergänzen:
  > **Gate-1-Re-Run am 2026-05-28/29:** Merge-Logik in Phase 4 hinzugefügt (heading-only und undersized segments werden gemergt), `min_words_per_segment: 50 → 150`, Book-Sonderpfad eingeführt (H1+H2-Splits für `doc_type_guess.label == "book"`). Block 0.K: `denkschulen_ueberblick_und_einfuehrung.md` (15.770 Wörter, 394 H2-Headings) als Survey-Doc aus Mainstream-Pipeline exkludiert (`_excluded/`-Subfolder). `similarity_threshold` iterativ getestet: 0.85→0 echte Cluster, 0.65→Mega-Cluster (168 Docs in C_cluster-0000), 0.75→85.9% unsortiert. Stand: 0.65 als Fallback, Mega-Cluster bleibt als bekanntes Problem für Block 0.L (Clustering-Strategie).
- Sektion 7: neue offene Punkte ergänzen:
  - 7.5 Clustering-Mega-Cluster (Block 0.L)
  - 7.6 Reports-Generator-Bug Cluster-Größen (Block 0.M)
- Frontmatter `updated: 2026-05-29`
- Änderungs-Log-Eintrag

**0J.8.2 — Reflexions-Skelette aktualisieren**

In `docs/learnings/PHASE_04_segment.md`, `PHASE_05_redundancy.md`, `PHASE_06_embeddings.md`, `PHASE_07_batches.md` je in Sektion 4 (Beobachtete Auffälligkeiten) kurze Notiz ergänzen:

- PHASE_04: Merge-Logik nachträglich hinzugefügt, Block 0.J. Book-Sonderpfad.
- PHASE_05: TF-IDF-Threshold + min_df ungeändert geblieben. Heading-Echo war Hauptverursacher der 642 1.0-Kanten — durch Phase-4-Fix eliminiert.
- PHASE_06: similarity_threshold-Iteration in 0.J/0.K (0.85→0.65→0.75→0.65). Mega-Cluster-Problem bei diesem Korpus mit agglomerativem Clustering nicht durch Threshold lösbar.
- PHASE_07: Batch-Bildung unverändert. Mega-Cluster wird durch Phase 7 in Sub-Batches gesplittet, semantische Konsistenz dabei aber nicht garantiert.

Lessons-Sektion bleibt TODO (wird in 0H.4 finalisiert).

**0J.8.3 — `docs/learnings/GATE_1_review_2026-05-28.md` erweitern**

Neue Sektion am Ende einfügen vor Änderungs-Log:

```markdown
## Verifikation 0.65-Iteration (Block 0.J zweiter Durchgang)

Re-Run mit similarity_threshold 0.65 nach Merge-Fix + Book-Pfad:

| Kriterium | Ziel | Vorher | Nachher | Status |
| ... | ... | ... | ... | ... |

4/6 erfüllt. Gate-1 akzeptiert mit zwei bekannten Schwächen:
- denkschulen-Mega-File (separat behandelt in Block 0.K)
- Mega-Cluster `C_cluster-0000` mit 168 Docs (Block 0.L)

## Block 0.K — denkschulen-Exklusion (2026-05-29)

Datei aus Mainstream-Pipeline entfernt (`_excluded/`-Subfolder).
Re-Run mit threshold 0.65, danach Threshold-Test 0.75 (verfehlt), zurück auf 0.65.

Endstand (1187 Segmente, 202 Files):
- Unsortiert: 26.1 %
- Cluster ≥3 Docs: 8
- Mega-Cluster C_cluster-0000: 807 Segmente / 168 Docs — Problem bleibt

Bekannte Verzerrung: Reports-Generator (cluster_report.md) zeigte „Top-Cluster 8 Docs"
statt tatsächlich 168. Diskrepanz aufgelöst per Direct-Query in cluster_proposals.json.
Reports-Bug wird in Block 0.M gefixt.
```

**0J.8.4 — Commit**

```
docs: project-status + reflexionen + gate-1 update für block 0.j + 0.k

- PROJECT_STATUS aktualisiert (commit-hashes, phase-4-notiz, offene punkte 7.5/7.6)
- PHASE_04/05/06/07 reflexionen sektion 4 ergänzt
- GATE_1-review um verifikation-sektion + 0.k erweitert
- mega-cluster und reports-bug als bekannte issues dokumentiert
```

### ⏸ App-Checkpoint nach 0J.8

```
Block: 0J.8 ABGESCHLOSSEN
Erledigt: 0J.8.1–0J.8.4
Commit: <hash>
Tests: <count> grün (keine Code-Änderungen, sollte stabil bleiben)
Nächster Block: 0.M (Reports-Bug)
Push: wartet auf User-OK
```

Bei OK: Push, dann direkt weiter zu 0.M.

---

## Block 0.M — Reports-Generator-Bug fixen (~30 Min)

### Kontext

`cluster_report.md` zeigte „Top-Cluster 8 Docs" obwohl C_cluster-0000 tatsächlich 168 Docs hat. Direct-Query in `cluster_proposals.json` bestätigte den Mega-Cluster.

Bug-Hypothese: Reports-Generator zählt Cluster-Größe via falscher Metrik (z.B. Segment-Count-basierte Filter, oder eine maximal-Cluster-Größen-Limit).

### Tasks

**0M.1 — Diagnose**

1. `pipeline/phase_10_reports.py` Funktion `generate_cluster_report()` analysieren
2. Speziell die „Top-20 Cluster nach Doc-Count"-Tabelle und die „Cluster-Größen-Histogramm"-Berechnung
3. Vergleichen mit der Direct-Query-Logik:
   ```python
   doc_ids = set(s.rsplit('-S', 1)[0] for s in seg_ids)
   doc_count = len(doc_ids)
   ```
4. Befund-Doku in `docs/learnings/0M1_reports_bug_diagnose_2026-05-29.md` (kurz, max 1 Seite)

### ⏸ App-Checkpoint nach 0M.1

```
Block: 0.M
Erledigt: 0M.1 (Diagnose)
Befund: <kurz>
Vorschlag-Fix: <konkret>
Frage an App: Fix-Strategie bestätigen?
```

Bei OK: weiter zu 0M.2.

**0M.2 — Fix implementieren**

- Doc-Count-Berechnung korrigieren
- Pro Cluster: aus `segment_ids` die distinct `doc_id`s extrahieren (per `s.rsplit('-S', 1)[0]`)
- In allen drei betroffenen Tabellen (Top-20, Histogramm, Mikrocluster-Liste) konsistent verwenden
- Sicherstellen dass `C_unsortiert` nicht in „Cluster ≥3 Docs"-Statistik einfließt

**0M.3 — Tests**

- Neuer Test `test_phase_10_cluster_report_doc_count`: synthetisches `cluster_proposals.json` mit Mega-Cluster (10 Segmente aus 5 verschiedenen Docs) → Doc-Count muss 5 sein, nicht 10
- Neuer Test `test_phase_10_cluster_report_excludes_unsortiert_from_stats`
- Bestehende Reports-Tests laufen weiter grün

**0M.4 — Reports neu generieren + verifizieren**

```bash
python -m pipeline reports
```

Verifikation:
- `cluster_report.md` zeigt jetzt: Top-Cluster mit Doc-Count konsistent zur Direct-Query
- Sanity-Check via `jq` analog zur Diskrepanz-Klärung

**0M.5 — Commit**

```
fix(phase_10): cluster_report.md zählt docs korrekt (statt segmente)

- Doc-Count via distinct doc_ids aus segment_ids (rsplit '-S')
- C_unsortiert wird von "Cluster ≥3 Docs"-Statistik ausgeschlossen
- 2 neue Tests gegen Regression
- Reports neu generiert, Mega-Cluster (168 Docs) jetzt sichtbar
```

### ⏸ App-Checkpoint nach 0.M

```
Block: 0.M ABGESCHLOSSEN
Erledigt: 0M.1–0M.5
Commit: <hash>
Tests: <count> grün (+2 neue)
Reports korrekt: ja/nein
Nächster Block: 0.L Vorbereitung (Daten-Analyse)
Push: wartet auf User-OK
```

Bei OK: Push, dann direkt weiter zu 0.L-Vorbereitung.

---

## Block 0.L Vorbereitung — Clustering-Strategie-Daten (~30 Min)

### Kontext

Strategie-Optionen aus voriger App-Session:
- A: HDBSCAN aktivieren (Phase 7b in Spec optional)
- B: Single-Doc-Fallback (echte Cluster durch 4-Stage, Rest 1:1)
- C: Qwen clustert selbst (Phase 6 minimal, Phase 8 Stage 1 macht semantisches Clustering)
- D: Anderes Embedding-Modell (deutsches spezialisiertes)

**Vor Strategie-Entscheidung in App** braucht es Daten — sonst ist die Entscheidung Bauchgefühl.

Diese Vorbereitung ist CC-autonom. Nur Daten sammeln, NICHT umsetzen.

### Tasks

**0L.0.1 — Analyse-Skript erstellen**

Neue Datei: `scripts/clustering_analysis.py`

Liefert:

1. **Pairwise-Similarity-Histogramm** (auf `embeddings.parquet`):
   - Histogramm der Cosine-Similarities zwischen allen Segment-Paaren
   - Bins: 0.0–0.1, 0.1–0.2, …, 0.9–1.0
   - Zweck: zeigt die natürliche Verteilung — wo sind die Lücken (= mögliche Threshold-Kandidaten)

2. **Cluster-Größen-Simulation bei verschiedenen Thresholds:**
   - Threshold-Werte: 0.55, 0.60, 0.65, 0.70, 0.75, 0.80
   - Pro Threshold: Anzahl Cluster, Top-Cluster-Größe, Mittlere Cluster-Größe, % unsortiert
   - Greedy-Clustering wie in Phase 6, aber nur In-Memory (kein Pipeline-Re-Run)

3. **Top-Themen-Wörter pro Cluster (TF-IDF-basiert):**
   - Pro Cluster aus `cluster_proposals.json`: Top-10 TF-IDF-Begriffe
   - Speziell: was sind die häufigsten Begriffe im Mega-Cluster `C_cluster-0000`?
   - Zweck: zeigt Heterogenität — wie verwandt sind 168 Docs wirklich?

4. **HDBSCAN-Trial (wenn Library installierbar):**
   - `pip install hdbscan` versuchen
   - Lauf mit `min_cluster_size: 3, min_samples: 2` auf bestehenden Embeddings
   - Output: HDBSCAN-Cluster-Anzahl, Verteilung, Vergleich mit agglomerativem Ist-Stand
   - Wenn Install scheitert: dokumentieren, überspringen

**0L.0.2 — Bericht zusammenstellen**

Neue Datei: `data/02_pipeline_output/clustering_analysis.md`

Format:

```markdown
---
title: Clustering-Strategie — Datenbasis
slug: clustering-analysis
status: stable
generated: 2026-05-29
---

# Clustering-Strategie — Datenbasis für Block 0.L

## 1. Pairwise-Similarity-Histogramm
[Histogramm als Tabelle oder ASCII-Plot]

## 2. Cluster-Größen bei verschiedenen Thresholds
[Tabelle 6 Threshold-Werte × 4 Metriken]

## 3. Top-Themen-Wörter
### Mega-Cluster C_cluster-0000
[Top-10 TF-IDF, Beobachtung]

### Echte Cluster (≥3 Docs)
[Top-5 Begriffe je Cluster]

### Unsortiert
[Top-10 Begriffe — was dominiert dort?]

## 4. HDBSCAN-Trial (falls ausgeführt)
[Vergleichs-Tabelle agglomerativ vs HDBSCAN]
[Falls nicht: Hinweis "hdbscan-Library nicht installierbar in Env XY"]

## 5. Beobachtungen
[Drei bis fünf datengetriebene Punkte, KEINE Strategie-Empfehlung]
```

**Wichtig:** CC formuliert KEINE Strategie-Entscheidung. Nur Daten. Entscheidung gehört in App.

**0L.0.3 — Tests**

`tests/test_clustering_analysis.py` mit 2–3 Tests:
- Skript läuft ohne Fehler auf bestehenden Daten
- Output-Datei wird erzeugt mit gültigem Frontmatter
- Hauptsektionen vorhanden

**0L.0.4 — Commit**

```
feat(scripts): clustering-analyse als datengrundlage für block 0.L

- pairwise-similarity-histogramm
- cluster-größen-simulation bei thresholds 0.55–0.80
- top-themen-wörter pro cluster (besonders C_cluster-0000)
- hdbscan-trial (falls library verfügbar)
- bericht in data/02_pipeline_output/clustering_analysis.md
```

### 🛑 App-Checkpoint nach 0.L-Vorbereitung — HARTER STOP

```
Block: 0.L VORBEREITUNG ABGESCHLOSSEN
Erledigt: 0L.0.1–0L.0.4
Commit: <hash>
Tests: <count> grün
Output: data/02_pipeline_output/clustering_analysis.md
Push: wartet auf User-OK

WICHTIG: KEINE Strategie-Entscheidung in dieser Session.
0.L Implementierung (Option A/B/C/D Wahl) erfolgt in neuer App-Session
mit datengetriebener Diskussion.

Hochzuladen in App-Konversation:
- data/02_pipeline_output/clustering_analysis.md
```

Bei OK: Push, dann Session-Ende.

---

## Abbruch-Bedingungen

CC pausiert und meldet App, wenn:

- Snapshot fehlt oder älter als 24h
- Bestehende Tests fehlschlagen vor Session-Start
- 0J.8: Reflexions-Skelette nicht vorhanden (sollten aus 0H.3 da sein)
- 0M.1 Diagnose ergibt unklaren Befund (Bug ist nicht offensichtlich)
- 0L.0.1 HDBSCAN-Install dauert > 5 Min (überspringen, dokumentieren)
- Memory-Pressure auffällig
- Context-Auslastung erreicht 80% (Auto-Compact verhindern)

In allen Fällen: kurzer Status-Block in Session ausgeben, App-Konversation öffnen.

## Erfolgs-Kriterium

Am Ende der Session sind alle drei Punkte erreicht:

- ✅ 0J.8 abgeschlossen, Doku synchron zum Code-Stand
- ✅ 0.M abgeschlossen, Reports korrekt
- ✅ 0.L-Vorbereitung abgeschlossen, `clustering_analysis.md` bereit für App-Diskussion

Zeitbudget: 90–120 Min realistisch. Bei Überschreitung: STOP nach aktuellem Block, kein Aufholen erzwingen.

## Was NICHT in dieser Session passiert

- 0.L Strategie-Entscheidung
- 0.L Implementierung
- Block 0.G (Vault-Foundations)
- Block 0.I (Backup)
- Block 8.A (Phase-8-Smoke)
- Block 0H.4 (Reflexionen Lessons-Sektionen)

Alle obigen folgen in späteren Sessions.

---

## Änderungs-Log

- 2026-05-29 — Initial-Version nach Mega-Cluster-Diskrepanz-Klärung
