# PKM-rebuild

Pipeline und Bereinigungs-Workflow für eine bestehende Markdown-Wissenssammlung. Ziel: aus ~200 unstrukturierten Markdown-Dateien einen sauber strukturierten Obsidian-Vault mit konsistentem Frontmatter, deduplizierten Inhalten und thematischer Ordner-Struktur generieren.

## Status

- **Phase:** abgeschlossen (2026-06-06)
- **Stand:** 2026-06-05
- **Vault:** 180 Artikel in 15 genutzten Ordnern (0 Pydantic-Fails, 0 SHA-Dups), inkl. `17_unsortiert` (8)
- **Deferred:** 19 `_hold` (Gedanken) · 3 `_excluded` (denkschulen + 2 Hangs) — über Inbox nachziehbar
- **Charakter:** Lernprojekt mit produktivem Output
- **Laufender Betrieb:** [`docs/FUTURE_RUN.md`](docs/FUTURE_RUN.md) (inkrementeller Standard-Workflow)
- **Verbleibend:** nur menschliche Qualitätsstufe-2-Review + Backup 2. Medium ([`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md))

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
| **D. Inkrementell** | neue `.md` → `data/00_inbox/` → `pipeline ingest` (Phasen 1–4 + 8, Option B) → Review → `build-vault`. Vokabular-Pflege über `scripts/manage_vocab.py`. |

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

> **Hinweis:** `python -m pipeline run` setzt Korpus-Daten unter `~/projects/aktiv/PKM_rebuild/data/` voraus (außerhalb des Repos). Pfade in `pipeline/pipeline.config.yaml` anpassen.

```bash
# Dry-Run (zeigt Phasen, schreibt nichts)
python -m pipeline run --dry-run

# Sample-Run (10 Files, setzt Daten voraus)
python -m pipeline run --phase 1 --sample 10

# Ab Phase 5 weiterlaufen
python -m pipeline run --from-phase 5

# Inkrementell: neue .md aus data/00_inbox/ verarbeiten (Option B)
python -m pipeline ingest --dry-run     # Plan zeigen, nichts schreiben
python -m pipeline ingest               # verarbeiten (braucht laufendes LM Studio)

# Vault bauen + Vokabular pflegen
python -m pipeline build-vault
python3 scripts/manage_vocab.py list
python3 scripts/manage_vocab.py validate
```

Details zu Setup, Daten-Layout und Datenpfaden: [`docs/02_pipeline_spec.md`](docs/02_pipeline_spec.md); inkrementeller Workflow: [`docs/FUTURE_RUN.md`](docs/FUTURE_RUN.md).

---

## Verzeichnis-Layout

**Code-Repo (Git, public):**

```
PKM-rebuild/
├── README.md                  ← hier
├── CLAUDE.md                  ← Working Rules für Claude Code
├── docs/                      ← Projekt-Dokumentation
│   ├── 00_persona_muente.md   ← gitignored
│   ├── 01_strategy.md
│   ├── 02_pipeline_spec.md
│   ├── 03_vault_standard.md
│   ├── 04_qwen_prompts.md
│   ├── 05_glossary.md
│   ├── 06_claude_code_workflow.md
│   ├── 07_backup_strategy.md
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
~/projects/aktiv/PKM_rebuild/
├── data/
│   ├── 00_inbox/              ← Inbox für inkrementellen Lauf (pipeline ingest)
│   ├── 01_corpus_input/       ← Original-Markdown (read-only)
│   ├── 02_pipeline_output/    ← JSONL, Embeddings, Reports, ingest_report.md
│   ├── 03_drafts/             ← Qwen-generierte Drafts
│   └── 04_vault/              ← finaler Obsidian-Vault (16 Ordner + 17_unsortiert)
└── backups/                   ← Time Machine + manuelle Snapshots
```

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
