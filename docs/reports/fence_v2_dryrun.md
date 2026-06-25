---
title: WP4 B-2 — Fence-Regel v2 Dry-Run
slug: fence-v2-dryrun
status: draft
created: '2026-06-19'
zweck: Read-only Dry-Run der Fence-Regel v2 (unclosed-close + low-conf→det-Tagging) gegen den Live-Vault. Vorschau, KEIN Vault-Write.
---

# WP4 B-2 — Fence-Regel v2 · Dry-Run

> **generiert/stale (Stand 2026-06-25).** WP4-B-2-Dry-Run-Momentaufnahme (2026-06-19, read-only). Regenerierbar via `pkm vault-audit` / `pkm vault-review` (Fence-Befunde).

**Read-only.** Vorschau der `repair_text`-v2-Änderungen am Live-Brain-Vault (`pipeline.vault_audit`). Nichts geschrieben. Anwendung = späterer Owner-gegateter B-2-safe-Lauf.

## Aggregat

- **Betroffene Files:** 23
- **unclosed-Fence-Fix:** 1  (system-script-management-symlinks.md)
- **det-Lang-Tags (neu):** 60
- **Tag-Verteilung:** md=56, html=2, sql=1, bash=1
- **Frontmatter-Änderungen:** 0 → **doc-count-neutral** (reine Body/Fence-Fixes; keine Archivierung/Titel/Slug/Status)
- **Parsebarkeits-Vorschau:** 165/165 Content-Files parsebar

> **Präzision statt Recall:** das B-2-Audit nannte ~191 *potenziell* det-fähige low-conf Fences als Oberwert. Nach Präzisions-Tuning (kein JS-als-bash, keine Diagramme-als-Text/md, keine Code-Kommentare-als-md, `/` bleibt prosa-verboten) bleiben **60 verlustfrei-deterministische** Tags. Die Differenz bleibt **bewusst untagged** → Editorial-Review (B-2 edit).

## 1. Unclosed-Fence-Fix — Pre/Post-Diff (Realfall)

`03_Betriebssysteme/system-script-management-symlinks.md`: offene ```` ```bash ```` (L58) verschluckte L59–92. v2 schließt deterministisch vor der ersten Leerzeile nach der Code-Zeile (`export PATH…`); Prosa/Headings wieder ausserhalb.

````diff
--- a/03_Betriebssysteme/system-script-management-symlinks.md
+++ b/03_Betriebssysteme/system-script-management-symlinks.md
@@ -57,6 +57,7 @@
 In der `~/.zshrc` muss folgender Pfad enthalten sein:
 ```bash
 export PATH="$HOME/.local/bin:$PATH"
+```
 
 Nach Änderung source ~/.zshrc nicht vergessen
 
````

## 2. Geplante det-Lang-Tags (File × Span × Tag)

| File | unclosed | Tags (Zeile→Sprache) |
|---|:--:|---|
| `markdown-reference.md` |  | 72→md, 82→md |
| `yaml.md` |  | 210→md |
| `network-protocols-apis-advanced.md` |  | 169→md |
| `system-script-management-symlinks.md` | ✓ | — |
| `file-and-document-management.md` |  | 617→md, 631→md |
| `anleitung-arbeitsweise-festhalten.md` |  | 300→md |
| `extended-ai-use-cases.md` |  | 59→md, 434→md |
| `nlp-grundlagen-und-named-entity-recognition.md` |  | 210→md |
| `thinkstation-pgx-roadmap.md` |  | 492→md, 514→md, 539→md, 565→md, 664→md |
| `thinkstation-pgx-use-cases-uebersicht.md` |  | 126→md |
| `linked-data-semantic-web.md` |  | 262→md, 271→md, 283→md, 933→md, 1715→md, 1731→md, 2119→md, 2510→md, 2582→md, 2594→md |
| `sql-grundlagen-sqlite-abfragen.md` |  | 96→sql |
| `web-scraping-reference.md` |  | 225→html, 865→md, 891→md, 1291→md |
| `text-based-diagramming-visual-languages.md` |  | 87→md, 97→md, 107→md, 116→md, 126→md, 1615→md, 1631→md |
| `knowledge-management-guide.md` |  | 245→md, 382→md |
| `data-visualization-dashboards.md` |  | 130→md, 139→md, 148→md, 1135→md |
| `personal-ci-workflow-figma-affinity.md` |  | — |
| `visual-communication-fundamentals.md` |  | 201→md, 924→md, 1177→md, 1325→md, 1344→md, 1365→md |
| `desktop-automation-gui.md` |  | 74→md |
| `macos-python-workflow-project-structure.md` |  | 61→bash |
| `n8n-fundamentals.md` |  | 81→md, 926→html, 1201→md, 1236→md, 1344→md |
| `word-documents-tables-cleaning.md` |  | 982→md |
| `workflow-automation-task-orchestration.md` |  | 166→md, 439→md |

## 3. Verify-Zusicherungen

- **Frontmatter byte-identisch** bei allen 23 Files (0 Abweichungen).
- **doc-count konstant** — reine Body/Fence-Änderungen, keine Datei hinzugefügt/entfernt/archiviert.
- **Idempotent** — zweiter `repair_text`-Lauf auf den geänderten Files = 0 weitere Aktionen (durch Test `test_repair_close_unclosed_fence` + Safe-Op-Idempotenz abgedeckt).
- **165/165 parsebar**, 0 Quarantäne.
- **edit-Subset unangetastet** — ASCII-Trees/Output-Dumps/mehrdeutige Snippets bleiben untagged.
