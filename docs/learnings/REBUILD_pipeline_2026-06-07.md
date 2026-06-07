---
title: Architektur-Umbau — Inkrement-Pipeline (go-forward)
slug: rebuild-pipeline-2026-06-07
status: stable
created: 2026-06-07
updated: 2026-06-07
---

# Architektur-Umbau: vom Korpus-Erstlauf zur Inkrement-Pipeline

Umbau des Erstlauf-Codes zu einer schlanken, wiederholbaren go-forward-Pipeline
(`TASK_build_pipeline.md`). Branch `rebuild-pipeline-20260606_224320`, WP0–WP6.

## Ausgangslage (Befund WP0)
- Live-Vault (`04_vault`) war **leer** — der finalisierte Vault war bereits in den
  produktiven Obsidian-Vault gezogen und nur als Tarball gesichert. WP1 startete
  `output/` deshalb **leer** (Entscheidung muente), statt 179 Artikel zu migrieren.
- 12 Standalone-Skripte hatten je eine eigene `DATA_ROOT`-Konstante (Drift-Risiko).
- Layout war `PKM_rebuild/data/{01_corpus_input,02_pipeline_output,03_drafts,04_vault}`.

## Was sich geändert hat
| Thema | Vorher | Nachher |
|---|---|---|
| Layout | `PKM_rebuild/data/0X_*` | `pkm-pipeline/{input,work,drafts,review,output,archive}` |
| Pfade | je Skript hardcodiert | zentral `pipeline/_paths.py` (ENV-überschreibbar) |
| Vokabular/Kategorien | im Code + Vault-md verstreut | `config/{categories,tag_vocabulary}.yaml` + `tag_merge_map.json` |
| Flow | Phasen 1–10 (inkl. Embedding/Batch) | `run_flow.py`: 1–3 + Token-Cap-Segmentierung + Qwen; **kein 5/6/7** |
| Review | ad-hoc (Zed + git diff) | file-basierte Gates A–D (`review/decisions.{jsonl,md}`) |
| Orchestrierung | `pipeline run` (Phasen) | `pkm run` = input→Gates→output, State-Maschine, resume-fähig |

## Entscheidungen mit Begründung
- **YAML als Single Source für Tags:** die alte `tag-system.md` nutzte `## Vokabular`,
  die Parser suchten `## Kern-Vokabular` → lieferten leer. `config/tag_vocabulary.yaml`
  ist jetzt kanonisch; md-Parser bleiben als Eingabe-Fallback (Bestands-Fixtures grün).
- **categories.yaml + CATEGORY_TO_FOLDER doppelt geführt:** Gate B aktualisiert beide
  (Drift-Guard-Test `test_config.py`); der Code bleibt Laufzeit-Authority, das YAML die
  dokumentierte Quelle. Vermeidet einen riskanten Umbau von `manage_vocab`/`phase_9`.
- **Gate D immer erzeugt:** A/B/C werden beim Apply VOR D angewandt (Gate-Reihenfolge),
  damit ein einziger Review-Zyklus genügt (statt zwei bei Docs mit offenem A/B/C).
- **`run` repurposed, Legacy → `corpus-run`:** `pkm run` ist der go-forward-Orchestrator;
  der Gesamtkorpus-Erstlauf bleibt als `corpus-run` erreichbar (Archiv/Altlauf).
- **Korpus read-only erhalten:** beim Verschieben wurde der gesamte `data/`-Ordner
  (schreibbar) als Einheit nach `archive/corpus_legacy/` umbenannt — der `0555`-Korpus
  darin blieb unangetastet (kein chmod, keine Inhaltsänderung).

## Token-Cap-Segmentierung
`phase_4` bekam einen `token_cap_words`-Modus: unter dem Cap (≈ Context-Window minus
Stage-3-Budget, in Wörtern) bleibt ein Doc **1 Segment**; darüber greift der klassische
Heading-Split. Default `None` = unverändertes Erstlauf-Verhalten.

## Verworfen (Alt-Code bleibt, nicht im go-forward)
Embedding (Phase 6), LLM-Batch-Bildung (Phase 7), korpus-interne Redundanz (Phase 5).
Embedding-Clustering war schon vorher verworfen (R9). Code bleibt für `corpus-run`.

## Offene Punkte
- `pkm` Console-Script wirkt erst nach `pip install -e .`; bis dahin `python -m pipeline`.
- `manage_vocab add-tag` schreibt nur md; YAML-Tag-Aufnahme läuft über Gate C.

## Test-Stand
425 → Tests grün (neu: `test_run_flow`, `test_review`, `test_orchestrator` inkl.
End-to-End-Smoke), ruff + format + mypy clean.
