---
title: PKM-rebuild — Projektstand
slug: project-status
status: stable
created: 2026-05-28
updated: 2026-06-25
---

# PKM-rebuild — Projektstand (2026-06-25)

Aktueller Stand, Architektur, Qualität und offene Punkte. Maßgeblicher Detailstand der letzten Session: `docs/handover/post-wp4-stand.md`.

> **Zyklen:** Basis-Pipeline (Phasen 0–12) **abgeschlossen** (Fundament). Darauf der **v3-Zyklus** (Wissensqualität — Stabilisierung, additive Synthese/MOC, Bestands-Remediation): **WP0–WP4 abgeschlossen + gemergt** (WP2 entfiel). Plan: `Projektplan_pipeline-v3.md`.

---

## 0. Aktueller Stand (2026-06-25)

**Basis-Pipeline (0–12, Option B — Pro-Doc, kein Cross-Doc-Merge) abgeschlossen. v3-Zyklus WP0–WP4 gemergt. Vault produktiv und idempotent. Menschlich verbleibend: Qualitätsstufe-2-Review.**

| Größe | Wert |
|---|---|
| Vault-Artikel (Brain-Vault #3) | **181 + 5 MOC** in 14 genutzten Ordnern (0 Pydantic-Fails, 0 SHA-Dups) |
| Ordner-Struktur | 16 thematische + `17_unsortiert` (Catch-all) + `00_Maps/` (MOCs) + `00_Meta/` |
| Idempotenz | `pkm regenerate-indices` = 0/14 (phase_9-Format, archive-before) |
| Test-Suite | **789** grün (`def test_`; 826 passed / 2 skipped parametrisiert), `ruff` clean, `mypy pipeline/` clean |
| Code-Schuld | `scripts/` 8 pre-existing mypy-Fehler (WP1-Backlog, kein Blocker) |
| Architektur | Option B (Pro-Doc, kein Merge); Embedding-Clustering **verworfen** (R9) |
| Taxonomie-SSoT | `config/`: `tag_vocabulary.yaml` (149 Tags), `categories.yaml`, `enums.yaml` |
| Entrypoint (kanonisch) | `pkm process` (O1) — universelle Erstverarbeitung, resume-fähig |
| Backup | Vault #3 per Time Machine täglich gesichert (O4 erfüllt) |

**DoD (`scripts/dod_check.py`):** automatisch 9 ✅ / 1 ⚠️ (dokumentierte Kleinordner-Ausnahme); menschlich verbleibend: Qualitätsstufe-2-Review (Backup 2. Medium ist über Time Machine erfüllt).

> **Tag-Befund (WP4):** Content-Tags sind 100 % konform zum 149er-Vokabular (0 OOV). Die 12 OOV-Tags in `00_Meta` (changelog/naming/review/…) sind kohärentes Meta-Vokabular **by design** außerhalb des Content-Vokabulars — kein Blocker (Disposition CLOSED, `post-wp4-stand.md`).

---

## 1. Phasen-Übersicht (Basis-Pipeline)

| Phase | Name | Status | Commit |
|---|---|---|---|
| 0 | Setup (Git, Toolchain, Backup, Doku) | ✅ done | `e1f3c35` |
| 1 | Inventar | ✅ done | `7c9a640` |
| 2 | Normalisierung | ✅ done | `7fd4ee3` |
| 3 | Strukturextraktion | ✅ done | `7af5c95` |
| 4 | Segmentierung | ✅ done | `87e7311` |
| 5 | Redundanz-Erkennung (Hash + TF-IDF) | ✅ done | `d9cb420` |
| 6 | Embeddings (mpnet; Cluster-Prep verworfen, R9) | ✅ done | `74de985` |
| 7 | LLM-Batch-Bildung (Token-Budget-Splits) | ✅ done | `231a2ff` |
| 8 | Qwen-Veredelung (Option B: Routing + Stage 3/4 pro Doc) | ✅ done | (mehrere) |
| 9 | Vault-Aufbau (Ordner, `_index.md`, Wikilinks) | ✅ done | `493b2f0` |
| 10 | Kontroll-Berichte + DoD-Check | ✅ done | `03ecaaf` |
| 11 | Cleanup (AP1–5) | ✅ done | (feature/cleanup) |
| 12 | Finalisierung (Workspace, `17_unsortiert`, ingest/manage_vocab, Docs) | ✅ done | (feature/finalize) |

---

## 2. v3-Zyklus (Wissensqualität)

Aufgesetzt auf der abgeschlossenen Basis-Pipeline. Fokus: Stabilität, additive Synthese, kontrollierte Bestands-Remediation — alles unter den Gates D4/D6/D7.

| WP | Inhalt | Stand |
|---|---|---|
| **WP0** Ist-Stand-Bereinigung | Doku-/Pfad-Drift weg; **EIN** Artikel-Count (181), **EIN** Vokabular-Stand (149); v2-Plan nach `_archive/` (superseded) | ✅ |
| **WP1** Stabilisierung | `structlog` verdrahtet (`work/pipeline.log`); Entrypoint kanonisch `pkm process` (O1); `scripts/` mypy-Rest als Backlog dokumentiert | ✅ |
| **WP2** Taxonomie-SSoT | **entfällt** — D1 (single canonical taxonomy) bereits durch `config/` erfüllt | n/a |
| **WP3** Synthese | 5 additive MOCs in `00_Maps/` (`status: draft`), gemergt; Korpus-Filter via `doc_type`/Ordner (`_attic`/`00_Meta` raus) | ✅ |
| **WP4** Bestands-Remediation | gemergt (PR #39 + Prune #40 + Post-WP4-Pass) | ✅ |

**WP4-Bilanz (gegateter, snapshot-gesicherter Vault-weiter Einmal-Pass, D7):**

| Tier | Ergebnis |
|---|---|
| T0 Verifikation | Audit/Plan als Hypothese geprüft (verify-first) |
| T1 Klassifikation | 7 Frontmatter-Reklassifikationen live; 5 → `00_Meta/_projektdoku/`; Body byte-identisch |
| T2 Dubletten | NLP-Paar verifiziert **distinkt** (D) → 0 Mutationen |
| T3 Tags/Format | Tags **No-op** (Content 100 % konform); Format **deferred/declined** (mdformat bricht Alias-Wikilinks) |
| T4 restructure | **1** echter Fix (`datenaufnahme`, 6× H1→H2) |
| T5 Indizes | regeneriert via `pkm regenerate-indices` |

**Kernlearning:** Verify-first hat den halben Backlog als stale entlarvt (Dubletten 6→0, Fehlklass. ~8→7, „12 OOV"-Content-Tags→0, restructure-Roh 26→1). Größte Hebelwirkung lag im Prüfen, nicht im Mutieren.

**Post-WP4-Dispositionen:** mdformat-wikilink-safe **DECLINED** (Vault bleibt unformatiert, funktional ok); 00_Meta-Governance-Tags **CLOSED** (niedriger Wert); Monolith-B → nlp-Serie **deferred** (eigenes Synthese-WP, `docs/handover/ideen-backlog.md`).

---

## 3. Phasen-Implementierung (Referenz)

Vollständig: `docs/02_pipeline_spec.md`. Logik je Phase (deterministisch, idempotent via Input-Hash, `--force` ignoriert Cache):

| Phase | Modul | Input → Output | Kernlogik |
|---|---|---|---|
| 1 Inventar | `phase_1_inventory.py` | Korpus → `files_manifest.jsonl` | `doc_id = D_<slug>` (Kollision → `_2`), SHA-256, `exclude_patterns` |
| 2 Normalisierung | `phase_2_normalize.py` | Manifest → `cleaned_documents.jsonl` | CRLF→LF, Tab→4 Spaces, max 3 Leerzeilen, Frontmatter-Extraktion; Code-Blöcke hash-identisch bewahrt |
| 3 Struktur | `phase_3_structure.py` | cleaned → `documents_structured.jsonl` | Headings/Code/Tabellen/Links/Images via `mistune`; heuristischer `doc_type_guess` (+ `book`-Label ab 8000 W) |
| 4 Segmentierung | `phase_4_segment.py` | cleaned + manifest → `segments.jsonl` | Split nach Headings; Code/Tabellen/Listen nie zerrissen; min 150 / target 900 / max 1500 Wörter; `heading_path`-Breadcrumb |
| 5 Redundanz | `phase_5_redundancy.py` | cleaned + segments → `exact_duplicates` + `near_duplicate_edges` | SHA-256-Exact + TF-IDF (Threshold **0.72**, n-gram [1,2]); Upper-Triangle |
| 6 Embeddings | `phase_6_embeddings.py` | segments → `embeddings.parquet` | mpnet-base (768-dim, MPS); nur Redundanz; **Clustering verworfen** (R9), nur `min_cluster_size`→`unsortiert` |
| 7 Batches | `phase_7_batches.py` | segments + edges → `batches/*.md` | Token-Budget-Splits (`max_input_tokens` 35000); kein Cluster-Merge |
| 8 Qwen (Option B) | `phase_8_synthesis.py`, `phase8_runner.py`, `pkm_triage.py` | batches/Doc → Drafts `CK_<slug>.*` | Pro-Doc-Routing `passthrough`/`stage3`/`gedanken` → Stage 4 Frontmatter; `json_mode=false`, Thinking-Strip, Pydantic-Validation; `merged_from` immer leer |
| 9 Vault-Aufbau | `phase_9_vault_build.py` | Drafts → Vault | `category` (Stage 4) + deterministisches Mapping auf 16 Ordner + `17_unsortiert`; `_index.md`; Wikilink-Validierung; Build-Tier repair→format→audit (nur `output/`, nie Live-Vault) |
| 10 Berichte | `phase_10_reports.py` | Vault → corpus/duplicate/cluster-Reports + `DOD_CHECK.md` | Vault-Ground-Truth-Zählung (distinct `doc_id`) |

**v3-Module (über Basis hinaus):** `process_orchestrator.py` (kanonischer `pkm process`), `orchestrator.py`/`run_flow.py`/`driver.py`, `restructure.py` + `batch_restructure.py` (typ-bewusst, Reasoning aus, v2-Prompts), `review.py`/`promotion.py` (Gates A–D, kein Auto-Promote), `redundancy_scan.py` + `synthesis_moc.py` (WP2/WP3), `taxonomy.py`/`vocab.py` (SSoT), `vault_audit.py`/`frontmatter_audit.py` (read-only), `regenerate_indices.py` (ersetzt `scripts/_deprecated/rebuild_indices.py`), `format_vault.py`/`fence_indented.py`, `ingest.py`/`ingest_md_download.py`.

---

## 4. Schemas (`pipeline/schemas.py`)

| Schema | Phase | Pflichtfelder (Auszug) |
|---|---|---|
| `DocumentRecord` | 1 | doc_id, path, sha256, size_bytes, word_count |
| `CleanedDocument` | 2 | doc_id, body, frontmatter, normalized_sha256 |
| `DocTypeGuess` / `StructuredDocumentRecord` | 3 | label (Literal), confidence, signals / title, headings, code_blocks |
| `SegmentRecord` | 4 | segment_id, doc_id, text, word_count, heading_path |
| `FrontmatterDraft` | 8 | title, slug, summary, type, doc_role, category, sources_docs, status, review_status, confidence, doc_version, created, updated, last_synthesized, prompt_version |

**Type-Enum (4 Werte):** `process-document | knowledge-article | compact-reference | gedanke`.
**Status:** `draft → review → stable → deprecated` · **Review-Status:** `ai_drafted → human_reviewed → verified`.

---

## 5. Konfiguration (verifiziert gegen `pipeline/pipeline.config.yaml`)

Pfade leben zentral in `pipeline/_paths.py` (nicht in der YAML). Override: `PKM_PIPELINE_ROOT`, `PKM_REPO_ROOT`, `PKM_BRAIN_VAULT`.

| Schlüssel | Wert |
|---|---|
| `qwen.model` / `context_window` | `qwen/qwen3.6-27b` / `49152` (~50K, Hard Limit 32 GB) |
| `qwen.json_mode` | `false` (Reasoning-Modell-Constraint, Block 0.D) |
| `qwen.prompt_version` | `v1` (Phase 8); `restructure.prompt_version` `v2` (typ-bewusst, `reasoning_effort: none`) |
| `embeddings.model` / `device` | `paraphrase-multilingual-mpnet-base-v2` / `mps` |
| `embeddings.similarity_threshold` | `0.65` |
| `redundancy.tfidf.threshold` | `0.72` |
| `redundancy_scan` (WP2) | `tfidf 0.72`, `embedding_dup 0.85`, `thematic_low 0.70`, `synthesis_min_members 3`; exclude `_attic`/`00_Meta` |
| `batching.max_input_tokens` | `35000` |
| `vault` Build-Tier | `repair_on_build` / `format_on_build` / `audit_on_build` = `true` (nur `output/`, nie Live-Vault) |
| `tags` | Vokabular `config/tag_vocabulary.yaml`; `strict_vocabulary: false`; 2–10 Tags/Artikel |

---

## 6. Datei-Layout (aktuell)

```
PKM-rebuild/                    ← Git, public (Ort #1)
├── README.md  CLAUDE.md  WAYFINDING.md  MANUAL_STEPS.md
├── Makefile  mise.toml  pyproject.toml
├── config/                     ← Taxonomie-SSoT (categories/enums/tag_vocabulary.yaml, tag_merge_map.json)
├── pipeline/                   ← Code + CLAUDE.md + pipeline.config.yaml
│   ├── phase_1..10_*.py        ← Basis-Pipeline
│   ├── process_orchestrator / orchestrator / run_flow / driver
│   ├── restructure / batch_restructure / review / promotion
│   ├── redundancy_scan / synthesis_moc / taxonomy / vocab
│   ├── vault_audit / frontmatter_audit / regenerate_indices / format_vault
│   └── _paths.py  schemas.py  config.py
├── prompts/                    ← v1 (Phase 8) + v2 (restructure) + schemas/, CLAUDE.md
├── scripts/                    ← manage_vocab, pkm_triage, dod_check, snapshot/restore.sh, … (_deprecated/rebuild_indices.py)
├── tests/                      ← 789 Tests (+ fixtures/)
└── docs/                       ← Projekt-Doku (s.u.)
    ├── 00_persona / 00b_arbeitsvereinbarung / 01_strategy / 02_pipeline_spec
    ├── 03_vault_standard / 04_qwen_prompts / 05_glossary / 06_claude_code_workflow / 06b_tool_routing / 07_backup_strategy
    ├── PROJECT_STATUS / Projektplan_pipeline-v3 / FUTURE_RUN / RUNBOOK_new_files
    ├── handover/   ← aktuell: post-wp4-stand.md, ideen-backlog.md (Rest = Historie)
    ├── learnings/  ← Phasen-Reflexionen (Historie)
    ├── vault_meta/ wayfinding/ reports/
    └── _archive/   ← superseded Artefakte
```

**Daten (außerhalb Git, Ort #2):** `~/projects/aktiv/pkm-pipeline/{input,work,drafts,review,output,archive}`.
**Produktiv-Vault (außerhalb Git, Ort #3):** `~/Zentrale/09_Brain-Vault/` (`pipeline._paths.BRAIN_VAULT`).

---

## 7. Code-Qualität

| Tool | Status |
|---|---|
| `pytest` | ✅ **789** grün (826 passed / 2 skipped parametrisiert) |
| `ruff check` / `ruff format` | ✅ clean |
| `mypy pipeline/` | ✅ clean |
| `mypy scripts/` | ⚠️ 8 pre-existing Fehler (WP1-Backlog, kein Laufzeitrisiko) |

---

## 8. Offene Punkte

| Punkt | Status |
|---|---|
| **Qualitätsstufe-2-Review** der Artikel (`draft → review/stable`) | offen, menschlich — **kein** Auto-Promote durch CC |
| `scripts/` mypy (8 pre-existing) | Backlog, kein Blocker |
| Time-Machine-Restore-Verifikation (Vault #3) | niedrige Prio, Owner-Check (früherer Mount-Fehler Code 18) |
| Backup 2. Medium (O4) | erfüllt — Vault #3 per Time Machine täglich gesichert |

---

## 9. Nächste Schritte

Im WP4-Scope ist **keine** offene Arbeit. Optionen für ein nächstes WP:

- **Monolith-B → nlp-Serie zerlegen** (additives Synthese-WP, eigener Plan + Gates; `docs/handover/ideen-backlog.md`). Bewusst NICHT als Cleanup-Nebenbei.
- **Konditionales WP5** (Klassifikations-Optimierung) — nur falls eine Stichprobe Fehlzuweisungen zeigt.

Vault-Mutationen weiterhin nur per Owner-`!`-Lauf (D-WP4-3), Gates heilig, kein Auto-Merge nach `main`.

---

## Änderungs-Log

- 2026-05-28 — Erstellt nach Abschluss Phase 8
- 2026-05-29 — Block 0.J/0.K: Phase-3/4-Updates, Threshold-Iteration, Mega-Cluster-Befund
- 2026-05-30 — Block 0.M (Reports-Bug behoben), 0.N (Autonomie-Setup)
- 2026-06-04 — Phase 8 abgeschlossen (Option B, 180 Drafts); Clustering verworfen (R9); Pre-Phase-9-Hardening
- 2026-06-05/06 — Phase 11/12 (Finalisierung); Vault gebaut + tag-bereinigt (149er Vokabular); Basis-Pipeline ABGESCHLOSSEN
- 2026-06-23 — v3-Zyklus-Start (WP0): Realstand verifiziert (181 Artikel, Tests grün); Doku-Drift bereinigt; v2-Plan archiviert
- 2026-06-25 — **Voll-Rewrite** auf Post-WP4-Stand: §0 aktualisiert (181 + 5 MOC, 760 Tests, idempotent); neue §2 v3-Zyklus (WP0–WP4 + WP4-Bilanz + Dispositionen); §3 Phasen-Referenz neu (ohne stale Metriken) + v3-Module; §5 gegen `pipeline.config.yaml` verifiziert (TF-IDF 0.85→**0.72** korrigiert); §6 Layout aktuell; §7 760 Tests / mypy pipeline clean; §8 Backup als erfüllt (Time Machine)
- 2026-07-01 — T1: Test-Richtwert 760 → **789** nachgeführt (`def test_`-Zählung; parametrisiert 826 passed / 2 skipped) nach Tier-1-Sweep (H2-Regressiontest + R1 vault-health-Tests, H1-Cleanup). Nur Zahlen-Korrektur (§0-Tabelle, §-Layout, §-Tool-Status)
