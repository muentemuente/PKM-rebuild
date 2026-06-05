---
task_id: 8A
title: Phase 8 — Smoke-Test (Single-Batch-Lauf)
status: open
owner: interactive (App + CC + User + LM Studio)
priority: P0 (Gate vor 8.B Voll-Lauf)
depends_on: [0F, 0G, 0H]
created: 2026-05-28
updated: 2026-05-28
estimated_effort: 3–4h (eine fokussierte Session mit Pausen)
---

# Block 8.A — Phase 8 Smoke-Test (Single-Batch)

## Kontext

Erstes Mal Qwen-Synthese gegen einen echten Korpus-Batch. Validiert:
- Quality der 4 Prompts gegen echten Inhalt
- Token-Budget-Realismus (insbesondere Reasoning-Overhead in Praxis)
- JSON-Parse-Robustheit (Retry-Mechanismus, halluzinierte Segment-IDs)
- Memory-Pressure-Verhalten (32 GB physisch, ~4 GB für macOS frei)
- Stage-Dauern und Gesamtdauer

**Dies ist NICHT der Voll-Lauf** — nur 1 sorgfältig gewählter Batch.

## Voraussetzungen (zwingend)

- [ ] Block 0.F abgeschlossen (Code-Bugs gefixt, CLI-Wiring fertig, max_tokens aus Config)
- [ ] Block 0.G mind. 0G.1–0G.3 und 0G.6 abgeschlossen (Vokabular, Gedanken-Sonderpfad)
- [ ] Block 0.H mind. 0H.1 abgeschlossen (`cluster_report.md` für Batch-Auswahl verfügbar)
- [ ] LM Studio installiert, Qwen 3.6 27B (4-bit) geladen
- [ ] Context-Window in LM-Studio auf ≥49152 gesetzt
- [ ] Verfügbarer RAM: prüfen via `vm_stat` (mind. 26 GB frei vor Qwen-Start)
- [ ] App-Hygiene-Protokoll aus `docs/00_persona_muente.md` Sektion 6 verinnerlicht

## Pflicht-Lektüre

1. `docs/00_persona_muente.md` Sektion 6 (Memory-Workflow)
2. `docs/04_qwen_prompts.md` (alle Stage-Prompts)
3. `docs/06b_tool_routing.md` Sektion 4 + 8
4. `docs/learnings/PHASE_00_setup.md` (Block 0.D — Reasoning-Overhead, Token-Verhalten)
5. `pipeline/phase_8_synthesis.py` (Verständnis der 4 Stages)
6. `data/02_pipeline_output/cluster_report.md` (aus 0H.1)

---

## Task 8A.1 — Batch-Auswahl

**Owner:** App-Konversation + User

**Tool:** App + Ghostty (für Inspektion)

**Ziel:** Kleinen, klaren Batch wählen — kein Mega-Cluster, kein Mikrocluster.

**Auswahl-Kriterien:**
- 5–10 Segmente (laut Batch-Frontmatter `segment_count`)
- 3–5 Quell-Docs (`doc_count`)
- Token-Schätzung < 5000 (`token_estimate`)
- Inhaltlich klar (kein offensichtlicher Mischcluster)

**Workflow:**

```bash
# In Ghostty: kleinste Batches finden
for f in data/02_pipeline_output/batches/batch_*.md; do
  est=$(grep "^token_estimate:" "$f" | awk '{print $2}')
  segs=$(grep "^segment_count:" "$f" | awk '{print $2}')
  echo "$est $segs $f"
done | sort -n | head -10
```

Kandidaten in App-Konversation diskutieren, finalen Batch festlegen.

**Output dieses Tasks:**
- Festgelegter Batch-Pfad (Variable `SMOKE_BATCH=batch_NNN_xyz.md`)
- Begründung der Auswahl, dokumentiert in 8A.6

### ⏸ App-Checkpoint nach 8A.1

```
Block: 8.A
Erledigt: 8A.1 (Batch-Auswahl)
Gewählter Batch: <name>
Segmente: <N>, Docs: <M>, Token-Estimate: <T>
Nächster Schritt: 8A.2 (manueller Single-Stage-Test in LM Studio)
```

---

## Task 8A.2 — Manueller Single-Stage-Test (vor Pipeline-Lauf)

**Owner:** User (mit Anleitung)

**Tool:** LM Studio (Chat-UI) + Ghostty (zum Files lesen)

**Ziel:** Stage 1 von Hand in LM-Studio-Chat-UI durchspielen. Zweck: Quality + Token-Verhalten beobachten, **bevor** die Pipeline das automatisiert macht.

**Schritte:**

1. **LM Studio öffnen**, Qwen 3.6 27B aktiv, Context auf 49152
2. **System-Prompt** kopieren aus `prompts/v1/stage1_cluster_analysis.md` — **ohne** YAML-Frontmatter (nur ab `# System-Prompt`)
3. **In Chat-Settings:**
   - Temperature: 0.3
   - Max Tokens: 20000 (entsprechend neuer Config aus 0F.4)
4. **User-Message:** kompletter Inhalt des gewählten Batch-Files
5. **Senden**
6. **Beobachten:**
   - Zeit bis Antwort
   - Reasoning-Output (sichtbar in LM Studio falls aktiviert)
   - Content-Output (nach Reasoning)
   - Memory-Pressure (Aktivitätsanzeige)
7. **Output speichern:** `~/Downloads/smoke_stage1_manual.json`
8. **JSON manuell extrahieren** aus Output und gegen Schema validieren:
   ```bash
   # In Ghostty
   cat ~/Downloads/smoke_stage1_manual.json | jq '.'
   ```

**Akzeptanzkriterien für Pipeline-Lauf:**
- Stage-1-Output ist valides JSON (manuell extrahierbar)
- Mind. 1 `concept_candidate` ist sinnvoll (Mensch-Bewertung)
- Memory-Pressure blieb grün während Lauf

**Wenn Quality schlecht:**
- Prompt-Iteration nötig — Block 0.J (entsteht nach 8A) oder Anpassung in Block 0.G nachgelagert
- Ggf. niedrigere Temperature versuchen (0.2 statt 0.3)

### 🛑 App-Checkpoint nach 8A.2 — STOP

In App-Konversation:

```
Block: 8.A
Erledigt: 8A.2 (manueller Stage-1-Test)
Beobachtungen:
  - Antwort-Zeit: <s>
  - Reasoning-Output: <Schätzung Tokens>
  - Content-Output: <Schätzung Tokens>
  - Memory-Pressure: grün/gelb/rot
  - JSON-Parse: erfolgreich/fehlgeschlagen
  - Quality-Bewertung: <gut/grenzwertig/schlecht>
Frage an App: Quality akzeptabel für Pipeline-Lauf?
```

Bei „nicht akzeptabel": Block 8.A pausieren, zurück zu Prompt-Iteration.

---

## Task 8A.3 — Pipeline-Smoke-Run (1 Batch)

**Owner:** Claude Code (Anleitung), User (Ausführung)

**Tool:** Zed-CC (Vorbereitung) + Ghostty (Ausführung)

**Vorbereitung — CC-Auftrag:**

Implementierung eines neuen CLI-Flags:
- `pipeline/__main__.py`: `--batch <pfad>` (in Kombination mit `--phase 8`)
- `run_phase_8` bekommt optionalen Parameter `batch_filter: list[Path] | None`
- Nur passende Batches verarbeiten

**CC-Akzeptanzkriterien für die Code-Änderung:**
- `python -m pipeline run --phase 8 --batch <pfad>` läuft nur diesen einen Batch
- Bei `--batch` ohne `--phase 8`: Click-Fehler
- Test: `test_phase_8_cli_batch_filter`

**Commit für CC:** `feat(phase_8): --batch flag für single-batch-läufe (smoke-test-helper)`

**Ausführung — User:**

```bash
# Memory-Pre-Flight
vm_stat | grep "Pages free"
# Sollten >6 GB frei sein vor Qwen-Start

# App-Hygiene aktivieren
# (Browser, Mail, Slack manuell schließen)

# LM Studio: Qwen geladen + Server gestartet (Server-Tab)
# Endpoint sollte auf http://localhost:1234/v1 lauschen

# Pipeline-Smoke-Run
python -m pipeline run --phase 8 --batch data/02_pipeline_output/batches/<SMOKE_BATCH>
```

**Akzeptanzkriterien:**

Erwartete Outputs:
- `data/02_pipeline_output/qwen/<batch_id>/stage1_analysis.json`
- `data/02_pipeline_output/qwen/<batch_id>/stage2_merges.json`
- `data/03_drafts/CK_<slug>.body.md` (mind. 1, abhängig von `proposed_concepts`)
- `data/03_drafts/CK_<slug>.frontmatter.json`
- `data/03_drafts/CK_<slug>.md` (kombiniert)
- `data/02_pipeline_output/qwen/needs_human.jsonl` (kann leer sein bei Erfolg)

**Console-Output:**
- Fortschritt pro Stage
- Stage-Dauer
- Summary am Ende: batches_processed, concepts_drafted, needs_human, errors, duration_seconds

**Logging:**
- Strukturierte JSON-Events in `data/02_pipeline_output/pipeline.log`
- Keine `ERROR`-Level-Events außer dokumentierte erwartete (z.B. needs_human-Hinweise)

---

## Task 8A.4 — Memory-Pressure-Beobachtung (parallel zu 8A.3)

**Owner:** User (Live)

**Tool:** Aktivitätsanzeige

**Protokoll:**

Während gesamtem 8A.3 Aktivitätsanzeige offen, alle 30s notieren:

| Zeit | Phase | Memory-Pressure | RAM Qwen | RAM frei | Bemerkung |
|---|---|---|---|---|---|
| T+0 | Start | grün | 27 GB | 4 GB | |
| T+30s | Stage 1 reasoning | grün/gelb | … | … | |
| ... | | | | | |

**Bei Gelb:** beobachten, nicht eingreifen.

**Bei Rot:** Pipeline pausieren (Ctrl+C in Ghostty), App-Hygiene verschärfen, neu starten.

**Output:** Notiz in 8A.6.

---

## Task 8A.5 — Output-Review (App)

**Owner:** App-Konversation + User

**Tool:** App + Editor (Files öffnen)

**Reviewt** in dieser Reihenfolge:

1. **`stage1_analysis.json`**
   - JSON valid?
   - Themen sinnvoll erkannt?
   - Segment-IDs alle existent (keine Halluzinationen)?
   - `overall_confidence`-Wert plausibel?

2. **`stage2_merges.json`**
   - Konzept-Vorschläge plausibel?
   - Slugs konform mit Naming-Conventions?
   - Kategorie-Zuordnung sinnvoll?
   - `merged_from` und `sources_docs` konsistent mit Stage 1?

3. **`CK_<slug>.body.md`** (jeder erzeugte Artikel)
   - Strukturell korrekt (H1, Sections laut Typ)?
   - Code-Blöcke aus Source-Segmenten unverändert?
   - Sprache: Deutsch im Inhalt, Englisch in Identifier?
   - Keine offensichtlichen Halluzinationen?
   - `> [!question]`-Marker an offenen Stellen?

4. **`CK_<slug>.frontmatter.json`**
   - Alle Pflichtfelder vorhanden?
   - `confidence`-Wert plausibel?
   - Tags aus Vokabular (wenn 0G.3 fertig)?
   - `sources_docs` und `source_chunks` konsistent mit Stage 2?

5. **`needs_human.jsonl`** (falls vorhanden)
   - Welche Fälle wurden geflaggt?
   - Plausibel?

**Bewertung — drei Ausgänge:**
- ✅ **Quality OK** → grünes Licht für Block 8.B (Voll-Lauf)
- ⚠️ **Quality grenzwertig** → Prompt-Iteration nötig, neuer Block 0.J entsteht
- ❌ **Quality schlecht** → Modell-Wechsel evaluieren (Llama-3.1-70B non-reasoning als Fallback?), Strategy-Update

### 🛑 App-Checkpoint nach 8A.5 — STOP

```
Block: 8.A
Erledigt: 8A.3, 8A.4, 8A.5
Outputs vorhanden: ja/nein
Quality-Bewertung: ✅/⚠️/❌
Memory-Pressure-Verlauf: grün/gelb/rot
Entscheidung: 8.B starten / 8.A iterieren / Modell-Wechsel
Frage an App: nächster Block?
```

---

## Task 8A.6 — Smoke-Reflexion

**Owner:** Claude Code (schreibt Skelett aus Daten) + App (füllt Lessons)

**Datei:** `docs/learnings/PHASE_08_smoke_<datum>.md`

**CC-Auftrag:**

Skelett aus tatsächlichen Outputs:

```markdown
---
title: Phase 8 Smoke-Test — <Datum>
slug: phase-08-smoke-<datum>
phase_id: "08-smoke"
phase_status: draft
status: draft
created: <Datum>
updated: <Datum>
---

# Phase 8 — Smoke-Test (<Datum>)

## 1. Gewählter Batch
- Batch-ID: <name>
- Segmente: <N>
- Docs: <M>
- Token-Estimate: <T>
- Begründung: <aus 8A.1>

## 2. Stage-Dauern
| Stage | Dauer | Tokens Input | Tokens Output | Reasoning-Ratio |
|---|---|---|---|---|

## 3. Reasoning-Output-Beobachtungen
<aus 8A.2 manuell + 8A.3 Pipeline>

## 4. JSON-Parse / Retries
<aus pipeline.log>

## 5. Memory-Pressure-Verlauf
<aus 8A.4 Notizen>

## 6. Quality-Bewertung
<aus 8A.5>

## 7. Outputs
- stage1_analysis.json: <Größe, validate-Status>
- stage2_merges.json: <…>
- CK_*.md erzeugt: <count>
- needs_human-Einträge: <count>

## 8. Lessons (vorläufig)

> [!todo] Vollständige Reflexion in App-Session, sobald 8.B-Entscheidung gefallen
```

**App-Auftrag:** Lessons-Sektion füllen nach 8A.5.

**Akzeptanzkriterien:**
- Skelett vorhanden, Sektionen 1–7 datengetrieben
- Sektion 8 explizit als TODO

**Commit:** `docs(learnings): phase 8 smoke-test reflexion`

---

## Definition of Done für Block 8.A

- [ ] Batch ausgewählt + dokumentiert
- [ ] Manueller LM-Studio-Test durchgeführt, Quality akzeptabel
- [ ] Pipeline-Smoke-Run erfolgreich
- [ ] `CK_<slug>.md` Body + Frontmatter Pydantic-valid
- [ ] Memory-Pressure-Verlauf dokumentiert
- [ ] Smoke-Reflexions-Skelett geschrieben + App-Lessons gefüllt
- [ ] Quality-Entscheidung getroffen (8.B / iterieren / Modell-Wechsel)
- [ ] `status` im Frontmatter dieses Files auf `done`

## Nach 8.A

**Bei grünem Licht:** Block 8.B entwerfen — Voll-Lauf 72 Batches:
- Mehrere Sessions (je 1–2h)
- Memory-Watch aktiv
- Resume-Pattern für Crash-Fälle
- Token-Budget-Tracking (Claude Pro Bucket, falls parallel CC-Arbeit nötig)

**Bei rotem Licht:** Block 0.J — Prompt-Iteration. Entsteht ad-hoc, nutzt `prompts/v1/` als Basis, bumped auf `v1.1` oder `v2` je nach Tiefe der Änderungen.

---

## Out-of-Scope für 8.A

- Voll-Lauf aller 72 Batches (Block 8.B)
- Prompt-Iteration für andere Stages (entsteht ad-hoc bei Bedarf)
- Modell-Vergleich Qwen vs. Llama (Eskalations-Pfad)
- `merge_decisions.json`-Drill (in 8.B oder eigener Block)

---

## Änderungs-Log

- 2026-05-28 — Initial-Version
