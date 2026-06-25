---
title: Capability-Inventur — 7 Baukasten-Fähigkeiten (main)
slug: capability-inventory
status: draft
created: '2026-06-20'
zweck: Phase-0a-Befund (read-only). Mappt den Code-Stand auf `main` gegen die 7 Baukasten-Fähigkeiten (scannen · normalisieren · analysieren · formatieren · (re)strukturieren · Syntax · Semantik). Composability-Check + single-pass/two-stage-Klärung + Gap-Liste.
---

# Capability-Inventur (Stand `main`, read-only)

> **generiert/stale (Stand 2026-06-25).** Phase-0a-Befund-Momentaufnahme des Code-Stands (`main` @ `104c4a0`), **nicht laufend gepflegt**. Kein CLI-Regen — aktueller Stand: `docs/PROJECT_STATUS.md`.

Basis: `main` @ `104c4a0` (PRs #11–#15 inkl.). Code-Module aus `pipeline/` + `scripts/`.
CLI-Oberfläche `python -m pipeline …` (`pipeline/__main__.py`).

## 1. Reife-Tabelle (7 Fähigkeiten)

| # | Fähigkeit | Modus / Tool (CLI) | Reife | Code-Einhängepunkt |
|---|---|---|---|---|
| 1 | **scannen** | `run`/`ingest` (Inbox→Manifest), `corpus-run --phase 1` | **reif** | `phase_1_inventory.py` (`_filename_to_slug`, hash, manifest), `ingest.py` / `ingest_md_download.py`, `vault_audit.build_index` (Vault read-only) |
| 2 | **normalisieren** | `corpus-run --phase 2` (Teil von `run`/`ingest`) | **teil** | `phase_2_normalize.py` — nur LF/Trailing-WS/Blank-Collapse/Tab/Frontmatter-Extract, **fence-aware**. Enthält **nicht** das WP4-Repair-Set (s. §3). |
| 3 | **analysieren** | `vault-audit`, `redundancy-scan`, `reports`, `corpus-run --phase 5/6/10` | **reif** | `vault_audit.audit_vault` (9 Regeln), `redundancy_scan.run_redundancy_scan` (Hash+TF-IDF+mpnet+opt. Qwen), `phase_5_redundancy`, `phase_6_embeddings`, `phase_10_reports` |
| 4 | **formatieren** | `format-vault` (WP3a), `fence-indented` (WP3b), `vault-repair` (WP4) | **reif (dry-run)** | `format_vault.py` (mdformat, safe/unsafe, Obsidian-Schutz), `fence_indented.py` (indented→fenced), `vault_audit.repair_text` (debold/setext/junk/fence-tag/close-unclosed/PUA) |
| 5 | **(re)strukturieren** | `corpus-run --phase 8` (stage3), `build-vault` (Phase 9), `taxonomy rename` | **teil** | `phase_8_synthesis.py` (stage3-Synthese, opt-in/Routing), `phase_9_vault_build.py` (category→Ordner-Placement), `taxonomy_migrate.py` (rename+Move+Index-Regen), `vault_audit.add_bidirectional_related` (Cross-Link-Graph) |
| 6 | **Syntax** | `vault-audit`/`vault-repair`/`vault-review` | **reif** | `vault_audit.check_fences`/`check_headings`/`check_wikilinks`/`check_frontmatter` + `repair_text`; fence-v2 (`detect_fence_lang`, `_is_*`), Inline-Code-Maske, `[[N]](url)`-Maske |
| 7 | **Semantik** | `redundancy-scan [--qwen]`, `corpus-run --phase 8`, Cross-Link/Alias | **teil** | `redundancy_scan` (emb+Qwen-Paarbewertung), `phase_8` stage3/stage4 (Synthese + Klassifikation), `vault_audit.read_cross_link_candidates`, Alias-Disambiguierung (§10-Konvention, manuell gated) |

Reife-Legende: **reif** = produktiv genutzt + getestet · **teil** = vorhanden, aber lückenhaft verdrahtet oder human-gated · **fehlt** = nicht vorhanden.

## 2. Composability-Befund

**Zwei getrennte Welten, nicht ein durchgehender Pipe:**

- **(A) Korpus-Pipeline** (`run`/`corpus-run`/`ingest`): sequenziell verkettet über JSONL-Artefakte
  in `pipeline_output/` (`files_manifest` → `cleaned_documents` → `documents_structured` →
  `segments` → `exact/near-dup` → `embeddings/cluster` → `batches` → `qwen/drafts` → `output/`).
  Output→Input echt verkettbar; Idempotenz über Input-Hash + `.meta.json`. Phasen einzeln
  wiederholbar (`--phase N`/`--from-phase N`). **Gut komponierbar.**
- **(B) Vault-Werkzeuge** (`format-vault`, `vault-audit`, `vault-repair`, `vault-review`,
  `fence-indented`, `redundancy-scan`): **parallele Geschwister**, je `Vault-DIR (read-only) → work/<tool>/`.
  Sie verketten **nicht** untereinander (Output von `vault-repair` ist `work/`-Arbeitskopie, nicht
  Input von `vault-audit`); jedes liest den rohen Vault neu. Der eigentliche Vault-Write passiert
  **außerhalb des Codes** (manuelles D4: Snapshot→Canary→Verify, kein `--apply`-Modus). **Schwach
  komponierbar** — bewusst, wegen Datenintegrität (Vault git-extern).

**Kopplungen:**
- `vault_audit` importiert `format_vault` (geteilte Masking-Helfer) — einzige Tool↔Tool-Kopplung.
- Korpus-Pipeline-Phasen sind reihenfolge-gekoppelt (Phase 4 braucht Phase 2+3-Outputs).
- **Ziel-Divergenz:** Pipeline (A) baut nach `output/` (Staging); Werkzeuge (B) zeigen auf
  `BRAIN_VAULT` (#3, git-extern). Das frisch gebaute `output/` wird **nicht** auditiert.

## 3. single-pass vs two-stage (Kern-Klärung)

**Befund: two-stage.** Die WP4-Detektoren/-Repairs (fence-v2, Inline-Code-/`[[N]](url)`-Masken,
`repair_text` = debold/setext/junk/fence-tag/close-unclosed/PUA) hängen **ausschließlich in
`pipeline/vault_audit.py`** und sind **nur** an die manuellen CLI-Kommandos `vault-audit`/
`vault-repair`/`vault-review` verdrahtet.

Verifiziert (grep, `main`): `vault_audit` wird **nur** von `pipeline/__main__.py` importiert —
**nicht** von `orchestrator.py`, `run_flow.py`, `ingest.py` oder `phase_2_normalize.py`.

**Konsequenz:** Ein neues File durch `pkm run` / `pkm ingest` durchläuft in Phase 2 nur die
**schmale** Normalisierung (Whitespace/LF/Tab/Frontmatter-Extract, fence-aware). Es bekommt die
WP4-Verbesserungen **nicht** automatisch. Um fence-v2/debold/Masken zu erhalten, ist ein
**separater** `vault-repair`-Lauf auf den gebauten/Brain-Vault nötig (heute manuell, D4-gated).

→ **Das ist die zentrale Composability-Lücke für Phase 1.** Ziel-Bild: WP4-`repair_text` als
deterministische Normalisierungs-Stufe in den Build-/Ingest-Pfad ziehen (single-pass), damit ein
neues File in **einem** Lauf alle Verbesserungen erhält — bei Vault-Mutation weiter D4-gated.

## 4. Gap-Liste (für vollen Baukasten)

| # | Gap | Fähigkeit | Phase-1-Kandidat |
|---|---|---|---|
| G1 | WP4-`repair_text` nicht im `normalize`/`ingest`-Pfad (two-stage) | normalisieren/Syntax | **ja** (single-pass) |
| G2 | `format_vault` (WP3a) + `fence_indented` (WP3b) sind **dry-run-only** DIR-Tools → `work/`; nie in Phase 9 / Build verdrahtet | formatieren | ja |
| G3 | Kein `--apply`-Modus für Vault-Werkzeuge; Vault-Write läuft manuell außerhalb Code (D4) | formatieren/Syntax | optional (Guardrail-Design) |
| G4 | Pipeline baut nach `output/`, Audit zielt auf `BRAIN_VAULT` — gebautes `output/` wird nicht auditiert | analysieren | ja |
| G5 | `config/categories.yaml` spiegelt `CATEGORY_TO_FOLDER` nur (Drift-Guard-Test), ist noch nicht **die** SSoT | (re)strukturieren | **ja** (Roadmap P1) |
| G6 | doc-count-Default-Baseline `194,6` mischt Hauptbestand (194) und Audit-Menge (165) — Reconcile ist Info statt echter Gleichheit | analysieren | ja (s. `doc_count_reconcile.md`) |
| G7 | Semantische (Re)Strukturierung (Synthese/Merge) bleibt human-gated/manuell; kein deterministischer Re-Struktur-Engine, Klassifikation mit Modell-Ceiling | (re)strukturieren/Semantik | Phase 2/3 (Qwen, konditional) |
| G8 | `17_unsortiert` ohne `_index.md` (Standard §4 fordert eins); `rebuild_indices.py` zielt auf `output/`-Staging, nicht Brain-Vault | (re)strukturieren | klein (Audit-Hygiene) |

## 5. Fazit

- **Stark:** scannen, analysieren, Syntax-Detektion+Repair, deterministisches Formatieren — alle
  reif und getestet (611 Tests, mypy strict).
- **Schwach verdrahtet:** Die reifen Format-/Repair-Fähigkeiten sind **nicht** in den Build-Pfad
  integriert (G1/G2/G4) → **two-stage**. Das ist der Haupt-Hebel der Phase-1-Konsolidierung.
- **Bewusst human-gated:** semantische (Re)Strukturierung (Fähigkeit 5/7) — Detection+Report reif,
  Transformation per Owner-Gate (Option-B-Invariante, D4).

**Read-only bestätigt:** Es wurden nur Doku-Files geschrieben; kein Code, kein Vault verändert.
</content>
