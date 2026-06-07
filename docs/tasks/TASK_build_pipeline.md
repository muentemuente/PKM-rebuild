# TASK — Aufbau `pkm-pipeline`: erweiterbare Dokumenten-Pipeline

**Rolle CC:** autonome Umsetzung im Repo. **Auftrag:** den bestehenden Verarbeitungs-Code zu einer schlanken, wiederholbaren Inkrement-Pipeline umbauen — neue `.md` in `input/`, möglichst automatisch bis `output/`, mit festen Review-Gates für alle manuellen Entscheidungen.

**Realität:** Umbau, kein Run. Mehrstündig. Arbeite in Arbeitspaketen (WP). Nach jedem WP `pytest` + `ruff` grün. Zwei ⏸-Checkpoints sind **harte Stopps** mit Rückmeldung in den App-Chat. **main-Merge ist NICHT freigegeben** — Abschluss endet auf dem Feature-Branch.

## Arbeitsregeln
- `$HOME`/absolute Pfade. Feature-Branch `rebuild-pipeline-<ts>`. Commits pro WP (conventional).
- Verify-Gates ⛔ müssen grün sein, sonst Abbruch + Rollback-Hinweis.
- Nichts in `data/` löschen ohne vorheriges Archiv (tar). WP0 legt Rollback-Snapshot an.
- An ⏸-Checkpoints: STOPP, `ℹ STATUS` ausgeben, auf Freigabe warten.
- Keine lauten Zwischenausgaben; pro WP eine 3-Zeilen-Abschlussnotiz.

---

## Ziel-Architektur (verbindlich)

### Datenordner `~/projects/aktiv/pkm-pipeline/` (lokal, gitignored)
```
pkm-pipeline/
├── input/            neue .md
├── work/             ALLE Zwischen-JSONL + state.json + logs (1 Ordner)
├── drafts/           Qwen-Outputs (body + frontmatter)
├── review/
│   ├── needs_human/  low-confidence / Validierungsfehler
│   ├── category_open/ unklare/neue Kategorie
│   ├── tags_open/    Tags außerhalb Vokabular
│   └── quarantine/   Hangs/Crashes
├── output/           gebauter, getaggter Staging-Vault (Mensch zieht raus)
└── archive/          verarbeitete Inputs + alte Runs + Backups
```

### Repo `~/projects/aktiv/PKM-rebuild/` (Git, bleibt)
- `config/` (NEU): `categories.yaml` (17 Kategorien + Mapping-Regeln), `tag_vocabulary.yaml` (Single Source, 149), `tag_merge_map.json`.
- `pipeline/_paths.py` (NEU): zentrale Pfad-/Config-Auflösung. **Alle** Skripte importieren von hier.
- `pipeline/` Phasen, `scripts/` Tools, `prompts/`, `docs/`.

### Flow (Option B, schlank — kein Dedup/Embedding/Batch)
```
input/*.md (1–10)
 → 1 Inventar (Doc-ID, SHA, manifest)
 → 2 Normalisierung
 → 3 Struktur + Routing (passthrough | stage3 | gedanke)
 → [Segmentierung NUR bei Token-Cap-Überschreitung]
 → 4 Qwen: stage3 (Prosa-Veredelung) ODER passthrough (Body 1:1) + stage4 Frontmatter
 → 5 Validierung → Routing in review/-Queues
      ⏸ GATE A  Qualität (low-confidence/Fehler)
 → 6 Category-Mapping (deterministisch → 17)
      ⏸ GATE B  Kategorie (unklar/neu)
 → 7 Tag-Apply (gegen Vokabular)
      ⏸ GATE C  Tags (neu außerhalb Vokabular)
 → 8 Build nach output/ + _index + Wikilink-Validierung
 → 9 validate_output
      ⏸ GATE D  Final-Sicht
 → Mensch zieht output/ in den produktiven Vault
```
Gates sind **Run-intern** (Stopp im Lauf), abgearbeitet über `pkm review`. Verwandte Files eines Runs werden je Gate **gebündelt** gezeigt.

---

## WP0 — Sicherung + Ist-Inventar
```bash
set -euo pipefail
REPO="$HOME/projects/aktiv/PKM-rebuild"; OLD="$HOME/projects/aktiv/PKM_rebuild"
TS=$(date +%Y%m%d_%H%M%S); cd "$REPO"
git checkout -b "rebuild-pipeline-$TS"
mkdir -p "$OLD/backups"; tar -czf "$OLD/backups/ROLLBACK_rebuild_$TS.tar.gz" -C "$OLD" data 2>/dev/null
echo "ROLLBACK: $OLD/backups/ROLLBACK_rebuild_$TS.tar.gz"
```
- **Inventar erstellen** `docs/REBUILD_inventory.md`: alle Files in `pipeline/` + `scripts/` auflisten; pro File grep nach hardcodierten Pfaden (`PKM_rebuild`, `01_corpus_input`, `02_pipeline_output`, `03_drafts`, `04_vault`). Diese Liste ist die Refactor-Checkliste für WP2.
- **Akzeptanz:** Snapshot da, Inventar listet jeden hardcodierten Pfad mit Fundstelle.

## WP1 — Layout-Migration
- `mv "$HOME/projects/aktiv/PKM_rebuild" "$HOME/projects/aktiv/pkm-pipeline"`.
- Neue Ordner anlegen: `input work drafts review/{needs_human,category_open,tags_open,quarantine} output archive`.
- Inhalte umräumen: `data/01_corpus_input/*` → archivieren nach `archive/` (Alt-Korpus, nicht mehr Input). `data/04_vault` → `output/` (die 179 Artikel bleiben dort, Mensch zieht sie später). `data/02_pipeline_output` + `data/03_drafts` (falls noch vorhanden) → `archive/`. Den leeren `data/`-Baum entfernen.
- **Akzeptanz:** Ziel-Layout existiert; `output/` enthält den bestehenden Vault; keine Daten verloren (Count-Abgleich gegen Snapshot).

## WP2 — Zentrale Pfade, Config, Refactor ⛔
- `pipeline/_paths.py`: liest Basis aus ENV `PKM_PIPELINE_ROOT` (Default `$HOME/projects/aktiv/pkm-pipeline`) + `PKM_REPO_ROOT`; exportiert `INPUT, WORK, DRAFTS, REVIEW, OUTPUT, ARCHIVE, CONFIG`. Konsolidiert zugleich die duplizierten Helfer/Enums (löst `_pkm_common`-Backlog).
- `config/`: `categories.yaml` (17 + deterministische Mapping-Regeln aus `apply_category_mapping.py` extrahiert), `tag_vocabulary.yaml` (149, aus `tag-system.md` generiert), `tag_merge_map.json` (verschieben aus scripts/). `tag-system.md` im Vault wird künftig aus `tag_vocabulary.yaml` **generiert** (Single Source = config).
- **Alle** Skripte/Phasen aus der WP0-Checkliste auf `_paths.py` umstellen. Keine hardcodierten Pfade mehr.
- Tests anpassen (Fixtures auf neues Layout).
- **Akzeptanz ⛔:** `grep -rE "PKM_rebuild|04_vault|03_drafts|01_corpus_input" pipeline/ scripts/ tests/` = 0 Treffer (außer in docs/archive). `pytest` + `ruff` grün.

### ⏸ REVIEW-CHECKPOINT 1
STOPP. `ℹ STATUS`: Layout migriert, Pfade zentralisiert, Tests grün, `output/` = N Artikel. **Auf Freigabe warten**, bevor Neucode (WP3+) beginnt.

## WP3 — Flow auf Option B trimmen
- Im Pipeline-Orchestrator den go-forward-Pfad definieren: Phasen 1–3 + Routing + Qwen(stage3/passthrough)+stage4 + Category-Mapping + Tag-Apply + Build + validate.
- **Entfernen/Deaktivieren** aus dem go-forward-Pfad: Embedding (Phase 6), Batch-Bildung (Phase 7), korpus-internen Redundanz-Schritt. Code darf bleiben (Archiv-/Altlauf), aber **nicht** im neuen `pkm run`.
- Segmentierung: nur Fallback bei Token-Cap (> stage3-Limit).
- Optionaler Intra-Run-SHA-Check (Duplikate *innerhalb* der 1–10 Input-Files), kein Bestands-Check.
- **Akzeptanz:** `pkm run` Pfad dokumentiert in Code-Kommentar; Embedding/Batch nicht im Pfad; Tests grün.

## WP4 — Review-Gate-System ⛔
**Mechanik (file-basiert, Zed-Review — kein TUI):**
- Validierung/Mapping/Tagging schreiben offene Punkte in die `review/`-Queues + sammeln sie in **`review/decisions.jsonl`**, ein Item pro Zeile:
  ```json
  {"doc_id":"D_x","gate":"category|tags|quality|final","question":"...","current":"...","options":["..."],"group":"<themengebiet>","decision":"","value":""}
  ```
- `pkm review` (CLI): erzeugt aus den Queues eine **editierbare** `review/decisions.md` (gruppiert nach `gate`, innerhalb nach `group` → verwandte Files zusammen). Mensch trägt Entscheidungen ein, speichert in Zed.
- `pkm review --apply`: liest die ausgefüllten Entscheidungen zurück und wendet sie an:
  - **Gate A:** freigeben | nachbessern (zurück in Qwen) | quarantäne.
  - **Gate B:** category zuweisen | **neue Kategorie** (Eintrag in `config/categories.yaml` + neuer output-Ordner) | unsortiert.
  - **Gate C:** Tag aufnehmen (`config/tag_vocabulary.yaml` + ggf. `tag_merge_map.json`) | auf bestehenden mappen | droppen.
  - **Gate D:** publish-freigabe (Flag im state).
- **Akzeptanz ⛔:** Unit-Tests pro Gate (Fixture-Items → decisions → erwartete Wirkung). Neue Kategorie/neuer Tag landen korrekt in `config/`. `pytest`+`ruff` grün.

## WP5 — Orchestrierung `pkm run` ⛔
- Ein Befehl fährt `input/` → `output/`, hält an jedem Gate mit offenen Punkten an und weist auf `pkm review` hin.
- **State-Maschine** `work/state.json` pro Doc: `ingested→normalized→drafted→needs_review→approved→published`. Idempotent (SHA-Skip), resume-fähig.
- 1–10 Files pro Run; Quarantäne-Pfad mit `max_tokens`-Cap gegen Reasoning-Hangs.
- **Akzeptanz ⛔:** Smoke-Run mit 3 synthetischen `.md` (1 prosa→stage3, 1 code→passthrough, 1 mit unbekanntem Tag→Gate C) läuft bis Gate, `pkm review --apply` + Fortsetzung bis `output/`. Tests grün.

## WP6 — Doku + Makefile + Runbook
- `docs/RUNBOOK_new_files.md` neu schreiben (neuer Flow + Gates + CLI).
- Makefile: `ingest`, `run`, `review`, `review-apply`, `publish-check`.
- `docs/02_pipeline_spec.md` + `03_vault_standard.md`: Layout/Flow/Gates aktualisieren; Embedding/Batch als „Alt (verworfen)" markieren.
- `docs/learnings/` Eintrag: Architektur-Umbau dokumentieren.
- **Akzeptanz:** `make run` auf leerem `input/` ist No-Op ohne Fehler; Doku konsistent; `pytest`+`ruff` grün.

### ⏸ REVIEW-CHECKPOINT 2
STOPP vor main. `ℹ STATUS`: alle WP grün, End-to-End-Smoke-Run erfolgreich, Branch-Diff-Zusammenfassung. **Auf Merge-Freigabe warten.**

---

## Abschluss — `ℹ STATUS` (≤12 Zeilen)
1. Layout migriert (`pkm-pipeline/` 6 Ordner) · `output/` = N Artikel
2. Pfade zentralisiert (`_paths.py`), 0 hardcodierte Pfade
3. Config: categories/tag_vocabulary/tag_merge_map im Repo
4. Flow Option-B-schlank (Embedding/Batch raus)
5. Review-Gates A–D + `pkm review` getestet
6. `pkm run` State-Maschine + Smoke-Run grün
7. Doku/Makefile/Runbook aktualisiert
8. pytest/ruff grün · Branch `rebuild-pipeline-<ts>`
9. Rollback-Snapshot-Pfad
10. **Offen für Freigabe:** main-Merge

**Stoppe an beiden ⏸-Checkpoints. Kein main-Merge ohne Freigabe.**
