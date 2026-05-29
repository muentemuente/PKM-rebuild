---
title: Roadmap Option B (Pro-Doc-Veredelung) + CC-Übergabe
slug: 0L-roadmap-option-b-cc-handover
status: stable
created: 2026-05-29
updated: 2026-05-29
---

# Roadmap Option B — Pro-Doc-Veredelung + CC-Autonomie-Setup

**Strategie-Entscheidung Block 0.L getroffen:** Option B (Pro-Doc-Veredelung).
Begründung: Korpus hat keine inhärente Cluster-Struktur (96.5 % aller Segment-Paare < 0.6 Similarity, HDBSCAN findet dieselbe Mega-Masse). Cross-Doc-Synthese wird verworfen. Jedes Doc wird 1:1 veredelt, kein automatischer Merge.

**Ziel dieses Dokuments:** maximale, sichere Autonomie für Claude Code (CC) + lückenlose Übergabe, damit CC ohne ständige App-Rückfragen durcharbeiten kann.

---

## 1. Strategische Festlegung Option B (verbindlich)

| Punkt | Festlegung |
|---|---|
| Cross-Doc-Merge | ❌ entfällt vollständig |
| Phase 8 Stages 1–2 (Cluster-Analyse, Merge) | übersprungen für alle Docs |
| Phase 8 Stage 3 (Synthese) | wird zu **Pro-Doc-Veredelung**: Normalisierung + Strukturierung nach Template, KEIN Zusammenführen mehrerer Docs |
| Phase 8 Stage 4 (Frontmatter) | läuft pro Doc, wie bisher spezifiziert |
| Cluster-Logik | nur noch **Ablage-Heuristik** für Vault-Ordner, nicht Synthese-Basis |
| `merged_from` | bleibt leer (kein Merge) |
| Review-Gate 2 (Merges) | entfällt |
| Review-Gate 3 | wird leichter: prüft 1:1-Veredelung, nicht Cross-Doc-Korrektheit |

**Konsequenz für Scope-Doc:** `01_strategy.md` Out-of-Scope um „Cross-Doc-Synthese" ergänzen; Phasen-Übersicht Phase 8 anpassen.

---

## 2. CC-Autonomie-Setup (Block 0.N — NEU, zuerst)

Ziel: CC arbeitet ohne Bestätigung für reversible Tasks, gesichert für destruktive.

### 2.1 Granulare Permissions in `.claude/settings.json`

Statt `always_allow_tool_actions: true` global → Permission-Regeln. Exakte Syntax gegen offizielle Docs verifizieren (https://docs.claude.com/en/docs/claude-code/overview).

Konzept:

| Kategorie | Inhalt |
|---|---|
| **allow** | File edit/read im Repo, `pytest`, `ruff check/format`, `git add/commit/status/diff/log`, `python -m pipeline status/validate/reports`, `python -m pipeline run --phase N` (ohne --force) |
| **ask** | `git push`, `python -m pipeline run --force`, `pip install` / Dependency-Änderung, `gh` write-Operationen |
| **deny** | `rm -rf`, jeder Schreibzugriff auf `data/01_corpus_input/`, jeder Pfad außerhalb `~/projects/aktiv/PKM-rebuild/`, `git push --force`, `gh repo delete` |

### 2.2 Sicherheitsnetz (Pflicht VOR Autonomie-Aktivierung)

- [ ] `scripts/snapshot.sh` lauffähig (Korpus + Vault tar.gz)
- [ ] frischer Snapshot vor jedem autonomen Lauf
- [ ] Korpus-Ordner `chmod`-readonly auf OS-Ebene (zusätzlich zur deny-Regel)
- [ ] SessionStart-Hook lädt Git-Status (Doc 06 Sektion 5.3) → CC sieht uncommitted Changes
- [ ] alle Arbeit auf Feature-Branches, `main` nur via reviewtem Merge

### 2.3 Akzeptanz 0.N

- [ ] Permissions getestet: allow-Task läuft ohne Prompt, deny-Task wird blockiert
- [ ] Snapshot vor autonomem Lauf nachweisbar

---

## 3. Roadmap (Block-Reihenfolge)

```
0.N  CC-Autonomie-Setup (Permissions + Sicherheitsnetz)   ← ZUERST
  ↓
0J.8 + 0.M  Doku-Update + Reports-Bug                      ← Quick Wins
  ↓
0.L-Impl  Option-B-Routing: Stage-1/2-Bypass, Stage-3 als Pro-Doc-Veredelung
  ↓
0.G  Vault-Foundations (Tag-Vokabular, 11 Templates, Gedanken-Pfad)
  ↓
0.I  Backup-DoD (Time Machine fixen, 2. Medium)
  ↓
8.A  Phase-8-Smoke-Test (1 Batch, Stage 3+4 Pro-Doc)
  ↓
8.B  Phase-8-Voll-Lauf (Stage 3+4 über alle 202 Docs)
  ↓
8.C  Reflexion Phase 8
  ↓
0.H.4  Reflexionen Lessons finalisieren
  ↓
9    Vault-Aufbau (Ordner, _index.md, Wikilink-Validierung)
  ↓
10   Kontroll-Berichte final
  ↓
DoD-Check
```

### Zeit-Schätzung (Sessions à 4–6h)

| Block | Sessions |
|---|---:|
| 0.N Autonomie-Setup | 0.5 |
| 0J.8 + 0.M | 0.5 |
| 0.L-Impl | 1–1.5 |
| 0.G | 1.5–2 |
| 0.I | 0.5 |
| 8.A | 0.5–1 |
| 8.B + 8.C | 1–2 |
| 0.H.4 | 0.5 |
| Phase 9 | 2–3 |
| Phase 10 + DoD | 0.5 |
| **Summe** | **~8.5–12** |

Kalenderzeit bei 2–3 Sessions/Woche: **3–5 Wochen** inkl. Reflexions-Puffer.
Größte Varianz: 8.A/8.B — Qwen lief nie real.

---

## 4. CC-Session-Zuschnitt (autonom, App-arm)

Jede Session = 1 Block, eigenes Task-File, eigener Branch.

| Session | Block(s) | Branch | App-Checkpoint |
|---|---|---|---|
| CC-1 | 0.N | `chore/cc-autonomy` | ℹ nach Permission-Test |
| CC-2 | 0J.8 + 0.M | `fix/reports-and-docs` | — autonom |
| CC-3 | 0.L-Impl | `feat/option-b-routing` | 🛑 vor Merge `main` |
| CC-4 | 0.G | `feat/vault-foundations` | ⏸ Tag-Vokabular-Review (menschlich) |
| CC-5 | 0.I | `chore/backup-dod` | ℹ 2. Medium-Entscheidung |
| CC-6 | 8.A | `test/phase8-smoke` | 🛑 Smoke-Output-Review |
| CC-7 | 8.B + 8.C | `run/phase8-full` | ⏸ Gate 3 (leichter Review) |
| CC-8 | 9 + 10 | `feat/vault-build` | 🛑 finaler Vault-Review |

Checkpoint-Legende (aus `docs/06b_tool_routing.md`): 🛑 Stop+Review · ⏸ menschliche Teilaufgabe · ℹ Info-Punkt.

---

## 5. Was bleibt zwingend menschlich (nicht automatisierbar)

| Aufgabe | Warum |
|---|---|
| Tag-Vokabular finalisieren (0.G) | semantische Kuration, kein LLM-Auto |
| Wikilink-Bestätigung (Phase 9) | Embedding schlägt vor, Mensch bestätigt |
| `stable`-Promotion | Bulk verboten (Vault-Standard §8) |
| 2. Backup-Medium wählen (0.I) | Infrastruktur-Entscheidung |
| Mega-Cluster-/Unsortiert-Doc-Ablage final | Heuristik schlägt vor, Mensch ordnet Rest |

---

## 6. DoD-Anpassung für Option B

Aus `01_strategy.md` §3 — folgende Kriterien ändern sich:

- ~~„Cluster mit < 3 Artikeln vermeiden"~~ → entschärft: Cluster sind reine Ablage, Mikrocluster/unsortiert erlaubt
- „Keine SHA-256-Duplikate" → bleibt (Phase 5 deckt ab)
- „Alle Vault-Artikel ≥ Qualitätsstufe 2" → bleibt, jetzt durch Pro-Doc-Veredelung erreicht statt Synthese
- NEU: „`merged_from` leer in allen Vault-Files" (Konsistenz-Check Option B)

---

## 7. Pflicht-Lektüre für CC pro Session (unverändert)

1. `/CLAUDE.md`
2. `docs/00_persona_muente.md` (gitignored)
3. `docs/01_strategy.md`
4. `docs/06b_tool_routing.md`
5. `docs/PROJECT_STATUS.md`
6. dieses Roadmap-Dokument
7. das jeweilige Task-File in `docs/tasks/`

---

## 8. Erste konkrete Aktion

1. Dieses Dokument als `docs/tasks/0L_roadmap_option-b.md` ins Repo legen
2. `01_strategy.md` + `02_pipeline_spec.md` (Phase 8) + `04_qwen_prompts.md` an Option B anpassen → Block 0J.8 mit aufnehmen
3. CC-1 starten: Block 0.N (Autonomie-Setup), Branch `chore/cc-autonomy`
4. Task-Files für 0.N + 0.L-Impl von CC erstellen lassen (App liefert nur Briefing)

---

## Änderungs-Log

- 2026-05-29 — Initial, nach Strategie-Entscheidung Option B + CC-Autonomie-Wunsch
