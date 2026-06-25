---
title: PKM-rebuild Strategie
slug: 01-strategy
status: stable
created: 2026-05-25
updated: 2026-06-05
---

# Strategie — PKM-rebuild

Steuerungsdokument für Scope, Ziele, Risiken und Erfolgskriterien.

> **Legacy-Hinweis:** Erfolgskriterien, Phasen-Tabelle und `data/04_vault/`-Pfade in diesem Dokument beschreiben den verworfenen Vollkorpus-Erstlauf (Option A) unter `~/projects/aktiv/PKM_rebuild/data/`. Aktueller Flow = Option B (`pkm run`, Daten unter `~/projects/aktiv/pkm-pipeline/`), siehe `docs/RUNBOOK_new_files.md`.

---

## 1. Vision

Aus ~200 unstrukturierten Markdown-Dateien einen kuratierten, deduplizierten Obsidian-Vault mit konsistentem Frontmatter und stabiler Cluster-Struktur bauen. **Gleichzeitig** als Lernprojekt für Pipeline-Engineering, lokale LLM-Orchestrierung, Claude Code Integration und systematische Projekt-Dokumentation.

---

## 2. Scope

### In Scope
- Inventarisierung, Normalisierung, Segmentierung der bestehenden Markdown-Sammlung
- Redundanz-Erkennung in 3 Stufen (Hash → TF-IDF → Embeddings)
- LLM-gestützte Pro-Doc-Veredelung mit Qwen 3.6 27B lokal (Stage 3 + Stage 4 pro Doc)
- Vault-Aufbau mit Frontmatter, Tag-Vokabular, Cluster-Struktur, Wikilinks
- Vollständige Doku-Suite (11 Files) + Reflexions-Layer
- Backup-Strategie für den Vault (außerhalb Git)

### Out of Scope (1.0)
- Knowledge-Graph-Visualisierung über Obsidian-Native hinaus
- RAG-System auf dem Vault (ggf. später)
- Multi-User / Sync / Mobile
- Automatische Validierung von Tech-Inhalten gegen offizielle Docs
- Übersetzung DE↔EN
- Automatisierte Wiki-Veröffentlichung des Vaults
- Bulk-Promotion `draft → stable`
- Ausbau des Vaults mit weiterführenden und ergänzenden Themen
- Cross-Doc-Synthese / **automatisches** Merging mehrerer Docs (Option A — verworfen: Korpus hat keine inhärente Cluster-Struktur)

> **Scope-Notiz (2026-06-15, pipeline-v2 / R12):** P5 ist ein **Teil-Reversal von Option B**: paarweise Redundanz- und Synthese-**ERKENNUNG + Report** (`redundancy_report.md`, `synthesis_candidates.md`) sind ab pipeline-v2 **in Scope**. **Out of Scope bleibt** das automatische Merging/Löschen — `merged_from` bleibt leer, jeder Kandidat nur als gescorter, provenance-tragender Vorschlag. Die Erkennung ≠ das verworfene Auto-Clustering (das 96,5-%-Unsortiert-Finding entkräftet die Erkennung nicht). Referenz: `docs/Projektplan_pkm-pipeline-v2` D2, Risiko R12 (Scope-Creep-Kontrolle via Strategie-Doc-Update).

> **Scope-Update (2026-06-23, pipeline-v3 / D6 — additive Synthese):** Über die Erkennung hinaus ist ab v3 die **additive Synthese in Scope**: aus freigegebenen Kandidaten entstehen **NEUE** Übersichts-/MOC-Artikel (`doc_type: moc`/`synthesis`, `status: draft`, `review_status: ai_drafted`, `confidence` Pflicht), die **ausschließlich auf Quell-Artikel verlinken** (kein Inhalts-Merge). **Weiterhin Out of Scope:** Quell-Artikel verändern/löschen, `merged_from` befüllen, Auto-Promotion `draft→stable`. Dies ist ein **bewusst akzeptiertes, dokumentiertes Teil-Reversal von Option B** — es hebt die wissensorganisatorische Ebene (Audit Phase 4 R-A), ohne die Gründe anzutasten, aus denen Cross-Doc-Merge verworfen wurde (Halluzination R1, 50K-Hardware, Solo-Review). Referenz: `docs/Projektplan_pipeline-v3.md` D6, Risiko R12/RV13.

---

## 3. Definition of Done

Alle Kriterien müssen erfüllt sein:

### Primary
- [x] Brain-Vault enthält strukturierten Obsidian-Vault (181 Artikel, Live-Messung 2026-06-23)
- [x] Jede `.md` im Vault hat valides Frontmatter nach `docs/03_vault_standard.md` (0 Pydantic-Fails)
- [x] Keine SHA-256-Duplikate im Vault
- [x] `category` aus Qwen-Stage-4 + deterministischem Mapping auf 16 Vault-Ordner (kein Embedding-Cluster); `17_unsortiert/` als regulärer Catch-all-Cluster für schwache Zuordnungen
- [x] `merged_from` leer in allen Vault-Files (kein Cross-Doc-Merge, Option B)
- [x] Index-Files (`_index.md`) pro genutztem Vault-Ordner generiert (außer `00_Meta`)
- [ ] Alle Vault-Artikel mindestens auf Qualitätsstufe 2 — **offen: menschliche Qualitätsstufe-2-Review**

### Secondary
- [x] `corpus_report.md`, `duplicate_report.md`, `cluster_report.md` generiert (Vault-Ground-Truth)
- [x] Pipeline läuft idempotent (zweimaliger Lauf = identische Outputs)
- [x] `--sample`-Modus funktioniert (`corpus-run --sample N`)
- [x] Alle Qwen-Prompts in `prompts/v1/` (+ `v2/` restructure) versioniert + Git-getrackt
- [x] Pipeline-Tests (`pytest`) laufen grün (760)

### Documentation
- [x] Doku-Suite existiert, querverlinkt (Konsolidierungs-Pass 2026-06-25)
- [x] Pro Phase Reflexions-Doku in `docs/learnings/` (PHASE_00–12)
- [x] README mit funktionsfähigem Quick Start

### Backup
- [x] Time Machine aktiv für Korpus + Vault (täglich, Owner bestätigt 2026-06-25)
- [x] Vault-Snapshot via `make backup-vault` (Off-Volume); Time-Machine-Ziel extern
- [x] Korpus-Originale unverändert (Hard Constraint, read-only)

---

## 4. Stakeholder

| Rolle | Person | Aufgabe |
|---|---|---|
| Owner / Reviewer | muente | alle Entscheidungen, alle Reviews |
| AI-Werkzeug Coding | Claude Code | Pipeline-Code, Doku, Prompts |
| AI-Werkzeug Synthese | Qwen 3.6 27B | Pro-Doc-Veredelung (Stage 3 + Stage 4), kein Merge |

Keine externen Stakeholder.

---

## 5. Constraints

| Bereich | Wert |
|---|---|
| Hardware-RAM | 32 GB (während Qwen-Lauf: ~4 GB Rest für macOS — knapp) |
| Speicher | 1 TB SSD, ausreichend |
| Zeit | nicht harten Deadline, Phasen je 4–6h |
| Token-Budget Claude Pro | begrenzt pro 5h-Fenster + wöchentlich (siehe `docs/06_claude_code_workflow.md`) |
| Skill-Level | „interessierter Laie" — Komplexitätsgrad muss erklärbar bleiben |
| Sprache | DE für Inhalt, EN für Tech-Identifier |
| GitHub | Pipeline-Repo public, Daten + Vault außerhalb Git |

---

## 6. Annahmen

- Qwen 3.6 27B liefert mit 50K-Kontext stabile Outputs für deutsche Tech-Texte *(Annahme revidiert: 128K-Ziel nicht erreichbar auf 32 GB RAM — Hard Limit gemessen: `context_window: 49152`. Einfluss auf Batch-Größe + Token-Budget: `04_qwen_prompts.md` §2 + §9)*
- ~200 Korpus-Files sind klein genug für Embedding + TF-IDF in vertretbarer Zeit auf M5
- ~~Bottom-up Cluster-Bildung passt zur Korpus-Realität (≥3 Files pro Cluster)~~ *(Annahme revidiert — R9 realisiert: Korpus hat keine inhärente Cluster-Struktur, Embedding-/HDBSCAN-Clustering verworfen. `category` kommt aus Qwen-Stage-4 + deterministischem Mapping auf 16 Vault-Ordner, siehe `03_vault_standard.md` Category-Mapping-Appendix.)*
- Pipeline-Repo darf public werden (enthält keinen Korpus-Inhalt, Persona gitignored)
- macOS Memory-Pressure ist managebar durch App-Hygiene während Qwen-Läufen
- ~~`mpnet-base-v2` Embedding-Modell ist gut genug für deutsche Cluster~~ *(Annahme obsolet — Clustering verworfen; Embeddings dienen nur noch der Redundanz-Erkennung in Phase 5/6.)*

---

## 7. Risiken & Gegenmaßnahmen

| ID | Risiko | Wkt. | Impact | Gegenmaßnahme |
|---|---|---|---|---|
| R1 | Qwen halluziniert in Pro-Doc-Veredelung | hoch | mittel | `confidence`-Feld Pflicht + Review-Gate 3 (pro Doc) + Auto-Flag bei Validierungsfehler; kein Cross-Doc-Merge reduziert Halluzinations-Angriffsfläche, hebt Risiko aber nicht auf |
| R2 | macOS Memory-Pressure → Qwen-Crash | mittel | hoch | App-Hygiene-Protokoll, Memory-Monitoring, Recovery-Snapshot vor Stages |
| R3 | Token-Limit Claude Pro mitten in Session | hoch | mittel | Snapshot-Pattern + `claude --resume` (Details: doc 06) |
| R4 | Korpus enthält Binaries/Bilder die Pipeline crasht | mittel | mittel | Phase 0: Hardware- + Korpus-Inventar als Warm-up |
| R5 | Vault-Datenverlust (nicht in Git) | mittel | sehr hoch | Backup-Strategie (doc 07): Time Machine + 2. Medium |
| R6 | Verlust roter Faden / ADHS-Drift | mittel | mittel | Phasen ≤ 4–6h, Reflexionsdoku Pflicht, klare Stop-Punkte |
| R7 | Schema-Drift Pipeline ↔ Vault | mittel | hoch | Pydantic-Validation + Test-Cases gegen Vault-Standard |
| R8 | Embedding-Modell zu schwach für DE | niedrig | mittel | mpnet-base gewählt (multilingual stark); Fallback TF-IDF + manuelle Verifikation |
| R9 | Cluster-Inflation (viele Mikrocluster) | — | — | **Realisiert + aufgelöst:** Korpus hat keine inhärente Cluster-Struktur (0.85→0 echte Cluster, 0.65→Mega-Cluster). Embedding-/HDBSCAN-Clustering **verworfen**; `category` aus Qwen-Stage-4 + deterministischem Mapping auf 16 Vault-Ordner. |
| R10 | Korpus enthält private/sensible Notizen | niedrig | hoch | Daten + Outputs außerhalb Git, `.gitignore` strikt |
| R11 | Qwen-Output-Format-Drift über Sessions | mittel | mittel | Pydantic-Schema-Validation, JSON-Mode forcieren wo möglich |
| R12 | Scope-Creep durch „nur noch eine Sache" | hoch | mittel | Out-of-Scope-Liste verbindlich, Änderungen brauchen Strategie-Doc-Update |

---

## 8. Lernziele

Separat von Liefer-Zielen. Pro Lernziel ein Reflexions-Doku in `docs/learnings/`.

| Lernziel | Verknüpfte Phase |
|---|---|
| Software-Projektaufbau, Repo-Struktur | Phase 0 |
| GitHub-Workflow (Branches, PRs, Conventional Commits) | durchgehend |
| Claude Code im Editor produktiv nutzen | durchgehend |
| CLAUDE.md-Patterns verstehen und pflegen | Phase 0 + iterativ |
| Python-Pipeline-Engineering (Pydantic, Dataclasses, CLI, Logging) | Phasen 1–5 |
| Lokale LLMs orchestrieren (Qwen, Prompt-Stages, Validation) | Phase 8 |
| Personal Knowledge Management (Frontmatter, Cluster, Naming) | Phase 9 |
| Reflexions- und Doku-Disziplin | durchgehend |
| Token-Management (Claude Pro Limits) | durchgehend |

---

## 9. Phasen-Übersicht mit Zeit-Schätzung

Drei Szenarien pro Phase. **Realistic** ist Planungs-Basis.

| Phase | Best | Realistic | Worst | Output |
|---|---:|---:|---:|---|
| 0. Setup & Sicherung | 2h | 4h | 8h | Repo, Doku-Suite, Sicherung, Hardware-Test |
| 1. Inventar | 1h | 2h | 4h | `files_manifest.jsonl` |
| 2. Normalisierung | 1h | 2h | 4h | `cleaned_documents.jsonl` |
| 3. Strukturextraktion | 2h | 3h | 6h | `documents_structured.jsonl` |
| 4. Segmentierung | 1h | 2h | 4h | `segments.jsonl` |
| 5. Redundanz (Hash + TF-IDF) | 2h | 3h | 6h | `exact_duplicates.json`, `near_duplicate_edges.jsonl` |
| 6. Embeddings *(nur Redundanz)* | 2h | 4h | 8h | `embeddings.parquet` — Cluster-Prep **verworfen** (R9) |
| 7. LLM-Batch-Bildung | 2h | 3h | 6h | `batches/batch_NNN_<topic>.md` (Token-Budget-Splits, kein Cluster) |
| ~~7b. UMAP+HDBSCAN~~ | — | — | — | **verworfen** — kein inhärentes Clustering (R9) |
| 8. Qwen-Veredelung (Stage 3+4 pro Doc, Option B) | 6h | 14h | 28h | `data/03_drafts/CK_*.{md,body.md,frontmatter.json}` |
| 9. Vault-Aufbau | 4h | 8h | 16h | `data/04_vault/` |
| 10. Kontroll-Berichte | 1h | 2h | 4h | 3× `*_report.md` |
| 11. Cleanup | — | — | — | `_pkm_common`, Config-Prune, mypy-clean, Intermediates-Entscheidung |
| 12. Finalisierung | — | — | — | Workspace clean, `17_unsortiert`, `ingest`+`manage_vocab`, Docs Ist-Stand |
| **SUMME** | **27h** | **51h** | **100h+** | |

> **Laufender Betrieb (nach Erstlauf):** inkrementell über `pipeline ingest` (Inbox → Phasen 1–4 + 8, Option B) + `scripts/manage_vocab.py` (Vokabular-Pflege). Workflow: `docs/FUTURE_RUN.md`.

**Bei 4–6h-Sessions = ~9–13 Sessions Realistic**, über mehrere Wochen mit Reflexions-Puffern.

---

## 10. Erfolgs- und Abbruchkriterien

**Erfolg:**
- DoD vollständig erfüllt
- Vault wird produktiv genutzt (nicht in Schublade)
- Pipeline re-runnable bei späteren Korpus-Erweiterungen
- Lernziele dokumentiert in `docs/learnings/`

**Abbruch in Betracht ziehen, wenn:**
- Phase 8 (Qwen-Veredelung) liefert nach 3 Iterationen am gleichen Doc keine brauchbaren Drafts → Modell-Wechsel oder Prompt-Re-Design
- Hardware-Setup instabil (häufige Crashes, Memory unlösbar) → Cloud-LLM evaluieren (Claude API als Fallback)
- Lernzielfortschritt deutlich unter Erwartung → Scope reduzieren, nicht Qualität

---

## 11. Aktualisierungs-Routine

Dieses Doc wird gepflegt bei:
- Scope-Änderungen (in/out)
- Neu erkannten Risiken
- DoD-Verfeinerungen
- Projekt-Retro (Phasenende, Projektende)

---

## Änderungs-Log

- 2026-05-25 — Initial-Version
- 2026-05-29 — Option-B-Anpassung: In-Scope Phase 8 auf Stage 3+4 pro Doc; Out-of-Scope Cross-Doc-Synthese ergänzt; DoD Cluster-Kriterium entschärft + merged_from-Kriterium neu; Annahme Kontext-Window 128K→50K korrigiert; R1 Gegenmaßnahme auf Pro-Doc-Kontext; Phase-8-Zeitschätzung angepasst; Abbruchkriterium Cluster→Doc
- 2026-06-04 — Clustering-Verwurf (R9 realisiert + aufgelöst): Embedding-/HDBSCAN-Clustering verworfen, `category` aus Qwen-Stage-4 + deterministischem Mapping auf 16 Vault-Ordner; Annahmen §6 (bottom-up, mpnet-Cluster) revidiert; Stakeholder-Tabelle + DoD + Phasen-Tabelle (6/7/7b) auf Ist-Stand; Phase 8 abgeschlossen
- 2026-06-05 — Phase 12: DoD auf Ist-Stand (Primary erfüllt außer menschl. Qualitätsstufe-2); `17_unsortiert` als regulärer Cluster; Phasen-Tabelle um 11/12 + inkrementellen Betrieb (`ingest`/`manage_vocab`)
- 2026-06-23 — pipeline-v3: D6 additive Synthese als dokumentiertes Teil-Reversal Option B (Scope-Update §2); Artikel-Count 180→181 (Live-Messung); DoD-Pfad auf Brain-Vault
- 2026-06-25 — DoD auf Ist-Stand (Secondary/Documentation/Backup erfüllt; offen nur Qualitätsstufe-2-Review); Legacy-Pfad in Secondary entfernt
