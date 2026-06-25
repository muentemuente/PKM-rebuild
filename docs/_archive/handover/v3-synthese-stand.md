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

---

# WP3b — Phase 0 (Count-Drift) + Phase A (Korpus-Filter) + Gate A

## Phase 0 — Count-Drift 187 vs 181 (geklärt)

| Korb | n | Inhalt |
|---|---|---|
| Live-Vault gesamt (`rglob`, ohne `_index`/`.body`) | **187** | alles |
| `_attic/` | 6 | aussortierte Dubletten (git-*, regex-*, ci-design, themenstraenge) — exakt die Near-Dups aus 3a |
| **Kanonisch (WP0-Stand)** | **181** | 187 − `_attic` (Content-Ordner 01–17 + `00_Meta`) |
| `00_Meta/` | 15 | Templates/Standards/Vokabular/System-Meta |
| **Synthese-Korpus (WP3b)** | **166** | 181 − `00_Meta` |

→ Kein Defekt: der 3a-Scan nutzte `rglob` über den **ganzen** Vault inkl. `_attic`.
Der kanonische Artikel-Count bleibt **181** (inkl. `00_Meta`, exkl. `_attic`). Der
**Synthese-Korpus** ist bewusst enger (166): Nicht-Wissensdokumente raus.

## Phase A — Korpus-Filter (config-getrieben)

`config.redundancy_scan.exclude_folders=["_attic","00_Meta"]` + `exclude_categories=["meta"]`
(kein Slug-Filter). Re-Scan: **166 Docs**, Schwellen unverändert (0.72 / 0.85 / 0.70 / ≥3).
Ergebnis: 0 exact · 0 near-dup · 1 semantic-dup · 39 thematic · **9 Kandidaten**
(`input_hash` im Report). Ausschlussliste steht im `redundancy_report.md` (Transparenz).

**Residual nicht filterbar:** Projekt-Dokus (`*-projektauftrag`, metadata-pipeline-*),
Tag-Sammlung, Quotes-Dump tragen `type: knowledge-article` + legitime Content-`category`
(automatisierung/grundlagen/wissensmodellierung) — per doc_type/category **nicht**
abgrenzbar; nur Slug/Titel verraten sie. Slug-Filter ist untersagt, Vault-Mutation (Re-Tag)
verboten (D6). Sie bleiben im Korpus, bilden aber genau die vom Owner **verworfenen**
Cluster (Junk/Projekt) → bekommen schlicht kein MOC.

## Gate A — Abgleich gefilterter Re-Scan ↔ Adjudikation

Cluster-IDs renumeriert (anderer Korpus) → Abgleich nach **Thema/Mitgliedern**:

| Adjudiziert (freigegeben) | Re-Scan | Status |
|---|---|---|
| Gestaltgesetze (hoch) | SC_001 (5 Docs, identisch) | ✅ bestätigt |
| API & Protokolle (hoch) | SC_002 (4 Docs) | ✅ bestätigt |
| Visuelle Kommunikation (hoch) | SC_003 (4 Docs) | ✅ bestätigt |
| NLP-Grundlagen (hoch) | SC_008 (3 Docs) | ✅ bestätigt |
| Arbeitsumgebung & Tools (niedrig) | SC_005 (3 Docs) | ✅ bestätigt |
| **Git (hoch)** | — | ⚠️ **zerfallen** — 3 von 4 Git-Docs lagen in `_attic` (Dubletten), nur `git-referenz` bleibt → keine Komponente ≥3 |
| SC_000/SC_001 (konditional) | SC_000 „Structure" (6 Docs, gemischt) | ➖ kein sauberer Sub-Cluster → bleibt verworfen |

**Verworfen (erwartungsgemäß noch sichtbar, kein MOC):** SC_004 (Junk: Architektur +
Kunst + Tag-Sammlung + Quotes), SC_006/SC_007 (Projekt-Dokus).

**Gate-A-Verdikt:** 5 von 6 freigegebenen Clustern **im Wesentlichen bestätigt** (gleiche
Themen + Mitglieder). **Eine freigegebene (Git, hoch) ist zerfallen** → der explizite
STOP-Trigger „freigegebene zerfallen" greift. Ursache ist allerdings benigne und
projektkonform (die Git-Redundanz war durch die `_attic`-Aussortierung **bereits gelöst** —
ein Git-MOC hätte überwiegend auf aussortierte Dubletten verlinkt).

**→ STOP an Gate A (Owner-Entscheidung).** Empfehlung: Phase B mit den **5 bestätigten**
Clustern (Gestaltgesetze, API, Visuelle Kommunikation, NLP, Arbeitsumgebung), Git droppen
(Begründung s. o.). Phase B braucht zusätzlich **laufendes LM Studio** (Qwen).
