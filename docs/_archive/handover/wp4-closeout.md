---
title: WP4 · Close-out + main-Merge-Gate-Prep
slug: wp4-closeout
status: review
created: 2026-06-25
updated: 2026-06-25
plan: Projektplan_pipeline-v3.md
gate: main-merge
---

# WP4 · Close-out

Read-only Gesamt-Verifikation aller Tiers gegen Live-Vault + T1-Master-Snapshot.

## Tier-Verifikation (live)

| Tier | Ergebnis |
|---|---|
| **T1** Klassifikation | 7/7 live korrekt: 5 in `00_Meta/_projektdoku/` (process-document, category meta), `metadaten-toolkit…`=process-document, `quotes-idioms…`=compact-reference |
| **Body-Integrität** | **7/7 Body byte-identisch** zum T1-Snapshot (keine Inhaltsänderung) |
| **Synthese-Ausschluss** | 166 gescannt / 26 ausgeschlossen (#1–5 raus, Rest drin) |
| **T2** NLP (D) | beide present, Body == Snapshot (unmutiert), wechselseitig `related` |
| **T4** datenaufnahme | 0 H1 / 6 H2 (Heading-Fix), Body byte-stabil außer Marker |
| **T5** Indizes | 3 regeneriert, **0 stale** (kein verschobener Slug mehr gelistet); 11 idempotent |
| **Schutzbereich** `_attic/` | 0 Diffs zum Snapshot (unangetastet); `15_Gedanken` existiert nicht |
| **Wikilinks** | **0 neue broken** durch WP4 (broken-Set 167 == Snapshot) |
| **Vault** | 192 Artikel (ohne `_index.md`) |
| **Tests** | `pytest` 757 passed; `pipeline/` ruff green |

## Q1-Entscheid dokumentiert
`01_Grundlagen/_index.md`-Regen korrigiert **zusätzlich** eine pre-existing Drift
(fügt `artikel-formatierung` hinzu, das im Live-Index nie gelistet war) — vom Owner
freigegeben (Q1 = ja). Index ist damit vollständig korrekt.

## Offene Punkte (kein Merge-Blocker — betreffen Vault, außerhalb Git)

1. **Kosmetisch:** `10_Datenarchitektur/_index.md` zeigt `Letzte Aktualisierung: 2026-06-24`
   statt `2026-06-25` (Reihenfolge-Artefakt: Index vor dem datenaufnahme-`updated`-Bump
   generiert). Inhalt/Counts korrekt. Finale Version gestaged; Ein-File-Nachzug
   `scratchpad/export_t5a_fix.py` **noch nicht gelaufen**.

## main-Merge-Gate für `feat/wp4-t1-klassifikation`

- **Branch-Inhalt vs main:** nur `docs/handover/*.md` + Move `scripts/rebuild_indices.py →
  scripts/_deprecated/` (+ Deprecation-Header). **Kein Pipeline-Code, kein Vault** (Vault
  ist außerhalb Git). Move bricht keinen Import (keine Referenzen außerhalb `_deprecated`).
- **Commits (6):** c8ecdda (WP3-Handover, vom Parent-Branch) + 968da32, 93bbd55, ea863c3,
  333775e, c8e8f0c (WP4 T0–T5). Merge bringt c8ecdda mit nach main (erwartet).
- **Achtung uncommitted:** Working-Tree hat **pre-existing** `D`-Löschungen
  (`docs/_archive/*`, `Zielbeschreibung…`-Rename) — **nicht** Teil der Branch-Commits,
  werden **nicht** mit-gemergt. Separat zu behandeln, nicht WP4.
- **Push/Merge:** erfordert explizite Owner-Freigabe (Hard Constraint).
