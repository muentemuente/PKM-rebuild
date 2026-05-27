---
title: PKM-rebuild Pipeline-Spezifikation
slug: 02-pipeline-spec
status: stable
created: 2026-05-25
updated: 2026-05-27
---

# Pipeline-Spezifikation

Technische Referenz: Architektur, Phasen, Schemas, Konfiguration, CLI, Tests.

---

## 1. Architektur-Überblick

```
┌─────────────────────────────────────────────────────────────────┐
│  data/01_corpus_input/   (read-only Original-Markdown)          │
└────────────────────────┬────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  Phase 1: Inventar  │ → files_manifest.jsonl
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 2: Normalize  │ → cleaned_documents.jsonl
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 3: Struktur   │ → documents_structured.jsonl
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 4: Segmente   │ → segments.jsonl
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 5: Redundanz  │ → exact_duplicates.json,
              │  (Hash + TF-IDF)    │   near_duplicate_edges.jsonl
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 6: Embeddings │ → embeddings.parquet,
              │   (mpnet-base)      │   cluster_proposals.json
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 7: Batches    │ → batches/batch_NNN_*.md
              └──────────┬──────────┘
                         │
   ┏━━━━━━━━━━━━━━━━━━━━━▼━━━━━━━━━━━━━━━━━━━━━┓  ← REVIEW-GATE 1
   ┃  Mensch prüft Cluster-Karte               ┃
   ┗━━━━━━━━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━━━━━┛
              ┌──────────▼──────────┐
              │ Phase 8: Qwen-Stage1│ → cluster_analysis.json
              │ Cluster-Analyse     │
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 8: Qwen-Stage2│ → merge_proposals.json
              │ Merge-Vorschläge    │
              └──────────┬──────────┘
                         │
   ┏━━━━━━━━━━━━━━━━━━━━━▼━━━━━━━━━━━━━━━━━━━━━┓  ← REVIEW-GATE 2
   ┃  Mensch genehmigt Merges                  ┃
   ┗━━━━━━━━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━━━━━┛
              ┌──────────▼──────────┐
              │ Phase 8: Qwen-Stage3│ → drafts/CK_*.md (Body)
              │ Synthese            │
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 8: Qwen-Stage4│ → drafts/CK_*.frontmatter.json
              │ Frontmatter         │
              └──────────┬──────────┘
                         │
   ┏━━━━━━━━━━━━━━━━━━━━━▼━━━━━━━━━━━━━━━━━━━━━┓  ← REVIEW-GATE 3
   ┃  Mensch reviewt Drafts pro Cluster         ┃
   ┗━━━━━━━━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━━━━━┛
              ┌──────────▼──────────┐
              │ Phase 9: Vault-Bau  │ → data/04_vault/
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 10: Berichte  │ → corpus/duplicate/cluster_report.md
              └─────────────────────┘
```

---

## 2. Daten-Layout

| Ort | Inhalt | Git? |
|---|---|---|
| `pipeline/` | Python-Modul | ✅ public |
| `prompts/v1/` | Qwen-Prompt-Files | ✅ public |
| `docs/` | Projekt-Doku | ✅ public (Persona gitignored) |
| `~/projects/aktiv/PKM_rebuild/data/01_corpus_input/` | Original `.md` (read-only) | ❌ lokal |
| `~/projects/aktiv/PKM_rebuild/data/02_pipeline_output/` | JSONL, Embeddings, Cluster | ❌ lokal |
| `~/projects/aktiv/PKM_rebuild/data/03_drafts/` | Qwen-Outputs | ❌ lokal |
| `~/projects/aktiv/PKM_rebuild/data/04_vault/` | finaler Obsidian-Vault | ❌ lokal |
| `~/projects/aktiv/PKM_rebuild/backups/` | Snapshots | ❌ lokal |

Pfad-Auflösung über `pipeline.config.yaml` → Env-Variable `PKM_DATA_ROOT` (default `~/projects/aktiv/PKM_rebuild/data`).

---

## 3. Konfiguration (`pipeline/pipeline.config.yaml`)

```yaml
# === Pfade ===
paths:
  data_root: "~/projects/aktiv/PKM_rebuild/data"
  corpus_input: "${data_root}/01_corpus_input"
  pipeline_output: "${data_root}/02_pipeline_output"
  drafts: "${data_root}/03_drafts"
  vault: "${data_root}/04_vault"

# === Segmentierung ===
segmentation:
  min_words_per_segment: 50
  max_words_per_segment: 1500
  target_words_per_segment: 900
  preserve_code_blocks: true
  preserve_tables: true
  preserve_lists: true

# === Redundanz ===
redundancy:
  tfidf:
    threshold: 0.72
    ngram_range: [1, 2]
    max_features: 20000
  embeddings:
    threshold: 0.85
    model: "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    batch_size: 32

# === Cluster ===
clustering:
  min_cluster_size: 3        # bottom-up Regel
  enable_umap_hdbscan: false # Phase 7b (optional)
  umap:
    n_neighbors: 15
    min_dist: 0.1
  hdbscan:
    min_cluster_size: 3
    min_samples: 2

# === Qwen ===
qwen:
  endpoint: "http://localhost:1234/v1"   # LM Studio default
  model: "qwen/qwen3.6-27b"
  context_window: 49152
  temperature_stage1: 0.3
  temperature_stage2: 0.2
  temperature_stage3: 0.4
  temperature_stage4: 0.1
  max_retries: 2
  json_mode: false

# === Sample-Modus ===
sample:
  enabled: false
  count: 10

# === Logging ===
logging:
  level: "INFO"
  file: "${pipeline_output}/pipeline.log"
  json: true
```

---

## 4. CLI-Interface

```bash
# Vollständiger Lauf
python -m pipeline run

# Sample-Modus (10 Files)
python -m pipeline run --sample 10

# Spezifische Phase
python -m pipeline run --phase 5

# Ab Phase X bis Ende
python -m pipeline run --from-phase 5

# Force-Rebuild (ignoriert Cache)
python -m pipeline run --force

# Spezifische Datei re-processen
python -m pipeline run --file <path>

# Status-Bericht
python -m pipeline status

# Validierung der Outputs
python -m pipeline validate

# Vault-Aufbau (Phase 9) explizit
python -m pipeline build-vault

# Bericht-Generierung
python -m pipeline reports
```

**Globale Flags:** `--config <path>`, `--verbose`, `--dry-run`

---

## 5. Logging

- Library: `rich` für Konsolen-Output, `structlog` für JSON-Logs
- Konsolen-Output: menschlich lesbar, mit Fortschrittsbalken
- File-Output: JSON Lines, eine Zeile pro Event
- Log-Level pro Phase: `DEBUG` für Detail, `INFO` für Übergänge, `WARNING` für Skip-Cases, `ERROR` für Failures

**Event-Schema:**
```json
{
  "ts": "2026-05-25T14:23:10",
  "level": "INFO",
  "phase": "phase_5_redundancy",
  "event": "exact_duplicate_found",
  "doc_ids": ["D_yaml-frontmatter", "D_yaml-fm-copy"],
  "details": {...}
}
```

---

## 6. Phasen-Detail

### Phase 0: Setup & Sicherung

**Input:** keiner
**Output:** Repo aufgesetzt, Doku-Suite vorhanden, Korpus gesnapshottet
**Akzeptanzkriterien:**
- [ ] Git-Repo initialisiert + erster Commit
- [ ] Alle 11 Doku-Files vorhanden + gegenseitig verlinkt
- [ ] `.gitignore` schließt `docs/00_persona_muente.md` aus
- [ ] Korpus-Snapshot in `backups/corpus_snapshot_YYYY-MM-DD.tar.gz`
- [ ] LM Studio mit Qwen 3.6 27B + 128K Kontext getestet (Memory-Verbrauch dokumentiert)
- [ ] Sample-Test: 1 Dummy-Markdown durch leeren Phasen-Skeleton

---

### Phase 1: Inventar

**Input:** `data/01_corpus_input/**/*.md`
**Output:** `data/02_pipeline_output/files_manifest.jsonl`
**Logik:**
- Rekursives Einsammeln aller `.md`
- Pro File: SHA-256, Größe, Zeilen-/Wort-/Zeichen-Zahl, Modified-Date
- Doc-ID: `D_<slug>` aus Dateiname (Naming-Conventions aus Vault-Standard)

**Schema:** siehe Sektion 7 (`DocumentRecord`)

**Akzeptanzkriterien:**
- [ ] Alle `.md` aus Input erfasst (Count check)
- [ ] Keine doppelten doc_ids (Slug-Kollisionen → Suffix `_2`, `_3`)
- [ ] SHA-256 für jedes File berechnet

---

### Phase 2: Normalisierung

**Input:** Phase 1 Output + Original-Files
**Output:** `data/02_pipeline_output/cleaned_documents.jsonl`
**Logik:**
- Encoding → UTF-8
- CRLF/CR → LF
- Tabs → 4 Spaces (außer in Code-Blöcken)
- 4+ Leerzeilen → 3 Leerzeilen
- Trailing Whitespace entfernen
- YAML-Frontmatter erkennen + parsen
- Original-Inhalt von Frontmatter trennen

**Akzeptanzkriterien:**
- [ ] Code-Blöcke unverändert (Hash-Check pre/post)
- [ ] Tabellen unverändert
- [ ] Frontmatter erkannt wo vorhanden, leeres Dict wo nicht

---

### Phase 3: Strukturextraktion

**Input:** Phase 2 Output
**Output:** `data/02_pipeline_output/documents_structured.jsonl`
**Logik:**
- H1–H6-Hierarchie extrahieren
- Code-Block-Indizes + Sprachen erfassen
- Tabellen-Indizes
- Link- und Bild-Verweise sammeln
- Heuristische Dokumenttyp-Vermutung (`doc_type_guess`) + Confidence + Signale

**Schema:** `StructuredDocumentRecord`

**Akzeptanzkriterien:**
- [ ] H1 für jedes Dokument (Fallback: Dateiname)
- [ ] Confidence-Wert + mind. 1 Signal pro `doc_type_guess`
- [ ] Alle Code-Blöcke mit Sprach-Tag (`unknown` wenn nicht erkennbar)

---

### Phase 4: Segmentierung

**Input:** Phase 3 Output
**Output:** `data/02_pipeline_output/segments.jsonl`
**Logik:**
- Primär nach Markdown-Überschriften trennen
- Sehr lange Sections (> `max_words_per_segment`) in Chunks teilen
- Code-Blöcke, Tabellen, Listen zusammenhalten
- Pro Segment: Heading-Pfad, vorherige/nächste Überschrift als Kontext

**Schema:** `SegmentRecord`

**Akzeptanzkriterien:**
- [ ] Jedes Segment zwischen `min_words` und `max_words`
- [ ] Code-Blöcke nicht zerrissen (Test: Anzahl ` ``` ` ist gerade)
- [ ] Heading-Pfad für jedes Segment vorhanden

---

### Phase 5: Redundanz-Erkennung

**Input:** Phase 1 + Phase 4 Outputs
**Output:**
- `data/02_pipeline_output/exact_duplicates.json` (Hash-basiert auf Dokument-Ebene)
- `data/02_pipeline_output/near_duplicate_edges.jsonl` (TF-IDF auf Segment-Ebene)

**Logik:**
- **Stufe 1:** SHA-256-Vergleich auf normalisierten Doc-Text → exakte Duplikat-Gruppen
- **Stufe 2:** TF-IDF-Vektoren der Segmente, Cosine-Similarity ≥ Threshold → Kanten in einem Ähnlichkeits-Graph

**Akzeptanzkriterien:**
- [ ] Performance: TF-IDF läuft auf 200 Docs / 3000 Segmenten < 5 min
- [ ] Threshold konfigurierbar
- [ ] Symmetrische Kanten (a→b == b→a)

---

### Phase 6: Embeddings + Cluster-Vorbereitung

**Input:** Phase 4 Output
**Output:**
- `data/02_pipeline_output/embeddings.parquet`
- `data/02_pipeline_output/cluster_proposals.json`

**Logik:**
- Embedding pro Segment via `paraphrase-multilingual-mpnet-base-v2`
- Cosine-Similarity-Matrix für semantische Ähnlichkeit
- Initiale Cluster-Vorschläge (greedy / agglomerativ, einfach)
- Min-Cluster-Size = 3 (bottom-up)

**Schema:** `EmbeddingRecord`, `ClusterProposal`

**Akzeptanzkriterien:**
- [ ] Embeddings als parquet (kompakt, schnell lesbar)
- [ ] Cluster-Vorschläge mit Label-Vermutung pro Cluster
- [ ] Mikrocluster (< 3) gehen in `unsortiert`

**Phase 7b — UMAP+HDBSCAN (optional):**
- Wenn `enable_umap_hdbscan: true`: 2D-Projektion + dichtebasiertes Clustering
- Output: `cluster_visualization.html` (Plotly)
- Kein DoD-Kriterium, rein Lernzweck

---

### Phase 7: LLM-Batch-Bildung

**Input:** Phase 5 + 6 Outputs
**Output:** `data/02_pipeline_output/batches/batch_NNN_<topic-slug>.md`

**Logik:**
- Pro Cluster ein Batch-File
- Inhalt: Metadaten, enthaltene Dokumente, bekannte Ähnlichkeiten (TF-IDF + Embeddings), alle Segmente mit IDs + Heading-Pfaden
- Token-Schätzung pro Batch (Ziel: < 35K Token Input, damit Reasoning-Raum für Qwen bleibt)
- Batches > 35K werden in Sub-Batches geteilt

**Akzeptanzkriterien:**
- [ ] Jeder Batch ist ein valides Markdown
- [ ] Jeder Batch enthält Anweisungs-Header für Qwen
- [ ] Token-Schätzung pro Batch geloggt

**→ REVIEW-GATE 1:** Mensch prüft `cluster_report.md` (aus Phase 10 vorgezogen) und entscheidet: weiter, Cluster anpassen, Schwellwerte ändern.

---

### Phase 8: Qwen-Synthese (4 Stages)

Pro Batch durchlaufen alle 4 Stages. Failure in einer Stage → Retry oder Flag, kein Auto-Verwurf.

#### Stage 1 — Cluster-Analyse
**Prompt:** `prompts/v1/stage1_cluster_analysis.md`
**Output:** `data/02_pipeline_output/qwen/{batch_id}/stage1_analysis.json`
**Inhalt:** Themen-Identifikation, Redundanz-Liste, Widersprüche, Struktur-Vorschlag

#### Stage 2 — Merge-Vorschläge
**Prompt:** `prompts/v1/stage2_merge_proposal.md`
**Output:** `data/02_pipeline_output/qwen/{batch_id}/stage2_merges.json`
**Inhalt:** Liste vorgeschlagener Concept-Notes (`CK_xxxx`), welche Source-Docs/Segmente in welches Concept fließen
**→ REVIEW-GATE 2:** Mensch genehmigt Merges (`merge_decisions.json`)

#### Stage 3 — Synthese
**Prompt:** `prompts/v1/stage3_synthesis.md`
**Output:** `data/03_drafts/CK_<slug>.body.md`
**Inhalt:** Artikel-Body (ohne Frontmatter), nach Vault-Standard formatiert

#### Stage 4 — Frontmatter-Generierung
**Prompt:** `prompts/v1/stage4_frontmatter_json.md`
**Output:** `data/03_drafts/CK_<slug>.frontmatter.json`
**Inhalt:** strukturiertes JSON, Python validiert gegen Pydantic-Schema, serialisiert als YAML, fügt vor Body

**→ REVIEW-GATE 3:** Mensch prüft pro Cluster: `data/03_drafts/CK_*.md` (mit Frontmatter)

**Akzeptanzkriterien (Phase 8 gesamt):**
- [ ] Pro Source-Doc eine Spur in `merged_from` oder `sources_docs`
- [ ] `confidence`-Feld gesetzt
- [ ] `prompt_version` gesetzt
- [ ] `last_synthesized` gesetzt
- [ ] Validation gegen Pydantic-Schema grün

---

### Phase 9: Vault-Aufbau

**Input:** Reviewte Drafts in `data/03_drafts/`
**Output:** `data/04_vault/<cluster>/<slug>.md`

**Logik:**
- Cluster aus `category` im Frontmatter ableiten
- Cluster-Ordner mit Nummern-Präfix anlegen (`02_webentwicklung/`)
- Datei-Slug = `slug` aus Frontmatter
- `_index.md` pro Cluster generieren (aggregiert Frontmatter aller Files im Cluster)
- Wikilinks aus `related: [[...]]` validieren (alle Targets müssen existieren)
- Vault-internes Glossar nicht aufbauen (in 1.0 Out-of-Scope)

**Akzeptanzkriterien:**
- [ ] Jeder Vault-File hat valides Frontmatter (Pydantic-Validation)
- [ ] Alle Wikilinks auflösbar
- [ ] Cluster-Index-Files vorhanden
- [ ] Keine SHA-256-Duplikate

---

### Phase 10: Kontroll-Berichte

**Output (alle in `data/02_pipeline_output/`):**
- `corpus_report.md` — Übersicht Korpus (Größe, Typen, Sprachen)
- `duplicate_report.md` — Duplikate, Merges, was wurde konsolidiert
- `cluster_report.md` — Cluster-Verteilung, Größen, Mikrocluster

**Akzeptanzkriterien:**
- [ ] Berichte regenerierbar (idempotent)
- [ ] Mensch-lesbar (nicht nur JSON-Dumps)

---

## 7. Schemas (Pydantic)

```python
# === pipeline/schemas.py ===
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

# --- Phase 1 ---
class DocumentRecord(BaseModel):
    doc_id: str                         # D_<slug>
    path: str
    filename: str
    size_bytes: int
    modified_at: datetime
    sha256: str
    line_count: int
    word_count: int
    char_count: int

# --- Phase 2 ---
class CleanedDocument(BaseModel):
    doc_id: str
    body: str
    frontmatter: dict
    normalized_sha256: str

# --- Phase 3 ---
class DocTypeGuess(BaseModel):
    label: Literal[
        "cheat_sheet", "tutorial", "wiki", "manual",
        "how-to", "explanation", "reference", "gedanke",
        "projektidee", "projektplanung", "unklar"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[str]

class StructuredDocumentRecord(BaseModel):
    doc_id: str
    title: str
    headings: list[dict]                # [{"level": 2, "text": "..."}]
    code_blocks: list[dict]             # [{"lang": "bash", "content": "..."}]
    tables_count: int
    links: list[str]
    images: list[str]
    doc_type_guess: DocTypeGuess

# --- Phase 4 ---
class SegmentRecord(BaseModel):
    segment_id: str                     # <doc_id>-S<index:04d>
    doc_id: str
    source_path: str
    heading_path: list[str]
    segment_index: int
    text: str
    word_count: int
    char_count: int
    contains_code: bool
    contains_table: bool

# --- Phase 6 ---
class EmbeddingRecord(BaseModel):
    segment_id: str
    embedding: list[float]              # 768-dim für mpnet-base
    model: str

class ClusterProposal(BaseModel):
    cluster_id: str                     # C_<slug>
    label_guess: str
    segment_ids: list[str]
    internal_similarity_mean: float

# --- Phase 8 (Qwen-Output) ---
class FrontmatterDraft(BaseModel):
    title: str
    slug: str
    aliases: list[str] = []
    summary: str
    type: Literal["process-document", "knowledge-article", "compact-reference"]
    doc_role: list[str]
    category: str
    subcategory: str | None = None
    tags: list[str]
    related: list[str] = []
    used_in: list[str] = []
    parent_concept: str | None = None
    child_concepts: list[str] = []
    sources_docs: list[str]
    source_chunks: list[str]
    merged_from: list[str] = []
    status: Literal["draft", "review", "stable", "deprecated"] = "draft"
    review_status: Literal["ai_drafted", "human_reviewed", "verified"] = "ai_drafted"
    confidence: Literal["low", "medium", "high"]
    doc_version: str = "0.1.0"
    created: str                        # YYYY-MM-DD
    updated: str
    last_synthesized: str
    prompt_version: str                 # e.g. "v1"
```

---

## 8. Idempotenz

**Skip-Logik pro Phase:**
- Vor Lauf: Hash der Inputs berechnen
- Wenn Output-File existiert UND `<output>.meta.json` denselben Input-Hash hat → skip
- Mit `--force` wird Cache ignoriert

**Meta-File pro Output:**
```json
{
  "phase": "phase_4_segmentation",
  "input_hash": "sha256:...",
  "output_hash": "sha256:...",
  "created_at": "2026-05-25T14:30:00",
  "duration_seconds": 12.5,
  "config_snapshot": {...}
}
```

---

## 9. Failure-Handling

| Failure-Typ | Behandlung |
|---|---|
| File nicht lesbar (Encoding) | Log Warning, skip File, in `errors.jsonl` |
| Qwen-Endpoint nicht erreichbar | Retry (Backoff), nach 3 Failures → Abort + Snapshot |
| Qwen-Output Validation-Fehler | `confidence: low` setzen, in `needs_human.jsonl` flaggen, weiterlaufen |
| Memory-Pressure detected | Pause, User-Prompt: „Apps schließen, fortfahren?" |
| Token-Limit Pipeline | Sub-Batches aufteilen, neu starten |

Globaler State-File: `data/02_pipeline_output/pipeline_state.json` mit aktueller Phase + Position für Resume.

---

## 10. Review-Gates

| Gate | Nach Phase | Mensch entscheidet |
|---|---|---|
| 1 | Phase 6/7 (Cluster) | Cluster-Verteilung okay? Schwellwerte anpassen? Cluster manuell mergen? |
| 2 | Phase 8 Stage 2 (Merges) | Welche Merges genehmigt? Welche ablehnen? `merge_decisions.json` |
| 3 | Phase 8 Stage 4 (Frontmatter) | Drafts pro Cluster review-en, freigeben für Phase 9 |

Review-UI: Markdown-Files in Zed öffnen + `git diff` für Vergleich.

---

## 11. Tests (`pytest`)

**Pflicht-Tests:**
- Schema-Validation für jedes Pydantic-Modell (gültige + ungültige Inputs)
- Normalisierung: Code-Blöcke bleiben unverändert
- Segmentierung: keine zerrissenen Code-Blöcke
- ID-Generierung: Slug-Kollision wird mit Suffix gelöst
- Idempotenz: zweiter Lauf erzeugt identische Outputs (Hash-Vergleich)
- Sample-Modus: läuft auf 10 künstlichen Files durch

**Test-Daten:** `tests/fixtures/sample_corpus/` mit 10 synthetischen Markdown-Files.

---

## 12. Performance-Erwartungen (auf M5, 32 GB RAM)

| Phase | Erwartung |
|---|---|
| Phase 1–4 | < 30 s gesamt |
| Phase 5 (TF-IDF) | < 5 min |
| Phase 6 (Embeddings) | 5–15 min (mpnet-base auf MPS) |
| Phase 8 (Qwen pro Batch) | 13–37 min pro Cluster (alle 4 Stages); ~4–12h gesamt bei ~20 Clustern (7.45 t/s gemessen, ~10× Reasoning-Overhead) |
| Phase 9 | < 1 min |

---

## 13. Aktualisierungs-Routine

Bei Schema-Änderungen: Schema-Version inkrementieren + Migration im Code. Bei Phasen-Änderungen: Doku + Tests anpassen. Bei Config-Änderungen: Beispiel-Config aktualisieren.

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
