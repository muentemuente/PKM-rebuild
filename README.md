# PKM-rebuild

Pipeline und Bereinigungs-Workflow für eine bestehende Markdown-Wissenssammlung. Ziel: aus ~200 unstrukturierten Markdown-Dateien einen sauber strukturierten Obsidian-Vault mit konsistentem Frontmatter, deduplizierten Inhalten und thematischer Ordner-Struktur generieren.

- **Basis-Pipeline:** abgeschlossen (Phasen 0–12, 2026-06-06)
- **v3-Zyklus:** WP0–WP4 abgeschlossen + gemergt (WP2 entfiel) — Stabilisierung, additive Synthese/MOC, Bestands-Remediation; Plan [`docs/Projektplan_pipeline-v3.md`](docs/Projektplan_pipeline-v3.md), Detailstand [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)
- **Post-WP4:** read-only Quality-Layer (`quality-score`/`vault-health`), Stage-3-Hardening (H3) und **NB-Feld-Backfill (A2a/A2b) promotet** — `key_points`/`open_questions`/`next_steps`/`keyphrases` auf allen 165 produktiv+nutzbaren Notes (NB-Linie geschlossen)
- **Vault:** 181 Artikel + 5 MOC in 14 genutzten Ordnern (0 Pydantic-Fails, 0 SHA-Dups); idempotent (`pkm regenerate-indices` = 0/14)
- **Charakter:** Lernprojekt mit produktivem Output
- **Erstnutzung:** [`docs/MANUAL.md`](docs/MANUAL.md) (Bedienungsanleitung: Walkthrough + CLI-Referenz + Troubleshooting)
- **Laufender Betrieb:** [`docs/FUTURE_RUN.md`](docs/FUTURE_RUN.md) (inkrementeller Standard-Workflow)
- **Verbleibend:** menschliche Qualitätsstufe-2-Review ([`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)); Vault #3 per Time Machine täglich gesichert

---

## Die drei Orte

Das Projekt verteilt sich auf drei physisch getrennte Orte. Sie nicht zu verwechseln ist wichtig — nur #1 ist versioniert, nur #1 wird von Claude Code beschrieben.

| # | Pfad | Rolle |
|---|---|---|
| 1 | `~/projects/aktiv/PKM-rebuild/` | Code + Doku (Git, public) — **hier wird gearbeitet** |
| 2 | `~/projects/aktiv/pkm-pipeline/` | Daten-Durchlauf (lokal, außerhalb Git) |
| 3 | `/Users/muente/Zentrale/09_Brain-Vault/` | produktiver Obsidian-Vault |

Orientierung pro Ort: `WAYFINDING.md` (im jeweiligen Root). Schreibzugriff von Claude Code nur auf #1; Schritte für #3 stehen in [`MANUAL_STEPS.md`](MANUAL_STEPS.md).

---

## Was macht dieses Projekt?

| Stufe | Inhalt |
|---|---|
| **A. Vorbereitung (Python)** | Inventar, Normalisierung, Strukturextraktion, Segmentierung, Redundanz-Erkennung (Hash → TF-IDF → Embeddings) |
| **B. Veredelung (Qwen 3.6 27B lokal, Option B)** | **Pro-Doc** statt Cross-Doc-Merge. Routing je Doc: `passthrough` (Code/Tabellen/Headings → Body 1:1 + Frontmatter) · `stage3` (Prosa → LLM-Veredelung + Frontmatter) · `gedanken` (Sonderpfad, Minimal-Frontmatter). Kein Cluster-Merge, `merged_from` immer leer. |
| **C. Vault-Aufbau** | bereinigte Artikel in Obsidian-Vault; `category` aus Qwen-Stage-4 + deterministischem Mapping auf 16 thematische Ordner (+ `17_unsortiert` Catch-all), Wikilinks, Tag-Vokabular |
| **D. Inkrementell** | neue `.md` → `pkm-pipeline/input/` → **`pipeline process`** (universelle Erstverarbeitung, **kanonischer go-forward-Pfad**) → Review → `promote` (Owner-Gate). `pipeline ingest`/`run` (Phasen 1–4 + 8, Option B) = Synthese-Linie; `ingest_md_download` = §3-Vorverarbeitung; `corpus-run` = Legacy/Batch. Pfad-Begründung: [`docs/handover/v3-entrypoints.md`](docs/handover/v3-entrypoints.md). Vokabular-Pflege über `scripts/manage_vocab.py`. |
| **E. Qualität & Backfill** | read-only Quality-Layer: `pipeline quality-score` (6 Dimensionen + Composite + Band, deterministisch, kein LLM) und `pipeline vault-health` (aggregiert die Score-Historie). Additiver NB-Feld-Backfill (`key_points`/`open_questions`/`next_steps` via Live-Qwen, `keyphrases` deterministisch) — abgeschlossen und in den Vault promotet. |

---

## Tech-Stack

| Bereich | Tool |
|---|---|
| Pipeline-Sprache | Python 3.12 (via `mise`) |
| Lokales LLM | Qwen 3.6 27B (4-bit) via LM Studio / Ollama |
| Embedding-Modell | `paraphrase-multilingual-mpnet-base-v2` |
| AI-Agent | Claude Code (Claude Pro) in Zed |
| Editor | Zed |
| Terminal | Ghostty + zsh + zinit + Powerlevel10k |
| Versionierung | Git + GitHub (`gh` CLI) |

---

## Quick Start

> Voraussetzung: macOS, `mise` installiert.

```bash
# Repo klonen
gh repo clone muentemuente/PKM-rebuild
cd PKM-rebuild

# Python-Env via mise
mise install
mise use python@3.12

# Erststart: Editable-Install inkl. dev-Tools (pytest, ruff, mypy)
make setup
# (entspricht `pip install -e ".[dev]"`; ohne dev-Tools: `pip install -e .`)

# Verifikation
python -m pipeline --version
python -m pipeline status
```

### Neue Dateien verarbeiten — `process` (der Weg)

`pipeline process` ist der **kanonische** Weg: jede neue `.md` (egal welcher Ausgangszustand) läuft durch dieselbe Stage-Kette bis `review_ready`. Kein Vault-Write — der Live-Vault wird erst im gegateten `promote` geschrieben.

```bash
# 1. Neue Roh-Dateien ablegen
#    → ~/projects/aktiv/pkm-pipeline/input/   (Daten-Root, außerhalb des Repos)

# 2. Verarbeiten (braucht laufendes LM Studio mit Qwen-Modell)
python -m pipeline process --source ~/projects/aktiv/pkm-pipeline/input/
#    → Drafts + Review-Sheet (.xlsx); resume-fähig via --resume

# 3. Review-Sheet ausfüllen (Mensch), dann einlesen
python -m pipeline review-ingest --sheet <sheet>.xlsx

# 4. In den Vault übernehmen (Owner-Gate)
python -m pipeline promote --draft <draft>            # dry-run: Plan + Diff
python -m pipeline promote --draft <draft> --execute  # Live-Write nach #3
```

Vollständiger Schritt-für-Schritt-Walkthrough mit Beispiel: **[`docs/MANUAL.md`](docs/MANUAL.md)**. Inkrementeller Workflow im Detail: [`docs/FUTURE_RUN.md`](docs/FUTURE_RUN.md).

> **Datenpfad:** `process` liest aus `~/projects/aktiv/pkm-pipeline/input/` (außerhalb des Repos). Daten-Root überschreibbar per `PKM_PIPELINE_ROOT`; zentrale Pfad-Auflösung in `pipeline/_paths.py`.

<details>
<summary><b>Legacy / Sonderfall</b> — nicht der Standard-Weg</summary>

```bash
# Option-B-Synthese-Linie (staging-basiert, für Batch-/Cluster-Synthese)
python -m pipeline ingest --dry-run          # Phasen 1–4 + 8 → Drafts
python -m pipeline run --dry-run             # input/ → Review-Gates → output/
python -m pipeline build-vault --dry-run     # Phase 9: Drafts → output/ (Staging)

# Legacy-Vollkorpus-Erstlauf (Archiv, NICHT go-forward)
python -m pipeline corpus-run --sample 10

# Read-only Reports & Vokabular
python -m pipeline quality-score             # Quality-Scoring (deterministisch)
python -m pipeline vault-health              # Health aus Score-Historie
python3 scripts/manage_vocab.py list         # Vokabular anzeigen
python3 scripts/manage_vocab.py validate     # Drift prüfen
```

Einordnung der Entrypoints: [`docs/handover/v3-entrypoints.md`](docs/handover/v3-entrypoints.md).
</details>

Details zu Setup, Daten-Layout und Datenpfaden: [`docs/02_pipeline_spec.md`](docs/02_pipeline_spec.md).

---

## Verzeichnis-Layout

**Code-Repo (Git, public):**

```
PKM-rebuild/
├── README.md                  ← hier
├── CLAUDE.md                  ← Working Rules für Claude Code
├── docs/                      ← Projekt-Dokumentation
│   ├── MANUAL.md              ← Bedienungsanleitung (Walkthrough + CLI-Referenz)
│   ├── 00_persona_muente.md   ← gitignored
│   ├── 01_strategy.md
│   ├── 02_pipeline_spec.md
│   ├── 03_vault_standard.md
│   ├── 04_qwen_prompts.md
│   ├── 05_glossary.md
│   ├── 06_claude_code_workflow.md
│   ├── 07_backup_strategy.md
│   ├── PROJECT_STATUS.md      ← aktueller Stand
│   ├── FUTURE_RUN.md          ← inkrementeller Workflow
│   └── learnings/
├── pipeline/                  ← Python-Modul
│   ├── CLAUDE.md
│   └── pipeline.config.yaml
├── prompts/                   ← Qwen-Prompts, versioniert
│   ├── CLAUDE.md
│   └── v1/
└── .gitignore
```

**Daten (außerhalb Git):**

```
~/projects/aktiv/pkm-pipeline/      ← Daten-Root (PKM_PIPELINE_ROOT, siehe pipeline/_paths.py)
├── _ingest/                   ← Roh-Downloads (md + Assets), Quelle für `pkm ingest`
├── input/                     ← neue .md (+ _assets/) pro Lauf
├── work/                      ← Zwischen-JSONL + state.json + logs
├── drafts/                    ← Qwen-generierte Drafts (CK_<slug>.*)
├── review/                    ← Gate-Queues + decisions.{jsonl,md}
├── output/                    ← gebauter Staging-Vault → Mensch zieht ihn in den produktiven Vault
└── archive/                   ← verarbeitete Inputs + alte Runs + Backups
```

> Der produktive Obsidian-Vault liegt separat unter `~/Zentrale/09_Brain-Vault/` (Ziel des manuellen Asset-Merge, `make publish-assets`).

Begründung der Trennung: Pipeline ist public (Lernprojekt-Wert), Korpus-Inhalt bleibt lokal. Backup-Strategie für den Vault: siehe [`docs/07_backup_strategy.md`](docs/07_backup_strategy.md).

---

## Assets & Diagramme

Konventionen für eingebettete Dateien und Diagramme im Vault (#3):

- **Assets** (Bilder, PDFs) → globaler flacher Pool `09_Brain-Vault/_assets/`, benannt `<note-slug>__<original-name>.ext`, eingebettet pfad-frei per `![[name]]`. Vollständig: [`docs/03_vault_standard.md`](docs/03_vault_standard.md) §15.
- **Diagramme** → ausschließlich Mermaid als ` ```mermaid `-Codeblock im Note-Body (diff-bar, kein Plugin-Lock-in). Excalidraw nicht eingeführt. Vollständig: [`docs/03_vault_standard.md`](docs/03_vault_standard.md) §16.

Eigenständige Schritt-für-Schritt-Anleitungen (Master für `00_Meta/`): [`docs/vault_meta/asset-management.md`](docs/vault_meta/asset-management.md) · [`docs/vault_meta/diagramm-standard.md`](docs/vault_meta/diagramm-standard.md).

---

## Dokumentation

Reihenfolge zum Einstieg (auch für Claude Code als Lese-Kontext):

| Datei | Zweck |
|---|---|
| [`docs/MANUAL.md`](docs/MANUAL.md) | **Bedienungsanleitung** — Einstieg für Erstnutzung (Walkthrough + CLI-Referenz + Troubleshooting) |
| [`CLAUDE.md`](CLAUDE.md) | Working Rules für Claude Code |
| [`docs/00_persona_muente.md`](docs/00_persona_muente.md) | Wer arbeitet hier, Constraints (lokal, gitignored) |
| [`docs/01_strategy.md`](docs/01_strategy.md) | Ziele, Scope, Definition of Done, Risiken |
| [`docs/02_pipeline_spec.md`](docs/02_pipeline_spec.md) | Pipeline-Phasen, Schemas, Akzeptanzkriterien |
| [`docs/03_vault_standard.md`](docs/03_vault_standard.md) | Frontmatter, Naming, Cluster, Qualitätsstufen |
| [`docs/04_qwen_prompts.md`](docs/04_qwen_prompts.md) | Prompt-Stages, Versionierung, Validierung |
| [`docs/05_glossary.md`](docs/05_glossary.md) | Begriffsdefinitionen |
| [`docs/06_claude_code_workflow.md`](docs/06_claude_code_workflow.md) | Claude Code in Zed, Token-Management, Recovery |
| [`docs/07_backup_strategy.md`](docs/07_backup_strategy.md) | Backup-Plan für den Vault |
| [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) | Aktueller Projektstand, Counts, DoD |
| [`docs/FUTURE_RUN.md`](docs/FUTURE_RUN.md) | Inkrementeller Standard-Workflow (Inbox → ingest → Vault) + Backlog |
| [`docs/learnings/`](docs/learnings/) | Reflexionsdokumente pro Phase |
| [`docs/_archive/`](docs/_archive/) | Erledigte Handover-/Task-Artefakte (Historie) |

---

## Lernprojekt-Hinweis

Dieses Projekt dient gleichzeitig als Lernumgebung für:

- Software-Projektaufbau, Dokumentations-Pflege, GitHub-Workflows
- Zed + Claude Code Integration in den täglichen Workflow
- Pipeline-Engineering in Python
- Lokale LLMs (Qwen) für strukturierte Datenverarbeitung
- Personal Knowledge Management mit Obsidian

Pro Phase entsteht ein Reflexionsdokument in [`docs/learnings/`](docs/learnings/).

---

## Lizenz

TBD — Festlegung vor erstem `git push public`.

---

## Autor

[muente](https://github.com/muentemuente)
