---
title: WP4 · T0 — Verifikation (read-only)
slug: wp4-verifikation
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T0-verifikation.md
gate: 4-0
---

# WP4 · T0 — Verifikation

Read-only Befund. Keine Vault-/Code-Mutation. Methode: Audit/Plan = Hypothese,
hier gegen Code + Live-Vault verifiziert. Live-Vault: `~/Zentrale/09_Brain-Vault`.

## V1 — Tools: Existenz · Ziel · Mutierend

Alle als CLI-Command real (`python -m pipeline <cmd>`). Default-Ziel = `BRAIN_VAULT`
(aus `_paths.py`), read-only; Output geht nach `work/…` bzw. `drafts/`.

| Tool | existiert? | Default-Ziel | mutiert Vault? | Entrypoint |
|---|---|---|---|---|
| `format-vault` | ✅ | `BRAIN_VAULT` (`--vault-dir`) read-only → `work/format` | nein (Arbeitskopie + `diff_report.md`) | `pipeline/format_vault.py` |
| `vault-repair` | ✅ | `BRAIN_VAULT` read-only → `work/vault_repair` | nein (Safe-Tier-Kopien) | `__main__` → `pipeline/vault_audit.py` |
| `vault-review` | ✅ | `BRAIN_VAULT` read-only → `work/vault_review` | nein (Unified-Diff-Patches) | `__main__` → `pipeline/vault_audit.py` |
| `restructure` | ✅ | `--file` (opt-in, eins) → `drafts/` | nein (Qwen-Draft, „schreibt NIE in den Vault") | `pipeline/restructure.py` |
| `manage_vocab` | ✅ | s. V2 — Zielpfad = `OUTPUT`, **nicht** BRAIN_VAULT | nein (`validate` read-only) | `scripts/manage_vocab.py` |

Zusatzbefund: `vault-audit` (9 Regeln, read-only → `work/vault_audit`) existiert ebenfalls
und ist der reichere Audit-Pfad gegenüber `manage_vocab validate`.

## V2 — Tag-SSoT + Konformitäts-Baseline

| Frage | Befund |
|---|---|
| SSoT physisch | `config/tag_vocabulary.yaml` (149 Tags, `rg -c` = 149 bestätigt) |
| `00_Meta/tag-system.md` | **generierter Spiegel** (`_paths.TAG_SYSTEM_DOC`), kein SSoT |
| `config/categories.yaml` | 18 Kategorien (separate Achse, s. Drift-Flag) |
| `manage_vocab validate` liefert Konformitätszahl? | **Nein.** Gibt Pass/Fail + Issue-Listen (`category_issues`/`tag_issues`), keine Zahl/Quote |
| validate Scan-Ziel | `vault_dir = _paths.OUTPUT` (+ `drafts/`) — **nicht** `BRAIN_VAULT` |
| validate-Ergebnis heute | „✓ Vokabular konsistent" — **trivial**, weil `OUTPUT` 0 `.md`-Files hat |

**Konsequenz:** `manage_vocab validate` misst den Live-Vault nicht. Für eine T3-Baseline
gegen `BRAIN_VAULT` direkt gemessen (read-only, via `_collect_used_tags_and_categories`
+ `parse_tag_vocab` auf BRAIN_VAULT):

| Metrik (Live BRAIN_VAULT) | Wert |
|---|---:|
| Vokabular-Größe | 149 |
| distinkte verwendete Tags | 161 |
| **out-of-vocab distinkte Tags** | **12** |
| verwendete Kategorien | 14 / 18 |

OOV-Tags (12): `changelog, conventions, meta, naming, organization, quality, review,
slug, sources, style, tagging, template` — überwiegend `00_Meta/`-Doks (Schutzbereich,
T3-Ausschluss prüfen). **T3-Baseline = 12 OOV / 161** (Ziel: messbar sinkend);
ein BRAIN_VAULT-Adapter für `validate` (oder `vault-audit`) ist nötig, kein
`OUTPUT`-Lauf.

## V3 — `pkm_triage`: Signale + Lücke zu D-WP4-1

`scripts/pkm_triage.py`. Scan-Ziele: `CORPUS_DIR=INPUT`, `DRAFTS_DIR=DRAFTS`,
`VAULT_DIR=OUTPUT`. **Sieht BRAIN_VAULT nicht** (Live-Lauf: Korpus 0, Vault 0).

Signale (`DraftAssessment` + `check_schema`):

| Kategorie | Signale |
|---|---|
| Body/Format | `body_headings`, `body_code_blocks`, `body_tables`, `body_wikilinks`, `body_words` (STUB-Schwelle) |
| FM-Inhalt | `summary_words`, `tags_count`, `has_provenance`, `confidence`, `category`, `title` |
| Schema | `missing_fields`, `invalid_type/status/review_status/confidence`, `unknown_category`, `umlaut_in_slug`, `invalid_slug_format`, `*_not_list` |
| Konsistenz | `diff_fields_critical/minor` (md↔json) |
| Klassen → Aktion | READY→MIGRATE · SCHEMA_FIXABLE/INCONSISTENT_MINOR→POSTPROCESS · STUB/BROKEN/ORPHAN/…→RERUN_LM · EMPTY→FRESH_RUN |

**Lücke zu D-WP4-1:** Die *Roh-Signale* (Heading-Count, summary_words, confidence,
Format/Schema) sind vorhanden — aber `pkm_triage` triagiert **Draft-Migrationsreife**
(corpus↔drafts↔output), nicht **Restructure-Bedarf von Live-Vault-Artikeln**. Es
fehlt (a) das Scan-Ziel BRAIN_VAULT, (b) eine „Restructure-Kandidat"-Klasse.
→ Adapter/eigener Triage-Pass über BRAIN_VAULT in T4 nötig (D-WP4-1).

## V4 — Standalone phase_9-`_index.md`-Generator für BRAIN_VAULT?

| Frage | Befund |
|---|---|
| Standalone-Generator auf BRAIN_VAULT? | **Nein.** |
| phase_9-Bausteine | `_render_index(folder, articles) -> str` (rein, idempotent, byte-stabil) + `_write_indexes(articles, vault_dir, archive_root, dry_run)` (pro Ordner, archive-before-delete, exkl. `00_Meta`) in `pipeline/phase_9_vault_build.py` |
| Aufruf-Signatur | beide brauchen `articles: list[_Article]` — werden im Build-Flow aus Drafts gebaut, **nicht** aus existierenden Vault-Files |
| Vorhandenes Skript | `scripts/rebuild_indices.py` → Ziel `_paths.OUTPUT` (stale, 0 Files), **direkter Write ohne dry-run/archive**, abweichendes Format ⇒ D-WP4-2-Kandidat (archivieren) |

→ **Adapter nötig in T5:** existierende BRAIN_VAULT-`.md` → `_Article`-Liste →
`_write_indexes(..., vault_dir=BRAIN_VAULT, dry_run=…)`. phase_9-Generator wiederverwenden,
`rebuild_indices.py` archivieren (D-WP4-2 bestätigt).

## V5a — Fehlklassifikation (Live-Gegenprüfung)

Quelle: `docs/handover/v3-wp4-backlog.md` §3. Alle 8 Slugs live vorhanden; 7× `type: knowledge-article`.

| Slug | type (live) | Ordner |
|---|---|---|
| `metadata-pipeline-project-summary` | knowledge-article | 14_Automatisierung-… |
| `metadata-processor-pipeline` | knowledge-article | 10_Datenarchitektur-… |
| `metadaten-toolkit-komplette-anleitung` | knowledge-article | 10_Datenarchitektur-… |
| `metadata-analyzer-projektauftrag` | knowledge-article | 14_Automatisierung-… |
| `metadaten-pipeline-projektauftrag` | knowledge-article | 14_Automatisierung-… |
| `metadata-analyzer-idea` | knowledge-article | 01_Grundlagen |
| `quotes-idioms-expressions` | knowledge-article | 01_Grundlagen |
| `erweiterte-tag-sammlung` | **compact-reference** ⚠️ | 12_Wissensmodellierung-… |

⚠️ **Drift Backlog↔Live:** Backlog führt `erweiterte-tag-sammlung` als `knowledge-article`;
live ist es `compact-reference`. Effektiv **7** als `knowledge-article` fehlklassifizierte
Projekt-/Meta-Doks (nicht 8).

## V5b — Dubletten (Live-Gegenprüfung)

Kein `lang:`-Frontmatter-Feld vorhanden; Sprache aus Titel/Inhalt — **alle Seiten DE**.
Die Regel „im Zweifel EN kanonisch" hat hier keine Live-Anwendung.

| Cluster | Slug | vorhanden | Ordner | status | Sprache |
|---|---|---|---|---|---|
| NLP (semantic-dup, cos 0.93) | `nlp-grundlagen-und-named-entity-recognition` | ✅ | 09_KI-und-Semantische-Systeme | draft | DE |
| NLP | `nlp-pkm-grundlagen` | ✅ | 01_Grundlagen | draft | DE |
| Git | `git-github-introduction` | ✅ | `_attic/` | deprecated | DE |
| Git | `git-setup-and-concepts` | ✅ | `_attic/` | deprecated | DE |
| Git | `git-workflow-im-alltag` | ✅ | `_attic/` | deprecated | DE |
| Git (kanonisch) | `git-referenz` | ✅ | 14_Automatisierung-… | draft | DE |

Befund: **1 echte offene NLP-Dublette** (beide Seiten live, beide draft, beide DE →
EN-Tiebreaker greift nicht, Owner-Entscheid Konsolidieren/Trennen). Git-„Cluster" ist
keine offene Dublette mehr: 3 Seiten bereits `_attic/`+`deprecated`, `git-referenz`
faktisch kanonisch → WP4 = Cleanup-Entscheid (endgültiges Entfernen `_attic`).

## Drift-Flag (V2/Appendix-A)

| Punkt | Befund |
|---|---|
| Plan v3 D1 nennt `pipeline/taxonomy.yaml` | **existiert nicht** — Phantom-Pfad |
| Realer Tag-SSoT | `config/tag_vocabulary.yaml` (149) |
| `pipeline.taxonomy` | **Modul** `pipeline/taxonomy.py`, lädt `config/categories.yaml` (kein `.yaml`-Datenfile) |
| Kategorien (18) vs Tags (149) | getrennte Achsen, **kein inhaltlicher Konflikt** |

⇒ **Echte Drift, aber harmlos:** nur falscher Dateiname im Plan v3 D1 (`pipeline/taxonomy.yaml`
statt `config/tag_vocabulary.yaml`). Kein Kategorien/Tags-Konflikt. Plan-Korrektur empfohlen.

---

```
Block: WP4-T0
Erledigt: V1–V5
Tools verifiziert (V1): format-vault ✅ / vault-repair ✅ / vault-review ✅ / restructure ✅ / manage_vocab ✅ — alle real; format/repair/review/audit default auf BRAIN_VAULT read-only → work/; restructure → drafts/; KEINES mutiert den Vault. Ausnahme manage_vocab: Ziel OUTPUT, nicht BRAIN_VAULT.
Tag-SSoT (V2): config/tag_vocabulary.yaml (149) · Konformitäts-Baseline: manage_vocab validate liefert KEINE Zahl + scannt OUTPUT (leer→trivial-grün). Live gegen BRAIN_VAULT direkt gemessen: 12 OOV / 161 verwendete Tags (Vokabular 149).
Triage-Deckung (V3): pkm_triage hat die Roh-Signale (headings/summary_words/confidence/Format+Schema), triagiert aber Draft-Migrationsreife gegen OUTPUT/INPUT (sieht BRAIN_VAULT nicht) — D-WP4-1 nicht abgedeckt: Adapter auf BRAIN_VAULT + Restructure-Kandidat-Klasse fehlen.
phase_9-Generator (V4): nein (kein Standalone). Bausteine _render_index(folder, articles)->str + _write_indexes(articles, vault_dir, archive_root, dry_run) vorhanden, brauchen _Article-Liste → Adapter nötig in T5; scripts/rebuild_indices.py (Ziel OUTPUT, Write ohne dry-run) = D-WP4-2-Archivkandidat.
Fehlklassifikation (V5a): 7 Slugs (nicht 8) als knowledge-article — erweiterte-tag-sammlung ist live compact-reference (Backlog-Drift). Liste: metadata-pipeline-project-summary, metadata-processor-pipeline, metadaten-toolkit-komplette-anleitung, metadata-analyzer-projektauftrag, metadaten-pipeline-projektauftrag, metadata-analyzer-idea, quotes-idioms-expressions.
Dubletten (V5b): 1 echte offene Dublette (NLP: nlp-grundlagen-und-named-entity-recognition ↔ nlp-pkm-grundlagen, beide live/draft/DE). Git-Cluster keine offene Dublette mehr (3× _attic+deprecated, git-referenz kanonisch). Kein lang-Feld → EN-Tiebreaker ohne Live-Anwendung, alle DE.
Drift-Flag: echte Drift, aber harmlos — Plan v3 D1 nennt nicht-existentes pipeline/taxonomy.yaml; realer SSoT = config/tag_vocabulary.yaml; pipeline.taxonomy ist ein Modul auf config/categories.yaml. Kategorien(18) ≠ Tags(149), kein Konflikt.
Frage an App: (1) manage_vocab validate scannt OUTPUT statt BRAIN_VAULT — in T3 Adapter bauen oder auf vault-audit (9 Regeln) als Konformitätsmesser umstellen? (2) V5a-Subset: erweiterte-tag-sammlung (compact-reference) und quotes-idioms-expressions/metadata-analyzer-idea in die type-Remediation aufnehmen oder nur die 5 reinen Projektdoks?
```
