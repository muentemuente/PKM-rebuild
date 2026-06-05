---
task_id: 0G
title: Vault-Foundations — Tag-Vokabular, Templates, 15_Gedanken-Sonderpfad
status: open
owner: mixed (App-led + CC-supported)
priority: P1
depends_on: []
created: 2026-05-28
updated: 2026-05-28
estimated_effort: 4–6h (verteilt auf mehrere Sessions)
---

# Block 0.G — Vault-Foundations

## Kontext

Vor Phase 9 müssen die Vault-Standards aus `docs/03_vault_standard.md` materialisiert werden. Drei Lücken:
1. **Tag-Vokabular** `00_Meta/tag-system.md` existiert nicht — Stage 4 validiert ins Leere (`tags.strict_vocabulary: false` als Workaround)
2. **11 Templates** in `data/04_vault/00_Meta/` fehlen vollständig (Vault-Standard Sektion 12)
3. **Sonderpfad `15_Gedanken/`** (laut `docs/04_qwen_prompts.md` Sektion 12) ist weder im Code noch in Prompts implementiert

## Pflicht-Lektüre

1. `/CLAUDE.md`
2. `docs/00_persona_muente.md`
3. `docs/06b_tool_routing.md`
4. `docs/03_vault_standard.md` (komplett, mind. Sektionen 7, 8, 12, 13)
5. `docs/04_qwen_prompts.md` Sektionen 7 + 12
6. `prompts/v1/stage4_frontmatter_json.md` (Vorlage für Gedanken-Variant)
7. `pipeline/phase_8_synthesis.py` (für Routing-Logik)
8. `pipeline/schemas.py` (FrontmatterDraft)

---

## Task 0G.1 — Tag-Inventar-Heuristik (CC)

**Owner:** Claude Code (autonom)

**Ziel:** Datengetriebener Vorschlag für initiales Tag-Vokabular, basierend auf existierenden Frontmatter-Tags im Korpus + Heading-Begriffen + Dateinamen-Mustern. Ergebnis ist Input für Block 0G.2 (App-Kuratierung).

**Neue Datei:** `scripts/tag_inventory.py`

**Logik:**
1. Iteriere alle 203 Files in `data/01_corpus_input/`
2. Extrahiere:
   - YAML-Frontmatter `tags`-Feld (wenn vorhanden)
   - H1/H2-Heading-Texte → Tokenize → unigrams + bigrams
   - Dateinamen-Tokens (Underscore/Bindestrich-getrennt)
3. Normalisiere: kleinschreibung, Umlaute mappen, Bindestriche
4. Aggregiere: Häufigkeit, Beleg-Files pro Kandidat
5. Stop-Word-Filter (deutsch + englisch, mit `mit`, `und`, `der`, `die`, `the`, `and`, `or`, …)
6. Mindestfrequenz: ≥2 Files (sonst Lärm)

**Output:** `data/02_pipeline_output/tag_inventory.md`

**Format:**
```markdown
---
title: Tag-Inventar (heuristisch)
slug: tag-inventory
status: draft
generated: <ISO-Datum>
---

# Tag-Inventar (Vorschlag für Vokabular-Kuratierung)

## Sektion A — Aus existierendem Frontmatter (höchste Vertrauenswürdigkeit)
| Tag | Häufigkeit | Beleg-Files (max 3) |
|---|---|---|
| markdown | 14 | yaml_frontmatter.md, markdown_cheatsheet.md, … |

## Sektion B — Aus Headings (mittlere Vertrauenswürdigkeit)
| Tag | Häufigkeit | Beleg-Files (max 3) |
|---|---|---|

## Sektion C — Aus Dateinamen (Hinweis-Charakter)
| Tag | Häufigkeit | Beleg-Files (max 3) |
|---|---|---|

## Cluster-Vorschlag (gruppiert nach Themen-Nähe)
- **Tech / Code:** python, markdown, yaml, git, github
- **Daten / Strukturen:** csv, json, frontmatter, schema
- ...

## Stats
- Files gescannt: 203
- Kandidaten gesamt (Sektion A+B+C): N
- Empfehlung Vokabular-Größe: 30–50
```

**Akzeptanzkriterien:**
- Skript läuft via `python scripts/tag_inventory.py`
- Output-File >5 KB, mind. 30 Tag-Kandidaten
- Keine Tags mit nur 1 Beleg
- Keine Stop-Wörter
- Frontmatter valid (parsebar)

**Tests:**
- `tests/test_tag_inventory.py` (mind. 3 Tests: Normalisierung, Frequenz-Filter, Frontmatter-Extraktion)

**Commit:** `feat(scripts): tag-inventar-heuristik als basis für vokabular-kuratierung`

### 🛑 App-Checkpoint nach 0G.1 — STOP

```
Block: 0.G
Erledigt: 0G.1
Output-File: data/02_pipeline_output/tag_inventory.md (N Tags Sektion A, M Sektion B, K Sektion C)
Commit: <hash>
Nächster Schritt: 0G.2 ist App-Domäne — User kuratiert in App-Session
Frage an App: Inventar in App-Konversation hochladen für Kuratierung?
```

CC wartet hier zwingend auf User. 0G.2 läuft NICHT in CC.

---

## Task 0G.2 — Tag-Vokabular kuratieren (App)

**Owner:** App-Konversation (Mensch + Claude.ai)

**Status:** ausstehend nach 0G.1

**Ziel:** `data/04_vault/00_Meta/tag-system.md` mit finalem Tag-Vokabular.

**Workflow:**
1. `data/02_pipeline_output/tag_inventory.md` aus 0G.1 in App-Konversation hochladen
2. Gemeinsam kuratieren:
   - Max 30–50 Tags Gesamt
   - Synonyme zusammenführen (Aliases dokumentieren)
   - Kategorien NICHT als Tags duplizieren (z.B. `webentwicklung` ist Kategorie, kein Tag)
   - Querschnittsthemen explizit (`security`, `performance`, `automation`, …)
3. Final-File in App generieren, lokal ablegen via Drag-Drop oder Editor
4. In Repo committen (Mensch oder via CC mit Auftrag)

**Format laut Vault-Standard Sektion 7:**

```markdown
---
title: Tag-System
slug: tag-system
status: stable
type: compact-reference
doc_role: [reference]
category: meta
created: <Datum>
updated: <Datum>
---

# Tag-System

Kontrolliertes Vokabular für alle Concept-Notes im Vault.

## Querschnittsthemen
- security
- performance
- automation
- privacy
...

## Tech-Domänen
- python
- markdown
- git
...

## Aliases / Synonyme
- ki → ai
- konfiguration → configuration
- doku → documentation

## Pflege
Erweiterungen brauchen Begründung + Eintrag hier.
```

**Akzeptanzkriterien:**
- File existiert in `data/04_vault/00_Meta/tag-system.md`
- 30–50 Tags
- Vault-Standard Sektion 7 erfüllt
- `status: stable`

---

## Task 0G.3 — Tag-Vokabular-Validation im Code (CC, nach 0G.2)

**Owner:** Claude Code

**Voraussetzung:** 0G.2 ist abgeschlossen (Datei vorhanden).

**Datei:** `pipeline/phase_8_synthesis.py`

**Akzeptanzkriterien:**
- Neue Funktion `_load_tag_vocabulary(vocab_path: Path) -> set[str]`:
  - Parst die Markdown-Datei, extrahiert alle Bullet-Point-Tags aus den Sektionen
  - Aliases werden zu Haupt-Tags aufgelöst (rechts der Pfeil)
  - Bei FileNotFoundError: leeres Set, Warnung loggen
- In Stage 4 nach Pydantic-Validation:
  - Laden des Vokabulars (über Config-Pfad)
  - Wenn `tags.strict_vocabulary: false`: nicht-passende Tags loggen (`log.info`), nichts ändern
  - Wenn `true`: Tags außerhalb Vokabular werden aus FM entfernt, `confidence: low`, needs_human-Eintrag mit reason `tags_not_in_vocabulary`
- Neue Tests:
  - `test_load_tag_vocabulary_parses_markdown`
  - `test_load_tag_vocabulary_resolves_aliases`
  - `test_stage4_strict_vocabulary_removes_unknown_tags`
  - `test_stage4_loose_vocabulary_only_logs`

**Commit:** `feat(phase_8): tag-vokabular-validation in stage 4`

---

## Task 0G.4 — Template-Skelette generieren (CC)

**Owner:** Claude Code

**Ziel:** 10 Template-Skelette in `data/04_vault/00_Meta/`. `tag-system.md` entsteht separat in 0G.2 — NICHT hier.

**Files (laut Vault-Standard Sektion 12):**
1. `artikel-template-grundlagen.md` — Vorlage für `knowledge-article`
2. `artikel-template-kompaktreferenz.md` — Vorlage für `compact-reference`
3. `artikel-template-prozessdokument.md` — Vorlage für `process-document`
4. `frontmatter-standard.md` — Auszug aus `docs/03_vault_standard.md` Sektion 3
5. `naming-conventions.md` — Auszug aus Sektion 5
6. `review-prozess.md` — Auszug aus Sektion 8 (inkl. Checkliste)
7. `dokumentationsstandard.md` — Sprach- und Format-Regeln (Sektion 6)
8. `quellenbewertung.md` — Skelett, App finalisiert inhaltlich
9. `changelog.md` — leeres Skelett mit Initial-Eintrag
10. `readme.md` — Vault-Einstieg (Was ist wo)

**Pro File:**
- Frontmatter:
  ```yaml
  ---
  title: <konkret>
  slug: <konkret>
  type: compact-reference
  doc_role: [reference, manual]
  category: meta
  tags: [meta, vault-standard]
  status: draft
  review_status: ai_drafted
  confidence: medium
  doc_version: "0.1.0"
  created: <heute>
  updated: <heute>
  sources_docs: ["D_docs-03-vault-standard"]
  source_chunks: []
  ---
  ```
- H1 = Titel
- Skelett-Struktur (Sections aus Vault-Standard ableitbar)
- Wo App-Finalisierung nötig: `> [!todo] Inhaltliche Finalisierung in App-Session 0G.5`

**Akzeptanzkriterien:**
- 10 Files vorhanden in `data/04_vault/00_Meta/`
- Alle haben valides Frontmatter (Pydantic `FrontmatterDraft` validiert)
- TODO-Marker an Stellen, wo inhaltlich nichts aus Vault-Standard 1:1 übernehmbar ist
- Templates sind syntaktisch valides Markdown

**Tests:** keine zusätzlichen Code-Tests nötig — Pydantic-Validation reicht. Optional: 1 Test in `test_vault_templates.py` der alle Files lädt und gegen `FrontmatterDraft` validiert.

**Commit:** `feat(vault): template-skelette in 00_meta/`

### ⏸ App-Checkpoint nach 0G.4

```
Block: 0.G
Erledigt: 0G.4
Output: 10 Template-Skelette in data/04_vault/00_Meta/
Commit: <hash>
Nächster Schritt: 0G.5 ist App-Domäne (inhaltliche Finalisierung)
Frage an App: Reihenfolge der Finalisierung? Empfohlen: dokumentationsstandard.md zuerst (steuert Stil)
```

---

## Task 0G.5 — Templates inhaltlich finalisieren (App)

**Owner:** App-Konversation (Mensch + Claude.ai)

**Status:** ausstehend nach 0G.4

Pro Template-Skelett aus 0G.4 in App-Session inhaltlich anreichern, `> [!todo]`-Marker entfernen, `status: stable` setzen.

**Empfohlene Reihenfolge:**
1. `dokumentationsstandard.md` (steuert Stil aller anderen)
2. `naming-conventions.md`
3. `frontmatter-standard.md`
4. Die 3 Artikel-Templates (`artikel-template-grundlagen`, `-kompaktreferenz`, `-prozessdokument`)
5. `review-prozess.md`
6. `quellenbewertung.md`
7. `changelog.md`, `readme.md`

**ADHS-Schutz:** max 2 Templates pro App-Session.

---

## Task 0G.6 — 15_Gedanken-Sonderpfad (CC)

**Owner:** Claude Code

### 🛑 App-Checkpoint vor 0G.6 — STOP

Bevor du 0G.6 implementierst, in App-Konversation Architektur-Frage klären:

```
Block: 0.G
Schritt: 0G.6 vor Implementierung
Frage: Detection-Zeitpunkt für Gedanken-Files
Option A: Erkennung in Phase 3 (doc_type_guess), Phase 6 schließt aus
  → bessere Cluster-Qualität, mehr Code-Änderungen, Re-Run nötig
Option B: Erkennung erst in Phase 8 (am Cluster-Label/Inhalt), dynamisches Routing
  → einfacher, schlechtere Cluster-Qualität
Empfehlung: Option A
```

Warte auf Entscheidung. Erst dann implementieren.

**Spec:** `docs/04_qwen_prompts.md` Sektion 12

**Erwartetes Verhalten (Option A):**
- Files mit `doc_type_guess.label == "gedanke"` werden von Phase 6 in Pseudo-Cluster `C_gedanken` gepoolt
- Phase 7 erzeugt keinen normalen Batch für Gedanken, sondern `batch_gedanken.md` mit speziellem Header
- Phase 8 erkennt `C_gedanken`-Batch und routet zu Bypass-Variant:
  - **Skip:** Stages 1, 2, 3
  - **Run:** Stage 4-Gedanken-Variante (1:1 pro File)
- 1:1-Mapping: 1 Korpus-File → 1 `CK_<slug>.md` in `data/03_drafts/`
- Frontmatter:
  - `type: "gedanke"` (neues Enum-Element)
  - `category: "gedanken"`
  - `doc_role: ["wiki"]`
  - `sources_docs`: das eine Original-File
  - `merged_from: []`
  - Tag-Vokabular-Validation: deaktiviert

**Code-Änderungen:**

1. `pipeline/schemas.py`:
   - `FrontmatterDraft.type` Literal erweitern um `"gedanke"`
   - `DocTypeGuess.label` enthält bereits `"gedanke"` ✓

2. `pipeline/phase_6_embeddings.py`:
   - Vor Cluster-Bildung: Filter — Gedanken-Files in eigenen Pseudo-Cluster
   - `cluster_proposals.json` enthält einen Eintrag `C_gedanken` mit allen Gedanken-Segmenten

3. `pipeline/phase_7_batches.py`:
   - Pseudo-Cluster `C_gedanken` erzeugt eigenen Batch-Typ `batch_gedanken.md`
   - Format: Liste von Files, keine Cluster-Analyse
   - Frontmatter `cluster_id: C_gedanken`, `bypass: true`

4. `pipeline/phase_8_synthesis.py`:
   - In `run_phase_8`: erkenne `C_gedanken`-Batch über Frontmatter-Feld `bypass: true`
   - Bypass-Routing: für jedes Source-Doc im Batch → 1 Stage-4-Aufruf direkt mit Gedanken-Prompt
   - Stages 1, 2, 3 werden übersprungen

5. `prompts/v1/stage4_frontmatter_gedanken.md` (neu):
   - Vorlage analog `stage4_frontmatter_json.md`
   - Adaptiert: `type: "gedanke"`, `category: "gedanken"` festgelegt
   - Input: einzelnes Korpus-File-Inhalt + Metadaten
   - Output: Stage-4-Frontmatter direkt, kein Stage-3-Body (Body = Original-Inhalt unverändert)

6. `prompts/v1/schemas/stage4_gedanken_output.schema.json` (neu):
   - JSON-Schema für Gedanken-Frontmatter

**Akzeptanzkriterien:**
- Re-Run der Pipeline auf bestehendem Output erkennt Gedanken-Files (erfordert `--from-phase 6 --force`)
- `batch_gedanken.md` entsteht in `data/02_pipeline_output/batches/`
- Phase 8 verarbeitet Gedanken-Batch ohne Stage 1–3
- Tests:
  - `test_phase_6_gedanken_pseudo_cluster`
  - `test_phase_7_gedanken_batch_format`
  - `test_phase_8_gedanken_bypass_stages_1_to_3`
  - `test_phase_8_gedanken_uses_alternative_prompt`

**Commit:** `feat(phase_6_7_8): 15_gedanken-sonderpfad (bypass stages 1-3)`

### 🛑 App-Checkpoint nach 0G.6 — STOP (Block-Abschluss)

```
Block: 0.G TEILWEISE ABGESCHLOSSEN
Erledigt durch CC: 0G.1, 0G.3 (wenn 0G.2 fertig), 0G.4, 0G.6
Erledigt durch App: 0G.2, 0G.5
Commit(s): <hashes>
Tests: <count> grün
Frage an App: Block 0.G komplett oder noch offene App-Tasks?
```

---

## Reihenfolge

```
0G.1 (CC)
  └─→ 0G.2 (App)
        └─→ 0G.3 (CC)

0G.4 (CC, parallel zu 0G.1/0G.2)
  └─→ 0G.5 (App, iterativ)

0G.6 (CC, parallel, unabhängig — aber Architektur-Checkpoint VOR Code)
```

## Definition of Done für Block 0.G

- [x] 0G.1: Skript läuft, `tag_inventory.md` vorhanden (145 Kandidaten, `e77ea7f`)
- [ ] 0G.2: `00_Meta/tag-system.md` final, App-reviewt, `status: stable` — **⏸ App-Task**
- [ ] 0G.3: Code + Tests grün, Stage 4 nutzt Vokabular — wartet auf 0G.2
- [x] 0G.4: 10 Template-Skelette in `data/04_vault/00_Meta/`, alle Pydantic-valide (2026-05-30)
- [ ] 0G.5: alle 10 Templates auf `status: stable` promoted — **⏸ App-Task**
- [x] 0G.6: Gedanken-Sonderpfad implementiert (Option B, Phase-8-Routing), 7 Tests grün (`0550427`)
- [ ] `status` im Frontmatter dieses Files auf `done`, Notiz im Body-Footer

## Out-of-Scope für 0.G

- Befüllung von `15_gedanken/` selbst (passiert in Phase 8 + 9)
- Wikilink-Pflege in Templates (Phase 9)
- Tag-Vokabular-Strict-Mode aktivieren (Block 0.H oder später)

---

## Änderungs-Log

- 2026-05-28 — Initial-Version
- 2026-05-30 — 0G.1 (tag_inventory.py), 0G.4 (10 Templates), 0G.6 (Gedanken-Sonderpfad) abgeschlossen. 0G.2+0G.5 = App-Tasks. 0G.3 wartet auf 0G.2.
