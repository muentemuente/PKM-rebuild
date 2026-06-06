---
title: Runbook — Neue Files in den Vault
slug: runbook-new-files
status: stable
created: 2026-06-06
updated: 2026-06-06
---

# Runbook — Neue Files verarbeiten und in den Vault bringen

Standard-Ablauf für neue Markdown-Files nach Projektabschluss. Idempotent, wiederholbar.

## 1. Files ablegen
Neue `.md` nach `data/01_corpus_input/` kopieren.

## 2. Pipeline laufen lassen
```bash
cd $HOME/projects/aktiv/PKM-rebuild
python -m pipeline run            # Phasen 1–8: Inventar → Synthese → Drafts
```
Ergebnis: neue Drafts in `data/03_drafts/`.

## 3. Drafts reviewen
Frontmatter-Konsistenz prüfen:
```bash
python3 scripts/check_frontmatter.py
```
Inhaltlicher Review der neuen Drafts (Stufe ≥2).

## 4. In den Vault bauen
```bash
python -m pipeline build-vault    # baut/ergänzt 04_vault aus Drafts
```

## 5. Tags vereinheitlichen
```bash
python3 scripts/apply_tag_map.py            # Dry-Run
python3 scripts/apply_tag_map.py --apply    # mit Auto-Backup
```
Neue, sinnvolle Tags außerhalb des Vokabulars erscheinen im Dry-Run als „Unbekannt".
Soll einer bleiben: erst in `00_Meta/tag-system.md` + `scripts/tag_merge_map.json` aufnehmen, dann applien.

## 6. Indizes aktualisieren + validieren
```bash
python3 scripts/rebuild_indices.py
python3 scripts/validate_vault.py
```

## Makefile-Kurzbefehle
```bash
make add-files     # = build-vault + apply --apply + reindex + validate
make tag-apply     # nur Tag-Map anwenden
make reindex       # _index.md neu
make validate      # Vault-Frontmatter prüfen
```
