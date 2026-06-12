# 🧭 WAYFINDING

> ## 📍 DU BIST HIER: **Code-Repo (#1)** — `~/projects/aktiv/PKM-rebuild/`
> Git, public. Code + Doku. **Nur dieser Ort wird versioniert und von Claude Code beschrieben.**

## Die drei Orte

| # | Pfad | Rolle | Git? |
|---|---|---|---|
| **1** ← du | `~/projects/aktiv/PKM-rebuild/` | Code + Doku | ✅ public |
| 2 | `~/projects/aktiv/pkm-pipeline/` | Daten-Durchlauf (lokal) | ❌ |
| 3 | `/Users/muente/Zentrale/09_Brain-Vault/` | produktiver Obsidian-Vault | ❌ |

## Regeln

- Claude Code schreibt **nur in #1**. Alles für #3 läuft über [`MANUAL_STEPS.md`](MANUAL_STEPS.md) (manuell ausgeführt).
- Keine Schreibzugriffe auf #2 / #3 durch die Toolchain.
- Korpus-Originale (in #2) sind read-only.

## Was liegt hier (#1)?

| Pfad | Inhalt |
|---|---|
| `CLAUDE.md` | Working Rules für Claude Code |
| `README.md` | Projekt-Einstieg, „Die drei Orte", Assets & Diagramme |
| `docs/` | Projekt-Doku (`03_vault_standard.md` = Vault-Standard inkl. §15/§16 Assets/Diagramme) |
| `docs/vault_meta/` | Master für `00_Meta/`-Anleitungen (Asset-Management, Diagramm-Standard) |
| `docs/wayfinding/` | WAYFINDING-Varianten für #2 und #3 |
| `pipeline/`, `config/`, `scripts/` | Pipeline-Code |
| `cc-tasks/` | lokale Task-Briefings (gitignored) |
| `MANUAL_STEPS.md` | manuelle Schritte für #3 |

## Wohin als Nächstes?

- Vault-Regeln (Frontmatter, Naming, Assets, Diagramme) → `docs/03_vault_standard.md`
- Begriffe → `docs/05_glossary.md`
- Produktiv-Vault bearbeiten → wechsle zu **#3**, dort liegt `WAYFINDING.md` (Vault-Variante)
