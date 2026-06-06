---
title: Finalisierung & Entscheidungen 2026-06-06
slug: finalisierung-2026-06-06
status: stable
created: 2026-06-06
updated: 2026-06-06
---

# Finalisierung PKM-rebuild — Entscheidungen 2026-06-06

Abschluss Phase 9/10. Alle an diesem Tag getroffenen Entscheidungen, gelockt.

## Tag-Vokabular

- Kontrolliertes Vokabular: **149 Tags**, Quelle `04_vault/00_Meta/tag-system.md`.
- Abgeleitet aus 306 Kandidaten über 3 Review-Stufen (Inventar → x-Markierung → Tier-Analyse).
- Reduktionsprinzip: Frequenz-Schwelle (≥5 Kern, 3–4 Querschnitt, 2 Fachbegriff selektiv) statt Bauchgefühl.

### Einzelentscheidungen
| Tag | Entscheidung | Grund |
|---|---|---|
| `configuration` | aufgenommen | wiederkehrendes Querschnitts-Thema; NICHT auf `devops` gemappt (semantisch verschieden) |
| `setup` | verworfen | prozess-/dokumenttyp-nah; Semantik trägt `doc_role` (how-to/manual), nicht Tags |
| `ci` | → `corporate-identity` | Belege = Corporate Identity, Kollision mit CI/CD vermieden |
| `design` | behalten | Survivor für `design-principles`/`composition` |
| `backup` | verworfen, später nachrüstbar | aktuell kein Anlass |
| `meta`, `best-practices` | verworfen | Kategorie-Slug = Tag verboten (Vault-Standard §7) |

- 46 Synonym-Remaps + 115 Drops, vollständig in `scripts/tag_merge_map.json`.

## Konventionen

- `17_unsortiert` mit Nummern-Präfix ist **gewollt** (Abweichung von §4-Default bewusst).
- Tag-Apply läuft auf den gebauten Vault (`04_vault`), Drafts sind ab Phase 9 Wegwerf-Intermediate.
- Tags optional pro Datei; Klassifikation zusätzlich über `category`/`subcategory`/`doc_role`.
- Vault-Slug aus Titel abgeleitet (≠ `CK_`-Dateiname) — Provenance-Abgleich über `sources_docs`, nicht Dateiname.

## Build-/Migrations-Befunde

- Vault = frischer Build aus 180 Drafts (Provenance-Jaccard 99,4 %), kein Altbestand.
- 1 Draft (`befriffssammlung-tags-taxonomie-referenz`, Slug-Tippfehler im Dateinamen) bereits als `00_Meta/taxonomie.md` (slug `taxonomie`, category meta) im Vault; Migration idempotent übersprungen, kein Datenverlust.
- Slug-Kollision behoben: zweiter Aspect-Ratio-Artikel (Screen-Auflösungen, category grundlagen) von ungültigem `aspect-ratio_2` auf `aspect-ratio-screen` umgestellt; Film-Artikel behält `aspect-ratio` (kunst-kultur).
- Gate „drop-Tags-Reste" (grep-Proxy) meldet 14 Body/Code-Treffer (`"meta":` in JSON, „funktioniert", `format` in Code) — keine echten Tag-Reste; autoritative Prüfung (`validate_vault`, Tags gegen Vokabular) = 0.
- Triage-Match-Bug (zählt über Dateiname statt Provenance → meldete 27 statt 179) → Post-Project-Backlog.

## DoD

- Vault strukturiert, valides Frontmatter, 0 SHA-256-Duplikate, 0 Slug-Kollisionen, alle Wikilinks auflösbar, `_index.md` pro Cluster, Tests grün, ruff clean.
