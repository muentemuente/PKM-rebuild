---
title: Runbook — Neue Files in den Vault
slug: runbook-new-files
status: stable
created: 2026-06-06
updated: 2026-06-07
---

# Runbook — Neue Files verarbeiten und in den Vault bringen

go-forward-Flow (Option B) für neue Markdown-Files. Ein Befehl (`pkm run`) fährt von
`input/` bis `output/` und hält an den Review-Gates an. Idempotent, resume-fähig.

> **Pfade:** zentral in `pipeline/_paths.py`. Daten-Root überschreibbar per
> `PKM_PIPELINE_ROOT` (default `~/projects/aktiv/pkm-pipeline`). `pkm` = `python -m pipeline`
> (Console-Script nach `pip install -e .`; sonst `python -m pipeline …`).

---

## Layout (gitignored, außerhalb des Repos)

```
pkm-pipeline/
├── input/     neue .md (1–10 pro Lauf)
├── work/      Zwischen-JSONL + state.json + logs
├── drafts/    Qwen-Outputs (CK_<slug>.{md,body.md,frontmatter.json})
├── review/    Gate-Queues + decisions.{jsonl,md}
├── output/    gebauter Staging-Vault  ← Mensch zieht ihn in den produktiven Vault
└── archive/   verarbeitete Inputs + alte Runs + Backups
```

---

## Ablauf

### 0. Browser-Download einspeisen (optional, WP2)
Wenn die `.md` ein Browser-Download mit zugehörigem Asset-Ordner ist (Bilder),
zuerst aufbereiten statt von Hand nach `input/` kopieren:

```bash
# Download (md + Asset-Ordner) in _ingest/ ablegen, dann:
python -m pipeline.ingest_md_download --dry-run   # Plan zeigen
python -m pipeline.ingest_md_download             # einspeisen
```

Das Tool findet den Asset-Ordner, benennt Assets `<quell-slug>__<original>.ext` um,
schreibt lokale Bild-Links auf pfad-freie Embeds `![[…]]` um (externe URLs bleiben),
und legt `.md` → `input/`, Assets → `input/_assets/`. `_ingest/` bleibt unangetastet
(read-only, idempotent). Mehrdeutiger/fehlender Asset-Ordner bei vorhandenen
Bild-Links → `_ingest/_quarantine/` (nicht geraten). Danach weiter mit Schritt 2.

> **Zwei Ingests, nicht verwechseln:** `pipeline/ingest_md_download.py` ist der **Vorprozessor** (`_ingest/` → `input/`, bereitet Browser-Downloads auf), `pipeline ingest` (CLI, Schritt 2 via `make ingest`/`pkm ingest`) ist der **Pipeline-Einstieg** (`input/` → Phasen 1–4 + 8) — Reihenfolge immer: erst `ingest_md_download`, dann `ingest`.

### 1. Files ablegen
Neue `.md` nach `input/` kopieren (max. 1–10 pro Lauf). Bei Browser-Downloads
übernimmt das Schritt 0.

### 2. Lauf starten
```bash
make run            # oder: python -m pipeline run
```
`pkm run` fährt: Inventar → Normalisierung → Struktur+Routing →
[Segmentierung nur bei Token-Cap] → Qwen (stage3/passthrough) + stage4 → Drafts.
Dann baut es die offenen **Review-Punkte** und **stoppt** an den Gates:

```
⏸ run: N neue Drafts, M offene Review-Punkte.
→ Nächster Schritt: review/decisions.md in Zed ausfüllen, dann
  `pkm review --apply`, dann erneut `pkm run`.
```

### 3. Review (Mensch)
`review/decisions.md` in Zed öffnen. Je Punkt **Entscheidung:** (und ggf. **Wert:**)
eintragen, speichern. Gates:

| Gate | Wann | Entscheidungen (Keyword) |
|---|---|---|
| **A quality** | Validierungsfehler | `freigeben` · `nachbessern` · `quarantaene` |
| **B category** | category ∉ Set | `zuweisen` (Wert: category) · `neu` (Wert: neue category) · `unsortiert` |
| **C tags** | Tag ∉ Vokabular | `aufnehmen` · `mappen` (Wert: kanonischer Tag) · `droppen` |
| **D final** | Publish-Freigabe | `publish` · `hold` |

```bash
make review-apply   # oder: python -m pipeline review --apply
```
Wirkung: neue Kategorien landen in `config/categories.yaml` (+ output-Ordner), neue/
gemappte/gedroppte Tags in `config/tag_vocabulary.yaml` bzw. `config/tag_merge_map.json`,
Publish-Freigaben im `work/state.json`. A/B/C werden vor D angewandt (ein Zyklus genügt).

### 4. Lauf fortsetzen → Build
```bash
make run
```
Sind keine offenen Punkte mehr übrig, baut `pkm run` die freigegebenen Drafts nach
`output/` (inkl. `_index.md` + Wikilink-Validierung) und verschiebt die verarbeiteten
Inputs nach `archive/processed_<ts>/`.

```
✓ run: K Artikel nach output/ gebaut (J Ordner), 3 Inputs archiviert.
```

### 5. Prüfen + in den produktiven Vault ziehen
```bash
make publish-check  # validiert output/ (Frontmatter/Enums/Slugs)
```
Danach `output/` in den produktiven Obsidian-Vault übernehmen.

---

## Resume / Idempotenz

- `pkm run` ist mehrfach aufrufbar: bereits verarbeitete Inputs (SHA-Skip) und
  publizierte Docs (`work/state.json`) werden übersprungen.
- Byte-identische Inputs **desselben** Laufs werden nur einmal synthetisiert
  (intra-run SHA-Dedup; kein Bestands-Check gegen Vault/Drafts).
- Bricht ein Lauf ab, einfach erneut `pkm run` — der State führt fort.

## State-Maschine (`work/state.json`)
`ingested → normalized → drafted → needs_review → approved → published`
(`ingested`/`normalized` sind Synthese-Sub-Schritte; persistiert werden die übrigen.)

## Vokabular-Pflege (separat)
```bash
python3 scripts/manage_vocab.py list        # Kategorien + Tags
python3 scripts/manage_vocab.py validate    # Drift prüfen
```

## Legacy-Erstlauf (Archiv)
Der Gesamtkorpus-Erstlauf (Phasen 1–10, inkl. Embedding/Batch — **verworfen**, nur
Archiv) liegt unter `python -m pipeline corpus-run`. Im go-forward-Flow nicht genutzt.

---

## Änderungs-Log
- 2026-06-06 — Initial (Bestands-Flow)
- 2026-06-07 — Neuschrieb auf go-forward (`pkm run`/`pkm review`, Gates A–D, neues Layout)
