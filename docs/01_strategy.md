---
title: PKM-rebuild Strategie
slug: 01-strategy
status: stable
created: 2026-05-25
updated: 2026-05-29
---

# Strategie — PKM-rebuild

Steuerungsdokument für Scope, Ziele, Risiken und Erfolgskriterien.

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
- Cross-Doc-Synthese / automatisches Merging mehrerer Docs (Option A — verworfen: Korpus hat keine inhärente Cluster-Struktur)

---

## 3. Definition of Done

Alle Kriterien müssen erfüllt sein:

### Primary
- [ ] `~/projects/aktiv/PKM_rebuild/data/04_vault/` enthält strukturierten Obsidian-Vault
- [ ] Jede `.md` im Vault hat valides Frontmatter nach `docs/03_vault_standard.md`
- [ ] Keine SHA-256-Duplikate im Vault
- [ ] Cluster als Ablage-Heuristik für Vault-Ordner; Mikrocluster und `unsortiert/` erlaubt (bottom-up Pflicht entfällt)
- [ ] `merged_from` leer in allen Vault-Files (kein Cross-Doc-Merge, Option B)
- [ ] Cluster-Index-Files (`_index.md`) pro genutztem Cluster generiert
- [ ] Alle Vault-Artikel mindestens auf Qualitätsstufe 2 (Strukturierter Artikel)

### Secondary
- [ ] `corpus_report.md`, `duplicate_report.md`, `cluster_report.md` in `data/02_pipeline_output/`
- [ ] Pipeline läuft idempotent (zweimaliger Lauf = identische Outputs)
- [ ] `--sample 10` Modus funktioniert
- [ ] Alle Qwen-Prompts in `prompts/v1/` versioniert + Git-getrackt
- [ ] Pipeline-Tests (`pytest`) laufen grün

### Documentation
- [ ] Alle 11 Doku-Dateien existieren, aktuell, querverlinkt
- [ ] Pro Phase Reflexions-Doku in `docs/learnings/`
- [ ] README mit funktionsfähigem Quick Start

### Backup
- [ ] Time Machine aktiv für Korpus + Vault
- [ ] Vault-Snapshot auf zweitem Medium (externe SSD oder Cloud)
- [ ] Korpus-Originale unverändert gegenüber Pre-Pipeline-Snapshot

---

## 4. Stakeholder

| Rolle | Person | Aufgabe |
|---|---|---|
| Owner / Reviewer | muente | alle Entscheidungen, alle Reviews |
| AI-Werkzeug Coding | Claude Code | Pipeline-Code, Doku, Prompts |
| AI-Werkzeug Synthese | Qwen 3.6 27B | Cluster-Analyse, Merge, Synthese |

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
- Bottom-up Cluster-Bildung passt zur Korpus-Realität (≥3 Files pro Cluster)
- Pipeline-Repo darf public werden (enthält keinen Korpus-Inhalt, Persona gitignored)
- macOS Memory-Pressure ist managebar durch App-Hygiene während Qwen-Läufen
- `mpnet-base-v2` Embedding-Modell ist gut genug für deutsche Cluster

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
| R9 | Cluster-Inflation (viele Mikrocluster) | mittel | niedrig | Bottom-up-Regel ≥3 Artikel; Mikrocluster → `unsortiert/` |
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
| 6. Embeddings + Cluster-Prep | 2h | 4h | 8h | `embeddings.parquet`, Cluster-Vorschläge |
| 7. LLM-Batch-Bildung | 2h | 3h | 6h | `batches/batch_NNN_<topic>.md` |
| 7b. UMAP+HDBSCAN *(optional)* | 1h | 2h | 4h | Cluster-Visualisierung |
| 8. Qwen-Veredelung (Stage 3+4 pro Doc) | 6h | 14h | 28h | `data/03_drafts/CK_*.md` |
| 9. Vault-Aufbau | 4h | 8h | 16h | `data/04_vault/` |
| 10. Kontroll-Berichte | 1h | 2h | 4h | 3× `*_report.md` |
| **SUMME** | **27h** | **51h** | **100h+** | |

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
