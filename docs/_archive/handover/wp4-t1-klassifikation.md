---
title: WP4 · T1 — Klassifikations-Vorschlag (Gate 4-1a)
slug: wp4-t1-klassifikation
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T1-klassifikation.md
gate: 4-1a
---

# WP4 · T1 — Klassifikations-Vorschlag

Read-only Stand vor jeder Mutation. Master-Snapshot liegt vor (s. unten).

## Mechanik (verifiziert, entscheidet „synthese-exclude?")

`filter_synthesis_corpus` (`pipeline/redundancy_scan.py`) schließt aus per
**Ordner ODER category** — Config (`pipeline.config.yaml` §redundancy):
`exclude_folders: ["_attic","00_Meta"]` · `exclude_categories: ["meta"]`.

**`type` ist KEIN Filterkriterium.** Folge: Eine reine `type`-Korrektur (z. B.
`knowledge-article → process-document`) ändert am Synthese-Ausschluss **nichts** —
Ausschluss erfordert `category: meta` (⇒ Move `00_Meta/`, Vault-Standard §4) oder
Move in einen ausgeschlossenen Ordner. Das trennt die zwei Ziele sauber:
- **Genauigkeit** (`type` korrekt) — immer.
- **Synthese-Ausschluss** — nur über `category: meta`/Move.

Inbound `[[wikilinks]]` auf alle 7 Slugs: **0** → Moves sind link-sicher
(`related:`-Slugs brechen bei Ordner-Move nicht).

## Vorschlagstabelle

C = clear project artifact · **J = JUDGMENT** (kann echtes Wissen sein → kein Default-Meta).

| # | slug | ist-`type` | soll-`type` | soll-`category` | Move-Ziel | synthese-exclude? | Snippet | conf |
|---|---|---|---|---|---|---|---|---|
| 1 C | `metadata-pipeline-project-summary` | knowledge-article | process-document | meta | `00_Meta/` | **ja** | „Projektzusammenfassung … Status: PRODUCTION-READY" — Statusbericht der eigenen Pipeline | high |
| 2 C | `metadata-analyzer-projektauftrag` | knowledge-article | process-document | meta | `00_Meta/` | **ja** | „Projektauftrag … Übergabe an: Claude Code, Autor: Muente (System Architect)" | high |
| 3 C | `metadaten-pipeline-projektauftrag` | knowledge-article | process-document | meta | `00_Meta/` | **ja** | „Projektauftrag … Spezifikation/Implementierungsplan eigene Python-App" | high |
| 4 J | `metadata-processor-pipeline` | knowledge-article | process-document | meta *(empf.)* | `00_Meta/` *(empf.)* | **ja (empf.)** | „Projektplan: Metadaten-Prozessor-Pipeline" — Titel = Projektplan eigenes Tool | medium |
| 5 J | `metadata-analyzer-idea` | knowledge-article | process-document *(o. gedanke)* | meta *(empf.)* | `00_Meta/` *(empf.)* | **ja (empf.)** | „# Idee: Python-Anwendung für macOS …" — Projektidee eigenes Tool | medium |
| 6 J | `metadaten-toolkit-komplette-anleitung` | knowledge-article | process-document | — *(kein Move)* | — | **nein (empf.)** | „Komplette Anleitung … 30 Min Setup" — How-To/Manual, Transferwert | medium |
| 7 J | `quotes-idioms-expressions` | knowledge-article | compact-reference | — *(kein Move)* | — | **nein** | Zitate/Idiome/unübersetzbare Wörter — Content-Dump, **kein** Projekt-/Meta-Doc | medium |

### Begründungen JUDGMENT (4–7)

- **#4 `metadata-processor-pipeline`** — Titel explizit „Projektplan" der eigenen
  Pipeline. Trotz JUDGMENT-Flag faktisch Projekt-Artefakt → Empfehlung Ausschluss
  (`meta`+Move). Wenn Owner es als generische Architektur-Referenz wertet:
  `type: process-document`, **kein** Move (bleibt im Korpus).
- **#5 `metadata-analyzer-idea`** — Brainstorm/Idee zum eigenen Analyzer.
  Empfehlung Ausschluss (`meta`+Move). Alternative: `type: gedanke` — **aber**
  `15_Gedanken/` ist Schutzbereich; Move dorthin nicht im T1-Scope → bei „gedanke"
  nur `type` ohne Move (dann **nicht** synthese-ausgeschlossen).
- **#6 `metadaten-toolkit-komplette-anleitung`** — `doc_role: manual/how-to`.
  Stärkster „echtes Wissen"-Kandidat (generische ExifTool/SQLite-Anleitung).
  Empfehlung: nur `type: process-document` (Anleitung ≠ Wissensartikel),
  **kein** Move → bleibt im Synthese-Korpus. Owner-Ruling falls projekt-spezifisch.
- **#7 `quotes-idioms-expressions`** — weder Projekt noch Meta, sondern roher
  Zitat-/Idiom-Dump. `type: compact-reference` (analog `erweiterte-tag-sammlung`).
  **Kein** Synthese-Ausschluss-Hebel (nicht `meta`); falls Owner es aus der Synthese
  will, ist das eine **Content-Qualitäts-**Entscheidung (eigener Task), nicht T1.

### Konsequenz-Übersicht

- Bei Annahme aller Empfehlungen: **5** Docs synthese-ausgeschlossen (#1–5),
  **2** nur `type`-korrigiert ohne Ausschluss (#6, #7).
- Body bleibt in allen Fällen byte-unverändert (Step 2: nur Frontmatter + Move).
