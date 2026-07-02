---
title: MANUAL — Bedienungsanleitung PKM-rebuild
slug: manual
status: stable
created: 2026-07-02
updated: 2026-07-02
---

# MANUAL — Bedienungsanleitung

Wie man die PKM-rebuild-Pipeline bedient: von „ich habe eine neue Markdown-Datei"
bis „sie steht sauber im Vault". Das Dokument hat zwei Ebenen — einen
**Anfänger-Walkthrough** (Teil 3) und eine **vollständige CLI-Referenz** (Teil 4)
zum späteren Nachschlagen.

Für das *Was* und *Warum* des Projekts siehe [`../README.md`](../README.md) und
[`01_strategy.md`](01_strategy.md); für den aktuellen Stand
[`PROJECT_STATUS.md`](PROJECT_STATUS.md). Dieses Manual ist das *Wie*.

---

## 1. Was ist das hier

PKM-rebuild verwandelt lose Markdown-Notizen in saubere, einheitlich strukturierte
Obsidian-Vault-Artikel — mit konsistentem Frontmatter, kontrollierten Tags und
thematischer Ordner-Struktur. Die Verarbeitung läuft lokal: eine Python-Pipeline
für die deterministischen Schritte, ein lokales Sprachmodell (Qwen) für die
inhaltliche Veredelung. **Kein Schritt schreibt automatisch in den Vault** — die
Übernahme ist immer eine bewusste, manuelle Freigabe.

---

## 2. Voraussetzungen & Setup

Einmalig, bevor irgendetwas läuft.

### 2.1 System

- **macOS** (das Projekt ist darauf entwickelt; Pfade/Backup gehen von macOS aus).
- **[mise](https://mise.jdx.dev/)** — verwaltet die Python-Version. Ohne mise kein
  reproduzierbares Setup.

### 2.2 Projekt einrichten

```bash
# Repo holen
gh repo clone muentemuente/PKM-rebuild
cd PKM-rebuild

# Python 3.12 via mise
mise install
mise use python@3.12

# Pipeline + Dev-Tools installieren (pytest, ruff, mypy)
make setup
#   entspricht: pip install -e ".[dev]"

# Prüfen, dass es läuft
python -m pipeline --version      # -> python -m pipeline, version 0.1.0
python -m pipeline status
```

`python -m pipeline` ist der Aufruf der Pipeline. (In manchen Docs steht `pkm` als
Kurzform gemeint — der reale Aufruf in diesem Projekt ist `python -m pipeline`.)

### 2.3 Lokales Sprachmodell (LM Studio + Qwen)

Jeder Schritt, der Inhalte veredelt (also `process`, `restructure`, der
NB-Feld-Backfill), braucht ein **laufendes** lokales Modell. Ohne das brechen diese
Befehle ab.

1. **[LM Studio](https://lmstudio.ai/)** installieren.
2. Das Modell **Qwen 3.6 27B** (4-bit) laden.
3. In LM Studio den lokalen **Server** starten (OpenAI-kompatibler Endpoint). Der
   erwartete Endpoint steht in [`../pipeline/pipeline.config.yaml`](../pipeline/pipeline.config.yaml)
   unter `qwen.endpoint`.
4. **Andere speicherhungrige Apps schließen** — das Modell braucht viel RAM
   (32 GB Hard Limit, Kontext-Window ~50K Token).

> Nur *echte* (nicht-`--dry-run`) Läufe mit LLM brauchen das laufende Modell.
> Read-only-Reports (`quality-score`, `vault-health`, `status`) laufen ohne.

### 2.4 Die drei Orte (wichtig, nicht verwechseln)

| # | Pfad | Rolle |
|---|---|---|
| 1 | `~/projects/aktiv/PKM-rebuild/` | Code + Doku (Git). **Hier wird gearbeitet.** |
| 2 | `~/projects/aktiv/pkm-pipeline/` | Daten-Durchlauf (außerhalb Git): `input/`, `work/`, `drafts/`, `review/`, `output/`, `archive/` |
| 3 | `~/Zentrale/09_Brain-Vault/` | der produktive Obsidian-Vault |

Die Pipeline schreibt **nie** autonom in #3 — das passiert nur im gegateten
`promote --execute`, das du selbst auslöst.

---

## 3. Der Standard-Workflow, Schritt für Schritt

Ziel: eine neue Notiz vault-ready machen und übernehmen. Der kanonische Weg dafür
ist **`process`**. Er nimmt jede Datei, egal wie roh, und führt sie durch dieselbe
feste Kette bis zum Zustand `review_ready`:

```
ingested → normalize → restructure → tags → assets → links → review_ready
         → [human_reviewed] → promoted        ← das sind deine Freigaben
```

### Schritt 1 — Datei ablegen

Lege die neue `.md` in den Input-Ordner (Ort #2):

```bash
cp meine-neue-notiz.md ~/projects/aktiv/pkm-pipeline/input/
```

### Schritt 2 — verarbeiten

```bash
python -m pipeline process --source ~/projects/aktiv/pkm-pipeline/input/
```

Was dabei passiert, in einfachen Worten: die Pipeline liest **alle** `.md` im
Quell-Ordner, normalisiert sie (Zeilenenden, Leerzeilen, Code-Blöcke bleiben
unangetastet), lässt Qwen den Text sauber restrukturieren, vergibt Tags aus dem
festen Vokabular, kümmert sich um Assets und Wikilinks — und stoppt bei
`review_ready`. Ergebnis: pro Datei ein **Draft** und ein **Review-Sheet** (`.xlsx`).
Es wird **nichts** in den Vault geschrieben.

- Der Lauf merkt sich seinen Fortschritt (`pkm-pipeline/work/process/state.jsonl`).
  Bei Abbruch: mit `--resume` genau dort weitermachen und gescheiterte Dateien
  erneut versuchen.
- Bereits verarbeitete Dateien werden übersprungen (Hash-Skip) — Doppelläufe sind
  ungefährlich.

### Schritt 3 — Drafts ansehen

Die Drafts liegen unter `~/projects/aktiv/pkm-pipeline/drafts/`. Ein Draft ist eine
fertige `.md` mit vollständigem Frontmatter, Status `review_status: ai_drafted` —
also „von der KI vorgeschlagen, noch nicht vom Menschen geprüft".

### Schritt 4 — Review-Sheet ausfüllen (Mensch)

Öffne das `.xlsx`-Review-Sheet. Pro Draft trägst du eine Entscheidung ein:
**accept** (übernehmen), **reject** (verwerfen) oder **edit** (erst noch anpassen).
Dann einlesen:

```bash
python -m pipeline review-ingest --sheet <sheet>.xlsx
```

Das setzt bei `accept` den `review_status` auf **`human_reviewed`**, verschiebt
`reject`-Drafts ins Archiv und markiert `edit`-Drafts. **Warum dieser Schritt nötig
ist:** die nächste Stufe (`promote`) lässt nur `human_reviewed`/`verified` Drafts
durch — ein rein KI-erzeugter Draft (`ai_drafted`) wird hart abgelehnt. Das ist die
Leitplanke gegen ungeprüfte KI-Inhalte im Vault.

### Schritt 5 — in den Vault übernehmen (Owner-Gate)

Erst als **Dry-Run** (zeigt nur, was passieren würde, schreibt nichts):

```bash
python -m pipeline promote --draft <draft-pfad>
```

Der Dry-Run zeigt den **Plan** (Ziel-Ordner, neu vs. Update) und bei einer
Kollision einen **Diff** (Bestand → promotet). Sieht das gut aus, dann echt
schreiben:

```bash
python -m pipeline promote --draft <draft-pfad> --execute
```

Jetzt wird geschrieben: Snapshot des Vault (für Rollback) → Datei nach #3 →
Verifikation → Ordner-Index neu erzeugt → Draft ins Archiv. `status` wird dabei auf
`review` gesetzt — **nie automatisch `stable`**. Der Sprung auf `stable` ist eine
separate, rein manuelle Entscheidung (Qualitätsstufe-2-Review).

### Durchgängiges Beispiel

Angenommen, du hast eine Datei `docker-basics.md`.

```bash
# 1. ablegen
cp docker-basics.md ~/projects/aktiv/pkm-pipeline/input/

# 2. verarbeiten (LM Studio läuft)
python -m pipeline process --source ~/projects/aktiv/pkm-pipeline/input/
#   Konsole (gekürzt):
#   process  docker-basics.md  ingested→normalize→restructure→tags→…→review_ready
#   Draft:        pkm-pipeline/drafts/docker-basics.md
#   Review-Sheet: pkm-pipeline/review/…/review_sheet_<ts>.xlsx

# 3./4. Sheet öffnen, "accept" für docker-basics eintragen, speichern, einlesen
python -m pipeline review-ingest --sheet pkm-pipeline/review/…/review_sheet_<ts>.xlsx
#   -> docker-basics.md: review_status = human_reviewed

# 5. Dry-Run, dann übernehmen
python -m pipeline promote --draft pkm-pipeline/drafts/docker-basics.md
#   Plan: docker-basics → …/09_Brain-Vault/xx_…/docker-basics.md (NEU)
python -m pipeline promote --draft pkm-pipeline/drafts/docker-basics.md --execute
#   ✓ Promotet: …/docker-basics.md (new)
#     Index regeneriert: xx_…/_index.md
#     Draft archiviert: …/archive/promoted_drafts/docker-basics.md
```

Fertig — `docker-basics.md` steht im Vault, `status: review`, bereit für deine
finale Sichtung.

---

## 4. CLI-Referenz

Alle Befehle laufen als `python -m pipeline <command>`. Die Angaben sind gegen den
echten `--help`-Output verifiziert (Stand 2026-07-02). Vollständige Befehlsliste:
`python -m pipeline --help`. Jeder Befehl hat `--help` mit allen Optionen.

| Befehl | Zweck | Wichtigste Flags | Beispiel |
|---|---|---|---|
| `process` | Universelle Erstverarbeitung: jede `.md` → `review_ready`. Kein Vault-Write. | `--source DIR` (Pflicht) · `--resume` · `--vault-dir` | `python -m pipeline process --source ~/projects/aktiv/pkm-pipeline/input/` |
| `review-ingest` | Owner-Entscheidungen aus dem Sheet einlesen (accept→`human_reviewed`, reject→archive, edit→Flag). Kein Vault-Write. | `--sheet FILE` (Pflicht) | `python -m pipeline review-ingest --sheet sheet.xlsx` |
| `promote` | Einen `human_reviewed` Draft in den Live-Vault übernehmen. **Default = dry-run.** | `--draft FILE` (Pflicht) · `--on-collision abort\|replace\|suffix` · `--execute` · `--vault-dir` | `python -m pipeline promote --draft d.md --execute` |
| `quality-score` | Read-only Quality-Scoring (6 Dimensionen + Composite + Band, deterministisch, kein LLM). | `--vault-dir` · `--out DIR` · `--xlsx` · `--top N` · `--reuse-redundancy` | `python -m pipeline quality-score --xlsx` |
| `vault-health` | Read-only Health-Report aus der `quality-score`-Historie (Aggregation). | `--quality-dir DIR` · `--out DIR` | `python -m pipeline vault-health` |
| `redundancy-scan` | Vault (read-only) auf Redundanz + Synthese-Potenzial prüfen → Reports. | `--vault-dir` · `--output-dir` · `--no-embeddings` · `--qwen` | `python -m pipeline redundancy-scan --no-embeddings` |
| `regenerate-indices` | Per-Ordner `_index.md` aus dem Vault-Stand neu erzeugen (idempotent). **Default = dry-run.** | `--vault-dir` · `--apply` | `python -m pipeline regenerate-indices --apply` |
| `format-vault` | Vault deterministisch formatieren — **DRY-RUN** (raw read-only → `work/`). Vault bleibt unangetastet. | `--vault-dir` · `--work-dir` · `--examples N` | `python -m pipeline format-vault` |
| `build-vault` | Phase 9: Vault aus Drafts nach `output/<NN_Cluster>/<slug>.md` bauen (Staging). | `--force` · `--dry-run` | `python -m pipeline build-vault --dry-run` |
| `status` | Aktuellen Pipeline-Status anzeigen. | `--config` | `python -m pipeline status` |
| `taxonomy` | Taxonomie-SSoT pflegen (Unterbefehle `add-category` / `add-tag` / `rename`). | (je Unterbefehl) | `python -m pipeline taxonomy add-tag docker --reason "…"` |

### Vokabular-Pflege: `scripts/manage_vocab.py`

Eigenständiges Skript (kein `pipeline`-Subcommand) für Kategorien + Tags:

```bash
python scripts/manage_vocab.py list          # Vokabular anzeigen
python scripts/manage_vocab.py validate      # Drift prüfen (fehlende Ordner, OOV-Tags)
python scripts/manage_vocab.py add-category  # neue category anlegen
python scripts/manage_vocab.py add-tag       # neuen Tag ins Vokabular aufnehmen
```

Die `taxonomy`-Subcommands der Pipeline sind der reichere Weg (inkl. Migration beim
`rename`); `manage_vocab.py` ist die schlanke Anzeige-/Validierungs-Alternative.

### Weitere Befehle (Sonderfall / Legacy)

`ingest`, `run`, `corpus-run` (Option-B-Synthese-Linie bzw. Legacy-Vollkorpus),
`restructure` / `restructure-batch` (einzelnes/mehrere Files re-strukturieren),
`synthesize-moc` (additive MOC-Drafts), `reports`, `vault-audit` / `vault-repair` /
`vault-review` / `vault-apply` (WP4-Remediation), `frontmatter-audit`,
`backfill-nb-fields` (NB-Feld-Backfill — abgeschlossen), `fence-indented`. Details
je Befehl: `python -m pipeline <command> --help` und
[`02_pipeline_spec.md`](02_pipeline_spec.md) §4.

---

## 5. Troubleshooting

### LM Studio läuft nicht / Modell nicht geladen
**Symptom:** `process`/`restructure`/Backfill brechen mit Verbindungs-/Timeout-Fehler
ab. **Lösung:** LM Studio öffnen, Qwen-Modell laden, lokalen Server starten (Endpoint
muss zu `qwen.endpoint` in `pipeline.config.yaml` passen). Read-only-Befehle
(`quality-score`, `vault-health`, `status`) brauchen das Modell nicht — zum Testen der
Installation geeignet.

### `needs_human` / Stage-3-Timeout
**Symptom:** eine Datei landet in `needs_human` statt als Draft, Reason
`output_truncated`. **Bedeutung:** der Stage-3-Call hat das Token-Limit erreicht
(`finish_reason=length`) — ein abgeschnittener Output wird **bewusst nicht** still als
Draft übernommen (H3-Hardening). **Was tun:** die Datei ist meist Meta-/Prompt-Inhalt,
der einen Reasoning-Loop auslöst. Optionen: hart auf `passthrough` routen, oder die
Datei manuell aufbereiten. Details: [`FUTURE_RUN.md`](FUTURE_RUN.md) (Abschnitt Hangs).

### Kollision bei `promote` (`--on-collision`)
**Symptom:** `promote` meldet „Kollision: Ziel existiert" und stoppt. **Bedeutung:** im
Vault gibt es schon eine Datei mit diesem Slug (bei Updates der Normalfall). **Optionen:**
- `abort` (Default) — nichts tun, nur Diff zeigen und stoppen. Sicher.
- `replace` — **Update**: Content-/Restructure-Felder + additive NB-/Keyphrase-Ebene
  kommen aus dem Draft, Taxonomie/Verlinkung/Quellen bleiben aus dem Bestand.
- `suffix` — als neue Datei `slug_2.md` schreiben, Bestand unberührt.

### Wo liegen Logs?
Strukturierte Logs: `~/projects/aktiv/pkm-pipeline/work/pipeline.log` (JSON,
`structlog`). Prozess-State: `~/projects/aktiv/pkm-pipeline/work/process/state.jsonl`.
Promote-Snapshots (Rollback): `~/Zentrale/_apply_backups/`.

### Fehlgeschlagenen Lauf fortsetzen
`process` ist resume-fähig: `python -m pipeline process --source <dir> --resume`
macht am letzten State weiter und versucht gescheiterte Dateien erneut. Unveränderte,
bereits erledigte Dateien werden übersprungen.

### Etwas versehentlich promotet
Jedes `promote --execute` legt vorher einen Snapshot unter `~/Zentrale/_apply_backups/`
an (im Konsolen-Output als „Snapshot (Rollback)" genannt). Diesen Ordner
zurückspielen stellt den Vor-Zustand her.

---

## 6. Glossar

Begriffe (Draft, Concept-Note, Option B, Stage 3/4, `review_status`, MOC, …) sind
zentral definiert in [`05_glossary.md`](05_glossary.md) — hier bewusst nicht doppelt
gepflegt.

---

## 7. Wo finde ich was

| Frage | Dokument |
|---|---|
| Was ist das Projekt, Quick Start | [`../README.md`](../README.md) |
| Ziele, Scope, Definition of Done | [`01_strategy.md`](01_strategy.md) |
| Pipeline-Phasen, Schemas, alle CLI-Befehle im Detail | [`02_pipeline_spec.md`](02_pipeline_spec.md) |
| Frontmatter-Schema, Naming, Ordner, Qualitätsstufen | [`03_vault_standard.md`](03_vault_standard.md) |
| Qwen-Prompts (Stages, Versionierung) | [`04_qwen_prompts.md`](04_qwen_prompts.md) |
| Begriffsdefinitionen | [`05_glossary.md`](05_glossary.md) |
| Inkrementeller Workflow + Backlog | [`FUTURE_RUN.md`](FUTURE_RUN.md) |
| Aktueller Stand, Counts, offene Punkte | [`PROJECT_STATUS.md`](PROJECT_STATUS.md) |
| Manuelle Schritte am Produktiv-Vault (#3) | [`../MANUAL_STEPS.md`](../MANUAL_STEPS.md) |
| Backup-Strategie für den Vault | [`07_backup_strategy.md`](07_backup_strategy.md) |
