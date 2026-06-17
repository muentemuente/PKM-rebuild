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

- **Code/Config/Doku** schreibt Claude Code nur in **#1** (Git).
- **#2** (`pkm-pipeline/`) ist das Daten-/Output-Verzeichnis: die Pipeline schreibt dorthin
  Zwischenstände + Reports (`work/`, `output/`, `drafts/`). Korpus-Originale dort sind read-only.
- **#3** (Live-Vault) wird **nie** autonom beschrieben: Vault-Mutation nur über das 3-State-
  Verfahren (raw → `work/` → **geprüfter** Export) nach explizitem Review-Gate. Manuelle
  Schritte: [`MANUAL_STEPS.md`](MANUAL_STEPS.md).
- **Git-Repo = #1 `PKM-rebuild`** (mit `-`), nicht `pkm-pipeline` (#2, kein `.git`).

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
