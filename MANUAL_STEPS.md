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

## ⚠ Offener Befund — Backup deckt Vault #3 NICHT ab

Bei der Verifikation (WP1, Scope OUT) festgestellt:

- `scripts/backup_vault.sh` **existiert nicht** (nur als Skelett in `docs/07_backup_strategy.md`).
- `scripts/snapshot.sh` und `scripts/restore.sh` sichern ausschließlich `PKM_PIPELINE_ROOT` (= `~/projects/aktiv/pkm-pipeline`, Ort #2).
- Der **produktive Vault #3 (`/Users/muente/Zentrale/09_Brain-Vault/`) ist von keinem Backup-Skript erfasst.**

**Entscheidung erforderlich (nicht geraten):** Soll #3 in die Backup-Strategie aufgenommen werden (Time Machine prüfen + Snapshot-Quelle erweitern)? → eigenes WP, nicht Teil von WP1.
