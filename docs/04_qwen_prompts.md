---
title: PKM-rebuild Qwen-Prompt-Spezifikation
slug: 04-qwen-prompts
status: stable
created: 2026-05-25
updated: 2026-05-25
---

# Qwen-Prompt-Spezifikation

Übersicht, Versionierung, Schemas und Iterations-Workflow der 4 Synthese-Stages.

---

## 1. Geltungsbereich

Gilt für alle Prompts in `prompts/v1/` und nachfolgende Versionen (`v2/`, `v3/`, …). Steuert wie Phase 8 (Qwen-Synthese) aus `docs/02_pipeline_spec.md` funktioniert.

**Nicht hier:** Frontmatter-Schema (→ `docs/03_vault_standard.md`), Pipeline-Mechanik (→ `docs/02_pipeline_spec.md`).

---

## 2. Modell- und Hardware-Constraints

| Wert | Setting |
|---|---|
| Modell | Qwen 3.6 27B (4-bit) |
| Runner | LM Studio (default) / Ollama (alternativ) |
| Endpoint | `http://localhost:1234/v1` (OpenAI-kompatibel) |
| Kontext-Window | **mindestens 128K** (sonst Gibberish) |
| RAM-Footprint | ~26–28 GB inkl. KV-Cache |
| Verbleibend macOS | ~4 GB |
| JSON-Mode | aktiviert, wo verfügbar |

**Memory-Workflow während Qwen-Läufen:** nur Zed + Ghostty + LM Studio offen. Browser/Mail/Slack zu. Memory-Pressure in Aktivitätsanzeige im Blick behalten.

---

## 3. Stage-Übersicht

| Stage | Zweck | Input | Output | Temperature |
|---|---|---|---|---|
| 1 | Cluster-Analyse | Batch-File (Segmente + Metadaten) | `stage1_analysis.json` | 0.3 |
| 2 | Merge-Vorschlag | Stage-1-Output + Batch-Kontext | `stage2_merges.json` | 0.2 |
| 3 | Synthese (Body) | Reviewte Merges + Segmente | `CK_<slug>.body.md` | 0.4 |
| 4 | Frontmatter (JSON) | Stage-3-Output + Segment-Metadaten | `CK_<slug>.frontmatter.json` | 0.1 |

**Temperaturen-Begründung:** niedrig wo Strukturtreue Pflicht, höher wo sprachliche Eigenleistung gefragt.

---

## 4. Verzeichnis-Layout (`prompts/`)

```
prompts/
├── CLAUDE.md                           ← Working Rules für Claude Code
├── README.md                           ← Version-Übersicht, Wechsel-Anleitung
├── v1/
│   ├── stage1_cluster_analysis.md
│   ├── stage2_merge_proposal.md
│   ├── stage3_synthesis.md
│   ├── stage4_frontmatter_json.md
│   ├── schemas/
│   │   ├── stage1_output.schema.json
│   │   ├── stage2_output.schema.json
│   │   └── stage4_output.schema.json
│   └── examples/
│       ├── stage1_example_input.md
│       ├── stage1_example_output.json
│       └── ...
└── v2/                                 ← bei Major-Iteration
    └── ...
```

**Aktive Version:** Pointer in `pipeline/pipeline.config.yaml` → `qwen.prompt_version: "v1"`.

---

## 5. Versionierungs-Strategie

### Wann neue Version?

| Änderung | Wie |
|---|---|
| Kleine Wortwahl, Tippfehler | gleiche Version, Git-Commit |
| Klärungs-Hinweise, zusätzliche Beispiele | Patch-Bump nicht nötig, Git-Commit reicht |
| Schema-Erweiterung (neues optionales Feld) | Minor-Bump: `v1` → `v1.1` Ordner oder Commit-Tag |
| Schema-Breaking-Change, neue Stage, geänderte Logik | Major-Bump: `v1` → `v2` (neuer Ordner) |

**Migrations-Regel:** Bei Major-Bump läuft die alte Version weiter, bis explizit umgestellt. Bestehende Drafts behalten ihre `prompt_version` im Frontmatter.

### Git-Workflow

- Branch pro Major-Iteration: `prompts/v2`
- PR-Review vor Merge in `main` (auch wenn nur Self-Review)
- Tag: `prompts-v2.0.0` bei Aktivierung

---

## 6. Prompt-File-Format

Jedes Stage-Prompt-File ist Markdown mit klarer Struktur:

````markdown
---
prompt_id: stage1_cluster_analysis
prompt_version: v1
created: 2026-05-25
updated: 2026-05-25
target_model: qwen-3.6-27b
expected_input: batch_file_markdown
expected_output: json
output_schema: schemas/stage1_output.schema.json
temperature: 0.3
---

# System-Prompt

[System-Instruktion auf Deutsch — Rolle, Kontext, Verhaltensregeln]

# Task

[Konkrete Aufgabe für diese Stage]

# Input-Format

[Beschreibung, wie das Input strukturiert ankommt]

# Output-Format

[Erwartetes JSON-Schema, mit Beispiel]

```json
{
  "key": "value"
}
```

# Beispiele

[1–3 Few-Shot-Beispiele wenn nötig]

# Constraints

- Nur valides JSON ausgeben
- Keine zusätzlichen Erläuterungen außerhalb des JSON
- Bei Unsicherheit: confidence-Feld auf "low"

# Failure-Hinweise

[Wie soll Qwen reagieren, wenn Input unklar/leer/ungültig]
````

---

## 7. Stage-Details

### Stage 1 — Cluster-Analyse

**Zweck:** Themen-Identifikation, Redundanz-Liste, Widersprüche, Struktur-Vorschlag innerhalb eines Cluster-Batches.

**Input:**
- Cluster-Batch-File (`batches/batch_NNN_<topic>.md`)
- Enthält: Cluster-Metadaten + alle Segmente mit `segment_id`, Heading-Pfad, Text

**Output-Schema (`stage1_output.schema.json`):**
```json
{
  "cluster_id": "C_apis-rest",
  "main_topics": [
    {
      "topic": "REST-Grundlagen",
      "segment_ids": ["D_rest-intro-S0001", "D_http-S0003"],
      "confidence": "high"
    }
  ],
  "redundancies": [
    {
      "segments": ["D_rest-S0001", "D_rest-v2-S0001"],
      "type": "exact_overlap | partial_overlap | conflicting",
      "note": "..."
    }
  ],
  "contradictions": [
    {
      "segments": ["D_a-S0001", "D_b-S0002"],
      "issue": "...",
      "suggested_resolution": "..."
    }
  ],
  "structure_proposal": {
    "concept_candidates": [
      {
        "tentative_slug": "rest-grundlagen",
        "tentative_title": "REST-Grundlagen",
        "covers_segments": ["..."],
        "type_guess": "knowledge-article"
      }
    ]
  },
  "overall_confidence": "medium"
}
```

**Failure-Modi:**
- Cluster zu groß → Sub-Batch-Hinweis im Output (`needs_split: true`)
- Cluster zu klein/leer → `overall_confidence: low` + Hinweis

---

### Stage 2 — Merge-Vorschlag

**Zweck:** Konkrete Concept-Notes mit Slugs vorschlagen, Quellen-Zuordnung festlegen.

**Input:**
- Stage-1-Output
- Vault-Standard-Kontext (verfügbare Templates, type/doc_role-Enums)

**Output-Schema (`stage2_output.schema.json`):**
```json
{
  "cluster_id": "C_apis-rest",
  "proposed_concepts": [
    {
      "ck_id": "CK_rest-grundlagen",
      "title": "REST-Grundlagen",
      "slug": "rest-grundlagen",
      "type": "knowledge-article",
      "doc_role": ["explanation", "reference"],
      "category": "webentwicklung",
      "subcategory": "rest-apis",
      "sources_docs": ["D_rest-intro", "D_http"],
      "source_chunks": ["D_rest-intro-S0001", "D_http-S0003"],
      "merged_from": [],
      "aliases_suggested": ["REST", "RESTful API"],
      "parent_concept_suggestion": "CK_apis",
      "child_concepts_suggestions": ["CK_rest-methods", "CK_rest-status-codes"],
      "rationale": "..."
    }
  ],
  "discarded_segments": [
    {
      "segment_id": "D_x-S0005",
      "reason": "duplicate_of_S0001"
    }
  ],
  "overall_confidence": "medium"
}
```

**Review-Gate 2:** Mensch erstellt `merge_decisions.json` mit `approved: [...]`, `rejected: [...]`, `modify: [...]`.

---

### Stage 3 — Synthese (Body)

**Zweck:** Artikel-Body schreiben nach Vault-Standard, ohne Frontmatter.

**Input:**
- Genehmigte Merge-Decisions (welche Concepts erstellen)
- Alle relevanten Source-Segmente (Originaltext)
- Vault-Standard-Auszug (Sprach-Regeln, Code-Block-Regel B4)

**Output:**
- Markdown-Body (kein Frontmatter)
- Strukturiert: H1 (= Titel), Summary-Absatz, dann themengetreue Sections
- Code-Blöcke **unverändert 1:1** aus Sources übernommen, ggf. Sprach-Tag ergänzt
- Wikilinks `[[...]]` nur wo Source-Segmente bereits referenzieren

**Pflicht-Sections (je nach `type`):**

| `type` | Pflicht-Sections |
|---|---|
| `knowledge-article` | Einleitung, Grundbegriffe, Beispiele, häufige Fehler, weiterführend |
| `compact-reference` | Kurzdefinition, Tabelle/Liste, Beispiele |
| `process-document` | Voraussetzungen, Schritte, Verifikation, Fehlerbehandlung |

**Constraints:**
- Sprache: Deutsch
- Code-Identifier, Befehle, Slugs in Links: Englisch
- Kein Fließtext über 4 Sätze ohne Listen/Tabellen
- Kein Lob, keine Floskeln
- Bei Wissenslücken: `> [!question] Offene Frage: ...` einfügen, **nicht** halluzinieren

---

### Stage 4 — Frontmatter (JSON)

**Zweck:** Strukturiertes Frontmatter generieren, das Python anschließend validiert (Pydantic `FrontmatterDraft` aus `02_pipeline_spec.md` Sektion 7) und als YAML serialisiert.

**Input:**
- Stage-3-Output (Body)
- Stage-2-Output (sources_docs, source_chunks, merged_from)
- Vault-Standard-Auszug (Pflichtfelder, Enums, Tag-Vokabular)

**Output-Schema (`stage4_output.schema.json`):**

Vollständig analog `FrontmatterDraft` aus `02_pipeline_spec.md`. Kernfelder:

```json
{
  "title": "REST-Grundlagen",
  "slug": "rest-grundlagen",
  "aliases": ["REST", "RESTful API"],
  "summary": "REST ist ein Architektur-Stil für verteilte Systeme...",
  "type": "knowledge-article",
  "doc_role": ["explanation", "reference"],
  "category": "webentwicklung",
  "subcategory": "rest-apis",
  "tags": ["rest", "http", "api", "web-architecture"],
  "related": [],
  "used_in": [],
  "parent_concept": "CK_apis",
  "child_concepts": ["CK_rest-methods"],
  "sources_docs": ["D_rest-intro", "D_http"],
  "source_chunks": ["D_rest-intro-S0001", "D_http-S0003"],
  "merged_from": [],
  "status": "draft",
  "review_status": "ai_drafted",
  "confidence": "medium",
  "doc_version": "0.1.0",
  "created": "2026-05-25",
  "updated": "2026-05-25",
  "last_synthesized": "2026-05-25",
  "prompt_version": "v1"
}
```

**Constraints:**
- Tags nur aus erlaubtem Vokabular (Pipeline validiert nach Output)
- Aliases automatisch aus `merged_from`-Titeln + alternative Bezeichnungen aus Sources
- `confidence`: ehrliche Selbsteinschätzung
- Bei fehlender Info: Feld leer lassen, **nicht** raten (z.B. `parent_concept: null`)

---

## 8. Output-Validation (Python)

Pipeline (Phase 8) validiert jeden Qwen-Output:

1. **JSON-Parse:** Schlägt fehl → Retry mit verstärktem Format-Hinweis (max. 2 Retries)
2. **Schema-Validation:** Pydantic gegen `FrontmatterDraft` bzw. Stage-Schema
3. **Vokabular-Check:** Tags gegen `00_Meta/tag-system.md`
4. **ID-Konsistenz:** `sources_docs` und `source_chunks` müssen existieren
5. **Slug-Konsistenz:** `slug` matched Naming-Conventions aus Vault-Standard

**Bei Failure:** `confidence: low` setzen, in `data/02_pipeline_output/qwen/needs_human.jsonl` flaggen, weiterlaufen mit nächstem Cluster.

---

## 9. Token-Budget (Schätzung)

| Stage | Input-Tokens (Range) | Output-Tokens | Kommentar |
|---|---|---|---|
| 1 | 10K–80K | 2K–8K | abhängig von Cluster-Größe |
| 2 | 5K–15K | 1K–4K | kompakter, da nur Strukturentscheidung |
| 3 | 15K–60K | 3K–10K | Synthese kostet Output-Tokens |
| 4 | 5K–15K | 1K–3K | strukturiertes JSON |

**Bei Überschreitung 100K Input:** Cluster splitten, in Phase 7 (Batch-Bildung) nachjustieren.

---

## 10. Iterations-Workflow (Prompt-Verbesserung)

```
1. Beobachtung: Output ist schlecht/falsch/inkonsistent
2. Hypothese: was im Prompt fehlt/missverständlich ist
3. Klein-Test: Prompt-Patch in v1/ + Re-Run auf 1–2 Test-Clustern
4. Vergleich: alter vs. neuer Output
5. Bei Erfolg: Git-Commit mit Begründung
6. Bei Major-Change: v2/ Ordner anlegen, Migration planen
7. Reflexion in docs/learnings/PHASE_08_<datum>.md
```

**Anti-Patterns vermeiden:**
- ❌ Mehrere Prompt-Änderungen gleichzeitig (Ursache unklar)
- ❌ Prompts ohne Test-Cluster ändern
- ❌ Major-Bump ohne Migrations-Notiz

---

## 11. Testing (Prompt-Qualität)

**Test-Cluster:** 3 synthetische Cluster in `tests/fixtures/qwen_clusters/`:
- `small_clear_cluster/` — 3 Segmente, klares Thema
- `large_mixed_cluster/` — 30 Segmente, gemischte Themen
- `contradictory_cluster/` — 5 Segmente mit Widersprüchen

**Regression-Test pro Prompt-Iteration:**
- Lauf gegen alle 3 Test-Cluster
- Schema-Validation grün
- Manuelle Bewertung: passt das Output zur erwarteten Struktur?

---

## 12. Sonderregel `15_Gedanken/`

Aus Strategy B5: Gedankentexte durchlaufen **keine** Stages 1–3. Sie werden nur:
- Normalisiert (Phase 2)
- Mit Minimal-Frontmatter versehen (Stage 4 angepasst, ohne `merged_from`, ohne `sources_docs` als Pflicht)
- Direkt in `15_Gedanken/` einsortiert

**Eigenes Prompt:** `prompts/v1/stage4_frontmatter_gedanken.md` (Variante von Stage 4).

---

## 13. Aktualisierungs-Routine

Dieses Doc wird gepflegt bei:
- Stage-Änderungen (neue Stages, Schema-Änderungen)
- Major-Version-Bump
- Lessons Learned aus Reflexionen

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
