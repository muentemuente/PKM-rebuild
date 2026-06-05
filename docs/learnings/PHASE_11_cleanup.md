---
title: PHASE_11 — cleanup
slug: phase-11-cleanup
type: phase-reflection
status: draft
phase_number: 11
phase_name: "Backlog / Technischer Abschluss"
session_started: "2026-06-05 08:30"
session_ended: "2026-06-05 10:30"
duration_minutes: 120
created: "2026-06-05"
updated: "2026-06-05"
---

# Phase 11: Backlog / Technischer Abschluss

Reflexionsdokument nach Abschluss der Phase. Pflicht laut `docs/01_strategy.md` Sektion 8.

---

## 1. Was war geplant?

Task `docs/tasks/11.A_cleanup.md`: 5 Arbeitspakete (AP1→AP5), atomare Commits,
ein Merge nach `FREIGABE`. Ziel: sauberer technischer Projekt-Stand vor der
inhaltlichen Review-Arbeit.

---

## 2. Was ist tatsächlich passiert?

| AP | Soll | Status |
|---|---|---|
| AP1 | `_pkm_common.py` extrahieren (Drift-Risiko killen) | ✅ done — `8a032fe` |
| AP2 | Config-Prune (stage1/2, verworfene Cluster-Settings) | ✅ done — `e6fdc30` |
| AP3 | mypy-Altlast bereinigen | ✅ done — `bebd291` |
| AP4 | `unsortiert/` `_index` + Diagnose-Report | ✅ done — `69a7f7c` |
| AP5 | E3: Intermediates archivieren | ⛔ **nicht ausgeführt** (Triage-Abhängigkeit, s. 3.1) |

### Ergebnis im Detail

- **AP1:** Enums (`ALLOWED_TYPE/STATUS/REVIEW/CONFIDENCE`) jetzt aus
  `pipeline.schemas`-Literals abgeleitet, `ALLOWED_CATEGORIES` aus
  `CATEGORY_TO_FOLDER` → Drift unmöglich. Geteilte Pure-Helfer + Slug-Logik in
  `scripts/_pkm_common.py`. 4 Skripte importieren statt eigener Kopien
  (`apply_category_mapping` hatte nichts zu teilen). `tests/test_pkm_common.py`
  bewacht Konsistenz. `check_schema`/`compare_*` bewusst lokal belassen
  (divergierende Output-Kontrakte → Vereinheitlichung wäre Verhaltensänderung).
- **AP2:** `qwen.temperature.stage1/2`, `qwen.max_tokens.stage1/2`,
  `clustering.initial_strategy` + `umap_hdbscan`-Block entfernt (referenz-geprüft,
  Dispatch liest sie nicht). embeddings + `min_cluster_size` behalten (Phase 6).
- **AP3:** `mypy pipeline/ scripts/` von 81 Fehlern (13 Dateien) → 0
  (26 Dateien Success). Nur Annotationen/Guards. `scripts/__init__.py` für
  eindeutige Modulnamen. scipy in mypy-overrides; pyarrow/Literal via dokumentierte
  `type: ignore`.
- **AP4:** `unsortiert/_index.md` existierte bereits (Builder behandelt unsortiert
  als genutzten Cluster). `scripts/unsortiert_diagnose.py` erzeugt
  `unsortiert_diagnose.md` (8 Artikel, 5 Domänen).

### Akzeptanzkriterien (Task)

- [x] AP1 Verhalten unverändert (pkm_triage STDOUT byte-identisch zu main)
- [x] AP2 status + `run --sample 10 --dry-run` rc=0
- [x] AP3 `mypy pipeline/ scripts/` clean
- [x] AP4 `unsortiert_diagnose.md` erstellt (verschiebt nichts)
- [ ] AP5 Intermediates archiviert — **bewusst nicht** (Datensicherheit, s. 3.1)
- [x] pytest (377) + ruff-Gate + mypy grün

---

## 3. Probleme & Blocker

- **AP1 Helfer-Divergenz:** `check_schema`/`compute_body_metrics`/`compare_*`
  waren NICHT byte-identisch zwischen den Skripten (unterschiedliche Issue-String-
  Formate, Feld-Coverage, Return-Typen). Naives Zusammenführen hätte Verhalten
  geändert. Lösung: nur die wirklich identischen Helfer + alle Enums zentralisiert;
  Validatoren lokal gelassen (referenzieren aber die geteilten Enums → Drift weg).
- **mypy-Volumen (AP3):** 81 Fehler. 35 trivial (`dict`→`dict[str, Any]`) per
  gezieltem Zeilen-Patcher (nur von mypy markierte Zeilen, kein Blind-sed).
  Rest manuell (Path|None-Narrowing via asserts, stats-Typ, Annotationen).

### 3.1 AP5 nicht ausgeführt — Triage hängt an den Intermediates

`pkm_triage.classify_draft` stuft einen Draft ohne separate `.frontmatter.json`
**und** `.body.md` als `ORPHAN` → `RERUN_LM` ein (Zeile 405). Non-destruktiv
verifiziert (`assess_draft` auf `CK_imagemagick-cheatsheet`):

```
MIT Intermediates : READY -> READY_TO_MIGRATE
OHNE (archiviert) : ORPHAN -> RERUN_LM
```

Archivieren würde **alle 180 Drafts** von READY auf RERUN_LM kippen. Das ist
exakt der AP5-Checkpoint „Triage hängt von Intermediates ab → STOP, nicht
archivieren". → **Nicht archiviert.** Entscheidung für muente:

- (a) `pkm_triage` robust gegen fehlende Intermediates machen (embedded YAML aus
  `.md` als Fallback statt separater `.frontmatter.json`), **dann** AP5 sicher
  ausführen; oder
- (b) Intermediates als bewusste Provenance behalten (Triage bleibt voll nutzbar).

---

## 4. Was wurde gelernt?

### 4.1 Technisch
- Enum-SSoT via `get_args(Literal)` aus dem Pydantic-Schema ist drift-sicher und
  testbar — besser als jede Kopie + Kommentar.
- mypy-Massenfehler effizient: gezielter Zeilen-Patcher nur auf die markierten
  Zeilen, statt riskanter globaler Ersetzungen.

### 4.2 Workflow / Methodik
- „Behavior unverändert" ernst genommen: vor jedem Refactor-Commit pkm_triage-
  STDOUT gegen die `main`-Version diff't (byte-identisch).
- AP5: erst die Abhängigkeit beweisen, dann entscheiden — nicht blind „Ballast"
  löschen. Der Checkpoint hat genau das verhindert.

### 4.3 Über Tooling
- Reine Coding-Phase, kein LLM. mypy-strict-Baseline war nie clean — jetzt ist sie es.

---

## 5. Was würde ich nächstes Mal anders machen?

- Bei „dedupe"-Tasks zuerst prüfen, ob die Kopien wirklich identisch sind —
  Divergenz ist oft schon eingetreten und Teil des Problems.
- Tool-Abhängigkeiten (Triage ↔ Intermediates) vor „Aufräum"-Schritten kartieren.

---

## 6. Token-Verbrauch (Claude Code)

| Wert | Schätzung |
|---|---|
| Anzahl Sessions | 1 (inkl. --resume) |
| Geschätzte Input-Tokens | hoch (5 Skripte + Pipeline-Module gelesen) |
| Geschätzte Output-Tokens | hoch (Refactor + 81 mypy-Fixes + Tests + Docs) |
| 5h-Limit erreicht? | nein |

---

## 7. Memory-/Hardware-Beobachtungen

Nicht relevant — kein Qwen-/Embedding-Lauf.

---

## 8. Folgende TODOs / offene Fragen

- [ ] AP5-Entscheidung (Triage robust machen → archivieren, oder Intermediates behalten).
- [ ] main-Merge nach wörtlichem `FREIGABE`.
- [ ] Manuelle DoD-Reste: Backup 2. Medium + Recovery-Drill, Qualitätsstufe-2-Review,
  `unsortiert/`-Finalzuordnung (Input: `unsortiert_diagnose.md`), Projekt-Retro.

---

## 9. Cross-Reference

| Bereich | Verweis |
|---|---|
| Task | `docs/tasks/11.A_cleanup.md` |
| SSoT-Modul | `scripts/_pkm_common.py` + `tests/test_pkm_common.py` |
| Diagnose | `data/02_pipeline_output/unsortiert_diagnose.md` (`scripts/unsortiert_diagnose.py`) |
| Vorherige Reflexion | `docs/learnings/PHASE_10_reports.md` |

---

## 10. Gesamtbewertung der Phase

**Lief gut wenn:** Drift-Risiko sauber an der Wurzel (Schema-abgeleitete Enums)
gekillt, mypy von 81→0 ohne Verhaltensänderung, AP5-Datenrisiko vor dem Löschen erkannt.
**Lief schlecht wenn:** man Helfer naiv zusammengeführt oder „Ballast" blind
archiviert hätte.

---

## Änderungs-Log

- 2026-06-05 — Initial-Bearbeitung nach Phasen-Ende (AP1–4 done, AP5 deferred)
