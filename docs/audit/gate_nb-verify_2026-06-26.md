---
title: "Gate-Report — NB-Verifikation + Ground-Truth-Snapshot"
slug: gate-nb-verify-2026-06-26
status: draft
created: 2026-06-26
updated: 2026-06-26
typ: gate-report
quelle-task: cc-tasks/task_verify-nb-luecken.md
gate: Gate-Report → Owner-Review → Architect (App)
---

# Gate-Report — NB-Verifikation + Ground-Truth (2026-06-26)

> Read-only statische Analyse. Kein Code-Edit, kein Vault-Write, kein LLM-Call,
> kein Commit. Jede Aussage mit Beleg (Datei:Zeile oder Befehl+Ergebnis).

## A. Repo-Fakten

- `$REPO` = `/Users/muente/projects/aktiv/PKM-rebuild` (real; enthält `pipeline/` + `pyproject.toml`). Kandidat `~/projects/aktiv/pkm-pipeline/` ist **kein** Repo-Root (= go-forward-Datenordner, außerhalb Git).
- git HEAD: `c02acdd` — *Merge pull request #43 from muentemuente/docs/consolidation-rest*
- working tree: **dirty** (nur untracked Doku): `docs/luecken-uebersicht-oos-nb-conf.md`, `docs/ziel-implementierungs-matrix.md`. Kein tracked-File modifiziert.

## B. Ground-Truth-Snapshot

### GT-1 Module `pipeline/*.py` (Datei | Zeilen)
Gesamt **37 Module**, **16 133** Zeilen. Größte:

| Datei | Zeilen |
|---|---|
| `__main__.py` | 1646 |
| `phase_8_synthesis.py` | 1394 |
| `vault_audit.py` | 1165 |
| `phase_10_reports.py` | 762 |
| `phase_4_segment.py` | 741 |
| `redundancy_scan.py` | 701 |
| `review.py` | 672 |
| `phase_9_vault_build.py` | 620 |
| `phase_3_structure.py` | 528 |
| `fence_indented.py` | 482 |

(Belег: `wc -l pipeline/*.py | sort -n`; `ls pipeline/*.py | wc -l` = 37. Kein Sub-Package mit `.py` unter `pipeline/`.)

### GT-2 CLI-Subcommands (`python -m pipeline --help`) — **23 Commands**
`build-vault`, `corpus-run`, `fence-indented`, `format-vault`, `frontmatter-audit`, `ingest`, `process`, `promote`, `redundancy-scan`, `regenerate-indices`, `reports`, `restructure`, `restructure-batch`, `review`, `review-ingest`, `run`, `status`, `synthesize-moc`, `taxonomy`, `vault-apply`, `vault-audit`, `vault-repair`, `vault-review`.

> Hinweis: Der installierte Console-Script `pkm` bricht beim Import ab (`ModuleNotFoundError: No module named 'mdformat'`, via `format_vault.py:37`). `python -m pipeline` lädt die volle Command-Liste fehlerfrei. Siehe §E.

### GT-3 Tests
- Gesamt: **721** `def test_` (Befehl: `rg "def test_" tests -c | awk -F: '{s+=$2} END{print s}'`).
- Soll ~760 → **Abweichung −39** (~5 % unter Richtwert). Alle Tests liegen unter `tests/` (51 Dateien); keine Tests außerhalb.
- Top-Dateien: `test_phase_4_segment.py` (60), `test_phase_8_synthesis.py` (54), `test_phase_3_structure.py` (46), `test_vault_audit.py` (44), `test_phase_9_vault_build.py` (41).

### GT-4 `FrontmatterDraft`-Felder (`pipeline/schemas.py`) — **24 Felder**
`title`, `slug`, `aliases`, `summary`, `type`, `doc_role`, `category`, `subcategory`, `tags`, `related`, `used_in`, `parent_concept`, `child_concepts`, `sources_docs`, `source_chunks`, `merged_from`, `status`, `review_status`, `confidence`, `doc_version`, `created`, `updated`, `last_synthesized`, `prompt_version`.
`type`/`status`/`review_status`/`confidence` werden per `field_validator` gegen `pipeline.taxonomy` (Runtime-Membership) geprüft; `category` bleibt bewusst ungeprüfter `str` (Catch-all → `17_unsortiert`).

### GT-5 Enums aktiv (`config/enums.yaml`)
- `type` (4): process-document, knowledge-article, compact-reference, gedanke
- `status` (4): draft, review, stable, deprecated
- `review_status` (3): ai_drafted, human_reviewed, verified
- `confidence` (3): low, medium, high
- `doc_role` (8): manual, how-to, best-practice, workflow, explanation, reference, cheatsheet, wiki

### GT-6 Taxonomie
- Tags: **149** (`rg -c "^\s*- " config/tag_vocabulary.yaml`; Kopf-Kommentar bestätigt „149 kanonische Tags in 17 Themenbereichen").
- Kategorien: **18** (`config/categories.yaml`: meta … 17_unsortiert).

### GT-7 Prompt-Versionen (`prompts/**.md`)
- v1: `stage1_cluster_analysis.md`, `stage2_merge_proposal.md`, `stage3_synthesis.md`, `stage4_frontmatter_gedanken.md`, `stage4_frontmatter_json.md` (+ `schemas/stage1_output.schema.json`)
- v2: `stage3_synthesis.md`, `stage4_frontmatter_json.md`, `MIGRATION.md`
- (aktive Veredelung = v2 stage3/stage4; v1-stage1/stage2 = deprecated Option-A-Cluster-Pfad, s. §E)

### GT-8 Lint/Type
- `ruff check pipeline/` → **All checks passed!**
- `mypy pipeline/` → **Success: no issues found in 37 source files** (nur Note: ungenutzte Section `hdbscan.*` in pyproject).

## C. NB-Verifikationstabelle

| ID | Klassifikation | Beleg (Datei:Zeile / „leer") | Notiz |
|----|----------------|------------------------------|-------|
| NB-1 | BESTÄTIGT ABWESEND | rg `duplicate.?paragraph\|doppelt.*absatz\|repeated.?block\|dedup.*paragraph` → 0 | Keine Doppel-Absatz-/Block-Heuristik. |
| NB-2 | BESTÄTIGT ABWESEND | 2 Treffer, beide nur als **Tag**: `config/tag_vocabulary.yaml:161`, `config/tag_merge_map.json:78` (`navigation`) | Vokabular-Tag ≠ Strip-Heuristik. Keine Navi-/Werbung-/Boilerplate-Entfernung im Code. |
| NB-3 | BESTÄTIGT ABWESEND | 4 Treffer, nur als **Tag** `ner`/`named-entity-recognition` (`config/tag_vocabulary.yaml:71,271`, `tag_merge_map.json:79,299`); pipeline-Treffer (`taxonomy.py:73,97`) = Substring in „Identität" (false positive) | Kein Entity-Extraktor. |
| NB-4 | BESTÄTIGT ABWESEND | engere Suche `key.?point\|kernaussage\|main.?claim\|takeaway\|\bthesis\b` ohne „synthesis" → 0 (alle 94 Roh-Treffer = Substring in „synthesis") | Keine Kernaussagen-Identifikation. |
| NB-5 | TEILWEISE | `prompts/v1/schemas/stage1_output.schema.json:5,32` + `stage1_cluster_analysis.md:63` führen Feld `contradictions`; Code-Refs `phase_8_synthesis.py:579` (stage1), `:616` (stage2, „deprecated — Option A") | Widerspruchs-Feld existiert **nur** im verworfenen Option-A-Cluster-Prompt; nicht auf Artikel-/Content-Ebene gewired, nicht im aktiven v2-Pfad. Abgrenzung: latent, inaktiv. |
| NB-6 | BESTÄTIGT ABWESEND | rg `missing.?context\|fehlend.*kontext\|context.?gap` → 0 | Keine Kontext-Lücken-Erkennung. |
| NB-7 | BESTÄTIGT ABWESEND | rg `content.?gap\|inhaltlich.*lück\|gap.?analys` → 0 (Frontmatter-Audit ausgenommen) | Keine **inhaltliche** Lückenanalyse; nur `frontmatter_audit.py` (Frontmatter-Felder, per Def. ausgeklammert). |
| NB-8 | BESTÄTIGT ABWESEND | rg `entities` in `schemas.py` + `enums.yaml` → 0 | Kein Feld „erkannte Entitäten". |
| NB-9 | BESTÄTIGT ABWESEND | rg `extract.?concept\|concept.?extract\|keyphrase` → 0 | Kein Konzept-Extraktor (Feld `child_concepts` existiert, aber Qwen-synthetisiert, kein Extraktor). |
| NB-10 | BESTÄTIGT ABWESEND | rg `open.?question\|offene.?frage` in `schemas.py`/`config` → 0 | Kein Feld „offene Fragen". |
| NB-11 | BESTÄTIGT ABWESEND | rg `next.?step\|weiterverarb\|follow.?up.?process` in `schemas.py` → 0 | Kein Feld „potenzielle Weiterverarbeitung". |
| NB-12 | BESTÄTIGT ABWESEND | 4 Treffer, nur Test-Fixtur-Text/Tag: `test_regenerate_indices.py:26,44,54` („veraltet" als Index-Body), `test_add_tag_governed.py:30` (Tag `veraltet: null`) | Keine Aktualitäts-/Staleness-Logik im Code. |
| NB-13 | BESTÄTIGT ABWESEND | rg `contradic\|conflict` in `redundancy_scan.py` → 0 | `RedundancyBand` = exact/near-dup/semantic-dup/thematic (`schemas.py`); **kein** Widerspruchs-Band. |
| NB-14 | BESTÄTIGT ABWESEND | rg `fragment\|rohmaterial\|stub.*content\|incomplete.?doc` → 0 | Keine Fragment-/Rohmaterial-Klassifikation. |
| NB-15 | BESTÄTIGT ABWESEND | rg `keyphrase\|key.?term\|central.?term\|begriffe.?extra` → 0 | Keine „zentrale Begriffe"-Extraktion (= NB-3/NB-9-Cluster). |

**Bilanz: 14 BESTÄTIGT ABWESEND · 1 TEILWEISE (NB-5) · 0 VORHANDEN(stale).**

## D. Korrekturbedarf an der Matrix

Nur Items mit Klassifikation ≠ BESTÄTIGT ABWESEND:

- **NB-5 → 🟡 (TEILWEISE)**: Matrix-Eintrag „Inhaltliche Widerspruchs-Markierung [NB]" präzisieren auf: *Feld `contradictions` existiert latent im **deprecated** Option-A-Stage-1-Prompt (`prompts/v1/`), ist aber im aktiven v2-Pfad nicht gewired und erzeugt keine Artikel-Markierung.* Empfehlung: Matrix von `[NB]` → `🟡 (latent/deprecated)` mit Hinweis auf Cluster-Verwurf (R9).

Die übrigen 14 NB-Behauptungen sind durch den Code-Stand **gedeckt** — keine Matrix-Korrektur nötig.

## E. Auffälligkeiten / Unsicherheiten

1. **`pkm`-Console-Script defekt im aktuellen venv**: `pkm --help` bricht mit `ModuleNotFoundError: No module named 'mdformat'` ab (Import-Kette `__main__ → ingest → phase_9_vault_build → format_vault.py:37`). `python -m pipeline` läuft fehlerfrei. Konsistent mit Memory „mdformat deferred (Wikilink-Schaden)" — `mdformat` ist nicht installiert, aber `format_vault.py` importiert es modulweit (Top-Level statt lazy). **Risiko:** jeder `pkm …`-Aufruf scheitert, solange `mdformat` fehlt; CLI nur via `python -m pipeline` nutzbar. Kein Blocker für diese Read-only-Task.
2. **Deprecated Stage-1/Stage-2 noch im Code**: `phase_8_synthesis.py:579/616/631` referenzieren `stage1_cluster_analysis.md` / `stage2_merge_proposal.md`; `:616` ist explizit als „deprecated — Option A" kommentiert. Funktionen + v1-Prompts existieren, gehören aber zum verworfenen Cross-Doc-Merge-Pfad (R9/R12). Toter/latenter Code — Aufräum-Kandidat (außerhalb Scope dieser Task).
3. **Test-Soll-Abweichung**: 721 statt ~760 (−39). Ursache nicht untersucht (Scope = Inventar, nicht Diff). Möglich: Richtwert stammt aus älterem Stand, oder Tests wurden konsolidiert. Architect sollte Richtwert ggf. auf 721 nachführen.
4. **NB-3/NB-15 Überlappung**: Beide zielen auf Begriffs-/Entity-Extraktion; beide abwesend. Falls Roadmap-Folge-Task gebaut wird, sind NB-3, NB-9, NB-15 ein gemeinsamer Funktionsblock („Term/Concept/Entity Extraction"), nicht drei separate.
