---
title: Pre-Phase-9 Hardening — Cleanup- und Redundanz-Bericht
slug: pre-phase9-hardening
status: draft
created: 2026-06-04
updated: 2026-06-04
---

# Pre-Phase-9 Hardening (2026-06-04)

Begleitbericht zu WP1–WP3 vor Phase 9. Code-Fixes und Tests sind im Branch
`chore/pre-phase9-hardening` committet; dieser Bericht hält die nicht-Code-
Ergebnisse (Cleanup, Redundanz-Empfehlung, Intermediates) fest.

## WP1 — Code-Hardening (Zusammenfassung)

| Fix | Ort | Wirkung |
|---|---|---|
| E2 — NFC-Slug | `pipeline/phase_1_inventory.py:_filename_to_slug` | NFC-Normalisierung vor Umlaut-Map. NFD-Dateinamen (macOS) ergaben vorher `ä→a` statt `ä→ae`; Root-Cause des false-Orphan. |
| Runner-Slug + Boundary | `scripts/phase8_runner.py` | `canonical_ck_slug` repliziert die Pipeline-Ableitung (Umlaut + 60-Cap); `verify_outputs` ist jetzt autoritativ — existierende Drafts gelten als Erfolg, kein false-FAIL an der 1800s-Boundary. |
| E1 — gedanke | `pkm_triage.py`, `check_frontmatter.py`, `draft_inventory.py` (`ALLOWED_TYPE`) | `type: gedanke` ist gültig. Pydantic `FrontmatterDraft.type` führte den Wert bereits. |

Tests: +33 (NFD-Slug, Runner-Drift-Guard, Runner-Authoritative, gedanke-Type).
Gesamt 359 grün, `ruff check`/`format` sauber.

## WP2 — Config/Ignore

- `pipeline.config.yaml`: stage1/stage2 (Temperatur + max_tokens) als
  **DEPRECATED (Option B)** inline markiert; `json_mode`, `timeout_seconds`,
  `stage3 max_tokens` inline kommentiert.
- **Nicht geprunt:** Das Schema (`config.py:QwenTemperatureConfig`/
  `QwenMaxTokensConfig`) verlangt stage1/stage2 als Pflichtfelder. Entfernen
  bräche die Pydantic-Validation. Vollständiges Prunen erst nach koordiniertem
  Schema-Umbau (eigener Task).
- `.gitignore`: `.DS_Store`, `data/`, `backups/`, `*.meta.json` bereits
  abgedeckt — keine Änderung nötig.

## WP3 — File-Cleanup

Archiviert nach `backups/archive_20260604_1852/` (verschoben, nicht gelöscht;
alles regenerierbar):

| Artefakt | Grund |
|---|---|
| `triage/rerun_batches/` (7 Files) | RERUN_LM=0; stale (Jun 2 + Jun 4 gemischt). Regenerierbar via `pkm_triage.py`. |
| `triage/fresh_run_batches/` (11 Files) | Stale Batches aus älteren Triage-Läufen. Regenerierbar. |
| `phase8_logs/` (11 Batch-Dirs, 748 KiB) | Logs/State abgeschlossener Läufe. |
| `04_vault/.DS_Store` | OS-Junk in `data/` — per Direktive archiviert statt gelöscht. |

Repo-`.DS_Store` (6 Stück, untracked, außerhalb `data/`) hart entfernt.

### Intermediates in `03_drafts/` (E3 — behalten)

| Gruppe | Files | Größe |
|---|---:|---:|
| `.md` (Artikel) | 180 | 2694 KiB |
| `.body.md` | 180 | 2488 KiB |
| `.frontmatter.json` | 180 | 251 KiB |
| hidden `.meta.json` | 156 | 24 KiB |

`03_drafts` gesamt (inkl. `_hold`): 7.4 MB. Bewusst behalten — `.body.md` und
`.frontmatter.json` sind Phase-9-Input.

## Skript-Redundanz: `draft_inventory.py` ↔ `pkm_triage.py`

**Befund:** 8 gleichnamige Funktionen in beiden Modulen (je ~850–875 LOC):
`check_schema`, `compare_frontmatter`, `compute_body_metrics`,
`parse_json_file`, `parse_yaml_text`, `split_md`, `write_report`, `main`.
Die `ALLOWED_*`-Enum-Sets sind ebenfalls dupliziert — der E1-Fix musste in
beiden (plus `check_frontmatter.py`) parallel nachgezogen werden, klassisches
Drift-Risiko.

**Distinkte Zwecke (kein Modul ist überflüssig):**
- `pkm_triage.py` — operativ: Korpus↔Drafts↔Vault-Reconcile, Action-Routing
  (READY/POSTPROCESS/RERUN_LM/FRESH_RUN), erzeugt die Runner-Batches.
- `draft_inventory.py` — diagnostisch: tiefe Pro-Draft-Qualitätsklassifikation
  (9 Klassen), reine Drafts-Sicht.

**Empfehlung (KEIN Blind-Delete):** Gemeinsame Helfer + Enum-Sets in ein
geteiltes Modul (`scripts/_pkm_common.py`) extrahieren, von beiden importiert.
Eliminiert das Drift-Risiko (eine Quelle für `ALLOWED_TYPE` etc.), ohne die
distinkten Tools zusammenzulegen. Eigener Refactor-Task nach Phase 9.
