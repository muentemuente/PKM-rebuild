---
title: PKM-rebuild Glossar
slug: 05-glossary
status: stable
created: 2026-05-25
updated: 2026-06-05
---

# Glossar

Projektspezifische Begriffsdefinitionen. Bei Konflikt zwischen Doku und Glossar gewinnt der ausführliche Eintrag im zugehörigen Spec-Dokument.

---

## Identifier-Begriffe

### `D_<slug>` — Doc-ID
Eindeutige Kennung für eine Original-Markdown-Datei aus dem Korpus. Slug-basiert, stabil über Re-Runs.
Beispiel: `D_yaml-frontmatter` für die Datei `yaml-frontmatter.md`.
Pipeline-intern. Erscheint im finalen Vault-Artikel nur als Provenance-Spur in `sources_docs`.
Definition: `docs/03_vault_standard.md` Sektion 2.

### `<doc_id>-S<index:04d>` — Segment-ID
Eindeutige Kennung für ein Segment innerhalb einer Doc. Vier-stelliger Zähler.
Beispiel: `D_yaml-frontmatter-S0003` für das dritte Segment.
Erscheint im Vault-Artikel als Provenance in `source_chunks`.

### `CK_<slug>` — Concept-ID
Eindeutige Kennung für einen Concept-Note (= ein Vault-Artikel). Slug-basiert.
Beispiel: `CK_yaml-frontmatter`.
Im Frontmatter via `parent_concept`, `child_concepts`, `merged_from` referenzierbar.

### `C_<slug>` — Cluster-ID (Pipeline-intern)
Technische Kennung für einen Cluster während der Pipeline-Phasen. Erscheint **nicht** im finalen Vault.
Beispiel: `C_apis-rest`.

---

## Pipeline-Begriffe

### Pipeline
Die Python-basierte Verarbeitungskette in `pipeline/`, die Korpus-Inputs in Vault-Outputs transformiert. Phasen 0–10. Vollständig dokumentiert in `docs/02_pipeline_spec.md`.

### Phase
Eine isolierte, idempotente Verarbeitungs-Einheit der Pipeline. Phasen können einzeln, ab einem Startpunkt, oder gesammelt ausgeführt werden. Jede Phase hat definierte Akzeptanzkriterien.

### Stage
Eine Unter-Einheit innerhalb von Phase 8 (Qwen-Veredelung). **Aktiv (Option B): Stage 3** (Pro-Doc-Veredelung des Body) + **Stage 4** (Frontmatter). Stage 1 (Cluster-Analyse) und Stage 2 (Merge-Vorschlag) sind **deprecated** — Option A, kein Cross-Doc-Merge. Jede aktive Stage hat einen eigenen Prompt in `prompts/v<n>/`.

### Idempotenz
Eigenschaft, dass wiederholte Ausführungen mit gleichem Input identische Outputs erzeugen. In der Pipeline durch Hash-basierte Skip-Logik realisiert. Mit `--force` umgehbar.

### Sample-Modus
Reduzierter Pipeline-Lauf mit nur N Files aus dem Korpus (Default: 10), aktiviert via `--sample 10`. Für schnelles Testen ohne Vollverarbeitung.

### Review-Gate
Punkt im Pipeline-Ablauf, an dem ein Mensch eine Entscheidung treffen muss, bevor weitergegangen wird. In Option B: nach Cluster-/Batch-Karte und nach dem Synthese-Draft pro Doc. **Gate 2 (Merge-Vorschläge) entfällt** — kein Cross-Doc-Merge.

### Cluster *(verworfen als Vault-Strukturprinzip)*
Gruppe semantisch verwandter Segmente. Embedding-/HDBSCAN-Clustering wurde **verworfen** — der Korpus hat keine inhärente Cluster-Struktur (`01_strategy.md` R9). Embeddings/TF-IDF dienen nur noch der **Redundanz-Erkennung** (Phase 5/6); die Vault-Ordner sind ein fixes kuratiertes 16er-Schema, `category` kommt aus Qwen-Stage-4 + deterministischem Mapping.

### UMAP / HDBSCAN *(nicht verwendet)*
Dimensionsreduktion (UMAP) + dichtebasiertes Clustering (HDBSCAN), ursprünglich als Phase 7b geplant. **Nicht verwendet / verworfen** (R9) — der Korpus clustert nicht sinnvoll. Code als Lern-Artefakt in `scripts/clustering_analysis.py`, nicht im Produktiv-Pfad.

### `17_unsortiert`
Vollwertiger nummerierter Vault-Cluster (vormals `unsortiert/`) für schwache/uneindeutige `category`-Zuordnungen (z.B. Business-Domänen ohne eigenen Ordner). `category`-Wert bleibt `unsortiert`; bekommt wie jeder genutzte Cluster ein `_index.md`. Zuordnung per Hand über `scripts/manage_vocab.py` + Frontmatter-Edit.

### Embedding
Numerische Vektor-Repräsentation eines Text-Segments, erzeugt durch `paraphrase-multilingual-mpnet-base-v2`. Dimensionsanzahl: 768. Verwendet für semantische Ähnlichkeits-Berechnungen.

### TF-IDF
Term Frequency – Inverse Document Frequency. Klassisches Verfahren zur lexikalischen Ähnlichkeits-Berechnung. In Phase 5 verwendet als günstige Vorstufe vor Embeddings.

---

## Vault-Begriffe

### Vault
Der finale strukturierte Obsidian-Ordner unter `~/projects/aktiv/PKM_rebuild/data/04_vault/`. Enthält alle Concept-Notes mit Frontmatter, organisiert in Cluster-Ordnern.

### Korpus / Corpus
Die ursprüngliche Sammlung unstrukturierter Markdown-Dateien unter `~/projects/aktiv/PKM_rebuild/data/01_corpus_input/`. Read-only. Quelle für die Pipeline.

### Concept-Note
Ein Vault-Artikel (`.md`-Datei) mit `CK_<slug>` als Identität. Entsteht aus einem oder mehreren Korpus-Segmenten durch Qwen-Synthese.

### Frontmatter
YAML-Block am Anfang einer Markdown-Datei, eingeschlossen in `---`-Zeilen. Enthält Metadaten (Titel, Status, Tags, Provenance, etc.). Vollständige Schema-Definition: `docs/03_vault_standard.md` Sektion 3.

### Slug
URL-sichere Kurzform eines Titels. Entspricht dem Dateinamen ohne `.md`. Naming-Conventions: Kleinschreibung, Bindestriche, keine Umlaute, keine Sonderzeichen.

### Wikilink
Obsidian-spezifische Link-Syntax `[[CK_yaml-frontmatter]]` oder `[[YAML und Frontmatter]]`. Verbindet Concept-Notes innerhalb des Vaults. Pflege erfolgt manuell, basierend auf Embedding-Vorschlägen.

### Ordner-Index
Pro genutztem Vault-Ordner eine `_index.md`-Datei, automatisch in Phase 9 generiert. Listet alle Artikel im Ordner mit Title, Status, Tags. Regenerierbar.

### Provenance
Spur, woher ein Vault-Artikel inhaltlich stammt. Realisiert durch die Felder `sources_docs`, `source_chunks`, `merged_from` im Frontmatter.

---

## Klassifikations-Begriffe

### `type` (Frontmatter-Feld)
Bestimmt das Template eines Artikels. Vier Werte: `process-document`, `knowledge-article`, `compact-reference`, `gedanke` (E1, für den Gedanken-Sonderpfad).

### `doc_role` (Frontmatter-Feld)
Funktionale Rolle eines Artikels. Liste-Feld. Mögliche Werte: `manual`, `how-to`, `best-practice`, `workflow`, `explanation`, `reference`, `cheatsheet`, `wiki`.

### `doc_type_guess` (Pipeline-intern)
Heuristische Typ-Vermutung in Phase 3. Mit Confidence + Signalen versehen. Erscheint **nicht** im finalen Frontmatter — wird durch `type` und `doc_role` ersetzt, die Qwen in Stage 4 setzt.

### `category` (Frontmatter-Feld)
Vault-Ordnername **ohne** Nummern-Präfix. Beispiel: `webentwicklung`. Der Ordner im Vault heißt `02_Webentwicklung/` (mit Nummer für UX), aber `category` führt nur den Namen. 18 erlaubte Werte (`ALLOWED_CATEGORIES`): 16 thematische Ordner + `meta` + `unsortiert`. Quelle: Qwen-Stage-4 + deterministisches Mapping (`03_vault_standard.md` Appendix A).

### `subcategory` (Frontmatter-Feld)
Zweite Cluster-Ebene innerhalb einer `category`. Beispiel: `subcategory: rest-apis` innerhalb `category: webentwicklung`.

---

## Status-Begriffe

### Status (Lifecycle)
Lebenszyklus eines Artikels: `draft → review → stable → deprecated`. Bewegung in beide Richtungen möglich (z.B. `stable → review` wenn etwas zu klären ist).

### Review-Status (Vertrauensgrad)
Orthogonal zum Status. Werte: `ai_drafted → human_reviewed → verified`. Beschreibt, wer den Inhalt geprüft hat.

### Confidence (Synthese-Vertrauen)
Selbstangabe von Qwen, wie sicher es bei der Synthese war. Werte: `low`, `medium`, `high`. Triage-Hilfe für menschlichen Review.

### Qualitätsstufe (1–4)
Inhaltliche Reife eines Artikels, unabhängig vom Status. Stufen: Rohnotiz → Strukturierter Artikel → Geprüfter Wissensartikel → Referenzfähiger Kernartikel. Definiert in `docs/03_vault_standard.md` Sektion 8.

---

## Workflow-Begriffe

### Routing (Phase 8, Option B)
Pro Doc deterministisch gewählter Verarbeitungspfad: **`passthrough`** (Doc enthält Code ODER ≥1 Tabelle ODER ≥3 Headings → Body 1:1, kein LLM-Call, nur Stage 4) · **`stage3`** (Prosa → LLM-Veredelung + Stage 4) · **`gedanken`** (Sonderpfad, Minimal-Frontmatter). Strukturierte Docs verlieren durch LLM-Umschreiben Information — daher passthrough.

### `passthrough`
Routing-Pfad, der den Doc-Body unverändert (1:1) aus den Segmenten übernimmt und nur Frontmatter (Stage 4) ergänzt. Kein Stage-3-LLM-Call.

### `canonical_ck_slug`
Kanonische Slug-Ableitung für `CK_<slug>`-Dateinamen, identisch zur Pipeline (`_filename_to_slug` ∘ `_slugify_ck`): NFC-Komposition (macOS-NFD-Fix) → Umlaut-Map → NFKD-Akzent-Strip → lowercase → Sonderzeichen→Bindestrich → 60-Cap → Kollisions-Suffix. Implementiert in `scripts/phase8_runner.py`, gegen die Pipeline per Test bewacht.

### Triage-Action
Eindeutige Einordnung pro Korpus-Slug durch `scripts/pkm_triage.py`: **`IN_VAULT`** (fertig) · **`READY_TO_MIGRATE`** (Draft sauber) · **`POSTPROCESS`** (deterministisch fixbar, z.B. category/slug) · **`RERUN_LM`** (semantisch/strukturell defekt → LM neu) · **`FRESH_RUN`** (kein Draft vorhanden). Separat: `ORPHAN_DRAFT`, `EXCLUDED`.

### `_hold/`
Unterordner in `03_drafts/` für **zurückgestellte** Drafts (aktuell 19 Gedanken). Von der Toolchain ignoriert (Top-Level-Glob), Manifest in `HOLD_MANIFEST.md`. Re-Run-Kandidaten, siehe `docs/FUTURE_RUN.md`.

### `_excluded/`
Unterordner in `01_corpus_input/` für aus der Mainstream-Pipeline **ausgeschlossene** Korpus-Files (aktuell 3: `denkschulen_…` als Survey-Doc + 2 Stage-3-Hangs). Phase 1 überspringt `_*`-Prefix.

### Inbox (`00_inbox/`)
Ablage in `data/` für **neue Roh-`.md`** im inkrementellen Modus. `pipeline ingest` verarbeitet nur diese Files; nach Vault-Übernahme wandern sie nach `01_corpus_input/` (Korpus). Außerhalb Git (`.gitignore`).

### `ingest` (inkrementeller Modus)
CLI-Kommando (`python -m pipeline ingest`): verarbeitet neue Files aus `00_inbox/` durch Phasen 1→4 (isoliertes Work-Dir) + Phase 8 (Option-B-Routing); Phasen 5/6/7 entfallen. Erzeugt `ingest_report.md` (category/tags neu-vs-bestehend). Bestehender Vault unberührt; idempotent. Workflow: `docs/FUTURE_RUN.md`.

### Snapshot
Manuelle oder automatische Sicherung des aktuellen Sessions-Kontexts oder Vault-Zustands. Wird vor Token-Limits, Pausen oder größeren Änderungen erstellt. Pfad: `.claude/snapshots/` (Session) oder `~/projects/aktiv/PKM_rebuild/backups/` (Vault).

### Memory-Workflow
Protokoll für App-Hygiene während Qwen-Läufen, da nur ~4 GB RAM für macOS frei sind. Browser, Mail, Slack zu — Zed, Ghostty, LM Studio offen. Definiert in `docs/00_persona_muente.md` Sektion 6.

### Review-Gate
Verpflichtender menschlicher Entscheidungspunkt zwischen Pipeline-Phasen oder Stages. In Option B zwei Gates (Gate 2/Merge entfällt; siehe oben „Review-Gate" unter Pipeline-Begriffe).

### Prompt-Iteration
Verbesserungs-Zyklus für einen Qwen-Prompt: Hypothese → Snapshot → Klein-Test → Diff → Entscheidung → Reflexion. Definiert in `docs/04_qwen_prompts.md` Sektion 10.

---

## Asset-Begriffe

### `_assets/`
Globaler, flacher Asset-Pool im Produktiv-Vault (#3): `09_Brain-Vault/_assets/`. Alle eingebetteten Dateien (Bilder, PDFs etc.) liegen hier, ohne Cluster-Subordner. Unterstrich-Präfix = nicht-inhaltlich, hebt sich von den nummerierten Wissens-Clustern ab. Definition: `docs/03_vault_standard.md` §15.

### Asset
Eine in eine Note eingebettete Nicht-Markdown-Datei (Bild, PDF, …). Lebt im `_assets/`-Pool, nicht neben der Note. Diagramme sind **keine** Assets — sie werden als Mermaid in den Body geschrieben (siehe Mermaid-Diagramm).

### Asset-Embed
Pfad-freie Einbettung eines Assets per Wikilink: `![[<slug>__<original>.ext]]`. Nie als Pfad-Embed `![](pfad)`. Pfad-frei → Note und Asset bleiben frei verschiebbar, ohne dass ein Move den Embed bricht. Definition: `docs/03_vault_standard.md` §15.3.

### Asset-Namensschema
Global eindeutiger Asset-Dateiname `<note-slug>__<original-name>.ext` (Doppel-Unterstrich als Trenner). `<note-slug>` ist der Slug der besitzenden Note. Eindeutigkeit ist zwingend, weil Embeds pfad-frei über den Dateinamen auflösen. Definition: `docs/03_vault_standard.md` §15.2.

### Mermaid-Diagramm
Strukturiertes Diagramm als Text-Codeblock ` ```mermaid ` im Note-Body. Einziger erlaubter Diagramm-Standard im Vault (diff-bar, versionierbar, kein Plugin-Lock-in). Excalidraw ist **nicht eingeführt**. Typen: `flowchart`/`graph`, `sequenceDiagram`, `erDiagram`, `classDiagram`, `stateDiagram-v2`. Definition: `docs/03_vault_standard.md` §16.

---

## Tooling-Begriffe

### Claude Code
Anthropic's CLI- und ACP-basierter AI-Coding-Assistent. In diesem Projekt primär über Zed-Integration genutzt. Limits: 5h-Rolling-Window + Weekly Cap (Pro Plan).

### Qwen 3.6 27B
Lokales Open-Weight-LLM (Alibaba), 27 Milliarden Parameter, in 4-Bit-Quantisierung ~26–28 GB RAM. Synthese-Engine für Phase 8. Läuft über LM Studio.

### LM Studio
Lokaler LLM-Runner mit OpenAI-kompatibler API. Default-Endpoint: `http://localhost:1234/v1`. Lädt Qwen-Modell, stellt Inference-Server bereit.

### ACP (Agent Client Protocol)
Offenes Protokoll für IDE-zu-AI-Agent-Kommunikation, seit Q1 2026 in Zed verfügbar. Ermöglicht Claude-Code-Integration im Editor ohne separates Setup.

### CLAUDE.md
Markdown-File mit Working Rules / Conventions für Claude Code. Wird zu Beginn jeder Session gelesen. In diesem Projekt: Root + Pipeline + Prompts (3 Stück, kaskadierend).

### `manage_vocab.py`
Helper-Skript (`scripts/manage_vocab.py`) zur Vokabular-Pflege: `add-category` (legt category konsistent in `CATEGORY_TO_FOLDER` + Vault-Ordner + Doku an; `ALLOWED_CATEGORIES` folgt abgeleitet), `add-tag --reason` (Kern-Vokabular in `00_Meta/tag-system.md`), `list`, `validate` (Drift: fehlende Ordner / Tags außerhalb Vokabular). Idempotent.

---

## Aktualisierungs-Routine

Neue Begriffe werden ergänzt, wenn sie im Projekt zum ersten Mal verwendet werden. Bei Schema-Änderungen (Frontmatter-Felder, Enums) auch hier nachziehen.

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
- 2026-06-04 — Option B + Clustering-Verwurf: Stage/Review-Gate/Cluster/category/type auf Ist-Stand; neue Begriffe Routing, passthrough, canonical_ck_slug, Triage-Action, _hold, _excluded, unsortiert, Ordner-Index
- 2026-06-05 — Phase 12: `unsortiert` → `17_unsortiert`; neue Begriffe Inbox, `ingest`, `manage_vocab.py`, UMAP/HDBSCAN (nicht verwendet)
- 2026-06-13 — Sektion „Asset-Begriffe": `_assets/`, Asset, Asset-Embed, Asset-Namensschema, Mermaid-Diagramm (WP1 Asset-Konvention)
