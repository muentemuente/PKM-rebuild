---
title: doc-count-Reconciliation — Baseline 194/6 vs. Audit-Menge 165
slug: doc-count-reconcile
status: draft
created: '2026-06-20'
zweck: Phase-0b-Befund (read-only). Klärt die Differenz zwischen der Handover-Baseline (194/6) und der vom `vault-audit` gemeldeten Audit-Menge (165). Schlägt eine saubere, stabil meldbare Baseline vor.
---

# doc-count-Reconciliation

Live gemessen am Brain-Vault #3 (`~/Zentrale/09_Brain-Vault`, read-only, `find` + `vault_audit.is_content_md`).

## 1. Die zwei Zahlen — was sie zählen

| Zahl | Quelle | Bedeutung |
|---|--:|---|
| **194 / 6** | Handover-/Curation-Log-Baseline (`--baseline 194,6`) | **194** = alle `.md` **außerhalb `_attic`** („Hauptbestand", inkl. `_index.md` + `00_Meta` + Template). **6** = `_attic`-Artikel. |
| **165** | `vault-audit` Audit-Menge (`VaultIndex.audit_files`) | nur **Content-Artikel** — `is_content_md` schließt `_attic`/`_assets`/`00_Meta`, alle `_index.md` und Template-Stems aus. |

Es ist **kein Widerspruch**, sondern zwei verschiedene Bezugsmengen. Die Differenz ist
**strukturell und vollständig erklärbar**.

## 2. Exakte Reconciliation (live gemessen)

```
200   alle .md im Vault (rglob)
−  6   _attic/            (deprecated; = Baseline-attic 6)        →  194  (= Baseline-Hauptbestand)
− 15   00_Meta/*.md       (Standards/Templates, keine Concept-Notes)
− 13   _index.md          (Cluster-Index, auto-generiert)
−  1   Template-Stem außerhalb 00_Meta: 01_Grundlagen/artikel-formatierung.md
─────
= 165  Content-Artikel (Audit-Menge)  ✔ exakt
```

Gegenprobe Code: `len(VaultIndex.audit_files) = 165` und `sum(is_content_md) = 165` — identisch.

**194 → 165 = −29**, zusammengesetzt aus genau: **15** (`00_Meta`) + **13** (`_index.md`) +
**1** (`artikel-formatierung`-Template). Keine Restlücke.

## 3. Beiträge der genannten Treiber

| Treiber | Beitrag zur Baseline |
|---|---|
| **`_attic`-Archivierungen** | 6 Files (Track-B-Merges: 3× Git-Trio → `git-referenz` + `personal-ci` + `regex` + `themenstraenge`). Sie sind aus dem Hauptbestand **raus** (194) und in `_attic` (6). Audit-Menge unberührt. |
| **Merges** | jeder Merge: Hauptbestand −1, `_attic` +1, Audit-Menge −1. Endstand nach Track B: Hauptbestand **194**, `_attic` **6**. Seither (B-1/B-2) **konstant** — alle weiteren Ops sind Body/Frontmatter-Edits ohne Archivierung/Neuanlage. |
| **Templates** | 4 Template-Stems aus Audit-Menge ausgeschlossen (3× `artikel-template-*` in `00_Meta` + `artikel-formatierung` in `01_Grundlagen`). 3 stecken bereits im `00_Meta`-Abzug, +1 separat. |
| **`00_Meta`** | 15 `.md` (3 Templates + 12 Standards/`readme`/`changelog`/`wayfinding`/`tag-system`/`taxonomie`/…). Plus 1 Nicht-`.md` (`obsidian-settings-backup.json`, nicht gezählt). |
| **`15_Gedanken`-leer** | Ordner **gar nicht vorhanden** (0 Gedanken-Artikel im Finalbestand) → Beitrag 0. Ebenso **absent**: `07_Best-Practices`, `08_Cheatsheets`. Diese 3 Standard-Cluster sind ungenutzt → kein `_index.md`, kein Beitrag. |

**`_index.md`-Detail:** 13 Stück. 14 thematische Content-Ordner sind belegt
(01–06, 09–14, 16, 17); davon haben 13 ein `_index.md`. **`17_unsortiert` fehlt** sein
`_index.md` (Standard §4 fordert eins → kleine Audit-Hygiene-Lücke, s. capability G8).
`00_Meta` hat regelkonform **keins**.

## 4. Baseline-Vorschlag (begründet)

**Problem heute:** Default `--baseline 194,6` vergleicht die Audit-Menge (165) gegen 194 — also
gegen eine **andere** Bezugsmenge. `reconcile_doc_count` gibt deshalb nur eine **Info**-Zeile aus
(„Content 165 / Baseline-Main 194 inkl. _index/Meta"), keine echte Gleichheits-Prüfung. Drift in
der Content-Menge (versehentliche Neuanlage/Archivierung) würde nur indirekt auffallen.

**Vorschlag — Baseline auf die invariante Content-Menge festschreiben:**

| Feld | neuer Wert | Begründung |
|---|--:|---|
| `content` (Audit-Menge) | **165** | seit Track-B-Abschluss invariant; die fachlich bedeutsame Zahl. Reconcile wird echte Gleichheit `165 == 165`. |
| `attic` | **6** | unverändert. |
| Struktur-Overhead | **29** (15 Meta + 13 `_index` + 1 Template) | als **separate Invariante** assertieren statt in eine 194-Mischzahl zu packen. So fällt z. B. ein fehlendes/zusätzliches `_index.md` getrennt auf. |

**Konkret:**

1. Default-Baseline `vault_audit_cmd` von `194,6` → **`165,6`** (Audit-Menge als `content`).
2. `reconcile_doc_count`: bei `content != base_content` ein **`warning`** (statt nur Info)
   emittieren — echter Drift-Wächter für die Content-Menge.
3. Struktur-Overhead (Total − `_attic` − Audit-Menge = 29) als **eigene** Info-/Assert-Zeile,
   aufgeschlüsselt (Meta/`_index`/Template). Damit bleibt die heute in der `194`-Zahl versteckte
   Struktur sichtbar **und** getrennt prüfbar.
4. Optionaler Zusatz-Check: `_index.md`-Vollständigkeit (1 pro belegtem thematischen Cluster) →
   würde die `17_unsortiert`-Lücke direkt melden.

**Künftig stabil meldbar:** `vault-audit` zeigt dann pro Lauf `content N (Baseline 165) · attic M
(Baseline 6) · struct 29` und schlägt bei Abweichung der Content-Menge als `warning` an — die
robuste, eindeutig interpretierbare doc-count-Aussage.

## 5. Read-only-Bestätigung

Nur Doku-Files geschrieben (dieser Report). Keine Vault-Mutation, keine Code-Änderung. Messung
ausschließlich lesend (`find`, `vault_audit.is_content_md`/`build_index` ohne Write).
</content>
