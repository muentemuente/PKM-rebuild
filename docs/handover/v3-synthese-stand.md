---
title: v3 — Synthese-Detection: Realstand + Wiederverwendung
slug: v3-synthese-stand
status: review
created: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: TASK_wp3a_synthese-detection.md (Phase A)
---

# Synthese-Detection — Stand & Wiederverwendung (D2)

**Befund:** Die Detection ist **bereits vollständig gebaut** (WP2, `pipeline/redundancy_scan.py`).
WP3a war damit überwiegend *Verifikation + Report-Erzeugung*, kein Neubau (Auftrag:
„Wiederverwenden vor Neubau").

---

## 1. Was schon da ist (wiederverwendet)

| Aspekt | Realstand | Quelle |
|---|---|---|
| **Verfahren** | Hash (exakt) + TF-IDF (lexikalisch) + paarweise Embedding-Cosine (semantisch), alles in-memory (numpy/sklearn), **kein Vector-DB** (D2) | `redundancy_scan.py` |
| **Embedding-Quelle** | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`, lokal gecached (`~/.cache/huggingface`), Device-Resolution reused aus `phase_6_embeddings._resolve_device` (MPS). Keine persistente Embedding-Datei — pro Lauf in-memory berechnet | `embed_similarity()` |
| **Schwellen** | Config-Block `redundancy_scan` (nicht hartkodiert): `tfidf_threshold=0.72`, `embedding_dup_threshold=0.85`, `embedding_thematic_low=0.70`, `synthesis_min_members=3` — am realen Vault gesweept (2026-06-16) + in REVIEW-Gate 2 bestätigt | `pipeline.config.yaml` |
| **Reproduzierbarkeit** | `input_hash` aus sortierten Body-Hashes; kein Wall-Clock im Report-Body → gleicher Input ⇒ byte-identischer Report (Test `test_write_reports_byte_identical_second_run`) | `run_redundancy_scan()` |
| **Read-only** | `load_vault_docs` öffnet nur lesend; `write_reports` schreibt ausschließlich ins `--output-dir`. `merged_from` wird **nie** befüllt, kein Merge, kein Löschen | by construction + Tests |
| **CLI** | `pkm redundancy-scan [--vault-dir] [--output-dir] [--no-embeddings] [--qwen]` | `__main__.py` |
| **Tests** | `tests/test_redundancy_scan.py` (Band-Klassifikation, Komponenten, Provenance, Idempotenz, Qwen-Parser) | — |

## 2. Klassen-Abdeckung (Task verlangt 5)

| # | Task-Klasse | Implementiertes Band | Status |
|---|---|---|---|
| 1 | exakte Dublette | `exact` (SHA-256 normalisierter Body) | ✓ |
| 2 | Near-Duplicate | `near-dup` (TF-IDF ≥ 0.72) | ✓ |
| 3 | semantisch ähnlich | `semantic-dup` (emb ≥ 0.85 bei niedriger Lexik) | ✓ |
| 4 | thematische Teilüberschneidung | `thematic` (emb ∈ [0.70, 0.85)) | ✓ |
| 5 | Synthese-Kandidat (≥3 verwandt) | Union-Find-Komponenten der thematischen Kanten, ≥ `synthesis_min_members` | ✓ |

## 3. Lücke → in WP3a ergänzt

Einzige Abweichung ggü. Task-Phase-C: ein **vorgeschlagener MOC-Titel** pro Kandidat fehlte.
Ergänzt als **reine deterministische Renderer-Heuristik** `suggest_moc_title()` (kein Schema-Feld,
kein LLM, kein Spec-Pflicht-Update): geteilte, nicht-generische Slug-Tokens nach Häufigkeit.
Der *echte* MOC-Titel entsteht erst in 3b (LLM, HITL). Markiert als „nur Vorschlag".

## 4. Lauf-Ergebnis (Live-Vault, 2026-06-24)

`pkm redundancy-scan --output-dir docs/reports` (Embeddings an, Qwen aus → deterministisch,
kein Endpoint), `input_hash: 3838696a9cfb358c`:

| Band | Paare |
|---|---|
| exact | 0 |
| near-dup | 3 |
| semantic-dup | 3 |
| thematic | 52 |
| **Synthese-Kandidaten (≥3)** | **10** |

Reports: `docs/reports/redundancy_report.md` · `docs/reports/synthesis_candidates.md`
(außerhalb des Vault, im Repo).

> [!note] **Denominator 187 ≠ 181:** Der Scan erfasst per `rglob("*.md")` **alle** Vault-`.md`
> (ohne `_index.md`/`.body.md`), also auch Meta-/Template-Dateien — daher 187 statt der 181
> kuratierten Artikel (WP0-Zählstand). Kein Defekt, nur ein breiterer Zähl-Korb; für die
> Detection unschädlich (mehr Vergleichsbasis).

## 5. Offen / Gate

**STOP — Review-Gate 3a:** Owner prüft die 10 Kandidaten an einer Stichprobe (Cluster
plausibel? Schwellen zu eng/weit?). Erst nach Freigabe (+ ggf. Schwellen-Anpassung in
`config`) folgt 3b (additive MOC-Generierung). Kein 3b in diesem Task.
