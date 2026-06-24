---
title: v3 — Entrypoint-Redundanz (Analyse + Empfehlung)
slug: v3-entrypoints
status: review
created: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: TASK_wp1_stabilisierung.md (Phase C)
gilt_fuer: Owner-Entscheidung (G-Weiche)
---

# Entrypoint-Redundanz — Analyse (D11)

**Auftrag:** Erstverarbeitungs-Pfade inventarisieren, echte Redundanz von legitimer
Spezialisierung trennen, EINEN kanonischen go-forward-Pfad empfehlen. **Kein Code-Umbau**
— Konsolidierung erst nach Owner-Entscheidung (G-Weiche).

---

## 1. Inventar

| Entrypoint | Aufruf | Input | Output / Default-Write | State | Tests | In Doku/RUNBOOK |
|---|---|---|---|---|---|---|
| **ingest_md_download** | `python -m pipeline.ingest_md_download` | `_ingest/` (Browser-Downloads, read-only) | `input/*.md` + `input/_assets/` | — (idempotent, reine Funktion der Quelle) | `test_ingest_md_download.py` | RUNBOOK Schritt 1 |
| **`pkm run`** | CLI `run` → `orchestrator.run_pipeline` | `input/*.md` | `drafts/` → (Gates) → `output/` Staging-Vault + `archive/` | `work/state.json` | `test_orchestrator.py` | RUNBOOK (Hauptbefehl) |
| **`pkm ingest`** | CLI `ingest` → `ingest.run_ingest` | `input/*.md` | nur `drafts/` (+ `ingest_report.md`); isoliertes Work-Dir | (kein eigener Lauf-State) | `test_ingest.py` | RUNBOOK Schritt 2 |
| **`pkm process`** | CLI `process` → `process_orchestrator.run_process` | `--source <ordner>` (alle `*.md`) | vault-ready bis `review_ready`; **kein** Vault-Write | `work/process/state.jsonl` | `test_process_orchestrator.py` | Projektplan v3 (Process-1) |
| **`pkm corpus-run`** | CLI `corpus-run` | Gesamtkorpus | Phasen 1–10 (inkl. Embedding/Batch) | `work/state.json` | — (kein direkter) | als Legacy/Archiv markiert |

---

## 2. Überlappung vs. Spezialisierung

**Keine Redundanz — distinkte Rolle (behalten):**

- **`ingest_md_download`** ist ein **Vorprozessor** (`_ingest/` → `input/`), kein
  Pipeline-Einstieg. Er steht *vor* allen anderen Pfaden (Asset-Detect/Slug/Rewrite).
  Schon im WP0-Audit-Reversal bestätigt (RUNBOOK-Schritt 1) — **nicht** anfassen.
- **`corpus-run`** ist der **Legacy-Vollkorpus-Erstlauf** (Phasen 1–10, inkl. der
  verworfenen Embedding/Batch-Phasen). In WP0 bereits als Archiv/Legacy gelabelt,
  Docstring sagt das explizit. Bewusst behalten, nicht go-forward.

**Echte Konkurrenz — drei „Erstverarbeitungs"-Pfade, zwei Philosophien:**

| | Option-B-Synthese-Linie | Process-1-Linie |
|---|---|---|
| Pfade | `pkm ingest` (→ drafts), `pkm run` (→ drafts → Gates → output/) | `pkm process` (Stage-Kette → review_ready) |
| Modell | Phasen 1–4 + 8 (Qwen-Synthese), Pro-Doc | normalize → restructure → tags → assets → links → review_ready |
| Output | Staging-Vault `output/` + Publish-Gate | vault-ready Files, Promotion (D4) **separat** |
| Stand | älter; RUNBOOK nennt `pkm run` als *den* einen Befehl | neuer (Process-1, PR #33); Docstring nennt sich *„der primäre Weg ... jedes md-File"* |

→ **Der Drift:** Zwei Stellen beanspruchen „primär" — RUNBOOK (`pkm run`) und der
`process_orchestrator`-Docstring (`pkm process`). `pkm ingest` ist faktisch die
Teilmenge von `pkm run` ohne Build/Gates (input → drafts).

**Sie sind aber keine reinen Duplikate:** `pkm run` deckt Synthese **+** Vault-Build
**+** Publish-Gate ab; `pkm process` deckt die Erstaufbereitung (normalize/restructure/
tags/assets/links) ab und stoppt vor der Promotion. Eine Konsolidierung muss die
Lücke schließen, nicht nur einen Befehl streichen.

---

## 3. Empfehlung

**Kanonischer go-forward-Erstverarbeitungs-Pfad = `pkm process`** (Process-1), weil:
- explizit als universeller, filter-freier Eingang konzipiert (jedes md, jeder Zustand),
- resilient (Einzelfehler → `needs_human`, Lauf fährt fort) + resumable + idempotent,
- eigener, sauberer State (`work/process/state.jsonl`),
- der jüngste, bewusst als Architektur-Entscheidung (Option A) gebaute Stand.

Konsequenz für die übrigen Pfade — **Owner wählt** (das ist die G-Weiche):

| # | Option | `pkm ingest` | `pkm run` | Konsequenz |
|---|---|---|---|---|
| **O1** (empfohlen) | Process-1 wird Eingang, Synthese-Linie wird *nachgelagerte* Phase | als Legacy markieren (Docstring + raus aus aktiver Doku) | bleibt für Synthese/Build/Publish **nach** `process` | klare Reihenfolge `ingest_md_download → process → (Synthese/run-Build) → Promotion`; RUNBOOK muss neu geschnitten werden |
| **O2** | Synthese-Linie bleibt kanonisch, `process` wird Spezial-Tool | bleibt | bleibt Hauptbefehl | `process_orchestrator`-Docstring „primär" zurücknehmen; Process-1-Invest teilweise geparkt |
| **O3** | Beide echten Linien zusammenführen | — | — | größter Umbau; eigener WP, nicht in WP1 |

**Nicht Teil der Empfehlung / nicht zu entfernen:** `ingest_md_download`, `corpus-run`
(distinkte Rollen, s. §2).

> [!question] Welche Option (O1/O2/O3)? Erst danach Folge-Task „Entrypoint-Konsolidierung"
> (Doc-Re-Cut + ggf. Docstring/Legacy-Labels). **STOP an G-Weiche — kein Code-Umbau in WP1.**

---

## 4. Offen / nicht behandelt

- `corpus-run` hat **keinen** direkten Test (alle anderen Pfade schon). Kein Defekt,
  aber Lücke — separat bewertbar, falls der Pfad doch aktiv bliebe.
- RUNBOOK_new_files.md spiegelt noch die Synthese-Linie als Hauptweg; Anpassung hängt
  an der O1/O2/O3-Entscheidung und gehört in den Folge-Task.
