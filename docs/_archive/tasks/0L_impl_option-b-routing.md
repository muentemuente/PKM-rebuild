---
title: Task 0.L-Impl — Option-B-Routing (Stage-1/2-Bypass, Pro-Doc-Veredelung)
slug: 0L-impl-option-b-routing
status: stable
created: 2026-05-29
updated: 2026-05-29
block: 0.L-Impl (Phase II.2)
branch: feat/option-b-routing
---

# Task 0.L-Impl — Option-B-Routing implementieren

**Strategie-Entscheidung:** Option B (Pro-Doc-Veredelung), beschlossen in Block 0.L.
Vollständige Begründung in `docs/tasks/0L_roadmap_option-b.md` §1.

---

## Ziel

Phase 8 der Pipeline auf Option B umstellen:

| Punkt | Ist (Option A) | Soll (Option B) |
|---|---|---|
| Iteration | pro Batch-File | pro Dokument (aus segments.jsonl) |
| Stage 1 (Cluster-Analyse) | läuft | übersprungen |
| Stage 2 (Merge-Vorschlag) | läuft | übersprungen |
| Stage 3 Input | Stage-2-Konzept | alle Segmente eines Docs |
| Stage 4 Input | Stage-3-Body + Stage-2-Metadaten | Stage-3-Body + Doc-Metadaten |
| `merged_from` | aus Stage 2 | immer `[]` |
| Summary-Key | `batches_processed` | `docs_processed` |

---

## Scope

### Geänderte Dateien

- `pipeline/phase_8_synthesis.py` — Hauptimplementierung
- `pipeline/__main__.py` — Dispatch + Console-Output
- `tests/test_phase_8_synthesis.py` — Tests aktualisieren

### Nicht geändert

- `pipeline/phase_7_batches.py` — Batch-Logik bleibt (für Gate-1-Review)
- `pipeline/schemas.py` — kein Schema-Bruch
- Prompt-Files — Stage-3/4-Prompts unverändert
- Config — keine neuen Config-Keys

---

## Akzeptanzkriterien

- [x] `run_phase_8` iteriert über Docs aus `segments.jsonl`, nicht über Batch-Files
- [x] Stage 1 + Stage 2 werden nicht aufgerufen (Funktionen bleiben als deprecated)
- [x] `merged_from` ist in jedem generierten Frontmatter `[]`
- [x] `sources_docs` enthält genau die Source-Doc-ID
- [x] Summary-Dict enthält `docs_processed` (statt `batches_processed`)
- [x] `pytest` grün (285 Tests)
- [x] `ruff check` + `ruff format` clean
- [x] `mypy` — keine neuen Fehler in geänderten Dateien

---

## Gate

🛑 Vor Merge nach `main` — Block-Ende-Bericht + explizite Freigabe.

---

## Änderungs-Log

- 2026-05-29 — Initial
