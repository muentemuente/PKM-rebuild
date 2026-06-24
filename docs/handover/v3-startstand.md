---
title: v3-Startstand — Realstand-Verifikation (WP0 Phase A)
slug: v3-startstand
status: stable
created: 2026-06-23
updated: 2026-06-23
plan: Projektplan_pipeline-v3.md
zweck: Faktenbasierter Live-Realstand vor dem v3-Zyklus. Ground Truth für Doku-Abgleich (WP0 Phase B). Read-only erhoben.
---

# v3-Startstand (2026-06-23)

Read-only erhobener Realstand. **Messwerte sind Ground Truth** — bei Konflikt mit alter Doku gewinnt diese Datei. Erhoben auf Branch `feat/pipeline-v3-foundation` (von `main @ 964d02b`).

---

## 1. Git

| Fakt | Wert |
|---|---|
| HEAD (main) | `964d02b` (Merge PR #33 `feat/process-orchestrator`) |
| Arbeits-Branch | `feat/pipeline-v3-foundation` |
| main sauber | ja (nur untracked: `AUDIT.md`, `Zielbeschreibung_*.md`, `docs/Projektplan_pipeline-v3.md`, `docs/audit/`) |
| Ungemergte Branches | remote+local: `docs/curation-log-sc007`, `docs/phase1-composability`, `docs/wp4b-logs`; nur local: `feat/wp4a-vault-audit-tooling` |

Die ungemergten Branches sind Altstände; keine Bereinigung in diesem Task (out of scope).

---

## 2. v2-Realstand (pro Modul)

Alle drei v2-Kernmodule existieren und sind getestet → **v2 ist real weiter umgesetzt als der „nicht verifiziert"-Vorbehalt im Plan annahm.**

| v2-WP / Modul | Datei | Tests | Reife |
|---|---|---|---|
| Taxonomie-SSoT (D1) | `pipeline/taxonomy.py` + `taxonomy_migrate.py` | `test_taxonomy.py` (15), `test_taxonomy_migrate.py` (6), `test_categories_ssot.py`, `test_pkm_common_ssot.py` (4) | **fertig** — SSoT aus `config/{enums,categories,tag_vocabulary}.yaml`, Loader-Facade, Runtime-Membership-Check, Rename+Migration |
| Restructure (LLM) | `pipeline/restructure.py` + `batch_restructure.py` | `test_restructure_resilience.py` (5), `test_restructure_review.py` (10), `test_type_aware_restructure.py` (7) | **fertig** — typ-bewusst, Reasoning aus, Resilienz |
| Process-Orchestrator | `pipeline/process_orchestrator.py` | `test_process_orchestrator.py` (8) | **fertig** — universeller Erstverarbeitungs-Pfad (PR #33) |
| Vault-Audit/Repair (9-Regel) | `pipeline/vault_audit.py` | `test_vault_audit.py` (46) | **fertig** (D15 — hohe LOC, Grenzfall im Audit) |
| Format/Repair/Review | `format_vault.py`, `transforms.py`, `driver.py`, `frontmatter_audit.py`, `promotion.py` | div. (`test_transforms.py` 15, `test_promotion.py` 8, …) | **fertig** |

**D1-Befund (relevant für WP2):** Taxonomie-SSoT ist bereits vollständig (`config/`-SSoT + `taxonomy.py`-Facade + Lock-in-Tests). → **WP2 entfällt voraussichtlich** (Plan §5: „Nur falls WP0 zeigt, dass D1 noch nicht erfüllt ist").

---

## 3. Qualität (Quality-Gates)

| Gate | Kommando | Ergebnis |
|---|---|---|
| Tests | `pytest -q` | **738 passed** |
| Lint | `ruff check .` | **clean** (All checks passed) |
| Format | `ruff format --check .` | **clean** (83 files already formatted) |
| Typen Kern | `mypy pipeline/` | **clean** (34 source files, no issues) |
| Typen Scripts | `mypy pipeline/ scripts/` | **8 Fehler in 2 Dateien** (pre-existing, s.u.) |

**mypy-scripts-Befund (kein G-A-STOP — kein Test-rot/Schema-Bruch/Daten-Inkonsistenz):**
- `scripts/rebuild_indices.py`: 3 (no-untyped-def, var-annotated, no-untyped-call)
- `scripts/apply_tag_map.py`: 5 (no-untyped-def ×3, type-arg)

Pre-existing Type-Schulden in Helper-Skripten, nicht im Pipeline-Kern. **Reparatur-Kandidat für WP1** (Plan-DoD „mypy clean"), nicht Teil dieses Doku-Tasks.
Zusatz: `pyproject.toml` meldet `note: unused section(s): module = ['hdbscan.*', 'umap.*']` → verwaiste mypy-Overrides der verworfenen viz-Phase (D16, WP1-Kandidat).

---

## 4. Vault-Realität (Brain-Vault, Ort #3)

`pipeline._paths.BRAIN_VAULT` = `/Users/muente/Zentrale/09_Brain-Vault` (existiert).

**Definition Artikel-Count:** `.md`-Dateien in den nummerierten Taxonomie-Ordnern, **ohne** `_index.md`, **ohne** `_`-Präfix-Ordner (`_assets`, `_attic`) und versteckte (`.obsidian`, `.smart-env`).

| Größe | Wert |
|---|---|
| **Artikel-Count (kanonisch)** | **181** |
| `_index.md` | 14 |
| `_attic/` (archiviert, nicht gezählt) | 6 |
| `17_unsortiert/` | 0 (leer) |
| `_assets/` | 0 `.md` |
| Genutzte Inhalts-Ordner | 14 (00_Meta, 01–06, 09–14, 16) |

Verteilung: 00_Meta 15 · 01_Grundlagen 36 · 02_Webentwicklung 8 · 03_Betriebssysteme 8 · 04_Protokolle 2 · 05_Dateitypen 5 · 06_Methoden 7 · 09_KI 16 · 10_Datenarchitektur 12 · 11_Dokumentenverarbeitung 5 · 12_Wissensmodellierung 4 · 13_Visualisierung 16 · 14_Automatisierung 39 · 16_Kunst-Kultur 8 = **181**.

> Die alten Doku-Zahlen (180 bzw. ~186) sind **superseded**: kanonisch gilt **181** (Live-Messung 2026-06-23).

---

## 5. Vokabular-Realität

| Fakt | Wert |
|---|---|
| **Aktives Tag-Vokabular** | **149 Tags** in 17 Sektionen (`config/tag_vocabulary.yaml`) |
| SSoT-Validierung | `manage_vocab validate` → ✓ konsistent, keine Drift |
| Kategorien | 18 (`config/categories.yaml`) inkl. `17_unsortiert` Catch-all |
| Type-Enum | 4 (`process-document`, `knowledge-article`, `compact-reference`, `gedanke`) |

> Die „47" (Kern-Vokabular) ist historisch; **kanonisch gilt 149** (aktives SSoT-Vokabular). Off-Vocab-Tags im Bestand bleiben Gegenstand der WP4-Tag-Remediation, nicht dieses Tasks.

---

## 6. Triage / Frontmatter (go-forward-Datenordner)

`scripts/pkm_triage.py` + `check_frontmatter.py` lesen aus `~/projects/aktiv/pkm-pipeline/` (Ort #2, zwischen Läufen leer):

| Fakt | Wert |
|---|---|
| Korpus-Slugs / Vault-Slugs (Ort #2) | 0 / 0 (erwartet — Lauf abgeschlossen, Bestand liegt in Ort #3) |
| Orphan-Drafts | 1 (bekannter benigner Rest, vgl. `runner_false_fail_bugs`) |
| Frontmatter-Check | 1 Draft-Stem ohne `.json` (derselbe Orphan) |
| Enum-Konformität | keine Drift (SSoT konsistent, §5) |

Kein G-A-Defekt — die Leere von Ort #2 ist der erwartete Zustand zwischen inkrementellen Läufen.

---

## 7. G-A-Bewertung

**Kein G-A-STOP.** Keine echten Defekte (kein Test rot, kein Schema-Bruch, keine Daten-Inkonsistenz). Einziger offener Qualitätspunkt: 8 pre-existing mypy-Fehler in `scripts/` + verwaiste viz-mypy-Overrides → als **WP1-Reparatur-Kandidaten** vermerkt, blockieren diesen Doku-Task nicht.

---

## 8. Ground-Truth-Zahlen für Phase B (Doku-Abgleich)

| Drift | Kanonischer Wert |
|---|---|
| B1 Artikel-Count | **181** |
| B2 Vokabular | **149** Tags |
| Kategorien | 18 |
| Type-Enum | 4 |
| Tests | 738 grün |
