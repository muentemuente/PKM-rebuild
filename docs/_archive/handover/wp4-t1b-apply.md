---
title: WP4 · T1b — Klassifikation angewendet (work/-Stage)
slug: wp4-t1b-apply
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T1b-apply.md
gate: 4-1b
---

# WP4 · T1b — Anwendung im work/-Stage

Mutation **nur** in der work-Kopie — **Live-Vault unangetastet**. Export ist
Gate-4-1b-pflichtig (separater Schritt, hier NICHT enthalten).

- Snapshot (raw, Rollback): `…/archive/backups/wp4_T1_master_20260624_231006/raw/` (207 .md, SHA-256-Manifest). **O4 vom Owner bestätigt.**
- work-Stage: `…/work/wp4_t1b/vault/` · `diff_report.md` · `scan_before/` · `scan_after/`

## Angewendet (Gate-4-1a-fix)

| # | slug | type → | category → | Move | Body-Byte |
|---|---|---|---|---|---|
| 1 | metadata-pipeline-project-summary | knowledge-article→process-document | …→meta | → `00_Meta/` | identisch |
| 2 | metadata-analyzer-projektauftrag | →process-document | →meta | → `00_Meta/` | identisch |
| 3 | metadaten-pipeline-projektauftrag | →process-document | →meta | → `00_Meta/` | identisch |
| 4 | metadata-processor-pipeline | →process-document | datenarchitektur→meta | → `00_Meta/` | identisch |
| 5 | metadata-analyzer-idea | →process-document | grundlagen→meta | → `00_Meta/` | identisch |
| 6 | metadaten-toolkit-komplette-anleitung | →process-document | unverändert | nein | identisch |
| 7 | quotes-idioms-expressions | →compact-reference | unverändert | nein | identisch |

`updated:` je File → `2026-06-24`. Body (alle Bytes nach Frontmatter) byte-identisch
gegen Live-Quelle für alle 7 (Test im Apply-Skript, 0 Abweichungen).

## Verifikation

| Prüfung | Ergebnis |
|---|---|
| Synthese-Korpus (realer Filter, Ordner ODER `category: meta`) | gescannt **171 → 166**; ausgeschlossen **21 → 26** |
| #1–5 ausgeschlossen | ✅ alle als „Ordner 00_Meta" im scan_after-Report |
| #6/#7 weiterhin im Korpus | ✅ nicht in der Ausschluss-Liste |
| `00_Meta/_index.md` erzeugt? | **nein** (Vault-Standard §4 gewahrt) |
| Schutzbereich `_attic/` | 0 Diffs vs Snapshot |
| Schutzbereich `15_Gedanken/` | existiert im Vault nicht (keine Gedanken) — nicht erzeugt |
| Inbound-Wikilinks auf die 7 | 0 (T1a) → Moves brechen keinen Link |
| Idempotenz (2. Lauf) | 0 Änderung (SHA-256-Diff leer) |
| ruff `pipeline/` | green; `scripts/`-Baseline (113, pre-existing) von T1b nicht berührt |
| Code-Änderung | **keine** (nur work/-Daten + docs) |

Export auf Live-Vault: **ausstehend** (Owner-Freigabe Gate 4-1b).
