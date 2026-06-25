# MANUAL_STEPS

Manuelle Schritte, die **du selbst** ausführst — Claude Code schreibt nur in #1 (`~/projects/aktiv/PKM-rebuild/`) und fasst #2/#3 nicht an. Diese Liste setzt die Asset-Konvention (WP1) im Produktiv-Vault #3 (`/Users/muente/Zentrale/09_Brain-Vault/`) um.

> Pfade mit `$HOME` statt `~` in Variablen-Assignments (Security-Wrapper, siehe `CLAUDE.md` §12).

---

## Checkliste — #3 (Produktiv-Vault)

### 1. Asset-Pool anlegen

```bash
mkdir -p "/Users/muente/Zentrale/09_Brain-Vault/_assets"
```

### 2. 00_Meta-Anleitungen ablegen

Master aus #1 nach `09_Brain-Vault/00_Meta/` kopieren:

```bash
REPO="$HOME/projects/aktiv/PKM-rebuild"
META="/Users/muente/Zentrale/09_Brain-Vault/00_Meta"
mkdir -p "$META"
cp "$REPO/docs/vault_meta/asset-management.md"  "$META/asset-management.md"
cp "$REPO/docs/vault_meta/diagramm-standard.md" "$META/diagramm-standard.md"
```

### 3. WAYFINDING in alle drei Roots

Je passende Variante als `WAYFINDING.md` in den jeweiligen Root:

```bash
REPO="$HOME/projects/aktiv/PKM-rebuild"
# #1 liegt bereits: $REPO/WAYFINDING.md
cp "$REPO/docs/wayfinding/WAYFINDING_pipeline.md" "$HOME/projects/aktiv/pkm-pipeline/WAYFINDING.md"
cp "$REPO/docs/wayfinding/WAYFINDING_vault.md"    "/Users/muente/Zentrale/09_Brain-Vault/WAYFINDING.md"
```

### 4. Obsidian-Settings setzen

Einstellungen → *Files & Links*:

| Setting | Wert |
|---|---|
| Use `[[Wikilinks]]` | on |
| Automatically update internal links | on |
| Default location for new attachments | `_assets` |
| New link format | Shortest path when possible |

### 5. Obsidian-Settings sichern

`.obsidian/` ist nicht in Git. Mindestens `app.json` sichern:

```bash
cp "/Users/muente/Zentrale/09_Brain-Vault/.obsidian/app.json" \
   "/Users/muente/Zentrale/09_Brain-Vault/00_Meta/obsidian-settings-backup.json"
```

---

## Backup-Abdeckung (Stand 2026-06-25)

- Produktiver Vault **#3** (`/Users/muente/Zentrale/09_Brain-Vault/`) ist **per Time Machine täglich gesichert** (Off-Volume). Damit ist die O4-Backup-Vorbedingung erfüllt.
- Zusätzlich expliziter Vault-Snapshot über `scripts/backup_vault.sh` / `make backup-vault` (tar+SHA, restore-getestet 2026-06-14) — schließt die frühere #3-Lücke.
- Repo-Skripte `scripts/snapshot.sh` / `restore.sh` sichern gezielt den Pipeline-Daten-Ort #2 (`PKM_PIPELINE_ROOT`). Details: `docs/07_backup_strategy.md`.

> Offener Owner-Check (niedrige Prio): optionale Off-Site-Kopie (Ebene 3, Diebstahl/Feuer) noch nicht etabliert.
