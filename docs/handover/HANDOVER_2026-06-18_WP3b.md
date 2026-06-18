---
title: Handover WP3b — Indented→Fenced (Vault-Format-Reparatur)
slug: handover-2026-06-18-wp3b
status: aktiv
created: 2026-06-18
updated: 2026-06-18
zweck: Resume-Kontext nach dem WP3b-Dry-Run. Stand, offene Schritte, Learnings für Export-Gate + Folge-Tasks ohne den Entscheidungs-Thread.
---

# Handover — WP3b (indented Code-Beispiele → fenced)

## 1. Stand (2026-06-18)

Branch **`feat/pipeline-v2-indented-fenced`** (von `main` = `ad984f1`, WP3a gemergt).
Neuer Code, **non-mutating** gegenüber dem Vault (#3) — reiner Dry-Run.

| Artefakt | Inhalt |
|---|---|
| `pipeline/fence_indented.py` | Engine: T1 indented→fenced (list-aware, bare ```), Sprach-Heuristik, Sicherheits-Gate, Scan/Report |
| `pipeline/__main__.py` | CLI `pkm fence-indented` (Dry-Run) |
| `tests/test_fence_indented.py` + `tests/fixtures/fence_indented/list_nested.md` | 13 Tests (Konversion, list-aware, Gate, Idempotenz, Heuristik) |

Qualität: **575 Tests grün** (562 Bestand + 13 neu), `ruff check`/`format` + `mypy` clean
für die neuen Files. (3 vorbestehende PT018 in `test_format_vault.py` bewusst unberührt.)

## 2. Scope-Korrektur (wichtig — Handover-WP3a-Diagnose war ungenau)

Die „18 LEAVE = indented Code" stimmt **nicht uniform**. Die 18 zerfallen in mehrere
mdformat-Korruptions-Mechanismen. Nach Owner-Entscheid:

- **Kat A raus** (Heading-Sonderzeichen, eigener Mini-Task): `nlp-pkm-grundlagen`,
  `themenstraenge-debatten`, `python-introduction`. Heading-Guard **nicht** aufweichen.
- **Git-Trio raus** (Track B): `git-setup-and-concepts` (`git-workflow-im-alltag` war nie
  unter den 18 — verifiziert).
- **WP3b-Scope = 14** (`KAT_B_FILES` in `fence_indented.py`).

## 3. Dry-Run-Ergebnis (14 Files)

`work/fence_indented/` (gitignored, #2): Report + pro `convertible` `*.diff` + `final`-
Arbeitskopie, pro `flagged` `*.flag`.

**6 convertible** (Konversion → danach `safe` + idempotent + textverlustfrei, verifiziert):
`konfigurationsformate-yaml-toml-frontmatter`, `moderne-datenokosysteme-und-protokolle`,
`csv-parquet-formats`, `hierarchische-formate-json-xml`,
`datenbank-design-und-projektorganisation`, `sql-grundlagen-sqlite-abfragen`.

**8 flagged** (anderer Mechanismus → manuelles Review, NICHT auto-konvertiert):
- *col-0 Beispiel-Frontmatter* (`---`-Block, empfohlen ```yaml): `metadata-processor-pipeline`,
  `claude-agenten-uebersicht`. **Funktionale Template-FM** (Fencing bräche Copy-Funktion):
  `artikel-template-grundlagen`, `artikel-template-kompaktreferenz`, `artikel-formatierung`.
- *versehentliches Setext-Heading* (`Prosa`+`---`): `vector-databases-embeddings`
  (Auto-Label nennt es ggf. „Beispiel-FM" — Heuristik; echter Fix = Leerzeile vor `---`).
- *Meta-Markdown* (`#`-Beispiele in 49 Fences): `markdown-syntax`.
- *emergentes Leer-Heading*: `thinkstation-pgx-roadmap`.

## 4. Offene Schritte (in Reihenfolge)

1. **Owner-Review der 6 Diffs** (`work/fence_indented/*.diff`). Beachten:
   - Inhalt mancher Beispiele ist **bereits in der Quelle korrumpiert** (multi-line YAML auf
     eine Zeile kollabiert, z. B. `konfigurationsformate` Z. 69). Fencing bewahrt den
     Ist-Zustand, **repariert** ihn nicht (bräuchte Korpus-Original → eigener Task).
   - Geordnete Listen erscheinen als `1./1./1.` (mdformat-`1.`-Stil, bereits WP3a-Standard,
     rendert 1,2,3) — kosmetisch, kein Fehler.
2. **Snapshot** `bash scripts/backup_vault.sh` **VOR** Export (Gate-3, Pflicht).
3. **Export** der 6 `convertible` nach #3 — `fence_indented.export_convertible()` ist
   **geschrieben, aber NICHT ausgeführt** (wartet auf Diff-Review-OK). Re-evaluiert aus
   Raw, weigert sich bei `flagged` (`refused-flagged`), idempotent (`skipped-unchanged`,
   da bereits konvertierte Files mdformat-stabil sind). Noch **kein CLI-Subcommand** — bewusst,
   damit kein versehentlicher Lauf. Nach Export: Idempotenz-Verify am geschriebenen Vault.
4. **WP3b mergen** (PR) nach Owner-OK.
5. **Folge-Tasks**: (a) Kat-A Heading-Typos; (b) **3 Deferred-Cleanup** (Display-Beispiel-FM
   `metadata-processor`/`claude-agenten` → ```yaml; Setext `vector-databases` → Leerzeile) +
   2 sonstige (`markdown-syntax`, `thinkstation`); (c) Beispiel-Inhalt-Reparatur aus Korpus.

**Dauerhafte Ausnahme (KEIN offener Punkt):** `artikel-template-grundlagen`,
`artikel-template-kompaktreferenz`, `artikel-formatierung` bleiben **unfenced** (funktionale
Template-FM; Fencing bräche Copy). Kodifiziert in `PERMANENT_UNFENCED` + Report-Sektion.

## 5. Learnings (verbindlich)

- **AST allein reicht nicht**: mistune klassifiziert listen-adjazenten 4-Space-Code als
  Paragraph/List (CommonMark-Mehrdeutigkeit), nicht als `block_code`. Detektion daher
  zeilenbasiert + **empirisches Gate** (konvertieren → `format_file` muss `safe`/`unchanged`
  + idempotent + textverlustfrei sein), statt auf AST-Code-Tokens zu vertrauen.
- **Gate-Falle**: `format_file(converted)` prüft nur mdformat-Stabilität der *konvertierten*
  Datei, **nicht** semantische Treue zum Original. Erster Konverter fencte fälschlich
  verschachtelte Prosa-Listen (→ Code). Fix: Regionen mit Listen-Marker als erster Zeile
  überspringen (`_LIST_MARKER_RE`).
- **List-aware Platzierung** ist Pflicht: Code unter geordnetem Item muss auf den Item-
  Content-Indent gefenced werden (`_governing_indent`), sonst „springt" er aus der Liste.
- **Bare Fences**: Sprach-Tags sind eine Inhalts-Annahme → separat als Vorschlagsliste
  (`language_tag_suggestions.md`), nie auto. `#`-Kommentar ist kein bash-Signal.

## 6. Resume-Kontext

`docs/Projektplan_pipeline-v2.md` (WP3 = P2) · `WAYFINDING.md` (3 Orte) · dieses Handover ·
WP3a-Handover. Live-Vault `~/Zentrale/09_Brain-Vault` (186 Docs). `python3` = `.venv`.
