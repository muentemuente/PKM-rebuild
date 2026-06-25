---
title: WP4 · T5a — Index-Regen (verify-first) + datenaufnahme-Fix (gestaged)
slug: wp4-t5a-index-fix
status: review
created: 2026-06-25
updated: 2026-06-25
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T5a-index-und-fix.md
gate: 4-5a
---

# WP4 · T5a — Index-Regen + datenaufnahme-Fix

Staging in `work/wp4_t5a/`, **keine Live-Writes** (Export per `!`-Lauf, Gate 4-5a).

## A — Index-Staleness (verify-first, read-only)

- Live-Vault hat **15 per-Ordner `_index.md`** (phase_9-Format, `type: index`);
  `00_Meta` hat keinen (korrekt).
- **Stale durch die 5 T1-Moves:** 3 Quell-Ordner-Indizes listen noch die verschobenen Slugs:
  - `14_Automatisierung-…` (article_count 39→36): metadata-pipeline-project-summary, metadata-analyzer-projektauftrag, metadaten-pipeline-projektauftrag
  - `10_Datenarchitektur-…` (12→11): metadata-processor-pipeline
  - `01_Grundlagen` (35→35): metadata-analyzer-idea **raus** + `artikel-formatierung` **rein**
    (Letzteres ist eine **pre-existing** Index-Drift, vom Regen mit-korrigiert — Hinweis an Owner)

→ Regen nötig für **3 Indizes**. (Kein neuer Index für `_attic` — Schutzbereich,
hatte nie einen; `00_Meta/_projektdoku/` bekommt keinen.)

## A2 — phase_9-Adapter Dry-Run

- Adapter: `_Article`-Liste aus `BRAIN_VAULT` → `_render_index`/`_write_indexes`-Bausteine
  (T0/V4), nur Ordner mit existierendem Live-Index, exkl. `00_Meta`/`_attic`.
- **11 Indizes byte-identisch** (idempotent → phase_9-Format & -Konvention bestätigt),
  **3 STALE→regen** (s. o.). Diff: `work/wp4_t5a/index_regen_diff.md`.

## B — datenaufnahme-und-verarbeitung Heading-Fix (gestaged)

- Deterministisch, **kein Qwen/Rewrite/Split**: die 6 flachen `#`-H1 → `##`-H2
  (Titel bleibt im Frontmatter; Body danach 0 H1 / 6 H2 — vault-konform).
- Body **byte-stabil außer den 6 Marker-Zeilen** (verifiziert) + `updated: 2026-06-25`.
- snapshot-before: `work/wp4_t5a/datenaufnahme/before.md`.

## C — Legacy aufgeräumt (Repo, Feature-Branch)

- `scripts/rebuild_indices.py` → `scripts/_deprecated/rebuild_indices.py`
  (archive-before via `git mv`) + Deprecation-Header (Ziel war `OUTPUT`, kein
  dry-run/archive; Ersatz = phase_9-Adapter). D-WP4-2 erledigt.

## D — Export-Skript (bereit, NICHT ausgeführt)

`scratchpad/export_t5a.py`: archive-before + Body-Byte-Sicherung (datenaufnahme),
schreibt Heading-Fix + 3 regenerierte Indizes nach `BRAIN_VAULT`. Wartet auf Owner-`!`-Lauf.

Live-Änderungen gesamt: **4 Files** (1 Heading-Fix + 3 Indizes).
