---
title: WP4 · T3a — mdformat Dry-Run + Schutzsyntax-Nachweis
slug: format-dryrun
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
task: cc-tasks/TASK_wp4_T3a-tags-format-dryrun.md
gate: 4-3a
---

# mdformat Dry-Run — Schutzsyntax-Nachweis: **FAIL → STOP-FLAG**

Read-only. mdformat lief auf einer **Kopie** (`work/wp4_t3a/fmt/`), Vault unangetastet.
Toolchain: mdformat 1.0.0 + mdformat-gfm 1.0.0 + mdformat_frontmatter 2.1.2, `--wrap keep`.

## Scope
- **166 Files** (Live-Korpus nach T1; ohne `_attic/`, `00_Meta/` inkl. `_projektdoku/`).
- `15_Gedanken/` **existiert nicht** (kein Gedanke im Vault) → Sonderbehandlung gegenstandslos.

## Dry-Run-Ergebnis
- **132 / 166** Files würden sich ändern.
- Änderungskategorien: Body-Whitespace/Leerzeilen, Listen-Marker-Normalisierung,
  Heading-Spacing, **Frontmatter-YAML-Reformatierung (13 Files)**,
  **Wikilink-Escaping (11 Files)**.

## Schutzsyntax-Nachweis (kritisch)

| Konstrukt | orig | nach mdformat | Status |
|---|---:|---:|---|
| Wikilink `[[…]]` | 218 | 110 | ❌ **FAIL** (108 Links in 11 Files escaped) |
| Embed `![[…]]` | 7 | 7 | ✅ intakt |
| Callout `> [!…]` | 42 | 42 | ✅ intakt |
| Mermaid-Fence ` ```mermaid ` | 75 | 75 | ✅ intakt |
| Frontmatter (YAML) | — | re-indentiert/unwrapped (13 Files) | ⚠️ semantisch neutral, **nicht byte-stabil** |

### Beleg Wikilink-Schaden (`00_Maps/moc-nlp-grundlagen.md`)
```
- orig:  - [[nlp-pkm-grundlagen|NLP für Personal Knowledge Management]] — …
- fmt:   - \[[nlp-pkm-grundlagen|NLP für Personal Knowledge Management]\] — …
```
mdformat-gfm escaped die äußeren Klammern (`[[…]]` → `\[[…]\]`) → **Obsidian-Wikilink
kaputt.** Betroffen: 11 von 31 wikilink-führenden Files (die übrigen 20 haben `[[`
nur in Code-Fences, dort unangetastet).

### Beleg Frontmatter (`moc-nlp-grundlagen.md`)
```
- orig:  - index            (Liste auf Key-Ebene)
- fmt:     - index          (+2 Indent)
- orig:  summary: '… verwandte\n  Artikel.'   (gefaltet, 2 Zeilen)
- fmt:   summary: '… verwandte Artikel.'      (zusammengezogen)
```
YAML-semantisch gleich, aber Byte-Änderung + Re-Serialisierung.

## Bewertung & Empfehlung (T3a A.3)
**STOP-FLAG: mdformat in der aktuellen Config darf NICHT auf den Vault.** Lieber kein
Format als zerstörte Wikilinks. Kein Schutz-Plugin (obsidian/wikilink) installiert.

Vor jedem T3b-Format-Erwägen muss **eine** Variante diesen Nachweis auf **PASS** bringen:
1. **mdformat-obsidian** (oder wikilink-safe Plugin) installieren + dieselbe Harness erneut → Wikilinks 218==218.
2. **Protect/Restore-Wrapper:** `[[…]]`/`![[…]]` vor mdformat durch Platzhalter ersetzen, danach zurück.
3. **Scope einschränken:** Format nur auf die 135 wikilink-freien Body-Files; 31 wikilink-Files ausnehmen.
4. **Frontmatter ausnehmen** (mdformat_frontmatter deaktivieren) oder separater deterministischer YAML-Normalizer.

Idempotenz-Vorschau: mdformat ist auf bereits formatierten Files stabil (2. Pass = 0 Änderung) —
**irrelevant**, solange der Schutz-Nachweis FAILt.
