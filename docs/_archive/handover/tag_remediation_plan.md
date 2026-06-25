---
title: WP4 · T3a — Tag-Strict-Plan (read-only)
slug: tag-remediation-plan
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T3a-tags-format-dryrun.md
gate: 4-3a
---

# Tag-Strict-Plan — Ergebnis: **No-op im Content-Korpus**

Read-only. Kein Re-Tagging-Write.

## Messer (Baseline)
`vault-audit` liefert **keine** Tag-OOV-Regel (Regeln: cross-link, doc-count,
fence-untagged, wikilink-stub). Daher gilt — wie in T3a B.1 vorgesehen — die
**direkte Messung** als Messer: verwendete Tags je Frontmatter gegen
`config/tag_vocabulary.yaml` (149).

## Befund (Scope = 166, ohne `_attic`/`00_Meta`)

| Metrik | Wert |
|---|---:|
| Scope-Files | 166 |
| distinct verwendete Tags | **147** |
| Vokabular | 149 |
| **OOV im Scope** | **0** |
| auto-mapbar (Synonym→kanonisch) | 0 |
| Review/Low-Confidence | 0 |

**Der Content-Korpus ist bereits zu 100 % tag-konform.** Kein File benötigt
Re-Tagging. `before→after` je File = identisch (0 Änderungen).

## Auflösung der T0-Diskrepanz (12 OOV / 161)
Die T0-Messung lief **vault-weit** (inkl. `00_Meta/`). Die 12 OOV-Tags
(`changelog, conventions, meta, naming, organization, quality, review, slug,
sources, style, tagging, template`) stammen **ausschließlich aus `00_Meta/`**
(Governance-/Template-Doks) und liegen damit **außerhalb** des T3-Scopes.
Differenz distinct 161 (vault-weit) → 147 (Scope) = Tags, die nur in `00_Meta`/`_attic` vorkommen.

→ **Konsequenz:** Tag-strict-Remediation auf dem Wissens-Korpus ist gegenstandslos.
Falls `00_Meta`-Tags vereinheitlicht werden sollen, ist das eine **separate
Governance-Entscheidung** (eigenes Vokabular für Meta-Tags?), nicht T3-Content-Scope.
