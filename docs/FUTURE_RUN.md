---
title: FUTURE_RUN — Backlog nächster Pipeline-Lauf
slug: future-run
status: draft
created: 2026-06-04
updated: 2026-06-04
---

# FUTURE_RUN — Backlog nächster Pipeline-Lauf

Sammelpunkt für alles, was **nach** dem aktuellen Projekt-Abschluss (Phase 9 mit den 180 fertigen Drafts) in einem späteren Lauf verarbeitet wird: geparkte Gedanken, bekannte Hangs und neu hinzukommende Korpus-Files.

Die 180 fertigen Drafts werden **nicht** erneut verarbeitet — Fixes (E1/E2) gelten nur für künftige Läufe.

---

## Re-Run-Set

### 19 `_hold`-Gedanken (`03_drafts/_hold/`)
Zurückgestellte Gedanken-Drafts, `type: gedanke`. Das Schema akzeptiert den Wert seit **E1** (Pydantic + Validatoren), ein Re-Run würde also nicht erneut am Type-Enum scheitern. Manifest: `03_drafts/_hold/HOLD_MANIFEST.md`. Verarbeitung über den Gedanken-Sonderpfad (Minimal-Frontmatter, kein Stage 3).

### 2 Hangs (`01_corpus_input/_excluded/`)
- `Prompt-Verbesserung.md` (`prompt-verbesserung`)
- `prompts_text_stil_grammatik.md` (`prompts-text-stil-grammatik`)

**Root-Cause:** Meta-/Prompt-Inhalt triggert im ersten Stage-3-Call einen Reasoning-Loop (das Modell „denkt über Prompts nach", statt zu veredeln). **Mitigation für den Re-Run:** entweder hart auf `passthrough` routen **oder** Reasoning/`max_tokens` je Call hart cappen. **Timeout-Hochsetzen wirkt nicht** — der Loop terminiert nicht von selbst.

> Das dritte `_excluded`-File, `denkschulen_ueberblick_und_einfuehrung.md`, ist ein bewusst exkludiertes Survey-Doc (15.770 Wörter, 394 H2), **kein** Hang — bleibt regulär außerhalb der Pipeline.

### Neue Korpus-Files (TBD)
Künftig hinzukommende Markdown-Files. Slug-Ableitung ist seit **E2** NFD-sicher.

---

## Voraussetzungen (erfüllt)

| Fix | Status |
|---|---|
| Slug-Kanonisierung NFC vor Umlaut-Map (E2) | ✅ `phase_1_inventory`, Runner-Slug angeglichen |
| `gedanke`-Type-Enum (E1) | ✅ Pydantic + 3 Validatoren |
| Runner `verify_outputs` autoritativ (kein false-FAIL an Timeout-Boundary) | ✅ `phase8_runner.py` |

---

## Offene technische Schulden (vor/während Re-Run angehen)

- **Vollprune der Stage-1/2-Config:** stage1/stage2 (Temperatur + max_tokens) sind als DEPRECATED markiert, aber noch Pflichtfelder im Schema (`config.py`). Entfernen braucht koordinierten Schema-Umbau.
- **`scripts/_pkm_common.py`:** `draft_inventory.py` und `pkm_triage.py` teilen 8 duplizierte Helfer + Enum-Sets (`ALLOWED_TYPE` musste 3× nachgezogen werden). Extraktion in ein gemeinsames Modul eliminiert das Drift-Risiko. Details: `docs/PRE_PHASE9_HARDENING.md`.

---

## Änderungs-Log

- 2026-06-04 — Initial-Version (Re-Run-Set: 19 Gedanken + 2 Hangs; E1/E2/Runner-Voraussetzungen; offene Schulden)
