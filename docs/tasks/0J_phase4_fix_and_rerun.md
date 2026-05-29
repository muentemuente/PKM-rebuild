---
task_id: 0J
title: Phase-4-Fix + Book-Sonderbehandlung + Re-Run
status: open
owner: claude_code (autonom mit App-Checkpoints)
priority: P0 (blockiert 8.A)
depends_on: [0F]
created: 2026-05-28
updated: 2026-05-28
estimated_effort: 2–3h
---

# Block 0.J — Phase-4-Fix + Book-Sonderbehandlung + Re-Run

## Kontext

Gate-1-Review hat ergeben (siehe `docs/learnings/GATE_1_review_2026-05-28.md`):
- 90.8 % der Segmente unsortiert → Phase 4 segmentiert zu fein, Merge-Logik greift nicht
- 642 Similarity-1.0-Kanten sind Heading-Boilerplate-Noise
- Mega-File `denkschulen_ueberblick_und_einfuehrung.md` (15.770 Wörter) erzeugt zig Mikrocluster

Entscheidung: Strategie A (Phase 4 fixen) + Sonderbehandlung für Books. Re-Run `--from-phase 3 --force`.

## Pflicht-Lektüre

1. `docs/learnings/GATE_1_review_2026-05-28.md`
2. `docs/02_pipeline_spec.md` Phase 3 + Phase 4
3. `docs/06b_tool_routing.md`
4. `pipeline/phase_3_structure.py`
5. `pipeline/phase_4_segment.py`
6. `pipeline/schemas.py` (`DocTypeGuess`, `SegmentRecord`)
7. `pipeline/pipeline.config.yaml`
8. `tests/test_phase_3_structure.py`
9. `tests/test_phase_4_segment.py`

---

## Task 0J.1 — Phase 4 Merge-Logik analysieren (DIAGNOSE)

**Owner:** Claude Code

**Ziel:** Befund formulieren, BEVOR gefixt wird. Ohne Diagnose kein Fix.

**Schritte:**

1. `pipeline/phase_4_segment.py` lesen, insbesondere die Merge-Funktion (wenn vorhanden) und die Logik um `min_words_per_segment`
2. Klären, was passiert mit einem Segment, das aus nur einem Heading besteht (z.B. `## Workflows` mit 1 Wort):
   - Wird es erzeugt?
   - Wird Merge mit dem Inhalt darunter versucht?
   - Was passiert wenn das nächste Segment auch nur ein Heading ist?
3. Drei Stichproben aus echten Outputs:
   ```bash
   # Wie viele Segmente unter 30 Wörtern?
   jq -r 'select(.word_count < 30) | .segment_id' \
     data/02_pipeline_output/segments.jsonl | wc -l

   # Wie viele Segmente unter 50 Wörtern (= konfigurierter min_words)?
   jq -r 'select(.word_count < 50) | .segment_id' \
     data/02_pipeline_output/segments.jsonl | wc -l

   # Segmente pro Doc Top-10
   jq -r '.doc_id' data/02_pipeline_output/segments.jsonl \
     | sort | uniq -c | sort -rn | head -10
   ```
4. Befund-Dokument schreiben — kurz, 1 Seite max

### 🛑 App-Checkpoint nach 0J.1 — STOP

In App-Konversation einfügen:

```
Block: 0.J
Erledigt: 0J.1 (Diagnose Phase 4)
Befund:
  - Segmente < 30 Wörter: <N>
  - Segmente < 50 Wörter: <N>
  - Top-5 Files nach Segment-Count: <Liste>
  - Merge-Logik-Beobachtung: <Bug / Lücke / konservative Heuristik>
  - denkschulen_ueberblick Segment-Count: <N>
Vorschlag-Fix: <konkret>
Frage an App: Fix-Strategie bestätigen?
```

Warte auf User-Entscheidung. KEIN Code-Edit vor User-Freigabe.

---

## Task 0J.2 — Phase 4 Merge-Logik fixen

**Owner:** Claude Code (nach 0J.1 + User-Freigabe)

**Akzeptanzkriterien (Standard-Vorschlag — User kann anpassen):**

- Segmente mit `word_count < min_words_per_segment` werden zwingend mit dem nächsten Segment **gleicher oder tieferer** Heading-Ebene gemergt (oder vorherigem, falls kein nächster).
- Ausnahme: wenn beide Nachbarn auch unter `min_words` sind → alle drei mergen, dann erneut prüfen.
- Code-Blöcke, Tabellen, Listen bleiben unzerrissen (Bestandsfunktion).
- Heading-only-Segmente (nur Heading-Text, kein Body-Text danach im Segment) werden grundsätzlich gemergt — sie haben per Definition kein eigenes Inhalts-Volumen.
- Edge-Case dokumentieren: Was passiert mit dem letzten Segment eines Files unter min_words?

**Neue Tests:**
- `test_phase_4_merges_heading_only_segment`
- `test_phase_4_merges_undersized_segment_into_next`
- `test_phase_4_merges_chain_of_undersized_segments`
- `test_phase_4_preserves_code_blocks_after_merge`

**Bestehende Tests:** dürfen sich ändern (Segment-Counts in Fixtures werden anders). Anpassung dokumentieren.

**Commit:** `fix(phase_4): heading-only und undersized segments werden gemergt`

---

## Task 0J.3 — Config-Anpassung `min_words_per_segment`

**Owner:** Claude Code

**Datei:** `pipeline/pipeline.config.yaml`

**Änderung:**
```yaml
segmentation:
  min_words_per_segment: 150   # vorher 50
  max_words_per_segment: 1500
  target_words_per_segment: 900
  # ... Rest unverändert
```

**Akzeptanzkriterien:**
- YAML-Wert geändert
- Begründungs-Kommentar im YAML: `# Gate-1 (2026-05-28): erhöht von 50, Heading-Echo eliminieren`
- Bestehende Tests laufen (sind teilweise auf min_words=50 ausgelegt — Fixtures ggf. anpassen)

**Commit:** `chore(config): min_words_per_segment 50 → 150 (gate-1 entscheidung)`

---

## Task 0J.4 — Book-Detection in Phase 3 (Schema-Erweiterung)

**Owner:** Claude Code

**Dateien:** `pipeline/schemas.py`, `pipeline/phase_3_structure.py`, `pipeline/pipeline.config.yaml`

**Schema-Änderung:**

```python
class DocTypeGuess(BaseModel):
    label: Literal[
        "cheat_sheet", "tutorial", "wiki", "manual",
        "how-to", "explanation", "reference", "gedanke",
        "projektidee", "projektplanung", "book",   # NEU
        "unklar"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[str]
```

**Heuristik in Phase 3:**

```python
# Zusätzliche Regel in der Doc-Type-Heuristik
def _detect_book(doc: StructuredDocumentRecord) -> bool:
    """Erkennt Buch-artige Files: sehr lang + viele Top-Level-Headings."""
    word_count_threshold = cfg.structure.book_word_threshold  # default 8000
    h1_h2_count = sum(1 for h in doc.headings if h["level"] in (1, 2))
    return doc.word_count > word_count_threshold and h1_h2_count >= 5
```

**Config-Ergänzung:**

```yaml
structure:
  # ...
  book_word_threshold: 8000    # files >= dieser Wortzahl + 5+ H1/H2 → label "book"
```

**Akzeptanzkriterien:**
- `DocTypeGuess.label` enthält `"book"`
- Heuristik in Phase 3 implementiert, priorisiert vor anderen Labels (wenn Book-Bedingung erfüllt → `book`)
- Bestehender Test `test_phase_3_doc_type_guess` erweitert um Book-Case
- Neuer Test: `test_phase_3_detects_book`

**Commit:** `feat(phase_3): book-label in doc_type_guess (für mega-files)`

---

## Task 0J.5 — Book-Sonderbehandlung in Phase 4

**Owner:** Claude Code

**Datei:** `pipeline/phase_4_segment.py`

**Logik:**

Wenn `doc_type_guess.label == "book"`:
- Segmentierung erfolgt nach **H1 + H2** (statt H2 + H3)
- `max_words_per_segment` wird auf `book_max_words_per_segment` aus Config angehoben (default 5000)
- `min_words_per_segment` ignoriert (Book-Sektionen sind groß genug per Definition)
- Sonst Standard-Logik unverändert

**Config-Ergänzung:**

```yaml
segmentation:
  # ...
  book_max_words_per_segment: 5000
  book_split_levels: [1, 2]   # bei books nach H1+H2 splitten
```

**Akzeptanzkriterien:**
- Book-Path implementiert mit Schalter `if doc.doc_type_guess.label == "book"`
- Standard-Path unverändert für andere Files
- Neue Tests:
  - `test_phase_4_book_segments_by_h1_h2`
  - `test_phase_4_book_allows_larger_segments`
  - `test_phase_4_book_ignores_min_words`
- `denkschulen_ueberblick` würde nach Re-Run vermutlich 10–30 Segmente haben (statt aktuell ~250)

**Commit:** `feat(phase_4): book-sonderpfad (h1+h2-splits, größere segmente)`

### ⏸ App-Checkpoint nach 0J.5

```
Block: 0.J
Erledigt: 0J.1–0J.5 (Diagnose + alle Code-Änderungen)
Commits: <hashes>
Tests: <count> grün
Vor Re-Run: prüfen ob alles korrekt
Nächster Schritt: 0J.6 (Re-Run ab Phase 3)
Frage an App: Re-Run starten?
```

---

## Task 0J.6 — Re-Run ab Phase 3

**Owner:** Claude Code (Ausführung), User (Beobachtung)

**Vorbereitung:**

```bash
# Snapshot vor Re-Run (für Rollback-Möglichkeit)
bash scripts/snapshot.sh

# Verifizieren dass alte Outputs umbenannt oder gelöscht werden
# `--force` macht das automatisch
```

**Befehl:**

```bash
python -m pipeline run --from-phase 3 --force
```

**Erwartete Dauer:**
- Phase 3: < 30 s
- Phase 4: < 30 s (mit neuer Merge-Logik)
- Phase 5: 2–5 min (TF-IDF)
- Phase 6: 5–15 min (Embeddings)
- Phase 7: 1–3 min
- **Gesamt:** 10–25 min

**Akzeptanzkriterien:**
- Pipeline läuft durch ohne Fehler
- Alle JSONL/JSON-Outputs in `data/02_pipeline_output/` aktualisiert
- Neue Meta-Files mit aktuellem Hash
- `pipeline.log` enthält keine ERROR-Level-Events außer dokumentierte

**Bei Fehler:** Snapshot zurückspielen, Bug fixen, neu starten.

---

## Task 0J.7 — Neue Reports generieren

**Owner:** Claude Code

**Befehl:**

```bash
python -m pipeline reports
```

**Akzeptanzkriterien:**
- Drei Reports in `data/02_pipeline_output/` aktualisiert
- `generated:` Datum im Frontmatter neu

### 🛑 App-Checkpoint nach 0J.7 — STOP (Gate-1 zweiter Durchgang)

```
Block: 0.J
Erledigt: 0J.1–0J.7
Re-Run-Dauer: <min>
Tests: <count> grün
Neue Reports vorhanden
Vergleich zu Gate-1-Erfolgskriterien:
  - Unsortiert: <N> % (Ziel <40%)
  - 1.0-Kanten: <N> (Ziel <100)
  - Mikrocluster: <N> (Ziel <20)
  - Cluster mit ≥3 Docs: <N> (Ziel ≥50)
  - denkschulen-Segmente: <N> (Ziel 10-30)
  - Ø Wörter/Segment: <N> (Ziel 200-400)
Frage an App: Erfolgskriterien erfüllt? Phase-8-Smoke-Test freigeben?
```

User entscheidet:
- ✅ Alle Kriterien erfüllt → 0J abgeschlossen, weiter mit 0.G/0.I, dann 8.A
- ⚠️ Teilweise → weitere Anpassung (Strategie B oder C nachschalten)
- ❌ Verfehlt → Eskalation, ggf. Strategy-Update

---

## Task 0J.8 — PROJECT_STATUS aktualisieren + Reflexion Phase 6/7 anpassen

**Owner:** Claude Code (nach User-Freigabe in 0J.7)

**Dateien:**
- `docs/PROJECT_STATUS.md`
- `docs/learnings/PHASE_04_segment.md`
- `docs/learnings/PHASE_05_redundancy.md`
- `docs/learnings/PHASE_06_embeddings.md`
- `docs/learnings/PHASE_07_batches.md`

**Änderungen:**

1. PROJECT_STATUS Sektion 1: Commit-Hashes für Phase 3/4/5/6/7 aktualisieren (Re-Run-Hashes)
2. PROJECT_STATUS Sektion 2: kurze Notiz unter Phase 4 Sub-Sektion: "Gate-1-Re-Run am 2026-05-28: Merge-Logik gefixt, min_words 50→150, Book-Sonderbehandlung eingeführt"
3. Reflexionen 4–7: in Sektion 4 (Auffälligkeiten) Notiz ergänzen, in Sektion 5 (Lessons) TODO bleibt — wird in 0H.4 in App finalisiert
4. PROJECT_STATUS Frontmatter `updated:`

**Commit:** `docs: project-status + reflexions update nach gate-1-re-run`

### 🛑 App-Checkpoint nach 0J.8 — STOP (Block-Abschluss)

```
Block: 0.J ABGESCHLOSSEN
Erledigt: 0J.1–0J.8
Commits: <hashes>
Tests: <count> grün
Gate-1 final: ✅ akzeptiert
Reports: aktualisiert in data/02_pipeline_output/
PROJECT_STATUS + Reflexionen 4-7: aktualisiert
git push: wartet auf User-OK
Nächster Block: 0.G (Vault-Foundations) oder 0.I (Backup) — beide parallel möglich
Dann: 8.A (Phase 8 Smoke-Test)
Frage an App: Push freigeben? Welcher Block als nächstes?
```

---

## Reihenfolge

```
0J.1 (Diagnose) ─🛑→ User-Freigabe
                     ↓
0J.2 → 0J.3 → 0J.4 → 0J.5 ─⏸→ User-OK
                              ↓
                              0J.6 (Re-Run) → 0J.7 (Reports) ─🛑→ Gate-1-Verifikation
                                                                  ↓
                                                                  0J.8 (Doku-Update) ─🛑→ Push
```

## Definition of Done für Block 0.J

- [ ] Alle 8 Tasks 0J.1–0J.8 abgeschlossen
- [ ] Tests grün (mind. +8 neue Tests für Merge-Logik und Book-Pfad)
- [ ] `ruff check . && ruff format .` grün
- [ ] `mypy pipeline/` keine neuen Fehler
- [ ] Re-Run erfolgreich
- [ ] Gate-1-Erfolgskriterien erfüllt (mind. 4 von 6)
- [ ] PROJECT_STATUS + Reflexionen 4–7 aktualisiert
- [ ] User-Freigabe für `git push`
- [ ] `status` im Frontmatter dieses Files auf `done`

## Out-of-Scope für 0.J

- 0.G Vault-Foundations (separat)
- 0.I Backup (separat)
- 8.A Smoke-Test (folgt nach 0.J)
- 0H.4 Reflexionen Lessons-Sektionen finalisieren (App, nach 0.J)
- Tag-Vokabular-Validation aktivieren (Block 0.G)
- Mypy-Schulden in Phase 2/3/6 abtragen (separater Task, kein Phase-9-Blocker)

---

## Änderungs-Log

- 2026-05-28 — Initial-Version basierend auf Gate-1-Entscheidung
