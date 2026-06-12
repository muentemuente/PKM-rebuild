# 🧭 WAYFINDING

> ## 📍 DU BIST HIER: **Produktiver Obsidian-Vault (#3)** — `/Users/muente/Zentrale/09_Brain-Vault/`
> Das Wissens-Ergebnis. **Nicht in Git.** Hier wird inhaltlich gearbeitet (Obsidian); Regeln und Code dazu leben in #1.

> **Verteil-Hinweis (an muente):** Diese Datei als `WAYFINDING.md` in den Vault-Root #3 kopieren.

## Die drei Orte

| # | Pfad | Rolle | Git? |
|---|---|---|---|
| 1 | `~/projects/aktiv/PKM-rebuild/` | Code + Doku | ✅ public |
| 2 | `~/projects/aktiv/pkm-pipeline/` | Daten-Durchlauf (lokal) | ❌ |
| **3** ← du | `/Users/muente/Zentrale/09_Brain-Vault/` | produktiver Obsidian-Vault | ❌ |

## Struktur hier (#3)

- Nummerierte Wissens-Cluster (`01_Grundlagen/` … `16_Kunst-Kultur/`, `17_unsortiert/`). Fehlende Nummern (07/08/15) sind gewollt.
- `00_Meta/` — Standards, Templates, Anleitungen (`asset-management.md`, `diagramm-standard.md`).
- `_assets/` — globaler flacher Asset-Pool (Bilder, PDFs). Unterstrich = nicht-inhaltlich.

## Asset- & Diagramm-Regeln (Kurzform)

- **Asset einbetten:** Datei nach `_assets/`, benennen `<note-slug>__<original-name>.ext`, einbetten mit `![[name]]` (nie `![](pfad)`). Anleitung: `00_Meta/asset-management.md`.
- **Diagramm:** nur Mermaid als ` ```mermaid `-Codeblock im Body. Kein Excalidraw. Anleitung: `00_Meta/diagramm-standard.md`.
- Vollständiger Standard: #1, `docs/03_vault_standard.md` §15/§16.

## Regeln

- Inhaltliche Arbeit passiert **hier** (Obsidian), nicht durch Claude Code — das schreibt nur in #1.
- `.obsidian/`-Settings sind nicht in Git; Backup liegt unter `00_Meta/obsidian-settings-backup.json`.

## Wohin als Nächstes?

- Regeln / Frontmatter / Naming → #1, `docs/03_vault_standard.md`
- Begriffe → #1, `docs/05_glossary.md`
