# CLAUDE.md — PKM-rebuild Root

Dieses Dokument ist der primäre Projekt-Kontext für Claude Code. Es wird zu Beginn jeder Session gelesen.

---

## 1. Projekt-Kontext

PKM-rebuild ist eine Pipeline und ein Workflow zur Bereinigung einer bestehenden Markdown-Wissenssammlung (~200 Dateien). Das Ergebnis ist ein strukturierter Obsidian-Vault mit konsistentem Frontmatter, ohne Redundanzen, in einer kuratierten 16-Ordner-Struktur.

**Aktueller Stand (2026-06-25):** Basis-Pipeline (Phasen 0–12, **Option B** — Pro-Doc, kein Cross-Doc-Merge) **abgeschlossen** → **181 Vault-Artikel + 5 MOC** (Live-Messung) im Brain-Vault. Embedding-Clustering wurde verworfen (Korpus ohne inhärente Cluster-Struktur). **v3-Zyklus: WP0–WP4 abgeschlossen + gemergt** (WP2 entfiel; Stabilisierung, additive Synthese/MOC, Bestands-Remediation); Vault idempotent. Plan: `docs/Projektplan_pipeline-v3.md`, aktueller Detailstand: `docs/handover/post-wp4-stand.md` + `docs/PROJECT_STATUS.md`.

Vollständiger Kontext: `README.md`, `docs/01_strategy.md`.

---

## 2. Pflicht-Lektüre vor jedem Task

Diese Dokumente werden in dieser Reihenfolge gelesen:

0. `docs/PROJECT_STATUS.md` + jüngstes `docs/handover/`-Stand-Doc — **aktueller Stand** (zuerst zur Orientierung)
1. `docs/00_persona_muente.md` — Persona, Setup, Arbeitsweise (**immer zuerst** vor inhaltlicher Arbeit)
2. `docs/01_strategy.md` — Projektziele, Scope, Definition of Done
3. Task-spezifisch:
   - Pipeline-Code → `docs/02_pipeline_spec.md` + `pipeline/CLAUDE.md`
   - Vault / Frontmatter → `docs/03_vault_standard.md`
   - Qwen-Prompts → `docs/04_qwen_prompts.md` + `prompts/CLAUDE.md`
   - Claude-Code-Workflow → `docs/06_claude_code_workflow.md`
   - Tool-Routing → `docs/06b_tool_routing.md`

---

## 3. Kommunikations-Stil

Der Kommunikations-Stil in diesem Projekt folgt der Persona-Definition (`docs/00_persona_muente.md` Sektionen 9–10). Kurzfassung:

- Antworten sind kompakt — Listen und Tabellen statt Fließtext
- Keine Einleitungen, Zusammenfassungen oder Floskeln
- Empfehlungen werden begründet
- Bei Unsicherheit wird gefragt, nicht geraten
- Sprache: Inhalt Deutsch, Tech-Begriffe und Code-Identifier Englisch, Code-Kommentare Deutsch
- Lob ohne Substanz hat keinen Platz

---

## 4. Working Conventions

### 4.1 Vor Code-Tasks

Relevante Doku wird gelesen, bevor Code geschrieben wird. Bei Unsicherheit zu Strategie oder Scope wird gefragt, statt geraten. Bestehende Konventionen (Naming, Frontmatter, IDs, Cluster) werden geprüft.

### 4.2 Code-Konventionen

Das Projekt nutzt Python 3.12 mit Type-Hints. Schema-Validation läuft über Pydantic v2, interne Records über Dataclasses. Logging ist strukturiert über `structlog` (JSON) und `rich` (Konsole). CLI-Argumente werden via `click` oder `argparse` definiert. Konfigurations-Werte leben in `pipeline/pipeline.config.yaml`, nicht im Code.

Re-Runs sind idempotent: Outputs werden übersprungen, wenn der Input-Hash unverändert ist. Mit `--force` wird der Cache ignoriert.

Details: `pipeline/CLAUDE.md`.

### 4.3 Doku-Konventionen

Markdown-Doku hat ein Frontmatter mit mindestens `title`, `slug`, `status`, `created`, `updated`. Naming folgt `docs/03_vault_standard.md`. Der Schreibstil entspricht der Persona-Definition.

### 4.4 Commit-Konventionen

Commits folgen Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`. Eine logische Änderung pro Commit. Vor `gh pr create` werden `git status` und `git diff --stat` gezeigt.

---

## 5. Hard Constraints (unveränderbar)

Diese Regeln sind nicht-verhandelbar und gelten für jede Session, jeden Task, jeden Output. Sie schützen Datenintegrität, Datenschutz und Idempotenz.

- **Korpus-Originale in `data/01_corpus_input/` sind read-only.** Sie werden nicht verändert, nicht überschrieben, nicht gelöscht.
- **Vault-Files (`data/04_vault/`) erreichen den Status `stable` nur nach explizitem menschlichem Review.** Keine Auto-Promotion `draft → stable`.
- **Qwen-Outputs werden nicht ungeprüft als Wahrheit übernommen.** Das `confidence`-Feld wird bei jedem synthetisierten Artikel gesetzt.
- **Inhalte aus `docs/00_persona_muente.md` und `data/` werden nicht in Code, Commits oder public Outputs übernommen.**
- **`git push` erfolgt nur nach explizitem User-OK.** Auch kleine Änderungen werden nicht ohne Bestätigung gepusht.
- **Operationen, die Token-Limits überschreiten würden, werden vorher angekündigt** — keine stillen Multi-Step-Tasks, die Budgets verbrennen.

---

## 6. Datenmodell (Kurzreferenz)

Vollständig in `docs/03_vault_standard.md`. Übersicht:

| Element | Format | Beispiel |
|---|---|---|
| Korpus-Datei-ID | `D_<slug>` | `D_yaml-frontmatter` |
| Segment-ID | `<doc_id>-S<index:04d>` | `D_yaml-frontmatter-S0003` |
| Concept-ID (Vault-Artikel) | `CK_<slug>` | `CK_yaml-frontmatter` |
| Type (4 Werte) | `process-document \| knowledge-article \| compact-reference \| gedanke` | `knowledge-article` |
| Status | `draft → review → stable → deprecated` | `review` |
| Review-Status | `ai_drafted → human_reviewed → verified` | `ai_drafted` |
| Confidence (Qwen) | `low | medium | high` | `medium` |

---

## 7. Pipeline-Phasen (Kurzreferenz)

Vollständig in `docs/02_pipeline_spec.md`.

```
0. Setup & Sicherung
1. Inventar
2. Normalisierung
3. Strukturextraktion
4. Segmentierung
5. Redundanz-Erkennung (Hash + TF-IDF)
6. Embeddings (mpnet-base) — nur Redundanz; Cluster-Prep VERWORFEN (R9)
7. LLM-Batch-Bildung (Token-Budget-Splits, kein Cluster)   [7b UMAP+HDBSCAN verworfen]
8. Qwen-Veredelung (Option B): Routing passthrough | stage3 | gedanken, dann Stage 4
9. Vault-Aufbau (16 Ordner; category aus Stage 4 + deterministischem Mapping)
10. Kontroll-Berichte
```

Review-Gates (Option B): nach Phase 7 (Batch-/Triage-Karte) und nach dem Synthese-Draft pro Doc (Phase 8). **Gate 2 (Merge-Vorschläge) entfällt** — kein Cross-Doc-Merge.

---

## 8. Phasen-Disziplin (ADHS-Schutz)

Arbeits-Sessions in diesem Projekt sind auf 4–6h pro Phase ausgelegt. Jede Phase schließt mit einem Reflexionsdokument in `docs/learnings/PHASE_<NN>_<slug>.md` ab.

Bei drohendem Token-Limit wird die Session sauber beendet, ein Snapshot in `.claude-context-snapshot.md` abgelegt, und später mit `claude --resume` aufgenommen. Details: `docs/06_claude_code_workflow.md`.

Während Qwen-Läufen werden andere Apps geschlossen (Memory-Pressure, siehe Persona Sektion 6).

### Kontext-Hygiene (verbindlich)

Session-Kontextgröße in Editor UND Chat aktiv überwachen. Vor jedem WP-/Task-Wechsel oder bei Token-Warnung: Stand in ein committetes Handover-Doc (`docs/handover/`) destillieren (Stand, offene Schritte, Learnings), DANN erst `/clear` bzw. neue Session, Resume mit Projektplan + `WAYFINDING.md` + jüngstem Handover. Commits/Reports bewahren das Ergebnis, nicht den Entscheidungs-Thread. Keinen WP-Wechsel in überladener Session beginnen (Regel-Drift, RV6).

---

## 9. File-Layout

```
PKM-rebuild/                    ← Git, public
├── README.md
├── CLAUDE.md                   ← HIER
├── config/                     ← categories/tag_vocabulary/enums.yaml (Taxonomie-SSoT)
├── docs/                       ← Projekt-Doku
├── pipeline/                   ← Code + sub-CLAUDE.md
├── prompts/                    ← Qwen-Prompts versioniert + sub-CLAUDE.md
└── .gitignore

~/projects/aktiv/pkm-pipeline/        ← go-forward-Daten, außerhalb Git (PKM_PIPELINE_ROOT)
├── input/                      ← neue .md (Run-Quelle)
├── work/                       ← Zwischen-JSONL, state.json, Reports (redundancy_*.md)
├── drafts/                     ← Qwen-Outputs
├── review/                     ← Gate-Queues
├── output/                     ← gebauter Staging-Vault
└── archive/                    ← verarbeitete Inputs + Backups + Snapshots
```

**Kanonischer Produktiv-Vault (#3, außerhalb Git):** `~/Zentrale/09_Brain-Vault`
(`pipeline._paths.BRAIN_VAULT`, überschreibbar per `PKM_BRAIN_VAULT`). Dort liegen
die 181 finalen Artikel (Live-Messung 2026-06-23); `pkm redundancy-scan` (WP2) und der manuelle Asset-Merge
(WP3) zeigen standardmäßig hierhin. Das Legacy-Layout `~/projects/aktiv/PKM_rebuild/data/0X`
(Option A, inkl. `04_vault/`) ist verworfen und existiert nicht mehr.

---

## 10. Eskalation bei Unsicherheit

Reihenfolge:

1. Relevante Doku lesen
2. `docs/00_persona_muente.md` Sektion 10 (Verhaltensregeln) prüfen
3. User fragen — kompakt, mit konkreten Optionen wenn möglich

Raten, mocken oder „so wird's schon passen"-Code sind keine Optionen.

---

## 11. Quick-Reference Befehle

```bash
# go-forward (Option B) — produktiv: input/ → output/ (docs/RUNBOOK_new_files.md)
python -m pipeline run                   # input/ → (Review-Gates) → output/ (resume-fähig)
python -m pipeline review                # review/decisions.md erzeugen
python -m pipeline review --apply        # ausgefüllte decisions.md anwenden (Gates A–D)
make run | review | review-apply | publish-check

# Legacy-Erstlauf (Archiv, Phasen 1-10, inkl. Embedding/Batch — verworfen)
python -m pipeline corpus-run --sample 10
python -m pipeline status                # Statusbericht

# Qualität
pytest                                   # Tests
ruff check . && ruff format .            # Lint + Format
mypy pipeline/                           # Type-Check
```

---

## 12. Shell-Commands

Der Claude-Code-Security-Wrapper wirft bei einer Tilde (`~`) im Value einer Bash-Variablen-Zuweisung und blockiert damit die autonome Ausführung. In Assignments steht deshalb `$HOME` statt `~`.

```bash
# nicht ok — Tilde im assignment value blockiert den Wrapper
DATA=~/projects/aktiv/PKM_rebuild/data
BAK=~/projects/aktiv/PKM_rebuild/backups/cleanup_$(date +%Y%m%d_%H%M)

# ok — $HOME im assignment value
DATA=$HOME/projects/aktiv/PKM_rebuild/data
BAK=$HOME/projects/aktiv/PKM_rebuild/backups/cleanup_$(date +%Y%m%d_%H%M)
```

Die Tilde außerhalb von Assignments (etwa als Command-Argument, `ls ~/foo`) ist unproblematisch; betroffen ist allein die Form `VAR=~/...`.

---

## Änderungs-Log

- 2026-05-25 — Initial-Version (faktisch-deklarativ, Hard Constraints abgegrenzt)
- 2026-05-28 — Sektion 2: tool-routing ergänzt; Sektion 11: CLI an Realität angepasst (--confirm/validate entfernt, --phase 8/--dry-run ergänzt)
- 2026-06-02 — Sektion 12 ergänzt: $HOME statt ~ in Bash-Assignments (Security-Wrapper)
- 2026-06-04 — Ist-Stand: Phase 8 abgeschlossen (Option B), Phase 9 next; §1 Stand-Block; §6 type-Enum (4 Werte, gedanke); §7 Phasen + Review-Gates auf Option B + Clustering-Verwurf
- 2026-06-07 — §11 Quick-Reference auf go-forward (`pkm run`/`review`, Gates A–D, Legacy `corpus-run`); Pipeline-Umbau zur Inkrement-Pipeline (Branch `rebuild-pipeline-*`, `_paths.py`, `config/`, `run_flow`/`review`/`orchestrator`)
- 2026-06-23 — §1 Stand-Block auf v3: Basis-Pipeline abgeschlossen, **181 Vault-Artikel** (Live), aktiver Zyklus v3; Artikel-Count 180/~186→181 vereinheitlicht (WP0)
- 2026-06-25 — §1 Stand-Block auf Post-WP4 (WP0–WP4 gemergt, 181 + 5 MOC, idempotent); §2 Pflicht-Lektüre um Stand-Orientierung (PROJECT_STATUS + jüngstes Handover) ergänzt; Detailstand-Pointer auf `post-wp4-stand.md`
- 2026-06-26 — Q1b: neuer read-only Quality-Score-Layer (`pkm quality-score`, `pipeline/quality_score.py`) — zwei Achsen (Readiness D1–D4 = Band ⊥ Integrations-Index D5/D6 = Tertil), deterministisch, kein LLM/Vault-Write; Config-Sektion `quality_score`; Spec §4. Engine-Reuse, keine `schemas.py`-Änderung
- 2026-07-01 — Tier-1-Sweep (H2/H1/O1/R1/T1): H2 CLI-Import-Regressiontest (lazy `mdformat` bereits gefixt); H1 toten Cluster-Merge-Pfad entfernt (stage1/2-Prompts+Schemas+`_run_stage1/2`, R9 — NB-5 jetzt bestätigt abwesend); R1 neuer read-only Report `pkm vault-health` (`pipeline/vault_health.py`, aggregiert quality-score-JSONL-Historie, Spec §4); O1 Keyphrase-Backend-Konsolidierung **verworfen** (Ø Jaccard 0.036 ≪ 0.6, all-mpnet vs. paraphrase-multilingual); T1 Test-Richtwert → 789. Test-Suite 789 (`def test_`) / 826 passed
- 2026-07-01 — H3 Stage-3 Reasoning-Loop-Hardening: Verify-first — `max_tokens`-Cap je Stage-3-Call existierte bereits (`max_tokens_stage3`, config-driven), Lücke war das stille Übernehmen abgeschnittener Outputs. Fix: `_run_text_stage` gibt `(body, truncated)`; bei `finish_reason=length` → `needs_human` (reason `output_truncated`) + kein Draft statt truncated Body. `restructure`-Caller angepasst. +2 synthetische Tests (Truncation→needs_human, normaler Call unbeeinträchtigt). Kein `schemas.py`-/Vault-Write. Test-Suite 828 passed / 2 skipped
