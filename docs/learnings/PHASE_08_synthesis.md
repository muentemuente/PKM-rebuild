---
title: Reflexion Phase 8 — Qwen-Veredelung (Option B)
slug: phase-08-synthesis
phase_id: 8
phase_status: done
status: draft
created: 2026-06-03
updated: 2026-06-04
---

# Phase 8 — Qwen-Veredelung (Option B)

Konsolidierte Reflexion. Quellen: `docs/PRE_PHASE9_HARDENING.md`, `data/02_pipeline_output/r2_diagnostic_report.md`, `triage_report.md`.

## 1. Endstand

| Größe | Wert |
|---|---|
| Vault-ready Drafts | **180** (0 Schema-Issues, alle `category` ∈ ALLOWED) |
| Zurückgestellt (`_hold/`) | 19 Gedanken (deferred → `docs/FUTURE_RUN.md`) |
| Exkludiert (`_excluded/`) | 3 (denkschulen + 2 Stage-3-Hangs) |
| Test-Suite | 359 grün, ruff sauber |

## 2. Architektur-Pivot: Option A → Option B

**Option A (verworfen):** Cluster-Batch → Stage 1 (Cluster-Analyse) → Stage 2 (Merge) → Stage 3 (Synthese) → Stage 4. Cross-Doc-Merge mehrerer Quellen zu einem Concept.

**Option B (umgesetzt):** **Pro-Doc**-Veredelung, 1 Doc → 1 Concept, **kein** Merge. `merged_from` immer leer. Nur **Stage 3 + Stage 4** aktiv; Stage 1/2 deprecated, Review-Gate 2 entfällt.

**Routing je Doc (deterministisch):**

| Pfad | Bedingung | Verhalten |
|---|---|---|
| `passthrough` | Code OR ≥1 Tabelle OR ≥3 Headings | Body 1:1, kein LLM-Call, nur Stage 4 |
| `stage3` | reine Prosa | LLM-Veredelung + Stage 4 |
| `gedanken` | `doc_type_guess.label == "gedanke"` | Minimal-Frontmatter, kein Stage 3 |

## 3. Clustering-Verwurf (R9 realisiert)

Embedding-/HDBSCAN-Clustering als Vault-Strukturprinzip **verworfen** — der Korpus hat keine inhärente Cluster-Struktur. Evidenz (`similarity_threshold`):

- `0.85` → 0 echte Cluster
- `0.65` → Mega-Cluster (168 Docs in `C_cluster-0000`)
- `0.75` → 85,9 % unsortiert

Konsequenz: Vault-Ordner sind ein **fixes kuratiertes 16er-Schema**; `category` aus Qwen-Stage-4 + **deterministischem Mapping** (E5). Embeddings dienen nur noch der Redundanz-Erkennung.

## 4. Triage-Toolchain

| Skript | Rolle |
|---|---|
| `pkm_triage.py` | Master — Korpus↔Drafts↔Vault, Action-Routing, erzeugt Runner-Batches |
| `draft_inventory.py` | tiefe Pro-Draft-Qualitätsklassifikation (9 Klassen) |
| `phase8_runner.py` | Batch-Runner (subprocess, State-File, autoritative Verifikation) |
| `check_frontmatter.py` | Frontmatter-Konsistenz (`.md` ↔ `.frontmatter.json`) |
| `apply_category_mapping.py` | deterministisches Category-Mapping (E5) |
| `r2_diagnose.py` | read-only Naming-/Slug-Diagnose |

**Actions:** `IN_VAULT` · `READY_TO_MIGRATE` · `POSTPROCESS` · `RERUN_LM` · `FRESH_RUN` (+ `ORPHAN_DRAFT`, `EXCLUDED`).

**Runner-Robustheit:** subprocess statt Shell-String (kein Quoting-Risiko) · File-Write statt Pipe (kein SIGPIPE) · State-File pro Batch (Resume) · Signal-Handler · Abort nach 5 consecutive Fails.

## 5. Bug-Katalog

| Bug | Ursache | Fix |
|---|---|---|
| Tilde-Assignment | `VAR=~/...` triggert CC-Security-Wrapper | `$HOME` in Assignments (CLAUDE.md §12) |
| SIGPIPE | `\| head` schloss Pipe mid-flight | File-Write statt Pipe |
| zsh-Quoting | Leerzeichen in Dateinamen | subprocess-Argumentliste |
| **NFD-Slug (E2)** | macOS-NFD-Dateinamen + Composed-Umlaut-Tabelle → `ä→a` statt `ae` → false-Orphan | NFC-Normalisierung vor Umlaut-Map; Runner-Slug angeglichen |
| **Timeout-Boundary** | `verify_outputs` false-FAIL an 1800s-Grenze trotz geschriebenem Draft | `verify_outputs` autoritativ: Files existieren → success |
| **Truncation** | 60-Cap divergierte Pipeline- vs. Batch-Slug | kanonische Ableitung + Cap im Runner repliziert (Test-Drift-Guard); 0 echte Kollisionen |
| Hidden Meta | `.meta.json` in Skip-Check übersehen | Skip prüft body + frontmatter meta |
| **gedanke-Enum (E1)** | finales `type`-Enum kannte `gedanke` nicht → Endlos-RERUN_LM | `gedanke` in Pydantic + 3 Validatoren |
| Stage-4-Dedup | Resume nummerierte existierende Slugs neu | existierender Slug bei Resume in `used_slugs` |

## 6. Entscheidungen E1–E5

| ID | Entscheidung |
|---|---|
| E1 | `gedanke` als gültiger `type`-Wert (Pydantic + Validatoren), statt Prompt-Zwang |
| E2 | Slug-Kanonisierung: NFC vor Umlaut-Map, 60-Cap, `_unique_slug`; Runner-Slug angeglichen |
| E3 | `03_drafts`-Intermediates (`.body.md`, `.frontmatter.json`) behalten — Phase-9-Input |
| E4 | `verify_outputs` autoritativ (Draft-Existenz schlägt Returncode) |
| E5 | `category` deterministisch via Mapping (`apply_category_mapping.py`), nicht per Prompt |

## 7. Test-Suite

359 Tests grün (vorher 326; +33 für NFD-Slug, Runner-Drift-Guard/Authoritative, gedanke-Type). `ruff check`/`format` sauber. Drift-Guard: `canonical_ck_slug` im Runner wird gegen die Pipeline-Ableitung getestet.

## 8. Übergabe an Phase 9

GO. 180 Drafts integer, Isolation sauber (19 `_hold` + 3 `_excluded`), Category-Mapping freigegeben + angewandt, Backups gesetzt. Deferred: `docs/FUTURE_RUN.md`.
