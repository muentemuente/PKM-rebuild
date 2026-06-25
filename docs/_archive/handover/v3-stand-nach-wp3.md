---
title: v3 — Stand nach WP3 (Handover)
slug: v3-stand-nach-wp3
status: stable
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
---

# v3 — Stand nach WP3

Destillierter Übergabe-Stand am Ende der WP0/WP1/WP3-Sessions. Einstieg für die
nächste Session: dieses Doc + `Projektplan_pipeline-v3.md` (§7) + `WAYFINDING_*`.

---

## 1. Erledigt (auf `main`)

| WP | Inhalt | Merge |
|---|---|---|
| **WP0** | Ist-Stand bereinigt: EIN Zählstand (181) + EIN Vokabular (149), Pfad-Drift weg, v2→`docs/_archive/`, D6 in `01_strategy` | PR #34 |
| **WP1** | `structlog` verdrahtet (`work/pipeline.log` lebt); `scripts/` mypy-clean; Entrypoint-Analyse (`pkm process` kanonisch, O1) | PR #35 |
| **WP3a** | Detection (Reuse `redundancy_scan.py`): 5 Klassen, Schwellen config+getunt; Reports + MOC-Titel-Heuristik | PR #36 |
| **WP3b** | Korpus-Filter (config), Re-Scan, **5 additive MOCs** generiert (Qwen-Rahmung, RV13-Descriptoren aus echtem `summary`) | PR #37 |
| **WP3b-Promote** | doc_type-Override `moc→00_Maps` + status-Erhalt; **5 MOCs live in `00_Maps/`** (`status: draft`), Wikilinks auflösbar | PR #38 |

**Vault-Stand:** 181 kuratierte Artikel + **5 MOCs** in `00_Maps/` (`status: draft`,
`doc_type: moc`, `merged_from` leer). Quell-Artikel byte-unverändert (D6 eingehalten).
MOC-Reife `draft → review/stable` bleibt ein **manueller** Owner-Schritt (kein CC-Auto-Promote).

**Tests:** 757 grün · ruff · format · mypy clean.

---

## 2. Offen / Defekt-Notiz

**`scripts/rebuild_indices.py` = Legacy/Staging-Tool.** Zielt hardcoded auf
`_paths.OUTPUT` (Staging) und erzeugt ein **anderes Index-Format** als der Brain-Vault
(Vault nutzt phase_9: `type: index` / `article_count`; Script: `# {name}` +
Tag-Häufigkeiten). **Nicht** vault-weit gegen den Brain-Vault laufen lassen — würde alle
Indizes umformatieren. Betroffene Folder-Indizes regeneriert `pkm promote` selbst
(phase_9). → WP4-Punkt 5.

---

## 3. WP4-Backlog — Bestands-Remediation (vault-mutierend, höchstes Risiko)

Quelle u. a.: `docs/handover/v3-wp4-backlog.md`. Plan: `Projektplan_pipeline-v3.md` §7.

1. **Frontmatter-Fehlklassifikation:** 8 Projekt-/Meta-Dokumente tragen
   `type: knowledge-article` statt einer Projekt-/Meta-Markierung (metadata-pipeline-*,
   *-projektauftrag, metadata-analyzer-*, `erweiterte-tag-sammlung`,
   `quotes-idioms-expressions`). Folge: Synthese-Korpus-Filter konnte sie nicht per
   `doc_type`/`category` ausschließen. → korrigieren, damit Folgeläufe sauber filtern.
2. **Dubletten konsolidieren:** DE/EN-Varianten + Grundlagen/Referenz-Splits +
   `git-referenz` (Git-Cluster zerfiel, Members lagen in `_attic`) + NLP-Dublette
   (`nlp-grundlagen-und-named-entity-recognition` ↔ `nlp-pkm-grundlagen`, Emb 0.93) +
   visuelle-Komm-Überschneidung (`diagrams-flowcharts-reference` ↔
   `text-based-diagramming-visual-languages`). In den MOCs als „→ WP4" vermerkt, nicht aufgelöst.
3. **Tags strict** gegen SSoT-Vokabular (149) über alle Bestands-Artikel
   (Low-Confidence → Review, kein blindes Re-Tagging).
4. **Format:** `mdformat` safe-auto als Bulk; LLM-restructure **nur** triage-geflaggt (G-1),
   nicht blind über alle Artikel.
5. **`rebuild_indices`** auf `BRAIN_VAULT` + phase_9-Index-Format umstellen — oder bewusst
   als Legacy/Staging-Tool belassen (Entscheidung treffen).

**Vorbedingungen WP4 (hart):**
- **Tägliches Backup steht** (O4-Anforderung erfüllt).
- **D4 zwingend:** 3-State raw/work/export + Snapshot-before bei jeder Vault-Mutation,
  Safe-auto / Unsafe-Review-Trennung. Non-negotiable.

---

## 4. Nächster Einstieg

`Projektplan_pipeline-v3.md` §7 (WP4) lesen → WP4-Task schneiden. Erst nicht-mutierende
Analyse/Triage, dann gegateter, snapshot-gesicherter Pass. Reihenfolge der 5 Punkte oben
ist Owner-Entscheidung (Empfehlung: 1 → 3 → 4 vor 2, da Dubletten-Konsolidierung am
riskantesten ist).
