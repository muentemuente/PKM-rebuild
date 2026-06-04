---
title: PKM-rebuild — Projektstand
slug: project-status
status: draft
created: 2026-05-28
updated: 2026-06-04
---

# PKM-rebuild — Projektstand (2026-06-04)

Vollständige Übersicht aller implementierten Phasen, Tests, Qualitätsstatus und offenen Punkte. Dient als Review-Basis vor Phase 9.

---

## 0. Aktueller Stand (2026-06-04)

**Phase 8 abgeschlossen — Phase 9 (Vault-Aufbau) als Nächstes.**

| Größe | Wert |
|---|---|
| Vault-ready Drafts | **180** (0 Schema-Issues, alle `category` ∈ ALLOWED) |
| Zurückgestellt `_hold/` | 19 Gedanken (deferred → `docs/FUTURE_RUN.md`) |
| Exkludiert `_excluded/` | **3** (`denkschulen_…` Survey-Doc + 2 Stage-3-Hangs) |
| Reconcile | 199 Korpus-Slugs (180 + 19) + 3 excluded = 202 |
| Test-Suite | **359** grün, ruff sauber |
| Architektur | Option B (Pro-Doc, kein Merge); Embedding-Clustering **verworfen** (R9) |
| Hardening | E1 (gedanke-Enum), E2 (NFC-Slug), E3–E5 — gemergt auf main |

Verdikt: **GO für Phase 9.** Details: `docs/learnings/PHASE_08_synthesis.md`, `docs/PRE_PHASE9_HARDENING.md`.

---

## 1. Phasen-Übersicht

| Phase | Name | Status | Commit |
|---|---|---|---|
| 0 | Setup (Git, Toolchain, Backup, Doku) | ✅ done | `e1f3c35` |
| 1 | Inventar | ✅ done | `7c9a640` |
| 2 | Normalisierung | ✅ done | `7fd4ee3` |
| 3 | Strukturextraktion | ✅ done | `7af5c95` |
| 4 | Segmentierung | ✅ done | `87e7311` |
| 5 | Redundanz-Erkennung | ✅ done | `d9cb420` |
| 6 | Embeddings (Cluster-Prep verworfen, R9) | ✅ done | `74de985` |
| 7 | LLM-Batch-Bildung (Token-Budget-Splits) | ✅ done | `231a2ff` |
| 8 | Qwen-Veredelung (Option B: Stage 3+4 pro Doc) | ✅ done — 180 Drafts | (mehrere) |
| 9 | Vault-Aufbau | 🔜 nächster Schritt | — |
| 10 | Kontroll-Berichte | ✅ done | `fd161be` |

---

## 2. Implementierungsdetails je Phase

### Phase 0 — Setup

**Blöcke:**

| Block | Inhalt | Status |
|---|---|---|
| 0.A | Git, pyproject.toml, mise, pytest, ruff, mypy | ✅ |
| 0.B | GitHub (Repo public, LICENSE) | ✅ |
| 0.C | Backup: snapshot.sh, restore.sh, Recovery-Drill | ✅ technisch; Backup-DoD offen |
| 0.D | Hardware-Test: Qwen/LM-Studio, RAM, Tokens/sek | ✅ inkl. Korrekturbedarf-Docs |
| 0.E | Doku-Korrekturen + schemas.py + phase_1_inventory Stub | ✅ |
| 0.J | Phase-4-Fix + Book-Sonderbehandlung + Re-Run Phasen 3–7 | ✅ |
| 0.K | denkschulen_ueberblick aus Mainstream-Pipeline exkludiert | ✅ |
| 0.M | Reports-Generator-Bug: cluster_report zählt Docs korrekt | ✅ |
| 0.N | CC-Autonomie-Setup (Permissions, Hooks, Arbeitsvereinbarung) | ✅ |

**Hardware-Befunde aus Block 0.D (permanent relevant):**
- Effektives Kontext-Window: ~50K Tokens (nicht 128K)
- `json_mode=True` inkompatibel mit Reasoning-Modell → `json_mode=False`
- Reasoning-Overhead ~91–93% — max_tokens = ~10× erwarteter Content

---

### Phase 1 — Inventar

**Modul:** `pipeline/phase_1_inventory.py` (292 Zeilen)  
**Input:** `data/01_corpus_input/**/*.md`  
**Output:** `data/02_pipeline_output/files_manifest.jsonl`

**Kernlogik:**
- Rekursive Suche mit konfiguriertem `exclude_patterns` + `include_extensions`
- `doc_id` = `D_<slug>` aus Dateiname (slugifiziert, Kollision → `_2`, `_3`)
- SHA-256 pro File
- Idempotenz via `files_manifest.jsonl.meta.json`

**Schema:** `DocumentRecord` (doc_id, path, sha256, size_bytes, word_count, …)  
**Tests:** 24 Tests — Slug-Kollision, SHA-256-Stabilität, Idempotenz, exclude_patterns, leeres Verzeichnis

---

### Phase 2 — Normalisierung

**Modul:** `pipeline/phase_2_normalize.py` (320 Zeilen)  
**Input:** `files_manifest.jsonl` + Korpus-Files  
**Output:** `data/02_pipeline_output/cleaned_documents.jsonl`

**Kernlogik:**
- CRLF → LF, Tabs → 4 Spaces (außer Code-Blöcke)
- Trailing Whitespace entfernen (außer Code-Blöcke)
- Max. 3 aufeinanderfolgende Leerzeilen
- YAML-Frontmatter extrahieren (Fallback: leeres Dict)
- Code-Blöcke werden hash-identisch bewahrt

**Schema:** `CleanedDocument` (doc_id, body, frontmatter, normalized_sha256)  
**Tests:** 25 Tests — Code-Block-Preservation, CRLF, Frontmatter-Extraktion, Idempotenz

---

### Phase 3 — Strukturextraktion

**Modul:** `pipeline/phase_3_structure.py` (488 Zeilen)  
**Input:** `cleaned_documents.jsonl`  
**Output:** `data/02_pipeline_output/documents_structured.jsonl`

**Kernlogik:**
- Heading-Extraktion (H1–H6) mit `mistune`
- Code-Blöcke mit Sprach-Tag (Fallback: `unknown`)
- Tabellen-Count, Links, Image-Referenzen
- `doc_type_guess`: heuristischer Typ-Guess (`knowledge-article`, `process-document`, `compact-reference`, …) mit Confidence-Score + Signals

**Schema:** `StructuredDocumentRecord` + `DocTypeGuess`  
**Tests:** 36 Tests — alle Extraktions-Felder, Typ-Guess-Signals, H1-Fallback, Idempotenz  
**Mypy:** 8 pre-existing Fehler (type-arg + 1 no-any-return + 1 arg-type) — bekannt, nicht regressions-verursacht

---

### Phase 4 — Segmentierung

**Modul:** `pipeline/phase_4_segment.py` (396 Zeilen)  
**Input:** `cleaned_documents.jsonl` + `files_manifest.jsonl`  
**Output:** `data/02_pipeline_output/segments.jsonl`

**Kernlogik:**
- Split nach Headings (konfigurierbar: `split_by_headings`)
- Segment-Grenzen respektieren Code-Blöcke, Tabellen, Listen (keine Risse)
- Segment-ID: `<doc_id>-S<index:04d>`
- `heading_path`: Breadcrumb-Pfad zu übergeordneten Headings
- Zu kurze Segmente werden mit Nachbar gemergt (min_words Threshold)
- Zu lange Segmente werden gesplittet (max_words Threshold)

**Schema:** `SegmentRecord` (segment_id, doc_id, text, word_count, heading_path, contains_code, …)  
**Tests:** 34 Tests — Code-Block-Integrität, Heading-Pfad, min/max_words, Idempotenz

**Block-0.J-Update (2026-05-29):**
- `407a610` — Heading-only und undersized Segmente werden korrekt mit Nachbar gemergt
- `16ba455` — `min_words_per_segment: 50 → 150`
- `7af5c95` — Phase 3: `doc_type_guess`-Label `book` für Files > 8000 Wörter
- `596137a` — Phase 4: Book-Sonderbehandlung: H1/H2-Split (statt H2/H3), größere Segmente
- `87e7311` — Book-Parameter korrekt an Phase 3 + 4 durchgereicht
- Re-Run ab Phase 3: **5.368 → 1.581 Segmente**, Ø Wörter ~60 → ~203

**Block-0.K + Threshold-Iteration (2026-05-29):**
- `denkschulen_ueberblick_und_einfuehrung.md` (15.770 Wörter, 394 H2-Headings) als Survey-Doc aus Mainstream-Pipeline exkludiert (`_excluded/`-Subfolder, `5155340`)
- Nach Exklusion Re-Run: **1.581 → 1.187 Segmente**
- `similarity_threshold` iterativ getestet: 0.85 → 0 echte Cluster, 0.65 → Mega-Cluster C_cluster-0000 (168 Docs), 0.75 → 85.9 % unsortiert, zurück auf 0.65
- Stand: 0.65 als Fallback, Mega-Cluster bleibt bekanntes Problem → Block 0.L (Clustering-Strategie)
- Reports-Generator zeigte „Top-Cluster 8 Docs" statt tatsächlich 168 — Diskrepanz per Direct-Query aufgelöst → Bug-Fix in Block 0.M

---

### Phase 5 — Redundanz-Erkennung

**Modul:** `pipeline/phase_5_redundancy.py` (331 Zeilen)  
**Input:** `cleaned_documents.jsonl` + `segments.jsonl`  
**Output:** `exact_duplicates.json` + `near_duplicate_edges.jsonl`

**Kernlogik:**
- Exakte Duplikate: SHA-256-Vergleich auf `normalized_sha256`
- TF-IDF-Ähnlichkeit: `sklearn.TfidfVectorizer` auf Segment-Texten
  - n-gram Range konfigurierbar (Default: `[1, 2]`)
  - Threshold konfigurierbar (Default: 0.85)
  - Upper-Triangle only (Symmetrie-Invarianz)
- Beide Methoden unabhängig, Ergebnisse werden in Phase 7 zusammengeführt

**Tests:** 19 Tests — SHA-Duplikate, TF-IDF-Threshold, Symmetrie, Performance-Bound, Idempotenz  
**Mypy:** clean

---

### Phase 6 — Embeddings + Cluster-Vorbereitung

**Modul:** `pipeline/phase_6_embeddings.py` (393 Zeilen)  
**Input:** `segments.jsonl`  
**Output:** `embeddings.parquet` + `cluster_proposals.json`

**Kernlogik:**
- Embedding-Modell: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
- Batch-Verarbeitung (konfigurierbar, Device: CPU/CUDA/MPS)
- Speicherformat: Parquet (kompakt, schnell nachladbar)
- Clustering: Cosine-Similarity-Matrix → agglomeratives Clustering (initiale Strategie konfigurierbar)
- Mikrocluster (`< min_cluster_size`) → Label `unsortiert`
- `cluster_proposals.json` enthält Cluster-ID, Label-Guess, Segment-IDs

**Tests:** 23 Tests — Embedding-Dimensionen, Parquet-Roundtrip, Mikrocluster-Handling, Idempotenz  
**Mypy:** 5 Fehler (scipy-Stubs, pyarrow-untyped-calls) — pre-existing, kein Regressionsrisiko

---

### Phase 7 — LLM-Batch-Bildung

**Modul:** `pipeline/phase_7_batches.py` (447 Zeilen)  
**Input:** `segments.jsonl` + `cluster_proposals.json` + `near_duplicate_edges.jsonl`  
**Output:** `data/02_pipeline_output/batches/batch_NNN_<slug>.md`

**Kernlogik:**
- Pro Cluster ein oder mehrere Batch-Files (Token-Budget: `max_input_tokens` aus Config)
- Cluster mit vielen Segmenten → aufgeteilt in Sub-Batches (`split_oversized_clusters`)
- Token-Schätzung: Zeichen / 4 (heuristisch für Qwen)
- Batch-File ist valides Markdown mit YAML-Frontmatter (batch_id, cluster_id, segment_count, token_estimate)
- Redundanz-Kanten aus Phase 5 werden als Hinweis-Block in jeden Batch eingebettet
- Nummerierung: `batch_001_`, `batch_002_`, … (lexikographisch stabil)

**Tests:** 24 Tests — Batch-Splitting, Token-Budget, Frontmatter-Validation, Redundanz-Einbettung, Idempotenz  
**Mypy:** clean

---

### Phase 8 — Qwen-Synthese (4-Stage) — *historisch (Option A)*

> Die folgende 4-Stage-Beschreibung dokumentiert den ursprünglichen Option-A-Entwurf. **Umgesetzt wurde Option B** (Pro-Doc, nur Stage 3+4, Routing). Siehe Update-Hinweis unten und `docs/learnings/PHASE_08_synthesis.md`.

**Modul:** `pipeline/phase_8_synthesis.py` (770 Zeilen)  
**Input:** `batches/*.md` + `segments.jsonl`  
**Output:** `data/02_pipeline_output/qwen/{batch_id}/stage1_analysis.json`  
         `data/02_pipeline_output/qwen/{batch_id}/stage2_merges.json`  
         `data/03_drafts/CK_{slug}.body.md`  
         `data/03_drafts/CK_{slug}.frontmatter.json`  
         `data/03_drafts/CK_{slug}.md` (kombiniert)  
         `data/02_pipeline_output/qwen/needs_human.jsonl`

**4-Stage-Logik:**

| Stage | Input | Output | Temp |
|---|---|---|---|
| 1 | Batch-Markdown | `stage1_analysis.json` — Themen, Cluster-Struktur, Kandidaten | 0.3 |
| 2 | Stage-1-JSON | `stage2_merges.json` — Konzept-Vorschläge, discarded_segments | 0.2 |
| 3 | Stage-2-Konzept + Quell-Segmente | `CK_slug.body.md` — Markdown-Artikel | 0.4 |
| 4 | Stage-3-Body + Stage-2-Metadaten | `CK_slug.frontmatter.json` — Pydantic-validiert | 0.1 |

**Besonderheiten:**
- `json_mode=False` (Reasoning-Modell-Constraint aus Block 0.D)
- JSON-Extraktion aus Freitext: `_extract_json()` — sucht `\`\`\`json`-Block, Fallback: äußerstes `{…}`
- Thinking-Tags (`<think>…</think>`) werden vor Parsing entfernt
- Retry bei JSON-Parse-Fehler (max_retries aus Config)
- Pflichtfelder (`status: draft`, `review_status: ai_drafted`, `last_synthesized`) werden nach Qwen-Antwort erzwungen
- Validation-Fehler → `confidence: low` setzen + `needs_human.jsonl`
- Review-Gate: `merge_decisions.json` überschreibt Stage-2-Output wenn vorhanden
- Slug-Kollisionsschutz: `_unique_slug()` mit `_2`, `_3`-Suffix
- Idempotenz: Hash-Cache pro Stage + `force`-Flag

**Prompts:** `prompts/v1/` — 4 Dateien mit YAML-Frontmatter (prompt_id, prompt_version, created)

**Tests:** 32 Tests — JSON-Extraktion (Sonderfälle), Slugify-Umlaute, Idempotenz, force-Re-Run, bad-Response-Handling, Pydantic-Validation, kombiniertes Draft-File

> **Update (2026-06-04):** Phase 8 ist **gegen den echten Korpus gelaufen** und abgeschlossen — 180 vault-ready Drafts. Umgesetzt als **Option B** (Pro-Doc, Routing passthrough/stage3/gedanken), nicht als 4-Stage-Merge. Die 4-Stage-Beschreibung oben ist historisch (Option A); Stage 1/2 sind deprecated. Mechanik: Triage (`pkm_triage.py`) + `phase8_runner.py`. Siehe `docs/learnings/PHASE_08_synthesis.md`.

---

## 3. Schemas (`pipeline/schemas.py`)

| Schema | Verwendet in | Pflichtfelder |
|---|---|---|
| `DocumentRecord` | Phase 1 Output | doc_id, path, sha256, size_bytes, word_count |
| `CleanedDocument` | Phase 2 Output | doc_id, body, frontmatter, normalized_sha256 |
| `DocTypeGuess` | Phase 3 Output | label (Literal), confidence, signals |
| `StructuredDocumentRecord` | Phase 3 Output | doc_id, title, headings, code_blocks, doc_type_guess |
| `SegmentRecord` | Phase 4 Output | segment_id, doc_id, text, word_count, heading_path |
| `FrontmatterDraft` | Phase 8 Output | title, slug, summary, type, doc_role, category, sources_docs, source_chunks, status, review_status, confidence, doc_version, created, updated, last_synthesized, prompt_version |

**Mypy:** 3 pre-existing `type-arg`-Fehler (`dict` ohne Parameter) — aus initialer Implementierung, kein Regressionsrisiko

---

## 4. Code-Qualität

| Tool | Status | Details |
|---|---|---|
| `ruff check` | ✅ clean | alle Phasen + Tests |
| `ruff format` | ✅ clean | |
| `mypy pipeline/` | ⚠️ 17 Fehler in 4 Dateien | Phase 8: 0 Fehler |
| Tests gesamt | ✅ 359/359 grün | inkl. Runner-, NFD-Slug-, gedanke-Type-Tests (Pre-Phase-9-Hardening) |

### Mypy-Fehler nach Datei

| Datei | Fehler | Typ | Bewertung |
|---|---|---|---|
| `schemas.py` | 3 | `type-arg` (dict ohne Params) | pre-existing, kein Laufzeitrisiko |
| `phase_2_normalize.py` | 1 | `type-arg` | pre-existing |
| `phase_3_structure.py` | 8 | `type-arg`, `no-any-return`, `arg-type` | pre-existing |
| `phase_6_embeddings.py` | 5 | scipy/pyarrow Stubs, `no-any-return` | pre-existing, Stubs nicht verfügbar |

Alle 17 Fehler sind in Phasen 2, 3, 6 aus den ersten Implementierungsläufen. Phase 8 ist mypy-clean. Behebung der restlichen Fehler ist kein Blocker, aber Schulden.

### Tests pro Phase

| Test-File | Tests |
|---|---|
| `test_config.py` | 5 |
| `test_phase_10_reports.py` | 11 |
| `test_phase_1_inventory.py` | 24 |
| `test_phase_2_normalize.py` | 25 |
| `test_phase_3_structure.py` | 42 |
| `test_phase_4_segment.py` | 60 |
| `test_phase_5_redundancy.py` | 19 |
| `test_phase_6_embeddings.py` | 23 |
| `test_phase_7_batches.py` | 24 |
| `test_phase_8_synthesis.py` | 37 |
| `test_sanity.py` | 5 |
| **Gesamt** | **282** |

---

## 5. Konfigurations-Schlüsselwerte (`pipeline.config.yaml`)

| Schlüssel | Wert | Begründung |
|---|---|---|
| `qwen.endpoint` | `http://localhost:1234/v1` | LM-Studio Default |
| `qwen.model` | `qwen/qwen3.6-27b` | gemessen Block 0.D |
| `qwen.context_window` | `49152` (~50K) | Hard Limit auf 32 GB RAM |
| `qwen.json_mode` | `false` | Reasoning-Modell inkompatibel |
| `qwen.prompt_version` | `v1` | aktive Prompt-Version |
| `embeddings.model` | `paraphrase-multilingual-mpnet-base-v2` | multilingual, 768-dim |

---

## 6. Datei-Layout (aktuell)

```
PKM-rebuild/
├── pipeline/
│   ├── __main__.py              ← CLI entry point
│   ├── config.py                ← Pydantic-Config-Loader
│   ├── schemas.py               ← alle Pydantic-Schemas
│   ├── phase_1_inventory.py
│   ├── phase_2_normalize.py
│   ├── phase_3_structure.py
│   ├── phase_4_segment.py
│   ├── phase_5_redundancy.py
│   ├── phase_6_embeddings.py
│   ├── phase_7_batches.py
│   └── phase_8_synthesis.py
├── prompts/
│   └── v1/
│       ├── stage1_cluster_analysis.md
│       ├── stage2_merge_proposal.md
│       ├── stage3_synthesis.md
│       ├── stage4_frontmatter_json.md
│       └── schemas/
│           ├── stage1_output.schema.json
│           ├── stage2_output.schema.json
│           └── stage4_output.schema.json
├── tests/
│   ├── conftest.py
│   ├── test_phase_1_inventory.py
│   ├── …
│   ├── test_phase_8_synthesis.py
│   └── test_sanity.py
└── docs/
    ├── 00_persona_muente.md
    ├── 01_strategy.md
    ├── 02_pipeline_spec.md
    ├── 03_vault_standard.md
    ├── 04_qwen_prompts.md
    ├── 06_claude_code_workflow.md
    └── learnings/
        └── PHASE_00_setup.md    ← einzige fertige Phase-Reflexion
```

---

## 7. Offene Punkte

### 7.1 Backup-DoD (kein Phase-9-Blocker, aber Pflicht vor Produktivlauf)

| Punkt | Status |
|---|---|
| Time Machine aktiv für Korpus + Vault | ❌ Mount-Fehler Code 18 (Volume nicht eingehängt) |
| Vault-Snapshot auf zweitem Medium | ❌ Medium noch nicht entschieden (ext. SSD / iCloud / Backblaze) |

### 7.2 Code-Qualität (Schulden, kein Blocker)

| Datei | Problem |
|---|---|
| `schemas.py` | 3× `dict` ohne Type-Parameter → `dict[str, Any]` |
| `phase_2_normalize.py` | 1× `dict` ohne Type-Parameter |
| `phase_3_structure.py` | 8 mypy-Fehler, davon 1 echter (`arg-type` bei `DocTypeGuess`) |
| `phase_6_embeddings.py` | scipy/pyarrow Stubs fehlen; `ignore_missing_imports` nachrüsten |

### 7.3 Phase-Reflexionen fehlen (Phases 1–8)

Gemäß CLAUDE.md Sektion 8 sollte jede Phase mit `docs/learnings/PHASE_NN_<slug>.md` abschließen. Bisher nur `PHASE_00_setup.md` vorhanden.

### 7.4 ✅ Phase 8 CLI-Integration (behoben)

Phase 8 ist in der CLI registriert und gelaufen (`--phase 8`, `--file` für Einzel-Korpus-Files). Produktiv über `phase8_runner.py`.

### 7.5 ✅ Clustering-Mega-Cluster (aufgelöst durch Verwurf, R9)

`C_cluster-0000` enthielt 168 Docs (83 %) bei `similarity_threshold=0.65`; 0.75 → 85.9 % unsortiert, 0.85 → 0 Cluster. **Befund:** der Korpus hat keine inhärente Cluster-Struktur. **Entscheidung:** Embedding-/HDBSCAN-Clustering als Vault-Strukturprinzip **verworfen**. `category` kommt aus Qwen-Stage-4 + deterministischem Mapping auf 16 Vault-Ordner (`apply_category_mapping.py`, `03_vault_standard.md` Appendix A). Embeddings dienen nur noch der Redundanz-Erkennung.

### 7.6 ✅ Reports-Generator-Bug Cluster-Größen (Block 0.M — behoben)

`cluster_report.md` zeigte „Top-Cluster 8 Docs" statt tatsächlich 168. Ursache: Doc-Count wurde via Segment-Count berechnet statt via distinct `doc_id`s. Behoben in `fa9669c` — Doc-Count via `s.rsplit('-S', 1)[0]` + 2 Regressions-Tests (`test_cluster_report_doc_count`, `test_cluster_report_excludes_unsortiert_from_stats`).

---

## 8. Nächste Schritte

Option B (Pro-Doc-Veredelung) — Stand 2026-06-04:

```
✅ 0.L-Impl  Option-B-Routing (passthrough/stage3/gedanken)
✅ 0.G  Vault-Foundations (Tag-Vokabular, Templates, Gedanken-Pfad)
✅ 8.A/8.B  Phase-8-Lauf → 180 vault-ready Drafts
✅ E1–E5  Pre-Phase-9-Hardening (gedanke-Enum, NFC-Slug, Category-Mapping, Runner)
→  9    Vault-Aufbau (16 Ordner, _index.md, Wikilink-Auflösung)
→  10   Kontroll-Berichte final + DoD-Check
↪  FUTURE_RUN  19 _hold-Gedanken + 2 Hangs + neue Files (docs/FUTURE_RUN.md)
○  0.I  Backup-DoD (Time Machine, 2. Medium) — vor Produktiv-Abschluss
```

---

## Änderungs-Log

- 2026-05-28 — Erstellt nach Abschluss Phase 8
- 2026-05-28 — Korrigiert: Phase 8 Status auf 🟡 (CLI-Wiring offen, kein Echtlauf), Sektion 8 → Verweis auf Master-Plan
- 2026-05-29 — Block-0.J: Phase-3/4-Commits aktualisiert, Phase-4-Notiz (Book-Sonderbehandlung + Re-Run-Ergebnis)
- 2026-05-29 — Block-0.K: denkschulen_ueberblick exkludiert; Blöcke 0.J+0.K in Sektion 2 ergänzt; Befund: `C_cluster-0000` Mega-Cluster (similarity_threshold-Problem) bleibt offen
- 2026-05-29 — Block-0.J.8: Phase-10 done (`fd161be`), Tests 222→275, Threshold-Iteration + Block-0.K in Phase-4-Sektion, Offene Punkte 7.5+7.6 ergänzt
- 2026-05-30 — Block-0.M abgeschlossen (`fa9669c`): §7.6 als behoben markiert; Block-0.N ergänzt (Autonomie-Setup, Permissions, Hooks); Tests 275→282; §8 Nächste Schritte auf Option-B-Roadmap aktualisiert
- 2026-06-04 — Phase 8 abgeschlossen (180 Drafts); §0 Aktueller Stand mit Counts (180/19/3); Clustering verworfen (§7.5 aufgelöst, R9); Phase-8-CLI §7.4 behoben; Tests 282→359; Phasen-Tabelle + §8 auf Ist-Stand; Pre-Phase-9-Hardening E1–E5
