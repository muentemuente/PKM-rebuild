# 🧭 WAYFINDING

> ## 📍 DU BIST HIER: **Daten-Durchlauf (#2)** — `~/projects/aktiv/pkm-pipeline/`
> Lokaler Arbeitsbereich der Pipeline. **Nicht in Git.** Hier laufen Inputs durch die Phasen; nichts hier ist die Single Source of Truth — der Code lebt in #1.

> **Verteil-Hinweis (an muente):** Diese Datei als `WAYFINDING.md` in den Root von #2 kopieren.

## Die drei Orte

| # | Pfad | Rolle | Git? |
|---|---|---|---|
| 1 | `~/projects/aktiv/PKM-rebuild/` | Code + Doku | ✅ public |
| **2** ← du | `~/projects/aktiv/pkm-pipeline/` | Daten-Durchlauf (lokal) | ❌ |
| 3 | `/Users/muente/Zentrale/09_Brain-Vault/` | produktiver Obsidian-Vault | ❌ |

## Regeln

- Der **Code** dafür liegt in #1 (`pipeline/`, `config/`, `scripts/`) — hier liegen nur **Daten/Outputs**.
- Korpus-Originale sind **read-only** (nicht verändern, nicht überschreiben, nicht löschen).
- Claude Code schreibt hier **nicht** autonom; produktive Vault-Änderungen passieren in #3.
- Layout/Pfade zentral in #1: `pipeline/_paths.py`.

## Wohin als Nächstes?

- Pipeline ausführen / verstehen → #1, `README.md` + `docs/02_pipeline_spec.md`
- Vault-Regeln → #1, `docs/03_vault_standard.md`
- Fertige Artikel ablegen → **#3** (`09_Brain-Vault/`)
