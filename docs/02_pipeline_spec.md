---
title: PKM-rebuild Pipeline-Spezifikation
slug: 02-pipeline-spec
status: stable
created: 2026-05-25
updated: 2026-06-05
---

# Pipeline-Spezifikation

Technische Referenz: Architektur, Phasen, Schemas, Konfiguration, CLI, Tests.

> **go-forward (Option B, ab 2026-06-07):** Der produktive Flow ist `pkm run`
> (`pipeline/orchestrator.py` + `pipeline/run_flow.py`): `input/` → Inventar →
> Normalisierung → Struktur+Routing → [Segmentierung nur bei Token-Cap] → Qwen
> (stage3/passthrough)+stage4 → Drafts → **Review-Gates A–D** → Build nach
> `output/`. **Phasen 5 (Redundanz), 6 (Embeddings), 7 (Batches) sind NICHT im
> go-forward** (Alt/verworfen, nur noch `corpus-run`). Layout + Pfade: `pipeline/_paths.py`.
> Ablauf: `docs/RUNBOOK_new_files.md`. Umbau-Doku: `docs/learnings/REBUILD_pipeline_2026-06-07.md`.

> [!warning] Legacy-Pfad-Layout (deprecated)
> **Alle `data/0X`-Pfade in diesem Dokument** (`data/01_corpus_input/`,
> `data/02_pipeline_output/`, `data/03_drafts/`, `data/04_vault/`, `data_root:
> ~/projects/aktiv/PKM_rebuild/data`) beschreiben den **verworfenen Option-A-Vollkorpus-Erstlauf**
> und **existieren nicht mehr**. Kanonisch gilt ausschließlich das go-forward-Layout
> unter `~/projects/aktiv/pkm-pipeline/` (`_ingest/ input/ work/ drafts/ review/
> output/ archive/`, aufgelöst über `pipeline/_paths.py`, überschreibbar per
> `PKM_PIPELINE_ROOT`) **plus** der produktive Brain-Vault `~/Zentrale/09_Brain-Vault`
> (`BRAIN_VAULT`). Die Phasen-Beschreibungen unten bleiben als technische Historie
> erhalten; für aktuelle Pfade siehe `pipeline/_paths.py` + `docs/RUNBOOK_new_files.md`.

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
              │ Phase 6: Embeddings │ → embeddings.parquet
              │ (mpnet, nur Redund.)│   (Cluster-Prep verworfen, R9)
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 7: Batches    │ → batches/batch_NNN_*.md
              │ (Token-Budget-Split)│   (kein Cluster)
              └──────────┬──────────┘
                         │
   ┏━━━━━━━━━━━━━━━━━━━━━▼━━━━━━━━━━━━━━━━━━━━━┓  ← REVIEW-GATE 1
   ┃  Mensch prüft Batch-/Triage-Karte         ┃
   ┗━━━━━━━━━━━━━━━━━━━━━┬━━━━━━━━━━━━━━━━━━━━━┛
              ┌──────────▼──────────┐
              │ Phase 8: Routing    │ passthrough | stage3 | gedanken
              │ + Stage 3 (Body)    │ → drafts/CK_*.body.md
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Phase 8: Stage 4    │ → drafts/CK_*.frontmatter.json
              │ Frontmatter         │
              └──────────┬──────────┘
                         │
   ┏━━━━━━━━━━━━━━━━━━━━━▼━━━━━━━━━━━━━━━━━━━━━┓  ← REVIEW-GATE 3
   ┃  Mensch reviewt Drafts pro Doc/Cluster     ┃
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

Repo (Git, public): `pipeline/`, `scripts/`, `prompts/v1/`, `config/`
(`categories.yaml`, `tag_vocabulary.yaml`, `tag_merge_map.json`), `docs/` (Persona gitignored).

Daten (gitignored, außerhalb des Repos) unter `~/projects/aktiv/pkm-pipeline/`:

| Ordner | Inhalt |
|---|---|
| `input/` | neue `.md` (Run-Quelle, 1–10 pro Lauf) |
| `work/` | Zwischen-JSONL + `state.json` + logs |
| `drafts/` | Qwen-Outputs (`CK_*.{md,body.md,frontmatter.json}`) |
| `review/` | Gate-Queues + `decisions.{jsonl,md}` |
| `output/` | gebauter Staging-Vault (Mensch zieht ihn raus) |
| `archive/` | verarbeitete Inputs, Alt-Korpus (`corpus_legacy/`), alte Runs, Backups |

Pfad-Auflösung **zentral** über `pipeline/_paths.py`. Env-Override:
`PKM_PIPELINE_ROOT` (Daten, default `~/projects/aktiv/pkm-pipeline`), `PKM_REPO_ROOT` (Repo).
Die `pipeline.config.yaml` hat **keinen** `paths:`-Block mehr; Legacy-Feldnamen
(`pipeline_output`→`work`, `vault`→`output`, `corpus_input`/`inbox`→`input`) sind gemappt.

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

# === Cluster (VERWORFEN — R9) ===
# Embedding-/HDBSCAN-Clustering liefert auf diesem Korpus keine brauchbaren
# Cluster. Block bleibt nur als Lern-Artefakt; category kommt aus Qwen-Stage-4
# + deterministischem Mapping (03_vault_standard.md Appendix A).
clustering:
  min_cluster_size: 3        # ungenutzt
  enable_umap_hdbscan: false # verworfen
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

### go-forward (Option B) — produktiv

```bash
python -m pipeline run            # input/ → (Review-Gates) → output/ (resume-fähig)
python -m pipeline review         # review/decisions.md aus den Drafts erzeugen
python -m pipeline review --apply # ausgefüllte decisions.md anwenden (Gates A–D)
python -m pipeline ingest         # nur input/ → Drafts (+ ingest_report.md), kein Build
```
`pkm` = `python -m pipeline` (Console-Script nach `pip install -e .`).
Make-Targets: `make run|review|review-apply|ingest|publish-check`.

### Legacy-Erstlauf (Archiv, Phasen 1–10)

```bash
# Vollständiger Korpus-Erstlauf (inkl. Embedding/Batch — verworfen, nur Archiv)
python -m pipeline corpus-run
python -m pipeline corpus-run --sample 10        # Sample-Modus
python -m pipeline corpus-run --phase 5          # einzelne Phase
python -m pipeline corpus-run --from-phase 5     # ab Phase X
python -m pipeline corpus-run --force            # Cache ignorieren
python -m pipeline corpus-run --file <path>      # spezifische Datei (Phase 8)

# Status / Reports / expliziter Vault-Aufbau
python -m pipeline status
python -m pipeline build-vault
python -m pipeline reports
```

**Globale Flags:** `--config <path>`, `--verbose`, `--dry-run`

### Vokabular-Pflege (Skript)

```bash
python3 scripts/manage_vocab.py list                          # Kategorien + Tags
python3 scripts/manage_vocab.py validate                      # Drift prüfen
python3 scripts/manage_vocab.py add-category <name>           # neue category konsistent anlegen
python3 scripts/manage_vocab.py add-tag <tag> --reason "..."  # Tag ins Kern-Vokabular
```

### Taxonomie-SSoT (`pkm taxonomy`, pipeline-v2 / P1)

Pflegt die Taxonomie-Single-Source (`config/{categories,tag_vocabulary,enums}.yaml`,
gebündelt über `pipeline.taxonomy`). `add-*` delegiert an `manage_vocab`; `rename`
zieht zusätzlich den Bestand nach (Migration) und ist **vault-mutierend**.

```bash
pkm taxonomy add-category <name> [--dry-run]            # SSoT (categories.yaml) + Vault-Ordner anlegen
pkm taxonomy add-tag <tag> --reason "..." [--dry-run]   # Tag DIREKT ins YAML-SSoT (governed growth, E1=A) + md-Sync
pkm taxonomy rename category <old> <new> [--dry-run]    # SSoT + Ordner-Move + Frontmatter + _index + Validierung
pkm taxonomy rename tag <old> <new> [--dry-run]         # SSoT (old→Synonym) + tags-Frontmatter + Validierung
```

`add-tag` schreibt den Tag direkt in `config/tag_vocabulary.yaml` (Sektion
„Erweiterungen" + `changelog`-Eintrag mit `--reason`, Pflicht) und hält das
generierte md-Doc `00_Meta/tag-system.md` (`_paths.TAG_SYSTEM_DOC`, Brain-Vault)
synchron. Idempotent (Re-Add = No-op, kein Dup); ein als Synonym geführter Alias
wird abgelehnt. `rename` ist ein reiner Rename (Ziel darf noch nicht existieren,
kein Merge), mutiert `output/` + Drafts → vorher Snapshot (`bash scripts/snapshot.sh`).
Engine: `pipeline/taxonomy_migrate.py` (pfad-parametrisiert, `--dry-run` plant
ohne Schreiben; Validierung = Schema + Wikilink-Auflösbarkeit §10).

### Redundanz-/Synthese-Erkennung (`redundancy-scan`, WP2)

Prüft einen **bestehenden Vault read-only** auf Dubletten + Synthese-Potenzial
(Detection + Report, kein Merge — Option-B-Teil-Reversal, R12). Engine:
`pipeline/redundancy_scan.py`.

```bash
pkm redundancy-scan [--vault-dir DIR] [--output-dir DIR] [--no-embeddings] [--qwen]
# default vault-dir = Brain-Vault (_paths), output-dir = work/
```

Bänder pro Doc-Paar: `exact` (SHA-256) · `near-dup` (TF-IDF ≥ Schwelle) ·
`semantic-dup` (Embedding ≥ Schwelle, TF-IDF niedrig) · `thematic` (Embedding-
Mittelband). Synthese-Kandidaten = thematische Komponenten ≥ N Docs. Schwellen in
`pipeline.config.yaml → redundancy_scan` (REVIEW-Gate-2-Weiche). Reports:
`redundancy_report.md` + `synthesis_candidates.md` (idempotent, kein Wall-Clock im
Body). `--qwen` aktiviert die optionale Paar-Bewertung (Default aus, Hang-Risiko).

Korpus-Filter (WP3b): `redundancy_scan.exclude_folders`/`exclude_categories`
begrenzen den Synthese-Korpus auf Wissensartikel (Ausschluss via Ordner/category,
**kein** Slug-Filter); ausgeschlossene Docs stehen transparent im Report.

### Additive MOC-Generierung (`synthesize-moc`, WP3b)

Erzeugt aus Gate-A-freigegebenen Synthese-Clustern **neue** MOC-Drafts in **Staging**
(`drafts/_moc/`, kein Vault-Write — D6 additiv). Engine: `pipeline/synthesis_moc.py`.

```bash
pkm synthesize-moc [--approved FILE] [--vault-dir DIR] [--out-dir DIR] [--no-qwen]
# default approved = docs/reports/moc_approved.yaml, vault = Brain-Vault, out = drafts/_moc
```

MOC = Frontmatter (`doc_type: moc`, `status: draft`, `review_status`, `confidence`,
`moc_members`, `merged_from: []`) + 2-3-Satz-Rahmung (Qwen, `/no_think`, gecappt;
Fehler → deterministische Fallback-Rahmung + `needs_human`) + Wikilinks auf die
Mitglieder. **Link-Descriptor = realer `summary` des Ziel-Docs** (RV13, keine
Generierung), kein Body-Kopieren, Quell-Artikel byte-unverändert. **Gate 3b:** Owner
prüft jedes MOC einzeln; Promotion Staging→Vault ist ein separater Schritt.

### Deterministische Formatierung (`format-vault`, WP3a)

Normalisiert einen Vault **deterministisch + idempotent** via `mdformat` (+gfm,
+frontmatter) — KEIN Content-Rewrite, KEIN LLM. Engine: `pipeline/format_vault.py`.
**Non-mutating gegenüber dem Vault** (#3): liest Originale (raw), schreibt
Arbeitskopien + `diff_report.md` nach `work/format/` (#2). Export nach #3 ist ein
separater, **Gate-3-pflichtiger** Schritt (nicht in dieser CLI).

```bash
pkm format-vault [--vault-dir DIR] [--work-dir DIR] [--examples N]
# default vault-dir = Brain-Vault (_paths), work-dir = work/format
```

Obsidian-**Schutzbereiche** (nie verändert): Wikilinks `[[…]]`/Embeds `![[…]]`
(maskiert, sonst escaped mdformat sie), Callouts `> [!x]`, Code-Block-Inhalte,
Frontmatter-Werte+Key-Order. **Tier-Split (D4):** `unchanged` · `safe` (rein
deterministische Formatierung → auto in Arbeitskopie) · `unsafe` (würde Schutz-
bereich/Heading-Text/Code-Inhalt berühren → nur `.patch`-Vorschlag, NIE auto).

### Vault-Audit/Repair (`vault-audit` / `vault-repair` / `vault-review`, WP4)

Zielgerichtetes Audit/Repair-Tooling über den produktiven Vault. Engine:
`pipeline/vault_audit.py`. **Non-mutating gegenüber dem Vault** (#3): `audit` ist
read-only, `repair` schreibt Safe-Tier-Arbeitskopien nach `work/vault_repair/` (#2),
`review` schreibt Unified-Diff-Patches nach `work/vault_review/`. Anwendung auf den
Vault ist **Gate-pflichtig** (WP4 Teil B), nicht in dieser CLI.

```bash
pkm vault-audit  [--vault-dir DIR] [--work-dir DIR] [--baseline content,attic]
pkm vault-repair [--vault-dir DIR] [--work-dir DIR]
pkm vault-review [--vault-dir DIR] [--work-dir DIR]
# default vault-dir = Brain-Vault (_paths); baseline-default = vault_audit.DOC_COUNT_BASELINE (165,6)
```

**`audit`** — neun read-only Detektionsregeln, gruppierter Markdown-Report:
(1) Frontmatter↔SSoT (Pflichtfelder/Enums/`slug`, gegen `pipeline.taxonomy`),
(2) Wikilink-Auflösbarkeit + Dangling-Klassifikation (intendierte Stub-Links unter
„Verwandte Themen"/„Folge-Notizen" vs. echt-defekt), (3) Heading-Defekte
(`**`-im-Heading, Junk-Heading, literales `\n`, Setext-Bruch), (4) Code-Fences ohne
Sprach-Tag, (5) Korruptions-Scan (`turn\d+(view|search)\d+`, PUA `\ue200-\ue201`,
URL-Mashups, fremdsprachige Kontamination), (6) Doc-Count-Metrik + Baseline-Reconcile,
(7) Alias-Kollisionen vault-weit, (8) Cross-Link-Kandidaten aus
`work/synthesis_candidates.md` (nur Liste), (9) Quarantäne nicht-parsebarer Files.
Ausgenommen: `_attic`/`_assets`/`00_Meta`/`_index.md`/funktionale Templates.

**`repair`** (Safe-Tier = **deterministisch + verlustfrei + idempotent**) — `**`-Heading
entbolden, Junk-Heading (`# Unbenannt`) entfernen, Setext-Bruch entkoppeln, PUA-Wrapper
bereinigen, **genuin unclosed Code-Fence schließen** (line-start-State-Machine endet
`in_fence`; Close vor erster Leerzeile/ATX-Heading/EOF), Code-Fences bei **eindeutiger**
Heuristik taggen (python/bash/sql/html/regex/json/toml/yaml/md/text; unsichere bleiben
untagged). Fence-Heuristik v2: bash mit Tool-Token (npm/docker/git/curl…, kein bares `$VAR`),
SQL (`SELECT…FROM`/DDL), HTML (`</tag>`+Öffner), md nur bei mehrheitlich Listen-Items;
ASCII-Diagramme/Trees (Box-Drawing) bleiben untagged. Bidirektionale `related:` aus
freigegebener Kandidatenliste (Teil B). Schutzbereiche (Frontmatter, Code-Inhalt,
Wikilinks) byte-genau erhalten.
**`review`** — Patch-Vorschläge für **verlustbehaftete/nicht-deterministische** Fälle
(kein Auto): `turn…`-Token-Leaks ohne rekonstruierbare URL (→ B-2) sowie URL-Mashup-
Rekonstruktion (`url<Text>https://<url>` → `[Text](url)`) — an der URL/Prosa-Grenze
nicht deterministisch (CANARY A-2.1: `figma.com:` schluckt den Doppelpunkt,
`affinity.serif.com/-Setup` verschluckt Prosa). Fences ohne erkennbare Sprache bleiben
Audit-Findings.

### Vault-Apply (`vault-apply`, Phase 1 / S6 D4)

CLI-Exposure des D4-Drivers `apply_to_vault` (`pipeline/driver.py`). Wendet eine
Transform-Chain auf alle Content-Files des Vault an. **Default = dry-run** (Diff +
Audit-Vorschau nach `work/vault_apply/`, **kein** Write).

```bash
pkm vault-apply [--vault-dir DIR] [--chain a,b,…] [--work-dir DIR]
                [--backup-dir DIR] [--execute] [--confirm]
# default vault-dir = Brain-Vault (_paths); default chain = repair-safe,format-safe
# default backup-dir = _paths.BACKUPS
```

`--execute` löst die echte D4-Mutation aus (Snapshot → Canary [1 Write + idempotent-Verify]
→ Mass-Write → Verify [Audit-Pass]), aber nur hinter einem **harten Owner-Gate**:
(1) explizite Bestätigung (`--confirm` oder interaktiver Prompt — sonst Abbruch ohne Write),
(2) **O4-Backup-Präsenz-Check** (`--backup-dir` muss existieren + nicht-leer sein, sonst
Abbruch). **tier-Gate:** Chains mit review/audit-mutierenden Transforms werden nie
auto-geschrieben (bleiben Diff, Exit 1). Canary-Verify rot → Mass-Write gestoppt, Rollback
über `restore_snapshot()` (Snapshot-Pfad wird ausgegeben).

### Inkrementeller Modus (`ingest`)

`ingest` verarbeitet **nur** Files aus `data/00_inbox/` durch die Per-Doc-Pipeline
(Phasen 1→4 in einem isolierten Work-Dir `02_pipeline_output/ingest/`, dann Phase 8
mit Option-B-Routing). Die Phasen 5/6/7 (Redundanz/Embeddings/Batches) entfallen —
Option B konsumiert sie nicht. Bestehender Korpus/Vault/Drafts bleiben unberührt
(Hash-/Slug-Skip); zweiter Lauf ohne neue Files = no-op. Output:
`02_pipeline_output/ingest_report.md` (pro neuem Doc: vorgeschlagene `category` +
`tags` mit Flag neu-vs-bestehend). Vollständiger Workflow: `docs/FUTURE_RUN.md`.

### Universelle Erstverarbeitung (`process`, Process-1) — primärer Weg

Der **primäre, universelle Erstverarbeitungs-Weg**: **jedes** md-File — egal welcher
Ausgangszustand (fertig, gescrapt, copy-paste, unformatiert) — läuft **immer** durch
**dieselbe** Stage-Kette und wird vault-ready. **Kein Vorab-Filter/Triage** (alle Files
durch alle Stages). Engine: `pipeline/process_orchestrator.py` (eigenständig, Option A —
hängt **nicht** in `pkm run` ein; eigener State `work/process/state.jsonl`). Synthese
(`pkm run`) ist eine **nachgelagerte** Phase (läuft auf bereits vault-ready Files),
**nicht** der Ingest.

```bash
pkm process --source <dir> [--vault-dir DIR] [--resume]
# default: alle *.md aus <dir> → Stage-Kette bis review_ready. Kein Vault-Write, kein D4.
```

Stage-Kette (fest verankert, der Reihe nach):
`ingested → normalize (repair-safe + format-safe) → restructure (typ-bewusst WP3c-4,
Passthrough wenn gut strukturiert) → tags (Mapping gegen kontrolliertes 149-Tag-Vokabular,
kein Freitext) → assets (Embed-Syntax) → links (Wikilink-Syntax) → review_ready →
[human_reviewed] → promoted`. Die letzten zwei sind Owner-Gates außerhalb des Laufs
(`review-ingest` / `promote`, WP3c-5/6). Eigenschaften: **idempotent** (unveränderte
Datei per Hash überspringt erledigte Stages, **nicht** die Datei), **resumable**
(`--resume` setzt am State fort + retryt gescheiterte Files), **resilient** (Einzelfehler
→ Datei `needs_human`, Lauf läuft weiter, Fehl-Liste am Ende). STOPpt bei `review_ready`
(Review-Sheet via WP3c-6). Reuse statt Neubau (`driver.run_chain`, `restructure_file`,
`taxonomy`, `batch_restructure`). Nur die restructure-Stage ruft das LLM (im Test
gemockt); alle anderen Stages sind deterministisch. **Kein Vault-Write, kein D4.**

### Frontmatter-Lücken-Audit (`frontmatter-audit`, WP3c-8)

Read-only, **deterministisch, kein LLM, kein Vault-Write**. Misst über den Live-Vault,
welche Frontmatter-Lücken bestehen und ob ein restructure-Lauf sie real schließen würde.
Engine: `pipeline/frontmatter_audit.py` (Reuse der Schema-Konstanten aus
`scripts._pkm_common` / `pipeline.taxonomy` — keine Parallel-Validierung).

```bash
pkm frontmatter-audit [--vault-dir DIR] [--out work/audit/] [--xlsx]
```

Jede Lücke wird nach **Schließbarkeit** klassifiziert: `mechanical` (deterministisch
füllbar — Timestamps, `doc_version`/`prompt_version`, `status`-Norm, Slug/Umlaut),
`llm` (restructure könnte füllen — `summary`/`type`/`doc_role`/`confidence`/`title`),
`owner` (nicht ableitbar — `category`, `sources_*`, unparsebares Frontmatter). Pro File
eine Empfehlung (Priorität owner > restructure > mechanical-fix > complete). Report
`work/audit/frontmatter_audit_<ts>.md` (+ optional `.xlsx`): Aggregat, kuratierte
restructure-Teilmenge, Owner-Liste, Fazit. **Ist-Stand (2026-06-22): 165/165 Files
complete & valide, 0 Lücken** → kein Großlauf/Fix indiziert.

### Batch-restructure + Review-Sheet (`restructure-batch` / `review-ingest`, WP3c-6)

Skaliert das typ-bewusste restructure auf mehrere Files mit Owner-Review-Schnittstelle.
Engine: `pipeline/batch_restructure.py`. **Gesamte Kette review-Tier** — nur Drafts
(`drafts/_wp3c6/`), **kein Vault-Write, kein D4**. Promotion bleibt separat (`pkm promote`).

```bash
pkm restructure-batch --file <a> --file <b> | --cluster <kategorie> [--out drafts/_wp3c6/]
pkm review-ingest --sheet <review_sheet_*.xlsx>
```

`restructure-batch`: opt-in-Selektion (explizite Files **oder** ein Cluster/Kategorie —
**kein** impliziter All-Vault-Lauf). Pro File ein Draft (non-thinking, typ-bewusst);
ein Fail (Timeout/Parse) stoppt den Batch **nicht** → Fehl-Liste (`needs_human.txt`).
Erzeugt `review_sheet_<ts>.xlsx` (openpyxl): eine Zeile/Draft mit `slug · type ·
type_source · restructure_action · confidence · promote_mode · genre_shift_flag ·
runtime_s · draft_path · owner_decision` (Dropdown accept/reject/edit). `promote_mode`
= `update` (Slug existiert im Live-Vault → Felder werden beim Promote geerbt) vs. `new`;
Hervorhebung von low-confidence / `reclassified` / `new`-ohne-Pflichtfelder.
`review-ingest`: liest die Entscheidungen — `accept` → `review_status: human_reviewed`
(nur Frontmatter; `new`-unvollständig → `edit` statt human_reviewed), `reject` →
`archive/rejected_drafts/`, `edit` → bleibt liegen. **Kein Vault-Write.** Ausgabe =
Liste promotion-bereiter Drafts für `pkm promote`.

### Draft → Vault-Promotion (`promote`, WP3c — D4)

Promotet **genau einen** human_reviewed Draft in den Live-Vault. Engine:
`pipeline/promotion.py`. **Promotion-Gate:** nur `review_status: human_reviewed`/
`verified` — `ai_drafted` bricht hart ab (kein Write; Bulk-`draft→stable` bleibt
verboten). Ziel-Ordner aus `category` via `taxonomy.load_category_to_folder()` (SSoT).
**status** wird nie automatisch `stable` — Promotion setzt `status: review`.

```bash
pkm promote --draft <path> [--vault-dir DIR] [--on-collision abort|replace|suffix] [--execute]
# default: dry-run (Plan + Diff, kein Write). --execute = D4-Live-Write (Owner-Gate!)
```

**Update-Modell:** ein restructure-Draft re-strukturiert ein **bestehendes** Vault-File
(Slug stammt daher) → Ziel existiert i.d.R. = **Kollision**. Kein Blind-Overwrite:
`abort` (Default) meldet Diff + STOP; `replace` = Update (Content/Restructure-Felder aus
Draft, Taxonomie/Verlinkung/Quellen aus Bestand); `suffix` = `slug_2.md`. Finalisiertes
Frontmatter wird gegen `schemas.FrontmatterDraft` (Pydantic-SSoT) validiert (unvollständig
→ Abbruch). **D4 (`--execute`):** `driver.snapshot_vault` → Write → Verify (FrontmatterDraft)
→ mandatorische Index-Regen (`phase_9._render_index`, G8) → Draft nach `archive/promoted_drafts/`;
jeder Fehler → `restore_snapshot`. `provenance`/`type_source`/`restructure_action`/
`prompt_version` aus dem Draft bleiben erhalten. Draft→stable bleibt separater Owner-Schritt.

### Semantische Re-Strukturierung (`restructure`, WP3c — review-Tier)

Erzeugt für **genau ein** Quell-File einen re-strukturierten **Draft** via Qwen.
Engine: `pipeline/restructure.py`. **review-Tier** (`pipeline.transforms.TIER_REVIEW`):
niemals Auto-Apply, niemals Safe-Tier, **nie ein Vault-Write** — Output ist
ausschließlich ein Draft in `drafts/` (Default `_paths.DRAFTS`); das Quell-File
bleibt unberührt. Kein Batch, kein Cross-Doc-Merge (Option B), kein `--execute`-Pfad.

```bash
pkm restructure --file <path> [--out drafts/]
# typ-bewusste v2-Prompts (qwen.restructure.prompt_version): Stage 3 (Body) + Stage 4
```

Ablauf (typ-bewusst, WP3c-4): **Type-Resolver** bestimmt den Ziel-`type` (Frontmatter
führend; fehlt → Light-Klassifikation `type_source: classified`; `knowledge-article`
+ klares Funktional-Signal → `compact-reference` `type_source: reclassified`). Die
**Skip-Schwelle** prüft zuerst: bereits gut strukturiert (Headings + Slug-konform +
keine Korruption) → **Passthrough** (Body verbatim, `restructure_action: passthrough`);
sonst type-konditionaler Stage-3-Rewrite (`compact-reference`/`gedanke` =
verbatim-/minimal-invasiv statt Erklär-Template → kein Genre-Shift). Stage 4 liefert
das Frontmatter inkl. `confidence`. Draft-Frontmatter-Kontrakt: `type` (aufgelöst) ·
`type_source` · `restructure_action` · `review_status: ai_drafted` · `confidence:
<low|medium|high>` (Vault-SSoT-Enum, `CLAUDE.md` §6 — kein Float) · `provenance`.
Liefert Stage 4 keine valide confidence → `low` + `confidence_fallback: true`. Nur der
restructure-Pfad nutzt v2; **Phase 8 bleibt auf v1**. Der Qwen-Client ist injizierbar
(`_call_qwen_api(client, …)`) → deterministisch mockbar. Draft→Vault-Promotion ist ein
separater, gegateter D4-Task (nicht in dieser CLI).

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

> **Alt / nicht im go-forward (Option B).** Nur `corpus-run`. Der go-forward nutzt
> stattdessen einen intra-run SHA-Dedup (`pipeline/run_flow.py`).

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

### Phase 6: Embeddings (nur Redundanz)

> **Alt / nicht im go-forward (Option B).** Nur `corpus-run`.
>
> **Architektur-Hinweis (2026-06-04):** Cluster-Vorbereitung **verworfen** (R9, `01_strategy.md`) — der Korpus hat keine inhärente Cluster-Struktur. Embeddings dienen nur noch der Redundanz-Erkennung (Phase 5). Die Vault-Ordner sind ein fixes 16er-Schema; `category` kommt aus Qwen-Stage-4 + deterministischem Mapping (`03_vault_standard.md` Appendix A).

**Input:** Phase 4 Output
**Output:** `data/02_pipeline_output/embeddings.parquet`

**Logik:**
- Embedding pro Segment via `paraphrase-multilingual-mpnet-base-v2`
- Cosine-Similarity für Near-Duplicate-Kanten (Phase 5)

**Schema:** `EmbeddingRecord`

**Akzeptanzkriterien:**
- [ ] Embeddings als parquet (kompakt, schnell lesbar)

**~~Phase 7b — UMAP+HDBSCAN~~ (verworfen):** Embedding-Clustering liefert auf diesem Korpus keine brauchbaren Cluster (0.85→0, 0.65→Mega-Cluster). Code bleibt als Lern-Artefakt (`scripts/clustering_analysis.py`), ist aber nicht Teil des Produktiv-Pfads.

---

### Phase 7: LLM-Batch-Bildung

> **Alt / nicht im go-forward (Option B).** Nur `corpus-run`. Der go-forward
> verarbeitet pro Doc ohne Batch-Bildung (1–10 Files/Run, Token-Cap-Segmentierung).

**Input:** Phase 5 + 6 Outputs
**Output:** `data/02_pipeline_output/batches/batch_NNN_<topic-slug>.md`

**Logik:**
- Batches sind **Token-Budget-Splits**, keine semantischen Cluster
- Inhalt: enthaltene Dokumente, alle Segmente mit IDs + Heading-Pfaden
- Token-Schätzung pro Batch (Ziel: < 35K Token Input, damit Reasoning-Raum für Qwen bleibt)
- Batches > 35K werden in Sub-Batches geteilt

**Akzeptanzkriterien:**
- [ ] Jeder Batch ist ein valides Markdown
- [ ] Jeder Batch enthält Anweisungs-Header für Qwen
- [ ] Token-Schätzung pro Batch geloggt

**→ REVIEW-GATE 1:** Mensch prüft die Batch-/Triage-Karte (`triage_report.md`, `scripts/pkm_triage.py`) und entscheidet: weiter, Batches/Schwellwerte anpassen.

---

### Phase 8: Qwen-Veredelung (Stage 3 + Stage 4 pro Doc)

Pro Doc durchlaufen Stage 3 und Stage 4. Failure in einer Stage → Retry oder Flag, kein Auto-Verwurf.

> **Option B:** Stage 1 (Cluster-Analyse) und Stage 2 (Merge-Vorschläge) entfallen vollständig. Kein Cross-Doc-Merge.
> Historische Referenz: `prompts/v1/stage1_cluster_analysis.md` + `stage2_merge_proposal.md` (deprecated, Option A).

**Routing pro Doc (deterministisch, vor Stage 3):**

| Pfad | Bedingung | Verhalten |
|---|---|---|
| `passthrough` | Doc enthält Code **ODER** ≥1 Tabelle **ODER** ≥3 Headings | Body 1:1 aus Segmenten, **kein** Stage-3-LLM-Call, danach Stage 4 |
| `stage3` | reine Prosa ohne starke Struktur | LLM-Veredelung (Stage 3) + Stage 4 |
| `gedanken` | `doc_type_guess.label == "gedanke"` | Sonderpfad: kein Stage 3, Minimal-Frontmatter via `stage4_frontmatter_gedanken.md` |

**Mechanik (Toolchain):** Triage (`scripts/pkm_triage.py`) routet Korpus-Slugs auf Actions (`READY_TO_MIGRATE`/`POSTPROCESS`/`RERUN_LM`/`FRESH_RUN`) und erzeugt Batches; `scripts/phase8_runner.py` fährt sie ab (subprocess pro Slug, State-File, **autoritative** Output-Verifikation: existieren `CK_<slug>.md` + `.frontmatter.json` → Erfolg, unabhängig vom Returncode). Slug-Ableitung kanonisch (NFC + Umlaut + 60-Cap), siehe `03_vault_standard.md` §5.

#### Stage 3 — Pro-Doc-Veredelung (Body)
**Prompt:** `prompts/v1/stage3_synthesis.md`
**Output:** `data/03_drafts/CK_<slug>.body.md`
**Inhalt:** 1 Doc → 1 veredelter Artikel-Body (ohne Frontmatter), normalisiert + strukturiert nach `type`-Template aus Vault-Standard; kein Merge mit anderen Docs; Code-Blöcke 1:1 erhalten

#### Stage 4 — Frontmatter-Generierung
**Prompt:** `prompts/v1/stage4_frontmatter_json.md`
**Output:** `data/03_drafts/CK_<slug>.frontmatter.json`
**Inhalt:** strukturiertes JSON, Python validiert gegen Pydantic-Schema, serialisiert als YAML, fügt vor Body

**→ REVIEW-GATE 3:** Mensch prüft pro Doc/Cluster: `data/03_drafts/CK_*.md` (mit Frontmatter; Veredelung + Frontmatter-Korrektheit prüfen)

**Akzeptanzkriterien (Phase 8 gesamt):**
- [ ] `sources_docs` belegt (Source-Doc referenziert); `merged_from` leer (`[]`)
- [ ] `confidence`-Feld gesetzt
- [ ] `prompt_version` gesetzt
- [ ] `last_synthesized` gesetzt
- [ ] Validation gegen Pydantic-Schema grün

> **Hinweis (Block 8.A.1):** `confidence` ist Qwen-Selbsteinschätzung — im Smoke-Test als unzuverlässig erkannt (hohe Werte trotz unvollständiger Outputs). Kein Auto-Triage auf Basis von `confidence`. **Alle Drafts brauchen menschliches Review** unabhängig vom confidence-Wert.

---

### Phase 9: Vault-Aufbau

> **Hinweis (2026-06-05):** Vault-Aufbau ist **Phase 9** (`build-vault`). Phase 10 erzeugt
> nur die **Kontroll-Berichte** über den bereits gebauten Vault. Embedding-Clustering ist
> verworfen (R9); `cluster_report` beschreibt die reale Ordner-Verteilung, keine berechneten Cluster.

**Input:** gebauter Vault `data/04_vault/`, Build-Plan aus `data/03_drafts/`, Phase-1/5-Outputs.
**Output (alle in `data/02_pipeline_output/`):** `corpus_report.md`, `duplicate_report.md`, `cluster_report.md`.

**Logik:**
- **Ground-Truth-Regel:** alle Zähl-Werte direkt aus Quelldaten (manifest, segments, exact/edges,
  gebauter Vault) ableiten — **nie** aus anderen Reports.
- `corpus_report`: Doc-Count (manifest), Größen/Typ/Sprache, **Segment-Counts strikt von Doc-Counts
  getrennt**, Verarbeitungs-Status (ready/hold/excluded) aus Vault + `_excluded/`.
- `duplicate_report`: exakte Gruppen + near-dup-Kanten; **Option B**: `merged_from` überall leer →
  „keine Konsolidierungen" explizit vermerkt.
- `cluster_report`: Artikel-Verteilung pro Vault-Ordner (Build-Plan gegen Vault gecheckt, Summe == aktueller Live-Count, z. B. 181),
  `17_unsortiert/`-Sektion (Mapping-Lücke gekennzeichnet, nicht verschoben), Tag-Häufigkeiten gesamt + pro Ordner.
- Idempotent via Input-Hash; mensch-lesbares Markdown (keine JSON-Dumps).

**Akzeptanzkriterien:**
- [ ] 3× `*_report.md` vorhanden + mensch-lesbar
- [ ] Counts gegen Ground Truth verifiziert (Ordner-Summe = Live-Count, aktuell 181; manifest 202 aus Korpus-Erstlauf)
- [ ] segment- vs doc-Counts getrennt; `merged_from`-leer vermerkt
- [ ] Reports idempotent (2. Lauf byte-identisch)
- [ ] `docs/DOD_CHECK.md` erzeugt (`scripts/dod_check.py`)

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
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pipeline import taxonomy   # SSoT-Facade (pipeline-v2)

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
        "projektidee", "projektplanung", "book", "unklar"
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
    embeds: list[str]                   # ![[…]]-Embed-Targets (Asset-Routing, WP3)
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

class ClusterProposal(BaseModel):       # VERWORFEN (R9) — nicht im Produktiv-Pfad
    cluster_id: str                     # C_<slug>
    label_guess: str
    segment_ids: list[str]
    internal_similarity_mean: float

# --- Phase 8 (Qwen-Output) ---
# pipeline-v2 (P1): type/status/review_status/confidence sind str + werden zur
# LAUFZEIT per field_validator gegen die Taxonomie-Facade (pipeline.taxonomy,
# Quelle config/enums.yaml) geprüft — kein Literal mehr (governed growth ohne
# Schema-Edit). `category` bleibt bewusst ein weicher str (unbekannt → Phase-9-
# Routing nach 17_unsortiert, nicht hart abgewiesen). Single Source: pipeline.taxonomy.
class FrontmatterDraft(BaseModel):
    title: str
    slug: str
    aliases: list[str] = []
    summary: str
    type: str                              # Runtime-Check ∈ taxonomy.ALLOWED_TYPE (inkl. "gedanke")
    doc_role: list[str]
    category: str                          # weich: kein Runtime-Reject (17_unsortiert-Fallback)
    subcategory: str | None = None
    tags: list[str]
    related: list[str] = []
    used_in: list[str] = []
    parent_concept: str | None = None
    child_concepts: list[str] = []
    sources_docs: list[str]
    source_chunks: list[str]
    merged_from: list[str] = []            # immer leer in Option B (kein Cross-Doc-Merge)
    status: str = "draft"                  # Runtime-Check ∈ taxonomy.ALLOWED_STATUS
    review_status: str = "ai_drafted"      # Runtime-Check ∈ taxonomy.ALLOWED_REVIEW
    confidence: str                        # Runtime-Check ∈ taxonomy.ALLOWED_CONFIDENCE
    doc_version: str = "0.1.0"
    created: str                        # YYYY-MM-DD
    updated: str
    last_synthesized: str
    prompt_version: str                 # e.g. "v1"

    @field_validator("type", "status", "review_status", "confidence")
    @classmethod
    def _check_taxonomy_enum(cls, value, info):   # Membership-Check gegen taxonomy.allowed_values
        ...

# --- WP2: Redundanz-/Synthese-Erkennung (Detection + Report, kein Merge) ---
RedundancyBand = Literal["exact", "near-dup", "semantic-dup", "thematic"]

class RedundancyPair(BaseModel):
    slug_a: str
    slug_b: str
    band: RedundancyBand
    exact: bool                          # identischer normalisierter Body (SHA-256)
    tfidf: float                         # lexikalische Cosine-Similarity [0,1]
    embedding: float                     # semantische Cosine-Similarity [-1,1] (mpnet)
    sources_a: list[str] = []            # Provenance aus Frontmatter
    sources_b: list[str] = []
    chunks_a: list[str] = []
    chunks_b: list[str] = []
    qwen_relation: str | None = None     # optionale Qwen-Bewertung (Default aus)
    qwen_recommendation: str | None = None
    qwen_confidence: str | None = None

class SynthesisCandidate(BaseModel):
    candidate_id: str                    # SC_<index:03d>
    slugs: list[str]                     # Mitglieder (>= synthesis_min_members)
    mean_similarity: float
    pair_count: int                      # thematische Kanten in der Komponente
    sources: list[str] = []
    qwen_relation: str | None = None     # Verdict des repräsentativen Paars (optional)
    qwen_recommendation: str | None = None
    qwen_confidence: str | None = None

class QwenPairVerdict(BaseModel):        # Schema der optionalen Qwen-Paar-Bewertung
    relation: Literal["duplicate", "overlap", "complementary", "unrelated"]
    recommendation: Literal["merge", "cross-link", "keep-separate"]
    confidence: Literal["low", "medium", "high"]
    rationale: str
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

### go-forward (Option B) — Gates A–D (`pipeline/review.py`)

File-basiert: Producer → `review/decisions.jsonl`; `pkm review` → editierbare
`review/decisions.md`; `pkm review --apply` wendet je Gate an. A/B/C werden vor D
angewandt (ein Review-Zyklus genügt).

| Gate | Auslöser | Entscheidungen (Wirkung) |
|---|---|---|
| **A quality** | Frontmatter-Validierungsfehler | `freigeben` · `nachbessern` (→ `review/needs_human`) · `quarantaene` (→ `review/quarantine`) |
| **B category** | `category` ∉ Set | `zuweisen` · `neu` (→ `config/categories.yaml` + output-Ordner) · `unsortiert` |
| **C tags** | Tag ∉ Vokabular | `aufnehmen` (→ `config/tag_vocabulary.yaml`) · `mappen` (+ `tag_merge_map.json`) · `droppen` |
| **D final** | Publish-Freigabe | `publish` / `hold` (→ `work/state.json`) |

Review-UI: `review/decisions.md` in Zed ausfüllen, speichern, `pkm review --apply`.

### Alt (verworfen, nur `corpus-run`)

| Gate | Nach Phase | Mensch entscheidet |
|---|---|---|
| 1 | Phase 7 (Batch-/Triage-Karte) | Batch-Verteilung okay? (kein Cluster-Merge — verworfen) |
| 3 | Phase 8 Stage 4 | Drafts pro Doc prüfen, freigeben für Phase 9 |

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
| Phase 8 (Qwen pro Doc) | passthrough: Sekunden (kein LLM); stage3: Minuten pro Doc (~10× Reasoning-Overhead, 7.45 t/s gemessen) |
| Phase 9 | < 1 min |

---

## 13. Aktualisierungs-Routine

Bei Schema-Änderungen: Schema-Version inkrementieren + Migration im Code. Bei Phasen-Änderungen: Doku + Tests anpassen. Bei Config-Änderungen: Beispiel-Config aktualisieren.

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
- 2026-05-29 — Option-B-Anpassung: Architektur-Diagramm Stage 1/2 + Gate 2 entfernt; Phase-8-Header auf Stage 3+4 pro Doc; Stage 1/2 als entfallen markiert; Stage 3 als Pro-Doc-Veredelung neu definiert; Akzeptanzkriterien merged_from→leer; FrontmatterDraft-Kommentar ergänzt; Gate-2-Zeile entfernt
- 2026-05-30 — Block 0G.6: FrontmatterDraft.type um "gedanke" erweitert (Sonderpfad 15_Gedanken/)
- 2026-05-30 — Block 8.A.1: Phase-8-Routing 1:1-Passthrough (code/table/headings); confidence-Hinweis zu Akzeptanzkriterien
- 2026-06-04 — Clustering-Verwurf (R9): Phase 6 auf Embeddings-nur-Redundanz, Phase 7b verworfen, ClusterProposal/Cluster-Config als ungenutzt markiert; Phase-7-Batches als Token-Budget-Splits; Phase-8-Routing-Tabelle (passthrough/stage3/gedanken) + Triage/Runner-Mechanik; Architektur-Diagramm + Gate-1-Label + Performance-Tabelle auf Ist-Stand
- 2026-06-05 — Phase 12: CLI um `ingest` + `manage_vocab` erweitert; Abschnitt „Inkrementeller Modus" (Inbox → Phasen 1-4 + 8, Option B); `17_unsortiert/` im cluster_report
- 2026-06-07 — Pipeline-Umbau go-forward: Banner + neues Layout (`pkm-pipeline/`, `_paths.py`); CLI `run`=Orchestrator / `review` / Legacy `corpus-run`; Phasen 5/6/7 als „Alt/nicht im go-forward" markiert; Review-Gates A–D (`review.py`)
- 2026-06-15 — pipeline-v2 P1 (Taxonomie-SSoT): §7 FrontmatterDraft `type/status/review_status/confidence` von `Literal` auf `str` + Runtime-`field_validator` gegen `pipeline.taxonomy` (Quelle `config/enums.yaml`); `category` als bewusst weicher str dokumentiert (17_unsortiert-Routing); §4 CLI `pkm taxonomy add-category|add-tag|rename` (Rename-Migration, `taxonomy_migrate.py`) ergänzt
- 2026-06-16 — REVIEW-Gate-1: E1=A — `pkm taxonomy add-tag` schreibt direkt ins YAML-SSoT (Sektion „Erweiterungen" + `changelog` mit `--reason`) + md-Sync `00_Meta/tag-system.md`, idempotent; §4 angepasst. Passives Surfacing: `build-vault` weist 17_unsortiert-Füllstand aus + warnt über `vault.unsorted_warn_threshold` (default 10, §3), read-only (kein P4)
- 2026-06-16 — WP2 (P5 Redundanz/Synthese-Erkennung): §4 CLI `pkm redundancy-scan` (read-only Detection + Report, kein Merge); §7 Schemas `RedundancyPair`/`SynthesisCandidate`/`QwenPairVerdict`; §3 Config-Block `redundancy_scan` (Schwellen, Gate-2-Weiche). Engine `pipeline/redundancy_scan.py` (Hash + TF-IDF + mpnet paarweise, in-memory)
- 2026-06-17 — WP3a (P2 deterministische Formatierung): §4 CLI `pkm format-vault` (mdformat +gfm +frontmatter, non-mutating Dry-Run → work/format/). Obsidian-Schutzbereiche (Wikilink/Embed-Maskierung, Callout/Code/Frontmatter-Guards), Tier-Split safe/unsafe (D4 raw→work→export), Export Gate-3-pflichtig. Engine `pipeline/format_vault.py`
- 2026-06-19 — WP4 Teil A-2 (Safe-Tier komplettiert): `repair_text` um Junk-Heading-Removal, Setext-Entkopplung, URL-Mashup-Rekonstruktion, Fence-Tagging-Apply (high-conf, +yaml/json/toml/md/text) erweitert; `turn…`-Token-Strip **aus** dem Safe-Tier entfernt (verlustbehaftet → `vault-review`/B-2). Safe-Tier-Definition gelockt: deterministisch+verlustfrei+idempotent. §4 angeglichen. Engine `pipeline/vault_audit.py` (37 Tests)
- 2026-06-19 — WP4 Teil B-2 (Fence-Regel v2): Safe-Tier um `_close_unclosed_fences` erweitert (deterministische Schließ-Regel: line-start-State-Machine endet `in_fence` → Close vor erster Leerzeile/ATX-Heading/EOF; verlustfrei/idempotent; trifft im Vault genau 1 Realfall). Fence-Tagging-Heuristik verschärft: `_is_bash` (+Tool-Token, kein bares `$VAR` → JS-fest), neu `_is_sql`/`_is_html`, `_is_md` (Listen-mehrheitlich + yaml-/Box-Guard), `_is_text` (+Box-Drawing-Guard); det/edit präzisions-getunt (~60 verlustfrei-det vs. ~191 Audit-Oberwert, Rest bleibt untagged/Editorial). §4 angeglichen, 8 neue Tests. Engine `pipeline/vault_audit.py`
- 2026-06-19 — WP4 Teil A-2.1 (url-Mashup raus aus Safe-Tier): URL-Mashup-Rekonstruktion aus `repair_text` (Safe-Tier) entfernt → `review_patches` (Review-Tier, kein Auto), analog `turn…`-Token. CANARY-Befund: URL/Prosa-Grenze nicht deterministisch (`figma.com:` Doppelpunkt, `affinity.serif.com/-Setup` Prosa-Schluck, `.com,` Komma). Safe-Tier bleibt: entbolden/Junk-Heading/Setext/PUA/Fence-Tagging. §4 angeglichen, 3 Realfälle als Regressionsfixtures. Engine `pipeline/vault_audit.py`
- 2026-06-19 — WP4 Teil A (Vault-Audit/Repair-Tooling): §4 CLI `pkm vault-audit`/`vault-repair`/`vault-review` (3 Modi, non-mutating → work/). Neun read-only Detektionsregeln (Frontmatter↔SSoT, Wikilink-Auflösbarkeit+Dangling-Klassifikation, Heading-Defekte, untagged Fences, Korruptions-Scan, Doc-Count-Reconcile, Alias-Kollisionen, Cross-Link-Kandidaten, Quarantäne); Safe-Tier-Repair (entbolden/Token-Clean/bidir-`related:`) idempotent mit 3-State; Review-Patches für Unsafe. Engine `pipeline/vault_audit.py` (reuse `pipeline.taxonomy`/WP3a-Schutzmuster). Anwendung = Teil B (gegatet). Keine `schemas.py`-Änderung (Dataclasses `Finding`/`VaultIndex`, kein Pydantic → §7 n/a)
- 2026-06-20 — Phase-1 S1 (G1, Repair-Finalize-Hook): Phase 9 (`build-vault`/`pkm run`) wendet Safe-Tier-`repair_text` (entbolden/Junk-Heading/Setext/PUA/unclosed-Fence/Fence-Tag-high-conf) auf **jeden Body** am Build-Chokepoint (`_finalize_body` vor `_render_article`) an → neue Files bekommen die deterministischen Fixes single-pass (G1). Review-Tier (url-Mash, `turn…`-Token) bleibt ausgenommen. Wirkt **nur** auf `output/`, nie auf den Live-Vault oder die Quell-Drafts. Config-Toggle `vault.repair_on_build` (default **true**, §3); Summary-Feld `repaired_files`. Two-stage bleibt additiv (`vault-audit`/`-repair`/`-review` unverändert). 6 neue Tests. Engine `pipeline/phase_9_vault_build.py`
- 2026-06-20 — Phase-1 S2 (G2, Format-Finalize): `_finalize_body` wendet **nach** `repair_text` (Reihenfolge **repair→format**) safe-tier-`format_body_safe` (mdformat, neu in `pipeline/format_vault.py`) auf jeden Body an. Übernommen wird das Format-Ergebnis **nur**, wenn es nicht `unsafe` ist (s. `classify`) **und** Code-Fences + Tabellen **byte-identisch** bleiben (`_protected_fingerprint`, HARD-Garantie analog Phase-2-Code-Schutz) → mdformat-GFM-Tabellen-Realignment/Code-Änderung führt zum konservativen Überspringen. Verlustfrei + idempotent; Frontmatter unberührt. Wirkt **nur** auf `output/`, nie auf den Live-Vault/Quell-Drafts. Config-Toggle `vault.format_on_build` (default **true**, §3); Summary-Feld `formatted_files`. Two-stage additiv (`format-vault` Dry-Run-Tool unverändert). 10 neue Tests. Engine `pipeline/phase_9_vault_build.py` + `pipeline/format_vault.py`
- 2026-06-21 — Phase-1 S3 (G4, Audit-on-Build): Phase 9 (`build-vault`/`pkm run`) führt **nach** repair+format einen **read-only** Audit-Pass über das gebaute `output/` aus (neu `vault_audit.audit_build_output`, reuse `build_index`/`repair_text`/`check_wikilinks`, **kein** Doc-Count-Reconcile). Verifiziert den sauberen Build: Summary-Felder `audit_safe_tier_rest` (erwartet **0** bei repair-on-build), `audit_parse_errors`, `audit_dangling` + `audit_on_build`. **Mutiert nichts** (weder `output/` noch Live-Vault). Config-Toggle `vault.audit_on_build` (default **true**, §3); `build-vault` druckt die Befund-Zeile. Two-stage additiv (`vault-audit`-Modus unverändert). 7 neue Tests. Engine `pipeline/vault_audit.py` + `pipeline/phase_9_vault_build.py`
- 2026-06-21 — Phase-1 S4 (Composability-Kern, Transform-Registry): neues Modul `pipeline/transforms.py` — gemeinsames `Transform`-Protokoll (Body → `TransformResult(text, changed, report)`) + Registry. **Code-only, non-mutating, kein `--apply`.** Adaptiert (kein Re-Implement) die Bestands-Engines als Transforms: `repair-safe` (`repair_text`, tier=safe, mutating), `format-safe` (`format_body_safe`, tier=safe, mutating), `audit-readonly` (index-freie `check_headings`/`check_fences`/`check_corruption`, tier=audit, read-only). Metadaten `tier`/`mutating` + `DEFAULT_CHAIN=("repair-safe","format-safe")` (Entscheidung 2A) legen die Schnittstelle **chain-ready** (S5) und **apply-ready** (S6/D4) aus, ohne sie zu implementieren. 15 neue Tests (Listing, Metadaten, Adapter-Äquivalenz == Direkt-Funktion, Non-Mutation). Two-stage additiv (bestehende CLI-Tools unverändert).
- 2026-06-21 — Phase-1 S5+S6 (Chain-Driver + D4-`--apply`-Driver): neues Modul `pipeline/driver.py`. **S5 `run_chain(text, chain=DEFAULT_CHAIN)`** — non-mutating, verkettet Transforms (Output→Input, Reports gemerged), konfigurierbare Reihenfolge (2A). **S6 `apply_to_vault(target_dir, chain, execute=False)`** — Entscheidung 1A: **Default dry-run** (Diff + Audit-Vorschau, kein Write); `execute=True` löst vollständiges **D4** aus: auto-`snapshot_vault` → Canary (1 Write + Idempotenz-Verify) → bei grün Mass-Write → Verify (`audit_build_output`); Canary rot → Stop + `restore_snapshot`-Hinweis (kein Mass-Write). **tier-Gate:** nur `safe`-Transforms sind auto-write-fähig; `review`/`audit`-mutierend → `writable=False`, kein Write (nur Diff). Frontmatter + fm↔body-Separator byte-stabil (Body-only-Transform). **Kein CLI-Command** (Library-API; Live-Vault-Anbindung später mit Owner-Gate). 12 neue Tests auf `tmp_path`/Test-Vault (Chain-Äquivalenz/custom/idempotent/audit-readonly; dry-run schreibt nichts, execute schreibt+verifiziert+snapshot, fm byte-stabil, tier-Gate, Rollback). `transforms.unregister` ergänzt. Two-stage additiv.
- 2026-06-21 — WP3c-3 (restructure Performance + Resilienz): **A (Reasoning aus):** restructure-Pfad schaltet Reasoning ab — empirisch verifiziert ist auf dem Stack (LM Studio + qwen3.6) nur `reasoning_effort:"none"` wirksam (`reasoning_tokens=0`), das geplante `chat_template_kwargs.enable_thinking:false` **und** `/no_think` werden ignoriert. `_call_qwen_api`/`_run_text_stage`/`_run_json_stage` um optionale `top_p`/`presence_penalty`/`reasoning_effort`/`extra_body`-Kwargs erweitert (Default `None` → Phase 8 **byte-unverändert**, isoliert); restructure nutzt Sampler (temp 0.7/top_p 0.8/presence_penalty 1.5) + gesenkte `max_tokens` (4000/2000, kein 16000-Reasoning-Budget). Neue Config `qwen.restructure` (§3). **A/B-Realmessung:** non-thinking 150s vs. thinking 1666s (~11×), confidence high statt medium, Stage-4-JSON valide, keine Qualitätsregression. **B (Resilienz):** `restructure.RestructureError` + `_guarded()` fangen `APITimeoutError`/`APIConnectionError` → saubere CLI-Fehlerzeile + Exit≠0 statt Traceback; **kein Draft** bei Fail, Quell-File unberührt (review-Tier-Garantie). `qwen.timeout_seconds` 600→1200. 5 neue Resilienz-Tests (Timeout→kein Draft/Quell-stabil, CLI-Exit, Sampler+reasoning_effort durchgereicht, Phase-8-Call unverändert). Engine `pipeline/restructure.py` + `pipeline/phase_8_synthesis.py` + `pipeline/config.py`.
- 2026-06-22 — Process-1 (universeller Erstverarbeitungs-Orchestrator): §4 CLI `pkm process --source <dir> [--vault-dir] [--resume]` — der **primäre** Weg, durch den **jedes** md-File (egal Ausgangszustand) immer läuft und vault-ready wird; **kein Vorab-Filter** (alle Files durch alle Stages). Architektur-Entscheidung **Option A** (vorheriger STOP-Fork): eigenständiges Modul `pipeline/process_orchestrator.py`, eigener State `work/process/state.jsonl`, **kein** Einhängen in `pkm run` (Synthese bleibt unberührt; Synthese ist nachgelagerte Phase, nicht der Ingest). Stage-Kette `ingested→normalize(repair-safe+format-safe)→restructure(typ-bewusst WP3c-4)→tags(149-Tag-Vokabular-SSoT, kein Freitext)→assets→links→review_ready→[human_reviewed]→promoted`. **Idempotent** (Hash-Skip erledigter Stages, nicht der Datei), **resumable** (`--resume` setzt am State fort + retryt gescheiterte), **resilient** (Einzelfehler→needs_human, Lauf läuft weiter). STOPpt bei `review_ready` (Review-Sheet via WP3c-6); Promotion = separater Owner-Schritt (WP3c-5). Reuse statt Neubau (`driver.run_chain`/`restructure_file`/`taxonomy`/`batch_restructure`); nur restructure ruft das LLM (im Test gemockt), Rest deterministisch. Kein Vault-Write/D4. Keine `schemas.py`-Änderung. 8 Tests auf tmp-Source/tmp-Vault (alle Varianten formatted/scraped/copy-paste/unformatted→review_ready, Stage-Idempotenz byte-stabil, Gesamt-Idempotenz ohne Doppel-LLM-Calls, Resume nach Abbruch, Resilienz 1-Fail, kein Vault-Write); Live-Vault unberührt. Engine `pipeline/process_orchestrator.py`.
- 2026-06-22 — WP3c-8 (Frontmatter-Lücken-Audit): §4 CLI `pkm frontmatter-audit [--vault-dir] [--out] [--xlsx]` — **read-only, deterministisch, kein LLM, kein Vault-Write**. Neues Modul `pipeline/frontmatter_audit.py`: reuse der Schema-Konstanten (`REQUIRED_FIELDS`/`SLUG_RE`/`UMLAUT_MAP` aus `scripts._pkm_common`, Enums aus `pipeline.taxonomy` — keine Parallel-Validierung); neu ist die **Schließbarkeits-Klassifikation** jeder Lücke (`mechanical`/`llm`/`owner`) + Pro-File-Empfehlung (owner > restructure > mechanical-fix > complete). Report `work/audit/frontmatter_audit_<ts>.md` (+ optional `.xlsx`): Aggregat, kuratierte restructure-Teilmenge, Owner-Liste, Fazit. **Realbefund: 165/165 Files complete & valide, 0 Lücken** → pauschaler Großlauf/Fix nicht indiziert (quantitativ bestätigt). Keine `schemas.py`-Änderung. 7 Tests auf tmp-Vault (Klassifikation je Lücken-Typ, complete→keine Lücke, Empfehlungs-Priorität, Index/Meta-Exklusion); Live-Vault unberührt. Engine `pipeline/frontmatter_audit.py`.
- 2026-06-22 — WP3c-6 (Batch-restructure + Review-Sheet): §4 CLI `pkm restructure-batch --file …|--cluster …` + `pkm review-ingest --sheet …`. Neues Modul `pipeline/batch_restructure.py`, **gesamte Kette review-Tier** (nur Drafts in `drafts/_wp3c6/`, kein Vault-Write/D4). `run_batch_restructure`: opt-in-Selektion (Files **oder** Cluster, **kein** All-Vault), pro File ein Draft via WP3c-4-`restructure_file` (non-thinking, typ-bewusst); ein Fail (Timeout/Parse) **stoppt den Batch nicht** → Fehl-Liste `needs_human.txt`. `write_review_sheet` (openpyxl): Zeile/Draft mit slug/type/type_source/restructure_action/confidence/promote_mode/genre_shift_flag/runtime_s/draft_path + Owner-Decision-Dropdown (accept/reject/edit, DataValidation); `promote_mode` aus Slug-Existenz im Live-Vault (update vs new); Hervorhebung low-confidence/reclassified/new-unvollständig. `ingest_review_sheet`: accept→`review_status: human_reviewed` (nur Frontmatter; new+unvollständig→edit), reject→`archive/rejected_drafts/`, edit→liegen lassen — **kein Vault-Write**; Output = promotion-bereite Drafts für WP3c-5. **Neue Dependency `openpyxl>=3.1`** (war nicht installiert; +mypy-override). **Kein All-Vault-Großlauf** vor Reclassify-Realtest (Leitplanke). 5 Tests (LLM+Vault gemockt: Fail-Isolation, promote_mode, Sheet-Spalten/Dropdown/Highlights, ingest accept/reject/edit, kein-Vault-Write). Engine `pipeline/batch_restructure.py`.
- 2026-06-22 — WP3c-5 (Draft→Vault-Promotion, D4): §4 CLI `pkm promote --draft <path> [--on-collision abort|replace|suffix] [--execute]` (Default **dry-run**). Neues Modul `pipeline/promotion.py`: **Promotion-Gate** (nur `human_reviewed`/`verified`; `ai_drafted` → harter Abbruch, kein Write), Ziel-Ordner aus `category`-SSoT (`taxonomy.load_category_to_folder`), Frontmatter-Finalisierung (`status: review` — **nie** auto-stable; `updated`/`last_synthesized` gestempelt; `provenance`/`type_source`/`restructure_action`/`prompt_version` erhalten) gegen `schemas.FrontmatterDraft` (Pydantic-SSoT) validiert. **Update-Modell** (restructure-Draft = bestehendes File): Ziel-Kollision → kein Blind-Overwrite, `abort` meldet Diff+STOP / `replace` updatet (Content aus Draft, Taxonomie aus Bestand) / `suffix` = `slug_2.md`. **D4** (`--execute`, Owner-Gate): `snapshot_vault` → Write → Verify → mandatorische Index-Regen (`phase_9._render_index`, G8) → Draft → `archive/promoted_drafts/`; Fehler → `restore_snapshot`. Reuse statt Parallel-Impl. (`driver`/`phase_9`/`taxonomy`/`schemas`). Keine `schemas.py`-Änderung. 8 Tests auf tmp-Vault (Gate, SSoT-Ordner, Finalize, Kollision abort/replace/suffix, Dry-run kein-Write, Index-Regen + doc-count, unvollständig→Abbruch); Live-Vault unberührt. Engine `pipeline/promotion.py`.
- 2026-06-22 — WP3c-4 (typ-bewusstes restructure): behebt den Genre-Shift (WP3c-2: jeder Input wurde ins `knowledge-article`-Erklär-Template gepresst → nutzbare Artefakte verloren ihre Funktion). **Hybrid-Type-Resolver** (`_resolve_type`): Frontmatter-`type` führend; fehlt/ungültig → Light-Klassifikation (non-thinking) gegen die 4 Enum-Werte (`type_source: classified`); `knowledge-article` + klares Funktional-Signal → Reklassifikation nach `compact-reference` (`type_source: reclassified`), sonst Frontmatter behalten (Leitplanke: korrekte manuelle Typen nicht aggressiv überschreiben). **type-konditionale Stage-3-Direktive** (neuer Prompt **v2**, `compact-reference`/`gedanke` = verbatim-/minimal-invasiv statt Erklär-Rewrite). **Passthrough-Schwelle zuerst**: bereits gut strukturierte Files (Headings + Slug-konform + keine Korruption) → Body verbatim, nur Frontmatter ergänzt (`restructure_action: passthrough`). Draft-Frontmatter um `type` (aufgelöst), `type_source`, `restructure_action` erweitert; provenance um `type_source`. Isoliert via `qwen.restructure.prompt_version: v2` — **Phase 8 bleibt auf v1** (`qwen.prompt_version` unverändert). Prompts: `prompts/v2/stage3_synthesis.md` (neu, type-aware), `prompts/v2/stage4_frontmatter_json.md` (unverändert aus v1), `prompts/v2/MIGRATION.md`. **A/B-Realmessung:** Draft A (`prompt-optimierung…`, frontmatter=knowledge-article, gut strukturiert) → Passthrough, Body **byte-verbatim** (419w==419w, Genre-Shift behoben), 104s; knowledge-article-Control → Passthrough, type korrekt, 86s; beide confidence high, Quell-Files unberührt. Keine `schemas.py`-Änderung (Draft-Frontmatter dict→YAML). 7 neue type-aware-Tests (Frontmatter-Respekt, classified, reclassified, type-Direktive in Stage-3-Message, Passthrough vs. rewrite) + 15 bestehende restructure-/Resilienz-Tests angepasst. Engine `pipeline/restructure.py` + `pipeline/config.py` + `prompts/v2/`.
- 2026-06-24 — WP3b (Synthese-Korpus-Filter + additive MOC): §3 `redundancy_scan.exclude_folders`/`exclude_categories` (Synthese-Korpus = nur Wissensartikel, Ausschluss via Ordner/category, **kein** Slug-Filter, ausgeschlossene Docs transparent im Report). §4 CLI `pkm synthesize-moc [--approved FILE] [--vault-dir DIR] [--out-dir DIR] [--no-qwen]` — neue MOC-Drafts aus Gate-A-freigegebenen Clustern nach `drafts/_moc/` (D6 additiv, kein Vault-Write). Engine `pipeline/synthesis_moc.py`: Frontmatter (`doc_type: moc`, `merged_from: []`, `confidence`, `moc_members`) + 2-3-Satz-Qwen-Rahmung (`/no_think`, gecappt; Fehler → deterministische Fallback + `needs_human`) + Wikilinks; **Link-Descriptor = realer `summary` des Ziel-Docs (RV13, keine Generierung)**, kein Body-Kopieren, Quell-Artikel byte-unverändert. Keine `schemas.py`-Änderung (Draft-Frontmatter dict→YAML). 8 MOC-Tests (LLM injiziert) + 3 Korpus-Filter-Tests. **Gate 3b:** Owner prüft jedes MOC einzeln, Export separat.
- 2026-06-24 — WP3b-Promote (MOC → Vault): `promotion.py` `FOLDER_BY_DOC_TYPE` (`doc_type: moc` → `00_Maps/`, Override **vor** dem category→Ordner-Mapping) + `PRESERVE_STATUS_DOC_TYPES` (`moc` bleibt `status: draft`, wird NICHT auto-`review`). `synthesis_moc.build_moc` emittiert jetzt zusätzlich die Vault-Pflichtfelder `summary` / `doc_role: [index]` / `sources_docs: []` / `source_chunks: []` → MOCs sind über `pkm promote` FrontmatterDraft-validiert promotierbar. 2 neue Promotion-Tests (Override-Routing 00_Maps + status-Erhalt draft). Keine `schemas.py`-Änderung.
- 2026-06-21 — WP3c-1 (restructure-review Scaffold): §4 CLI `pkm restructure --file <path> [--out drafts/]` (review-only, **nie** Vault-Write, kein `--execute`). Neues Modul `pipeline/restructure.py`: `RestructureReviewTransform` (tier=**review**, mutating, registry-fähig → `driver._chain_writable` blockt Auto-Write) + `restructure_file()` Single-File-Orchestrator. **Reuse** der kanonischen v1-Prompts Stage 3 (Body) + Stage 4 (Frontmatter) und der injizierbaren Call-Layer (`_load_prompt`/`_run_text_stage`/`_run_json_stage` aus `phase_8_synthesis`) — kein neuer Prompt. Draft-Frontmatter: `review_status: ai_drafted` · `confidence: <low|medium|high>` (Vault-SSoT-Enum, kein Float; Stage-4-Wert auf Enum normalisiert) · `provenance` (Quelle-Slug/Modell/Prompt-Version/Timestamp); fehlende/ungültige confidence → `low` + `confidence_fallback: true`. Quell-File read-only, Output nur `drafts/`. Draft→Vault-Promotion = separater D4-Task (Folge-Inkrement). Keine `schemas.py`-Änderung (Draft-Frontmatter als dict→YAML, kein Pydantic → §7 n/a). 10 neue Tests (LLM gemockt: byte-stabiler Draft, Frontmatter-Kontrakt, confidence-Enum+Fallback, Quell-File-Snapshot, Driver-Invariante review→kein Write). Engine `pipeline/restructure.py`.
