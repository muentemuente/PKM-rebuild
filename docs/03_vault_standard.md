---
title: PKM-rebuild Vault-Standard
slug: 03-vault-standard
status: stable
created: 2026-05-25
updated: 2026-06-05
---

# Vault-Standard

Single Source of Truth für Frontmatter, Naming, Cluster, Tags, Sprache, Qualitätsstufen. **Verbindlich** für Pipeline-Output, Qwen-Synthese und alle manuell editierten Vault-Files.

---

## 1. Geltungsbereich

Gilt für:
- alle Files in `data/04_vault/`
- alle Drafts in `data/03_drafts/`
- alle Pipeline-Outputs, die als Vault-Vorstufe dienen

Gilt **nicht** für:
- Projekt-Doku in `docs/` (eigenes Frontmatter-Schema)
- Pipeline-Outputs in `data/02_pipeline_output/` (technisch, JSONL)

---

## 2. Identifier-System

Alle IDs slug-basiert, stabil über Re-Runs, lesbar.

| ID-Typ | Format | Beispiel | Verwendung |
|---|---|---|---|
| Korpus-Datei (Pipeline-intern) | `D_<slug>` | `D_yaml-frontmatter` | Pipeline-Phasen 1–7 |
| Segment | `<doc_id>-S<index:04d>` | `D_yaml-frontmatter-S0003` | Pipeline-Phasen 4–8 |
| Concept-Note (Vault-Artikel) | `CK_<slug>` | `CK_yaml-frontmatter` | Vault-Files |
| Cluster (technisch) | `C_<slug>` | `C_apis-http-json` | Pipeline-intern, nicht im Vault |

**Slug-Regeln:** siehe Sektion 5 (Naming Conventions).
**Kollisions-Behandlung:** Bei doppeltem Slug → Suffix `_2`, `_3` etc.

---

## 3. Frontmatter-Schema (verbindlich)

```yaml
---
# === Identität ===
title: ""                          # menschen-lesbar, mit Großschreibung
slug: ""                           # url-safe, identisch mit Dateiname ohne .md
aliases: []                        # alternative Bezeichnungen, generiert aus merged_from

# === Inhalt ===
summary: ""                        # 1–2 Sätze, was ist das
type: ""                           # process-document | knowledge-article | compact-reference | gedanke
doc_role: []                       # manual | how-to | best-practice | workflow | explanation | reference | cheatsheet | wiki
category: ""                       # Vault-Ordner ohne Nummern-Präfix, z.B. "webentwicklung" (16 Ordner + meta + unsortiert → 17_unsortiert)
subcategory: ""                    # 2. Ebene, z.B. "rest-apis"

# === Klassifikation ===
tags: []                           # kontrolliertes Vokabular, max 5–10, kleingeschrieben, EN
related: []                        # [[wikilinks]] verwandter Notes, manuell bestätigt
used_in: []                        # in welchen Workflows referenziert (initial leer)

# === Hierarchie ===
parent_concept: null               # CK_xxxx oder null
child_concepts: []                 # Liste CK_xxxx

# === Provenance ===
sources_docs: []                   # D_<slug>-Liste, alle Original-Quellen aus Korpus
source_chunks: []                  # segment_ids für Trace
merged_from: []                    # IMMER LEER — Option B macht keinen Cross-Doc-Merge (1 Doc → 1 Concept)

# === Status & Qualität ===
status: draft                      # draft | review | stable | deprecated
review_status: ai_drafted          # ai_drafted | human_reviewed | verified
confidence: medium                 # high | medium | low — von Qwen gesetzt

# === Versionierung ===
doc_version: "0.1.0"               # semver-style, beschreibt Artikel-Stand (nicht Technologie)
technology_versions: {}            # optional, z.B. { astro: "5.x", tailwind: "4.x" }

# === Zeit & Reproduzierbarkeit ===
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"              # menschliche Edit-Zeit
last_synthesized: "YYYY-MM-DD"     # letzte Qwen-Synthese
prompt_version: "v1"               # Prompt-Set zur Synthese
---
```

### Pflichtfelder vs. optional

| Pflicht | Optional |
|---|---|
| `title`, `slug`, `summary` | `aliases` |
| `type`, `doc_role`, `category` | `subcategory`, `tags`, `related` |
| `sources_docs`, `source_chunks` | `merged_from`, `used_in`, `parent_concept`, `child_concepts` |
| `status`, `review_status`, `confidence` | `technology_versions` |
| `doc_version`, `created`, `updated` | |
| `last_synthesized`, `prompt_version` (wenn KI-erstellt) | |

### Enum-Werte

| Feld | Erlaubte Werte |
|---|---|
| `type` | `process-document`, `knowledge-article`, `compact-reference`, `gedanke` |
| `doc_role` | `manual`, `how-to`, `best-practice`, `workflow`, `explanation`, `reference`, `cheatsheet`, `wiki` |
| `status` | `draft`, `review`, `stable`, `deprecated` |
| `review_status` | `ai_drafted`, `human_reviewed`, `verified` |
| `confidence` | `low`, `medium`, `high` |

---

## 4. Cluster-Struktur

### Ordner-Hierarchie

```
data/04_vault/
├── 00_Meta/                              ← Regeln, Templates, Standards
├── 01_Grundlagen/
├── 02_Webentwicklung/
├── 03_Betriebssysteme/
├── 04_Protokolle-und-Standards/
├── 05_Dateitypen-und-Konfiguration/
├── 06_Methoden-und-Prozesse/
├── 07_Best-Practices/
├── 08_Cheatsheets/
├── 09_KI-und-Semantische-Systeme/
├── 10_Datenarchitektur-und-Datenbanken/
├── 11_Dokumentenverarbeitung-und-Extraktion/
├── 12_Wissensmodellierung-und-Knowledge-Graphs/
├── 13_Visualisierung-Reporting-und-Design-Systeme/
├── 14_Automatisierung-Scripting-und-Pipelines/
├── 15_Gedanken/
├── 16_Kunst-Kultur/
├── 17_unsortiert/                        ← regulärer Cluster: Mapping-Lücke / Domäne ohne eigenen Ordner
└── _attic/                               ← deprecated, nicht gelöscht (einziger Sonderordner)
```

### Ordner-Zuordnung (Embedding-Clustering verworfen)

> **Architektur-Hinweis (2026-06-04):** Embedding-/HDBSCAN-Clustering ist **verworfen** — der Korpus hat keine inhärente Cluster-Struktur (siehe `01_strategy.md` R9). Die 16 Ordner sind ein **fixes, kuratiertes Schema**, keine berechneten Cluster. Die Zuordnung läuft über `category` aus **Qwen-Stage-4** plus ein **deterministisches Mapping** auf die 16 Ordner (siehe Appendix A — Category-Mapping).

- **`category` im Frontmatter** entspricht Ordnername **ohne Nummern-Präfix** (z.B. `webentwicklung`, nicht `02_webentwicklung`). Sonderfall: `category: unsortiert` → Ordner `17_unsortiert/` (Wert bleibt `unsortiert`, der Nummern-Präfix ist nur Ordnername).
- **`17_unsortiert/`**: vollwertiger nummerierter Cluster für schwache/uneindeutige Zuordnungen (z.B. Business-Domänen ohne eigenen Ordner) — bekommt wie jeder genutzte Cluster ein `_index.md`; später per Hand zuordnen (`scripts/manage_vocab.py` + Frontmatter-Edit) oder belassen
- **`_attic/`** ist der **einzige Sonderordner** (deprecated, kein `_index.md`); `00_Meta` enthält Standards/Templates statt Concept-Notes und bekommt deshalb ebenfalls kein `_index.md`
- **Ordnernummern sind UX**, keine Daten — können bei Restrukturierung neu vergeben werden
- **`00_Meta`** und **`15_Gedanken`** folgen eigenen Regeln:
  - `00_Meta`: keine inhaltliche Bewertung, enthält Standards/Templates
  - `15_Gedanken`: kein Merge, kein Embedding, `type: gedanke`, Minimal-Frontmatter (Sonderpfad Phase 8)

### Cluster-Index-File (`_index.md`)

Pro genutztem Vault-Ordner automatisch generiert in Phase 9. Inhalt:
- Anzahl Artikel im Ordner
- Liste aller Artikel mit `title`, `slug`, `status`
- Tag-Häufigkeiten innerhalb des Ordners
- Letzte Aktualisierung

---

## 5. Naming Conventions

### Regeln (Dateinamen + Slugs)

- Kleinschreibung
- Wörter mit Bindestrich trennen (`-`)
- Keine Leerzeichen
- Keine Umlaute (`ä` → `ae`, `ö` → `oe`, `ü` → `ue`, `ß` → `ss`)
- Keine Sonderzeichen außer Bindestrich
- Kurz, aber eindeutig
- Englische Fachbegriffe wenn Standard, deutsche erklärende Begriffe wenn verständlicher
- Keine Versions-/Datumssuffixe im Namen (außer Teil des Themas)

### Slug = Dateiname ohne `.md`

```yaml
title: "YAML und Frontmatter"
slug: "yaml-frontmatter"            # = yaml-frontmatter.md
```

### Beispiele

| Gut | Schlecht |
|---|---|
| `yaml-frontmatter.md` | `YAML Frontmatter.md` |
| `http-https.md` | `HTTP & HTTPS!.md` |
| `static-site-generation.md` | `Meine Notizen zu Static Site Generation.md` |
| `wissensartikel-erstellung.md` | `Wissensartikel_Erstellung_final_neu.md` |
| `semantische-inhaltsanalyse.md` | |
| `mcp-in-ki-workflows.md` | |

### Titel im Frontmatter

Lesbarer als Slug. Großschreibung erlaubt. Beispiel:

```yaml
title: "HTTP und HTTPS"
slug: "http-https"
```

### Kanonische Slug-Ableitung (verbindlich)

Die Pipeline leitet Slugs **deterministisch** aus dem Korpus-Dateinamen ab. Identische Logik in `pipeline/phase_1_inventory.py:_filename_to_slug` (doc_id) und `pipeline/phase_8_synthesis.py:_slugify_ck` (CK-Slug); `scripts/phase8_runner.py:canonical_ck_slug` repliziert sie für die Draft-Verifikation (Drift durch Test bewacht).

Schritte:

1. **NFC-Normalisierung zuerst** — macOS liefert Dateinamen NFD-zerlegt (`o` + combining ¨). Ohne Komposition matcht die Umlaut-Tabelle nicht und NFKD würde `ä→a` statt `ä→ae` strippen (E2-Bug, behoben 2026-06-04).
2. **Umlaut-Map:** `ä→ae`, `ö→oe`, `ü→ue`, `ß→ss` (Composed + Uppercase).
3. NFKD + Combining-Strip (Akzente weg), lowercase.
4. Sonderzeichen → Bindestrich (`[^a-z0-9]+ → -`), führende/abschließende `-` entfernen.
5. **60-Zeichen-Cap** auf dem CK-Slug.
6. **Kollisions-Suffix:** bei doppeltem Slug `_2`, `_3` … (`_assign_doc_ids` bzw. `_unique_slug`).

```text
"Lösung Übersicht.md"  (NFD)  → loesung-uebersicht
"erklärung_sage.md"           → erklaerung-sage
```

---

## 6. Sprache (DE/EN-Hybrid)

| Element | Sprache | Beispiel |
|---|---|---|
| Artikel-Inhalt (Body) | Deutsch | „REST ist ein Architektur-Stil …" |
| `title` | Deutsch | `"HTTP und HTTPS"` |
| `summary` | Deutsch | `"Erklärung der Unterschiede zwischen HTTP und HTTPS …"` |
| `slug` | Englisch | `http-https` |
| `tags` | Englisch | `http`, `tls`, `security` |
| `category`, `subcategory` | Deutsch (Ordnername) | `webentwicklung`, `rest-apis` |
| `doc_role`, `type`, `status` | Englisch (Enum) | `tutorial`, `stable` |
| Code & Code-Kommentare | EN für Identifier, DE für Kommentare | `# Lade Konfiguration` |
| Heading im Body | Deutsch | `## Grundlagen` |

**Regel-Quelle:** Englisch wo Tech-Standard, Deutsch wo Verständnis verbessert wird.

---

## 7. Tag-System

### Regeln

- Klein geschrieben
- Englisch (Tech-Begriffe sind Standard)
- Kontrolliertes Vokabular (siehe `00_Meta/tag-system.md` — aus Phase 9 generiert)
- Max. 5–10 Tags pro Artikel
- Synonyme vermeiden
- Kategorien **nicht** als Tags duplizieren (`category: webentwicklung` ≠ `tag: webentwicklung`)
- Tags für Querschnittsthemen nutzen (`security`, `performance`, `automation`)

### Beispiel

```yaml
tags:
  - "markdown"
  - "metadata"
  - "yaml"
  - "documentation"
  - "knowledge-management"
```

### Vokabular-Aufbau

- **Initiale Pflege:** Phase 9, Mensch finalisiert Liste in `00_Meta/tag-system.md`
- **Erweiterung:** neue Tags brauchen Begründung + Eintrag im Vokabular → `scripts/manage_vocab.py add-tag <tag> --reason "…"` (schreibt mit Begründung ins Kern-Vokabular)
- **Drift-Check:** `scripts/manage_vocab.py validate` meldet Tags in Vault/Drafts, die nicht im Vokabular stehen
- **Qwen-Vorschlag in Stage 4:** Tags werden vorgeschlagen, müssen aber gegen Vokabular validiert werden (Pipeline-Check)

---

## 8. Status & Qualitätsstufen

### Status-Lifecycle

```
draft → review → stable → deprecated
              ↓
         (zurück möglich)
```

- `draft`: Initial-Zustand nach Qwen-Synthese
- `review`: Mensch hat angeschaut, noch nicht final freigegeben
- `stable`: geprüft, freigegeben, produktiv
- `deprecated`: ersetzt oder veraltet, ggf. in `_attic/`

**Bulk-Promotion** `draft → stable` ist verboten. Promotion immer per Hand pro File.

### Qualitätsstufen (orthogonal zu Status)

| Stufe | Bezeichnung | Merkmale | Typischer Status |
|---|---|---|---|
| 1 | Rohnotiz | unstrukturiert, keine vollständigen Quellen, keine Einordnung | `draft` |
| 2 | Strukturierter Artikel | Template angewendet, Frontmatter vorhanden, zentrale Abschnitte ausgefüllt, verwandte Themen ergänzt | `draft` oder `review` |
| 3 | Geprüfter Wissensartikel | offizielle Quellen geprüft, Beispiele getestet, Begriffe definiert, Fehlerquellen ergänzt, Änderungsverlauf gepflegt | `stable` |
| 4 | Referenzfähiger Kernartikel | didaktisch verständlich, technisch korrekt, mit Cheatsheet/Prozessdoku verbunden, Wikilinks gesetzt, Review-Zyklus | `stable` |

**DoD-Mindestlevel:** Alle Vault-Files mind. Stufe 2.

### Review-Checkliste (vor Promotion auf `stable`)

```markdown
- [ ] Frontmatter vollständig (alle Pflichtfelder)
- [ ] Titel eindeutig
- [ ] Kurzdefinition (`summary`) verständlich
- [ ] Thema systemisch eingeordnet (`category`, `subcategory`)
- [ ] Grundbegriffe erklärt
- [ ] Beispiele vorhanden
- [ ] häufige Fehler dokumentiert
- [ ] Quellen ergänzt (`sources_docs`)
- [ ] offizielle Dokumentation geprüft
- [ ] verwandte Themen verlinkt (`related`)
- [ ] Tags gegen Vokabular validiert
- [ ] Review-Datum gesetzt (`updated`)
- [ ] Änderungsverlauf aktualisiert
- [ ] keine offensichtlichen Redundanzen
- [ ] keine ungeprüften Sicherheitsrisiken
```

---

## 9. Provenance & Hierarchie

### Provenance-Felder

| Feld | Bedeutung |
|---|---|
| `sources_docs: []` | Alle Original-Korpus-Dateien (`D_<slug>`), aus denen dieser Concept entstand |
| `source_chunks: []` | Konkrete Segment-IDs für RAG-Trace und Auditierbarkeit |
| `merged_from: []` | **Immer leer** — Option B konsolidiert nicht über Docs (1 Doc → 1 Concept) |

**Regel:** `source_chunks` bleibt sichtbar im Frontmatter (Auditierbarkeit + Lernwert).

### Hierarchie-Felder

| Feld | Bedeutung |
|---|---|
| `parent_concept: null` | Übergeordneter Concept (`CK_xxxx`), oder `null` wenn Top-Level |
| `child_concepts: []` | Untergeordnete Concepts |

**Initial-Befüllung:** Qwen schlägt vor in Stage 4, Mensch bestätigt.

**Beispiel:**
```yaml
# In CK_rest-api:
parent_concept: "CK_apis"
child_concepts: ["CK_rest-status-codes", "CK_rest-methods"]
```

---

## 10. Wikilinks (`related`, `used_in`)

### `related`

- Verwandte Concept-Notes, manuelle Bestätigung Pflicht (Embedding-Vorschläge gehen durch Review)
- Format: `[[CK_<slug>]]` oder Title-basiert `[[YAML und Frontmatter]]` (Obsidian-kompatibel)
- Bidirektional sinnvoll, aber nicht erzwungen

### `used_in`

- Workflows / Prozessdokumente, die diesen Concept referenzieren
- Initial leer; wird gepflegt, wenn Prozessdokumente angelegt werden
- Pflege erfolgt am referenzierenden Doku, nicht am referenzierten Concept

---

## 11. Redundanz-Regelwerk

Redundanz ist nicht grundsätzlich schlecht. Sie ist problematisch, wenn dieselbe Information an mehreren Stellen unterschiedlich gepflegt wird.

### Regeln

| Dokumenttyp | Inhaltliche Verantwortung |
|---|---|
| Hauptartikel (`knowledge-article`) | Definitionen, Erklärungen |
| Cheatsheets (`compact-reference`, `doc_role: cheatsheet`) | Kurzformen, Verweis auf Hauptartikel |
| Prozessdokumente (`process-document`) | Verweis auf Definition, beschreibt Ablauf |
| Best-Practice-Dokumente (`doc_role: best-practice`) | Bewertet Anwendung, nicht Definition |
| Cluster-Index (`_index.md`) | Ordnet ein, ersetzt keinen Fachartikel |

### Konsolidierungs-Regel

- Definition steht **genau einmal** im Hauptartikel
- Andere Dokumente: Wikilink zur Definition, keine duplizierte Definition
- Bei Konflikt zwischen Cheatsheet und Hauptartikel: Hauptartikel gewinnt

### Codeblock-Sonderregel

Wenn ein Markdown-Dokument selbst Markdown-Codeblöcke demonstriert: äußerer Codeblock muss mehr Backticks haben als innerer.

````markdown
````markdown
```yaml
title: "Beispiel"
```
````
````

---

## 12. Templates (`00_Meta/`)

Werden in Phase 0 erstellt, **vor** Pipeline-Start. Sind Pflicht-Inputs für Qwen-Prompts.

| Template-File | Zweck |
|---|---|
| `artikel-template-grundlagen.md` | Vorlage für `knowledge-article` |
| `artikel-template-kompaktreferenz.md` | Vorlage für `compact-reference` |
| `artikel-template-prozessdokument.md` | Vorlage für `process-document` |
| `frontmatter-standard.md` | Kopie/Auszug dieses Dokuments für Vault-Konsumenten |
| `naming-conventions.md` | Kopie/Auszug für Vault-Konsumenten |
| `tag-system.md` | Kontrolliertes Tag-Vokabular |
| `review-prozess.md` | Review-Checkliste + Promotion-Regeln |
| `dokumentationsstandard.md` | Sprach-, Format- und Stil-Regeln (DE/EN-Hybrid) |
| `quellenbewertung.md` | Wie werden Quellen bewertet (offiziell vs. Community) |
| `changelog.md` | Vault-weiter Änderungslog |
| `readme.md` | Vault-Einstieg, was ist wo |

---

## 13. KI-Umgang (verbindliche Regeln)

KI darf nicht ungeprüft als fachliche Autorität behandelt werden.

| Regel | Bedeutung |
|---|---|
| 1 | Qwen-Outputs sind initial `draft`, `review_status: ai_drafted` |
| 2 | Technische Aussagen müssen mit offiziellen Quellen abgeglichen werden, bevor `stable` |
| 3 | Codebeispiele müssen getestet oder als ungetestet markiert werden |
| 4 | Versionsabhängige Aussagen brauchen Datum/Versions-Bezug (`technology_versions`) |
| 5 | Sicherheitsrelevante Empfehlungen besonders prüfen |
| 6 | Bei Unsicherheit: offene Frage im Artikel dokumentieren (`> [!question]`) |

**Sonderregel `15_Gedanken/`:** Keine Quellen-Pflicht, aber `review_status` bleibt `ai_drafted` wenn KI-generiert.

---

## 14. Aktualisierungs-Routine

Dieses Doc wird gepflegt bei:
- Schema-Änderungen (Frontmatter-Felder, Enums)
- Cluster-Restrukturierung
- Naming-Convention-Änderungen
- Tag-Vokabular-Erweiterungen (Quer-Verweis auf `00_Meta/tag-system.md`)

Bei Schema-Änderung: Schema-Version im Body-Footer notieren, Migration für bestehende Vault-Files planen.

---

## Appendix A — Category-Mapping (E5)

Embedding-Clustering ist verworfen (siehe Sektion 4). `category` entsteht in **zwei Schritten**:

1. **Qwen Stage 4** schlägt eine freie `category` vor (88 distinkte Ist-Werte über 180 Drafts).
2. **Deterministisches Mapping** (`scripts/apply_category_mapping.py`, Single Source of Truth: `data/02_pipeline_output/r3_category_mapping_proposal.md`) bildet diese auf die kanonischen Vault-Kategorien ab. Idempotent, regelbasiert, kein LLM.

### Kanonische `category`-Werte (`ALLOWED_CATEGORIES`, 18)

16 thematische Vault-Ordner (Nummern-Präfix nur als Ordnername, nicht im Feld) plus `meta` (→ `00_Meta/`) und `unsortiert` (→ `17_unsortiert/`):

| # | category | # | category |
|---|---|---|---|
| 01 | `grundlagen` | 09 | `ki-und-semantische-systeme` |
| 02 | `webentwicklung` | 10 | `datenarchitektur-und-datenbanken` |
| 03 | `betriebssysteme` | 11 | `dokumentenverarbeitung-und-extraktion` |
| 04 | `protokolle-und-standards` | 12 | `wissensmodellierung-und-knowledge-graphs` |
| 05 | `dateitypen-und-konfiguration` | 13 | `visualisierung-reporting-und-design-systeme` |
| 06 | `methoden-und-prozesse` | 14 | `automatisierung-scripting-und-pipelines` |
| 07 | `best-practices` | 15 | `gedanken` |
| 08 | `cheatsheets` | 16 | `kunst-kultur` |
| 00 | `meta` (00_Meta) | 17 | `unsortiert` (17_unsortiert) |

### Resultierende Verteilung (180 aktive Drafts, nach Mapping)

`automatisierung-scripting-und-pipelines` 42 · `grundlagen` 37 · `visualisierung-reporting-und-design-systeme` 17 · `ki-und-semantische-systeme` 16 · `datenarchitektur-und-datenbanken` 12 · `webentwicklung` 8 · `kunst-kultur` 8 · `betriebssysteme` 8 · `unsortiert` 8 · `methoden-und-prozesse` 7 · `dokumentenverarbeitung-und-extraktion` 5 · `dateitypen-und-konfiguration` 5 · `wissensmodellierung-und-knowledge-graphs` 4 · `protokolle-und-standards` 2 · `meta` 1.

> Offene Mapping-Entscheidungen (generische Dev-Kategorien → `automatisierung-…`, Business-Domänen → `unsortiert`, Bild/Film-Grenze) sind im Proposal dokumentiert.

---

## Änderungs-Log

- 2026-05-25 — Initial-Version, konsolidiert aus Frontmatter-Schema + Vault-Struktur + Entscheidungen N1–N3
- 2026-06-04 — `type`-Enum auf 4 Werte (`gedanke`, E1); kanonische Slug-Ableitung (NFC + Umlaut + 60-Cap + unique, E2); Sektion 4 auf fixes Ordner-Schema (Embedding-Clustering verworfen, R9); `merged_from` immer leer (Option B); Appendix A Category-Mapping (E5)
- 2026-06-05 — `unsortiert/` → `17_unsortiert/` als vollwertiger nummerierter Cluster (AP2): Sektion 4 (Ordner-Hierarchie, `_attic/` einziger Sonderordner), Appendix A (category `unsortiert` → `17_unsortiert/`). category-Wert bleibt `unsortiert`.
