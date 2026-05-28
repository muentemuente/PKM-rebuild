# PKM-rebuild

Pipeline und Bereinigungs-Workflow für eine bestehende Markdown-Wissenssammlung. Ziel: aus ~200 unstrukturierten Markdown-Dateien einen sauber strukturierten Obsidian-Vault mit konsistentem Frontmatter, deduplizierten Inhalten und stabiler Cluster-Struktur generieren.

## Status

- **Phase:** Phasen 1–8 implementiert, Echtlauf ausstehend (Phase 9–10 Stub)
- **Stand:** 2026-05-28
- **Charakter:** Lernprojekt mit produktivem Output
- **Offene Tasks:** [`docs/tasks/README.md`](docs/tasks/README.md)

---

## Was macht dieses Projekt?

| Stufe | Inhalt |
|---|---|
| **A. Vorbereitung (Python)** | Inventar, Normalisierung, Segmentierung, Redundanz-Erkennung (Hash → TF-IDF → Embeddings), thematische Cluster-Bildung |
| **B. Synthese (Qwen 3.6 27B lokal)** | mehrstufige Verarbeitung: Cluster-Analyse → Merge-Vorschläge → Synthese → Frontmatter-Generierung |
| **C. Vault-Aufbau** | bereinigte Artikel in neuen Obsidian-Vault mit Cluster-Struktur, Wikilinks, Tag-Vokabular |

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

# Dependencies
pip install -e .

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
```

Details zu Setup, Daten-Layout und Datenpfaden: [`docs/02_pipeline_spec.md`](docs/02_pipeline_spec.md).

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
│   ├── 01_corpus_input/       ← Original-Markdown (read-only)
│   ├── 02_pipeline_output/    ← JSONL, Embeddings, Cluster
│   ├── 03_drafts/             ← Qwen-generierte Drafts
│   └── 04_vault/              ← finaler Obsidian-Vault
└── backups/                   ← Time Machine + manuelle Snapshots
```

Begründung der Trennung: Pipeline ist public (Lernprojekt-Wert), Korpus-Inhalt bleibt lokal. Backup-Strategie für den Vault: siehe [`docs/07_backup_strategy.md`](docs/07_backup_strategy.md).

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
| [`docs/learnings/`](docs/learnings/) | Reflexionsdokumente pro Phase |
| [`docs/tasks/README.md`](docs/tasks/README.md) | Offene Tasks + Blöcke (P0–P2) |

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
