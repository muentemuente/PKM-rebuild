---
title: WP4 · T4a — restructure-Kandidaten + Kalibrierung (read-only)
slug: restructure-candidates
status: review
created: 2026-06-25
updated: 2026-06-25
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T4a-restructure-triage.md
gate: 4-4a
---

# restructure-Triage — Kalibrierung + Kandidaten

Read-only, kein Qwen, keine Mutation. Scope = **166** (Live-Korpus, ohne
`_attic`/`00_Meta`). T1c live bestätigt (5 in `00_Meta/_projektdoku/`).

## Kalibrierung (Norm aus dem Korpus, nicht blind geschwellt)

| Norm | Messung | Konsequenz |
|---|---|---|
| **H1-Count** | 134/166 = **genau 1 H1** (norm=1); 16× 0 H1; 16× >1 H1 | „>1 H1" ist Signal — **aber** stark false-positive-lastig (s. u.) |
| **summary-Prävalenz** | **100 %** gefüllt (166/166) | „summary fehlt" feuert **nie** → als Signal gegenstandslos |
| **Wortzahl** | median 1121 · **P75 2109** · P90 3829 · max 5966 | Schwelle „lang" = >P75 |
| confidence | high 150 · medium 15 · **low 1** | 1 valider Kandidat |

## Roh-Kriterium (Task-Wortlaut) → **26 Kandidaten → Cap 25 ÜBERSCHRITTEN**

| Signal | Treffer |
|---|---:|
| confidence:low | 1 |
| >1 H1 | 16 |
| level-jump (H1→H3 / H2→H4) | 12 |
| lang(>P75) + <2 Sektionen | **0** |
| **Union** | **26** |

**Diagnose (RV5/RV12): Kriterium zu scharf, nicht Vault kaputt.**
- `>1 H1` (16) trifft fast nur **Markup-/Referenz-Doks**, die `#`-Zeilen als
  **didaktische Syntax-Beispiele** außerhalb von Fences führen
  (`regex-text-transformation` 78×H1, `markdown-templates…` 38×, `markdown-referenz-css…`,
  `css-test…`, `gestaltgesetze-*`, `markdown-syntax`). Kein struktureller Defekt.
- `level-jump` (12) ist überwiegend **benigner Compact-Reference-Stil**
  (Titel-H1 → H3, H2 übersprungen: `usb-standards`, `imagemagick-commands`,
  `terminal-commands`, `din-paper-formats` …). Keine echte Schwäche.
- Das **genuine** D-WP4-1-Signal „lang + unstrukturiert" = **0**.

## Geschärftes Kriterium → **5** (echte Struktur-Schwäche)

confidence:low ODER (H1>1 **und** <2 Sektionen, flach) ODER (0 H1 **und** <2 Sektionen).

| slug | Folder | gefeuerte Signale (Werte) | Snippet | Bewertung |
|---|---|---|---|---|
| `datenaufnahme-und-verarbeitung` | 10_Datenarch. | **6×H1 / 0 Sektionen**, 683w (knowledge-article) | 6 flache Top-Themen: Datenaufnahme · Container · Monitoring · Identität · RAG · Sicherheit (aus `D_up-pgx-lexikon`) | ✅ **echter Kandidat** (Grab-Bag, flache H1-Liste) |
| `markdown-reference` | 01_Grundlagen | **confidence:low**, 374w, 1 H1 / 10 sec (compact-reference) | sonst sauber strukturiert; Qwen-low | ⚠️ nur Confidence-Flag |
| `moc-gestaltgesetze` | 00_Maps | 0 H1 / 1 sec, 256w (knowledge-article) | MOC = terse Link-Map | ⓘ MOC-Konvention — vermutl. **exempt** |
| `moc-api-protokolle` | 00_Maps | 0 H1 / 1 sec, 188w | MOC-Map | ⓘ MOC-Konvention — exempt? |
| `moc-arbeitsumgebung-tools` | 00_Maps | 0 H1 / 1 sec, 136w | MOC-Map | ⓘ MOC-Konvention — exempt? |

## Empfehlung
- **T4b-Subset = 1 File: `datenaufnahme-und-verarbeitung`** (einzige echte
  Struktur-Schwäche). Optional `markdown-reference` (nur Confidence-Review, kein
  Struktur-Defekt — evtl. eher human-review als Qwen-restructure).
- **3 MOCs ausnehmen:** terse Maps sind Konvention; „0 H1" ist hier kein Defekt.
  Falls MOC-Heading-Norm gewünscht → eigener, deterministischer MOC-Fix (kein Qwen).
- Der Vault ist strukturell **sehr sauber** → WP4 ist nach T1 faktisch durch;
  T4b schrumpft auf ein Einzel-File (oder entfällt, falls Owner `datenaufnahme`
  als akzeptabel wertet).
