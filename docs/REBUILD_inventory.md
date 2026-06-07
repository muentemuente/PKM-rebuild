---
title: Rebuild-Inventar — Refactor-Checkliste Pipeline-Umbau
slug: rebuild-inventory
status: living-document
created: 2026-06-06
updated: 2026-06-06
---

# Rebuild-Inventar — hardcodierte Pfade + Refactor-Surface

Ist-Aufnahme vor dem Umbau zur Inkrement-Pipeline (`TASK_build_pipeline.md`).
Diese Liste ist die **Refactor-Checkliste für WP2** (Umstellung auf `pipeline/_paths.py`).

Rollback-Snapshot: `~/projects/aktiv/PKM_rebuild/backups/ROLLBACK_rebuild_20260606_224320.tar.gz` (7.0 MB, `data/`).
Feature-Branch: `rebuild-pipeline-20260606_224320`.

---

## 0. Ist-Zustand der Daten (Abweichung von der Task-Annahme)

Die Task (WP1) nahm 179 Artikel in `data/04_vault/` an. **Real ist der Live-Vault leer** —
der finalisierte Vault wurde bereits in den produktiven Obsidian-Vault gezogen und nur als
Tarball gesichert.

| Ort | Realität (2026-06-06) |
|---|---|
| `data/01_corpus_input/` | 200 `.md` (read-only) — Alt-Korpus |
| `data/02_pipeline_output/` | JSONL/Reports/Embeddings (Build-Artefakte) |
| `data/03_drafts/` | **existiert nicht mehr** (in Tarball `archive_drafts_…`) |
| `data/04_vault/` | **leer** — nur `.obsidian/` + `.DS_Store` |
| `data/00_inbox/` | leer |

**Migrations-Entscheidung (muente, 2026-06-06):** `output/` startet **leer** (reines Staging für
künftige Runs); bestehende Tarballs werden nach `archive/` **verschoben** (nicht entpackt).

---

## 1. Refactor-Surface — Übersicht

| Klasse | Befund |
|---|---|
| **A. config-getrieben (bereits sauber)** | `pipeline/*.py`, `pipeline/__main__.py`, `scripts/dod_check.py` lesen Pfade aus `cfg.paths` → nur `config.yaml` muss umgestellt werden |
| **B. Standalone-Skripte mit eigener `DATA_ROOT`-Konstante** | 12 Skripte in `scripts/` → müssen auf `pipeline/_paths.py` umgestellt werden |
| **C. `config.yaml` Pfad-Defaults** | `data_root` + `backups` zeigen auf altes Layout |
| **D. Shell-Skripte** | `snapshot.sh`, `restore.sh` |
| **E. Tests** | 1 Test mit hartem `PKM_rebuild`-Pfad; restliche Test-Pfade sind tmp-intern (OK) |
| **F. nur Docstrings/Kommentare** | kosmetisch, opportunistisch mitziehen |

---

## 2. Klasse C — `pipeline/pipeline.config.yaml`

Single Source für die config-getriebenen Komponenten (Klasse A).

| Zeile | Fundstelle |
|---|---|
| 13–14 | Kommentar Default-Pfad + `PKM_DATA_ROOT` |
| 16 | `data_root: "~/projects/aktiv/PKM_rebuild/data"` |
| 17–21 | abgeleitete Pfade `00_inbox` / `01_corpus_input` / `02_pipeline_output` / `03_drafts` / `04_vault` |
| 22 | `backups: "~/projects/aktiv/PKM_rebuild/backups"` |

WP2-Ziel: neues Layout (`input/ work/ drafts/ review/ output/ archive/` unter
`~/projects/aktiv/pkm-pipeline/`), aufgelöst über `pipeline/_paths.py`.

---

## 3. Klasse B — Standalone-Skripte mit hardcodierter Pfad-Bindung

Jedes Skript definiert aktuell eine eigene Konstante. **Alle** müssen in WP2 von
`pipeline/_paths.py` importieren.

| Skript | Zeile(n) | Konstante(n) | Go-forward? |
|---|---|---|---|
| `scripts/phase8_runner.py` | 48,49,53 | `PROJECT_ROOT` (Repo), `DATA_ROOT`, `BACKUP_BASE` | ✅ (Qwen-Lauf, geht in `pkm run`/WP5 auf) |
| `scripts/pkm_triage.py` | 90 | `DATA_ROOT` (+ CORPUS/DRAFTS/VAULT/OUTPUT abgeleitet) | ✅ (Routing) |
| `scripts/manage_vocab.py` | 50 | `DATA_ROOT` (+ VAULT/DRAFTS) | ✅ (Vokabular-Pflege) |
| `scripts/check_frontmatter.py` | 59 | `DATA_ROOT` (+ DRAFTS/OUTPUT) | ✅ (Validierung) |
| `scripts/validate_vault.py` | 6 | `VAULT` | ✅ (Build-Validierung) |
| `scripts/rebuild_indices.py` | 8 | `VAULT` | ✅ (`_index.md`) |
| `scripts/apply_tag_map.py` | 48,49,50 | `DATA_ROOT`, `REPO_ROOT`, `BACKUP_ROOT` | ✅ (Tag-Apply) |
| `scripts/tag_inventory.py` | 31,32 | `_DEFAULT_CORPUS`, `_DEFAULT_OUTPUT` | ◑ (Diagnose; argparse-overridebar) |
| `scripts/apply_category_mapping.py` | 30 | `DATA` (+ DRAFTS/PROPOSAL) | ◑ (Mapping-Quelle → `config/categories.yaml`) |
| `scripts/draft_inventory.py` | 98 | `DATA_ROOT` (+ DRAFTS/OUTPUT) | ○ (Build-Diagnose, Altlauf) |
| `scripts/r2_diagnose.py` | 52 | `DATA_ROOT` | ○ (Build-Diagnose, Altlauf) |
| `scripts/unsortiert_diagnose.py` | 28 | `DATA_ROOT` | ○ (Build-Diagnose, Altlauf) |
| `scripts/clustering_analysis.py` | — | argparse, kein `home()`-Konstante | ○ (verworfen, Lern-Artefakt) |

Legende: ✅ go-forward · ◑ go-forward mit Einschränkung · ○ Altlauf/Diagnose (Code bleibt, nicht im neuen Pfad)

---

## 4. Klasse A — config-getriebene Module (kein eigener Pfad-Code)

Diese lesen Pfade aus `cfg.paths.*`; sie ziehen automatisch mit, sobald `config.yaml` +
`_paths.py` umgestellt sind. **Kein direkter Edit nötig** (außer Docstring-Kosmetik).

```
pipeline/__init__.py        pipeline/config.py          pipeline/__main__.py
pipeline/ingest.py          pipeline/schemas.py
pipeline/phase_1_inventory.py  … phase_2 … phase_10_reports.py
scripts/dod_check.py        (lädt config über --config, nutzt cfg.paths)
```

`scripts/_pkm_common.py`: kein Pfad-Code, leitet Enums aus `pipeline.schemas` +
`pipeline.phase_9_vault_build.CATEGORY_TO_FOLDER` ab. Bei WP2-Konsolidierung
(`_pkm_common` ↔ `_paths`) beachten.

---

## 5. Klasse D — Shell-Skripte

| Skript | Zeile(n) | Befund |
|---|---|---|
| `scripts/snapshot.sh` | 15 | `DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"` (+ 01/03/04-Subdirs) |
| `scripts/restore.sh` | 18,23,124 | `DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"` |

---

## 6. Klasse E — Tests

| Test | Zeile | Befund |
|---|---|---|
| `tests/test_clustering_analysis.py` | 21 | `_DATA_DIR = Path.home()/"projects/aktiv/PKM_rebuild/data/02_pipeline_output"` — harter Pfad |
| übrige Tests | div. | `tmp_path / "03_drafts"` etc. — Fixture-intern, **kein** Bezug zum echten Layout (OK; ggf. Namen für Klarheit anpassen) |

---

## 7. Klasse F — nur Docstrings / Kommentare (kosmetisch)

`pipeline/phase_2,4,5,6,7_*.py` (Input/Output-Docstrings), `pipeline/__main__.py`
(Help-Texte `data/00_inbox`, `data/04_vault`), diverse Skript-Docstrings,
`pipeline/CLAUDE.md`. Opportunistisch beim jeweiligen File-Edit mitziehen.

---

## 8. Mapping-/Vokabular-Quellen für `config/` (WP2)

| Ziel-Config | Quelle heute |
|---|---|
| `config/categories.yaml` (17 + Mapping-Regeln) | `pipeline/phase_9_vault_build.py:50` `CATEGORY_TO_FOLDER` + `scripts/apply_category_mapping.py` (deterministische Regeln) |
| `config/tag_vocabulary.yaml` (149) | `04_vault/00_Meta/tag-system.md` (im Vault-Tarball; Abschnitt „## Kern-Vokabular"); gespiegelt von `scripts/manage_vocab.py` |
| `config/tag_merge_map.json` | `scripts/tag_merge_map.json` (verschieben) |

---

## Änderungs-Log

- 2026-06-06 — Initial (WP0): Ist-Aufnahme, hardcodierte Pfade je File, Daten-Ist-Zustand
