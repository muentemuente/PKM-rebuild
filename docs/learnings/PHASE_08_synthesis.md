---
title: Reflexion Phase 8 — Qwen-Synthese
slug: phase-08-synthesis
phase_id: 8
phase_status: draft
status: draft
created: 2026-06-03
updated: 2026-06-03
---

# Phase 8 — Qwen-Synthese

## 1. Status

| Lauf | Umfang | Ergebnis |
|---|---|---|
| RERUN_LM | 70/70 | abgeschlossen, 0 Fehler, State konsistent |
| FRESH_RUN | 106 Slugs | ausstehend |

## 2. Toolchain

| Skript | Rolle |
|---|---|
| `scripts/pkm_triage.py` | Master — Triage über alle Drafts |
| `scripts/draft_inventory.py` | Inventar der Draft-Outputs |
| `scripts/phase8_runner.py` | Batch-Runner mit State-File |
| `scripts/check_frontmatter.py` | Frontmatter-Konsistenzprüfung |

## 3. Runner-Robustheit

- subprocess über Argumentliste (kein Shell-String) — kein Quoting-Risiko
- File-Write statt Pipe — vermeidet SIGPIPE mid-flight
- State-File pro Batch — Resume-fähig
- Signal-Handler — sauberer Abbruch
- Abort nach 5 consecutive Fails — kein Token-Verbrennen bei Dauerfehler

## 4. Gelöste Bugs

| Bug | Ursache / Fix |
|---|---|
| Tilde-Assignment | `VAR=~/...` triggert CC-Security-Wrapper → `$HOME` (siehe CLAUDE.md §12) |
| SIGPIPE | `\| head` mid-flight schloss Pipe → File-Write statt Pipe |
| zsh-Quoting | Leerzeichen in Dateinamen → Argumentliste statt Shell-String |
| Slug-Mismatch | macOS NFD/NFC Unicode-Normalisierung → Normalisierung im Slugify |
| Hidden Meta | `.meta.json` in Skip-Check übersehen → Skip prüft body + frontmatter meta |
| Stage-4-Doppelarbeit | Dedup-Fix `phase_8_synthesis.py` ~Z885 — existierender Slug wird bei Resume in `used_slugs` übernommen statt neu durchnummeriert |

## 5. Frontmatter-Check (95 Stems)

| Befund | Anzahl |
|---|---|
| konsistent | 91 |
| inkonsistent | 4 (Altlast 05-30/05-31, kein RERUN) |
| `unknown_category` | 70 |
| `invalid_type` (`gedanke`) | 5 |

## 6. Entscheidung: category + type deterministisch im POSTPROCESS

`category` und `type` werden **nicht** per Prompt erzwungen (fragil), sondern
deterministisch im POSTPROCESS über alle 201 Drafts gemappt.

**Begründung:** konsistent mit „Validierung nach Output" (`docs/04_qwen_prompts.md` §8),
robuster als Prompt-Engineering.

## 7. Offene Entscheidungen

| ID | Frage |
|---|---|
| D1 | `category`-Mapping: Tabelle vs. 16er-Liste erweitern |
| D2 | `gedanke`-Type Spec-Lücke — `DocTypeGuess`-Enum kennt `gedanke`, finales `type`-Enum nicht |
