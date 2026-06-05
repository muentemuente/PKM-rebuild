---
task_id: 0H
title: Gate-1-Bericht + Berichte-Generator + Phase-Reflexionen 1-7
status: open
owner: mixed (CC-led + App-Review)
priority: P1
depends_on: []
created: 2026-05-28
updated: 2026-05-28
estimated_effort: 4–6h (verteilt)
---

# Block 0.H — Gate-1-Bericht + Berichte + Reflexionen

## Kontext

Drei Aufholungs-Aufgaben, alle vor Phase-8-Echtlauf wichtig:

1. **Gate-1-Bericht** (`cluster_report.md`) fehlt — Cluster-Output liegt seit 27.05. 21:17 ungeprüft. Review-Gate 1 (laut `docs/02_pipeline_spec.md`) ist faktisch übersprungen worden.
2. **Phase-10-Berichte** als Generator implementieren — vorgezogen aus Phase 10, weil Gate 1 sie braucht. Spart später Doppelarbeit.
3. **Reflexionen 1–7** fehlen — `/CLAUDE.md` Sektion 8 + `docs/01_strategy.md` Sektion 8 verlangen sie pro Phase als Lernziel.

## Pflicht-Lektüre

1. `/CLAUDE.md` Sektion 8
2. `docs/01_strategy.md` Sektion 8
3. `docs/02_pipeline_spec.md` Phase 10 + Review-Gates (Sektion 10)
4. `docs/06b_tool_routing.md`
5. `docs/learnings/PHASE_template.md` (Stilreferenz)
6. `docs/learnings/PHASE_00_setup.md` (Vorbild für Tonalität und Tiefe)

---

## Task 0H.1 — Berichte-Generator (Phase 10 vorgezogen)

**Owner:** Claude Code (autonom)

**Neue Datei:** `pipeline/phase_10_reports.py`

**Zweck:** Drei Markdown-Reports aus bestehenden Pipeline-Outputs generieren.

### 0H.1.a — `generate_corpus_report()`

**Input:**
- `data/02_pipeline_output/files_manifest.jsonl` (Phase 1)
- `data/02_pipeline_output/documents_structured.jsonl` (Phase 3)
- `data/02_pipeline_output/segments.jsonl` (Phase 4)

**Output:** `data/02_pipeline_output/corpus_report.md`

**Inhalt:**
```markdown
---
title: Korpus-Bericht
slug: corpus-report
status: stable
generated: <ISO-Datum>
pipeline_version: <version>
---

# Korpus-Bericht

## Übersicht
- Files gesamt: N
- Files-Größe gesamt: X MB
- Wörter gesamt: N
- Zeichen gesamt: N
- Segmente gesamt: N

## Doc-Typ-Verteilung (heuristische Vermutung)
| Typ | Anzahl | Anteil |
|---|---|---|
| knowledge-article | N | X % |
| ... | | |

## Sprach-Verteilung (heuristisch)
| Sprache | Anzahl |
|---|---|

## Größen-Verteilung
- < 100 Wörter: N
- 100–500: N
- 500–2000: N
- 2000–10000: N
- > 10000: N

## Top-10 längste Files
| Datei | Wörter |
|---|---|

## Top-10 kürzeste Files
| Datei | Wörter |
|---|---|
```

### 0H.1.b — `generate_duplicate_report()`

**Input:**
- `data/02_pipeline_output/exact_duplicates.json`
- `data/02_pipeline_output/near_duplicate_edges.jsonl`

**Output:** `data/02_pipeline_output/duplicate_report.md`

**Inhalt:**
```markdown
---
title: Duplikat-Bericht
slug: duplicate-report
status: stable
generated: <ISO-Datum>
---

# Duplikat-Bericht

## Exakte Duplikate (SHA-256)
- Anzahl Gruppen: N
- Betroffene Files: N
| Gruppe | Files |
|---|---|

## Nahe Duplikate (TF-IDF Cosine ≥ 0.72)
- Anzahl Kanten: N
- Top-10 nach Similarity
| Segment A | Segment B | Similarity |
|---|---|---|

## Verteilung
- Similarity 0.72–0.80: N
- 0.80–0.90: N
- 0.90–0.99: N
- 1.00 (exakt auf Segment-Ebene): N
```

### 0H.1.c — `generate_cluster_report()`

**Input:**
- `data/02_pipeline_output/cluster_proposals.json`
- `data/02_pipeline_output/batches/batch_*.md` (für Token-Schätzungen)
- `data/02_pipeline_output/near_duplicate_edges.jsonl` (für Inter-Cluster-Stats)

**Output:** `data/02_pipeline_output/cluster_report.md`

**Inhalt:**
```markdown
---
title: Cluster-Bericht (Gate-1-Input)
slug: cluster-report
status: stable
generated: <ISO-Datum>
---

# Cluster-Bericht — Review-Gate 1

## Übersicht
- Cluster gesamt: N
- davon mit ≥3 Files: N
- Mikrocluster (<3 Files): N
- Unsortiert (`C_unsortiert`): N Segmente

## Cluster-Größen-Histogramm
| Cluster-Größe (Segmente) | Anzahl Cluster |
|---|---|
| 3 | N |
| 4–5 | N |
| 6–10 | N |
| 11–20 | N |
| 21–50 | N |
| > 50 | N |

## Top-20 Cluster nach Doc-Count
| Cluster-ID | Label-Guess | Files | Segmente | Token-Schätzung |
|---|---|---|---|---|

## Mikrocluster-Liste
| Cluster-ID | Label-Guess | Files |
|---|---|---|

## Batch-Übersicht
- Batches gesamt: N
- Batch mit größtem Token-Estimate: <name> (N Tokens)
- Batch mit kleinstem Token-Estimate: <name>
- Mittlere Token-Estimate: N
- Empfehlung für Smoke-Test: <kleinster Batch mit 5–10 Segmenten>

## Nahe-Duplikat-Verteilung
- Kanten innerhalb gleicher Cluster: N
- Kanten zwischen verschiedenen Clustern: N (potenziell falsche Cluster-Zuordnung)

## Re-Run-Befehl
\`\`\`bash
python -m pipeline run --from-phase 6 --force
\`\`\`
```

**CLI-Wiring:**
- Zwei neue Commands in `__main__.py`:
  - `python -m pipeline run --phase 10` (regulärer Pipeline-Phasen-Lauf)
  - `python -m pipeline reports` (separater Convenience-Command)
- Beide rufen `generate_corpus_report()`, `generate_duplicate_report()`, `generate_cluster_report()`

**Akzeptanzkriterien:**
- Drei Markdown-Reports generiert, alle Frontmatter-valid
- Idempotent: zweiter Lauf erzeugt identische Outputs (Hash-Vergleich)
- CLI funktioniert: `--phase 10` UND `reports`
- `--from-phase 10` auch möglich (nutzt vorhandene Outputs ohne weitere Phasen-Läufe)
- `_IMPLEMENTED_PHASES` enthält 10
- Tests: `tests/test_phase_10_reports.py` mit mindestens:
  - `test_corpus_report_generates`
  - `test_duplicate_report_generates`
  - `test_cluster_report_generates`
  - `test_reports_idempotent`
  - `test_reports_command_runs`

**Commit:** `feat(phase_10): berichte-generator (corpus, duplicate, cluster)`

### ⏸ App-Checkpoint nach 0H.1

```
Block: 0.H
Erledigt: 0H.1
Output:
  - data/02_pipeline_output/corpus_report.md
  - data/02_pipeline_output/duplicate_report.md
  - data/02_pipeline_output/cluster_report.md
Commit: <hash>
Tests: <count> grün (+5 neue)
Nächster Schritt: 0H.2 ist App-Domäne (Gate-1-Review)
Frage an App: Reports in App-Konversation hochladen für Gate-1-Review?
```

CC pausiert. 0H.2 läuft in App.

---

## Task 0H.2 — Gate-1-Review (App)

**Owner:** App-Konversation + User

**Status:** ausstehend nach 0H.1

**Workflow:**
1. Reports aus 0H.1 in App-Konversation hochladen
2. Gemeinsam reviewen:
   - Cluster-Verteilung okay?
   - Mikrocluster-Anteil sinnvoll?
   - Inter-Cluster-Kanten Hinweis auf falsche Cluster-Zuordnung?
   - Top-Cluster inhaltlich plausibel (Labels-Sichtung)?
3. Entscheidung:
   - **Variante A:** Cluster okay → Gate-1-Bestätigung dokumentieren
   - **Variante B:** Schwellwerte anpassen (`tfidf.threshold`, `embeddings.similarity_threshold`, `clustering.min_cluster_size`) → Re-Run Phase 6/7 mit `--force`
   - **Variante C:** Manuelle Cluster-Merges via Override-File (nicht jetzt implementiert — Eskalation)
4. Bei A: `docs/learnings/GATE_1_review_<datum>.md` schreiben (Auftrag an CC)
5. Bei B: nach Re-Run Loop zurück zu 0H.1

**Output:** `docs/learnings/GATE_1_review_<datum>.md`

**Format:**
```markdown
---
title: Gate-1-Review (Cluster-Karte)
slug: gate-1-review-<datum>
status: stable
date: <YYYY-MM-DD>
decision: approved | rerun_phase_6_7 | escalate
---

# Gate-1-Review — <Datum>

## Geprüft
- corpus_report.md (Stand <hash/datum>)
- duplicate_report.md (Stand <hash/datum>)
- cluster_report.md (Stand <hash/datum>)

## Entscheidung
<approved / rerun_phase_6_7 / escalate>

## Begründung
<Freitext>

## Auffälligkeiten / Notizen
<Freitext>

## Konsequenzen
- Phase 8 Smoke-Test darf starten: ja/nein
- Schwellwert-Anpassungen: <…>
```

---

## Task 0H.3 — Phase-Reflexionen 1–7 Skelette (CC)

**Owner:** Claude Code (autonom)

**Ziel:** 7 Markdown-Files in `docs/learnings/` als Skelette, datengetrieben aus Code + Git + Outputs.

**Files:**
- `PHASE_01_inventory.md`
- `PHASE_02_normalize.md`
- `PHASE_03_structure.md`
- `PHASE_04_segment.md`
- `PHASE_05_redundancy.md`
- `PHASE_06_embeddings.md`
- `PHASE_07_batches.md`

**Pro File — Datenquellen:**
- `git log --oneline --all` für die Phase (Commit-Hashes aus PROJECT_STATUS Sektion 1)
- `pipeline/phase_N_*.py` (LOC, Imports, Funktionssignaturen)
- Test-File-Count + Test-Namen
- Output-File-Größe und Zeilenzahl
- mypy-Fehler-Liste (per Datei)

**Pro File — Struktur (analog `PHASE_template.md`):**

```markdown
---
title: Reflexion Phase N — <Slug>
slug: phase-NN-<slug>
phase_id: NN
phase_status: draft  # später "done" wenn App-Lessons gefüllt
status: draft
created: 2026-05-28
updated: 2026-05-28
---

# Phase N — <Name>

## 1. Was wurde gemacht
<aus Commit-Messages + Code-Übersicht, kompakt>

## 2. Output-Größen
| Datei | Größe | Zeilen |
|---|---|---|

## 3. Code-Stats
- Modul: `pipeline/phase_N_*.py` (LOC: N)
- Tests: N
- Mypy-Fehler: N (siehe PROJECT_STATUS Sektion 4)

## 4. Beobachtete Auffälligkeiten
<aus Code-Review: mypy-Hinweise, TODO-Kommentare, edge cases>

## 5. Lessons

> [!todo] Inhaltliche Reflexion in App-Session 0H.4

## 6. Verknüpfung
- Strategy: `docs/01_strategy.md` Phase N
- Spec: `docs/02_pipeline_spec.md` Phase N

## Änderungs-Log
- 2026-05-28 — Skelett generiert (Block 0.H.3)
```

**Akzeptanzkriterien:**
- 7 Files vorhanden in `docs/learnings/`
- Frontmatter valid
- Sektionen 1–4 datengetrieben gefüllt
- Sektion 5 (Lessons) explizit als TODO markiert
- Keine Halluzinationen — wenn Info fehlt, „nicht erfasst" notieren

**Commit:** `docs(learnings): phase 1-7 reflexions-skelette (datengetrieben)`

### ⏸ App-Checkpoint nach 0H.3

```
Block: 0.H
Erledigt: 0H.1, 0H.3
Output: 7 Reflexions-Skelette in docs/learnings/
Commit: <hash>
Nächster Schritt: 0H.4 ist App-Domäne (Lessons inhaltlich)
Frage an App: Reihenfolge der Reflexions-Finalisierung? Empfohlen: Phase 7 zuerst (aktuellste Erinnerung), rückwärts
```

---

## Task 0H.4 — Reflexionen 1–7 inhaltlich finalisieren (App)

**Owner:** App-Konversation + User

**Status:** ausstehend nach 0H.3

Pro Phase: Lessons-Sektion in App-Session füllen. Skelette aus 0H.3 bereitstellen, gemeinsam Reflexion schreiben.

**Reihenfolge:** rückwärts (Phase 7 → 1), weil aktuelle Phase besser erinnert.

**ADHS-Schutz:** max 2 Phasen pro App-Session.

**Per Phase:**
- Lessons-Sektion ausfüllen (Was lief gut, was würde ich anders machen, Skill-Lerneffekt)
- `phase_status: done` setzen
- `> [!todo]`-Marker entfernen
- `updated:` aktualisieren
- Änderungs-Log-Eintrag

---

## Reihenfolge

```
0H.1 (CC)
  └─→ 0H.2 (App, Gate-1-Review)
        └─→ ggf. Re-Run Phase 6/7 → zurück zu 0H.1

0H.3 (CC, parallel zu 0H.1/0H.2)
  └─→ 0H.4 (App, iterativ über mehrere Sessions)
```

## Definition of Done für Block 0.H

- [ ] 0H.1: drei Reports vorhanden, CLI funktioniert, Tests grün
- [ ] 0H.2: Gate-1-Entscheidung dokumentiert in `docs/learnings/GATE_1_review_<datum>.md`
- [ ] 0H.3: 7 Reflexions-Skelette vorhanden mit Sektionen 1–4 datengetrieben gefüllt
- [ ] 0H.4: alle 7 Reflexionen mit ausgefüllten Lessons (`phase_status: done`)
- [ ] `status` im Frontmatter dieses Files auf `done`

## Out-of-Scope für 0.H

- `validate`-CLI-Command implementieren (separate Task, kein Phase-9-Blocker)
- Mypy-Schulden in Phasen 2, 3, 6 abtragen (separater Task)

---

## Änderungs-Log

- 2026-05-28 — Initial-Version
