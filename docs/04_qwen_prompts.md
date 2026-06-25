---
title: PKM-rebuild Qwen-Prompt-Spezifikation
slug: 04-qwen-prompts
status: stable
created: 2026-05-25
updated: 2026-06-25
---

# Qwen-Prompt-Spezifikation

Übersicht, Versionierung, Schemas und Iterations-Workflow der Synthese-Stages. **Aktiv (Option B):** Stage 3 (Pro-Doc-Veredelung, mit Routing) + Stage 4 (Frontmatter). Stage 1/2 deprecated.

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
| Kontext-Window | **~49152 (50K)** (Hard Limit auf 32 GB RAM) |
| RAM-Footprint | ~26–28 GB inkl. KV-Cache |
| Verbleibend macOS | ~4 GB |
| JSON-Mode | **deaktiviert** (LM Studio inkompatibel mit Reasoning-Modell; JSON im Prompt erzwingen + Python parsen) |

**Reasoning-Charakter:** Qwen 3.6 27B denkt vor jeder Antwort (ähnlich o1). Gemessener Overhead: ~91–93 % der generierten Tokens sind Thinking-Tokens, nicht Content. `max_tokens` muss **10× die geplante Content-Größe** betragen, sonst wird die Antwort abgeschnitten (`finish_reason: length`).

**Hang-Lehre (2 Files):** Meta-/Prompt-Inhalt (`Prompt-Verbesserung.md`, `prompts_text_stil_grammatik.md`) triggert im Stage-3-Call einen **nicht-terminierenden Reasoning-Loop** (das Modell „denkt über Prompts nach"). **Timeout-Hochsetzen hilft nicht** — der Loop terminiert nicht von selbst. Mitigation: hart auf `passthrough` routen **oder** Reasoning/`max_tokens` je Call cappen. Die beiden Files liegen in `_excluded/` (siehe `docs/FUTURE_RUN.md`).

**Memory-Workflow während Qwen-Läufen:** nur Zed + Ghostty + LM Studio offen. Browser/Mail/Slack zu. Memory-Pressure in Aktivitätsanzeige im Blick behalten.

---

## 3. Stage-Übersicht

| Stage | Zweck | Input | Output | Temperature | Status |
|---|---|---|---|---|---|
| ~~1~~ | ~~Cluster-Analyse~~ | ~~Batch-File (Segmente + Metadaten)~~ | ~~`stage1_analysis.json`~~ | ~~0.3~~ | **deaktiviert (Option B)** |
| ~~2~~ | ~~Merge-Vorschlag~~ | ~~Stage-1-Output + Batch-Kontext~~ | ~~`stage2_merges.json`~~ | ~~0.2~~ | **deaktiviert (Option B)** |
| 3 | Pro-Doc-Veredelung (Body) | Alle Segmente eines Docs | `CK_<slug>.body.md` | 0.4 | aktiv |
| 4 | Frontmatter (JSON) | Stage-3-Output + Segment-Metadaten | `CK_<slug>.frontmatter.json` | 0.1 | aktiv |

**Temperaturen-Begründung:** niedrig wo Strukturtreue Pflicht, höher wo sprachliche Eigenleistung gefragt.

---

## 4. Verzeichnis-Layout (`prompts/`)

```
prompts/
├── CLAUDE.md                           ← Working Rules für Claude Code
├── Verzeichnis_schemas.txt
├── v1/                                 ← Phase-8-Synthese (aktiv)
│   ├── stage1_cluster_analysis.md      ← deprecated (Option A)
│   ├── stage2_merge_proposal.md        ← deprecated (Option A)
│   ├── stage3_synthesis.md
│   ├── stage4_frontmatter_json.md
│   ├── stage4_frontmatter_gedanken.md  ← Gedanken-Variante (§12)
│   └── schemas/
│       ├── stage1_output.schema.json
│       ├── stage2_output.schema.json
│       ├── stage4_output.schema.json
│       └── stage4_gedanken_output.schema.json
└── v2/                                 ← restructure-Pfad (WP3c-4), NUR `pkm restructure`
    ├── MIGRATION.md                    ← Diff v1→v2 + Re-Run
    ├── stage3_synthesis.md             ← type-konditional, non-thinking-Sampler
    ├── stage4_frontmatter_json.md      ← unverändert aus v1
    └── schemas/
        └── stage4_output.schema.json
```

**Aktive Version (Phase 8):** Pointer in `pipeline/pipeline.config.yaml` → `qwen.prompt_version: "v1"`.
**v2** ist **kein** Major-Bump der Synthese, sondern ein **isolierter** Pfad: nur `pkm restructure` nutzt ihn, aktiviert über `qwen.restructure.prompt_version: "v2"` (Phase 8 bleibt v1). Es gibt **kein** `examples/`-Verzeichnis und **kein** `prompts/README.md`.

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

### Stage 1 — Cluster-Analyse *(nicht aktiv — Option B)*

> **Status: deaktiviert (Option B).** Stage 1 entfällt. Prompt-File `prompts/v1/stage1_cluster_analysis.md` als `deprecated: option-a` markiert. Historische Referenz für Lernzwecke.

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

### Stage 2 — Merge-Vorschlag *(nicht aktiv — Option B)*

> **Status: deaktiviert (Option B).** Stage 2 entfällt. Prompt-File `prompts/v1/stage2_merge_proposal.md` als `deprecated: option-a` markiert. Review-Gate 2 entfällt ebenfalls. Historische Referenz für Lernzwecke.

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

~~**Review-Gate 2:** Mensch erstellt `merge_decisions.json` mit `approved: [...]`, `rejected: [...]`, `modify: [...]`.~~ *(entfällt in Option B)*

---

### Stage 3 — Pro-Doc-Veredelung (Body)

**Routing (je Doc, deterministisch in Phase 8):** Nicht jedes Doc läuft durch den LLM. Drei Pfade:

| Pfad | Bedingung | Stage-3-Verhalten |
|---|---|---|
| `passthrough` | Doc enthält Code **ODER** ≥1 Tabelle **ODER** ≥3 Headings | **Kein LLM-Call.** Body wird 1:1 aus den Segmenten übernommen (Struktur ist schon da), danach Stage 4. |
| `stage3` | reiner Prosa-Text ohne starke Struktur | LLM-Veredelung (dieser Abschnitt), danach Stage 4. |
| `gedanken` | `doc_type_guess.label == "gedanke"` | Sonderpfad (Sektion 12): kein Stage 3, Minimal-Frontmatter über Stage-4-Variante. |

Begründung: strukturierte Docs (Cheatsheets, Tabellen, Code) verlieren durch LLM-Umschreiben Information; sie brauchen nur Frontmatter. Das spart Token, Zeit und Halluzinations-Risiko.

**Zweck (Pfad `stage3`):** 1 Doc → 1 veredelter Artikel-Body nach Vault-Standard, ohne Frontmatter. Kein Merge mit anderen Docs. Normalisierung + Strukturierung nach `type`-Template.

**Input:**
- Alle Segmente eines einzelnen Docs (Originaltext)
- Vault-Standard-Auszug (Sprach-Regeln, Code-Block-Regel B4, `type`-Template)

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
- Segment-Metadaten des Source-Docs (sources_docs, source_chunks)
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
  "merged_from": [],                          // immer leer in Option B
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
- Aliases nur aus alternativen Bezeichnungen im Source-Doc (kein `merged_from`)
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

**Bei Failure:** `confidence: low` setzen, in `work/qwen/needs_human.jsonl` flaggen (Pfad zentral über `pipeline/_paths.py`), weiterlaufen mit nächstem Doc.

---

## 9. Token-Budget (Schätzung)

| Stage | Input-Tokens (Range) | Output-Tokens | Kommentar |
|---|---|---|---|
| ~~1~~ | ~~10K–35K~~ | ~~2K–8K~~ | *deaktiviert (Option B)* |
| ~~2~~ | ~~5K–15K~~ | ~~1K–4K~~ | *deaktiviert (Option B)* |
| 3 | 5K–35K | 3K–10K | Pro-Doc (nur Pfad `stage3`); `passthrough` macht keinen Call; 35K wegen 50K-Kontext + Reasoning-Output-Raum |
| 4 | 5K–15K | 1K–3K | strukturiertes JSON |

**`max_tokens` pro Call** (`pipeline.config.yaml` → `qwen.max_tokens`, 10× Content wegen ~93 % Reasoning-Overhead): **stage3 = 16000** (höchster Bedarf, voller Markdown-Body), stage4 = 10000. stage1/stage2 (20000/14000) sind **deprecated** (Option B) und ungenutzt.

**Bei Überschreitung 35K Input (Stage 3):** Doc aufteilen oder Sub-Batches bilden, in Phase 7 (Batch-Bildung) nachjustieren. Stage 4 hat kleineren Input und bleibt im 50K-Limit.

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

> **Status: nicht implementiert.** Die ursprünglich geplante synthetische
> Test-Cluster-Suite (`tests/fixtures/qwen_clusters/` mit `small_clear_cluster/`,
> `large_mixed_cluster/`, `contradictory_cluster/`) und ein `pkm test-prompts`-Runner
> wurden **nie gebaut**. Es existiert kein dedizierter Prompt-Schema-Test. Die
> Prompt-Qualität wird de facto über den realen Lauf + **manuelle Output-Inspektion**
> an den Review-Gates geprüft, nicht über eine automatisierte Regression-Suite.

**Faktischer Prozess pro Prompt-Iteration:**
- Prompt-Patch in `prompts/v1/` (eine logische Änderung)
- Re-Run auf 1–2 echten Docs (`pkm process --source <dir>` / `pkm run`)
- Manuelle Bewertung des Drafts gegen die erwartete Struktur (§7) am Review-Gate
- Schema-Konformität sichert die Pipeline-seitige Pydantic-Validation (§8), nicht ein Prompt-Test

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
- 2026-05-29 — Option-B-Anpassung: Stage-Übersicht Stage 1/2 als deaktiviert markiert; Stage-1/2-Detailabschnitte mit Status-Note versehen; Review-Gate-2-Verweis gestrichen; Stage 3 zu Pro-Doc-Veredelung umbenannt + Input neu; Stage 4 Input auf Segment-Metadaten, Aliases-Constraint auf Source-Doc-only, merged_from-Kommentar
- 2026-06-04 — Routing-Modell in Stage 3 (passthrough vs. stage3 vs. gedanken) ergänzt; `max_tokens`-Bezug zur Config (stage3=16000); Intro + Token-Budget auf Ist-Stand
- 2026-06-05 — Phase 12: Hang-Lehre dokumentiert (Reasoning-Loop bei Meta-/Prompt-Inhalt, Timeout wirkungslos, Mitigation passthrough/cap)
- 2026-06-25 — Konsolidierung (verify-first gegen Repo): §4 Verzeichnis-Layout auf Ist-Stand (v1 inkl. `stage4_frontmatter_gedanken.md` + 4 Schemas; v2 = realer isolierter restructure-Pfad WP3c-4, nicht Placeholder; kein `examples/`, kein `README.md`); §8 `needs_human`-Pfad `data/02_pipeline_output/` → `work/qwen/`; §11 Testing als **nicht implementiert** gekennzeichnet (qwen_clusters-Fixtures + `test-prompts`-Runner nie gebaut)
