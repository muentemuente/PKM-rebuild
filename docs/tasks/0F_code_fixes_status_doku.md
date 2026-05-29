---
task_id: 0F
title: Code-Fixes Phase 8 + Status-Korrektur + Doku-Hygiene
status: open
owner: claude_code
priority: P0
depends_on: []
created: 2026-05-28
updated: 2026-05-28
estimated_effort: 3–5h (eine Session oder zwei kurze)
---

# Block 0.F — Code-Fixes Phase 8 + Status-Korrektur + Doku-Hygiene

## Kontext

Phase 8 ist Code-fertig und Test-grün (32 Tests), aber:
- **CLI-Wiring fehlt komplett** — `pipeline/__main__.py` listet Phase 8 nicht in `_IMPLEMENTED_PHASES`. `python -m pipeline run --phase 8` schreibt nur „noch nicht implementiert"
- **5 Code-Bugs** verhindern korrekten Echtlauf gegen 72 Batches (B1, B2, B3, B4, B5)
- **1 Config-Bug** (B8): Pydantic-Modell ignoriert YAML-Sections still
- **2 Doku-Bugs** (B6 + Quickstart) sind stale
- **PROJECT_STATUS.md** ist irreführend ("Phase 8 done", obwohl nie gegen Echtdaten gelaufen)

Diese Tasks beheben das, bevor Phase 8 erstmals echt läuft.

## Pflicht-Lektüre

1. `/CLAUDE.md`
2. `pipeline/CLAUDE.md`
3. `docs/00_persona_muente.md` (Sektionen 9–10)
4. `docs/06b_tool_routing.md`
5. `docs/02_pipeline_spec.md` Phase 8 + Sektion 8 (Idempotenz)
6. `pipeline/phase_8_synthesis.py` (komplett)
7. `pipeline/__main__.py`
8. `pipeline/config.py`
9. `pipeline/pipeline.config.yaml`

---

## Task 0F.1 — PROJECT_STATUS.md korrigieren

**Datei:** `docs/PROJECT_STATUS.md`

**Problem:** Tabelle in Sektion 1 zeigt Phase 8 als ✅ done. Realität: Code fertig, aber CLI fehlt und nie gegen echten Korpus gelaufen.

**Schritte:**
1. Sektion 1, Phase-8-Zeile: Status auf `🟡 Code fertig, CLI-Wiring offen, Echtlauf ausstehend` ändern
2. Sektion 2 (Implementierungsdetails Phase 8): am Ende Hinweis ergänzen:
   > **Wichtig:** Phase 8 wurde noch NIE gegen den echten Korpus gelaufen. Alle 32 Tests laufen gegen Mock-Fixtures. Ein produktiver Lauf ist erst nach Block 0.F und Block 8.A geplant.
3. Sektion 7 (Offene Punkte) ergänzen um:
   > ### 7.4 Phase 8 CLI-Integration fehlt
   > `pipeline/__main__.py` Zeile 23: `_IMPLEMENTED_PHASES = {1, 2, 3, 4, 5, 6, 7}`. Phase 8 ist nicht in der CLI registriert. Wird in Block 0.F behoben.
4. Sektion 8 (Nächste Schritte): ersetzen durch:
   > Siehe `docs/tasks/README.md` für vollständigen Master-Plan bis Phase 9. Block-Reihenfolge: 0.F → 0.G → 0.H → 0.I (parallel) → 8.A → 8.B → 8.C → 9.
5. `updated:` im Frontmatter auf heute setzen
6. Änderungs-Log-Eintrag

**Akzeptanzkriterien:**
- `git diff docs/PROJECT_STATUS.md` zeigt nur die genannten Änderungen
- Keine neuen Phasen als „done" markiert ohne Grundlage

**Commit:** `docs: korrigiere project-status — phase 8 cli fehlt, kein echtlauf bisher`

### ⏸ App-Checkpoint nach 0F.1

Bevor weiter zu 0F.2, in App-Konversation einfügen:

```
Block: 0.F
Erledigt: 0F.1
Commit: <hash>
Nächster Schritt: 0F.2 (CLI-Wiring)
Frage an App: Diff zu PROJECT_STATUS okay?
```

Warte auf "weiter".

---

## Task 0F.2 — Phase 8 CLI-Wiring (Bug B1)

**Dateien:** `pipeline/__main__.py` (edit), `pipeline/phase_8_synthesis.py` (nur lesen)

**Akzeptanzkriterien:**
- `_IMPLEMENTED_PHASES` enthält 8
- `_dispatch_phase_8(cfg, force)` existiert, ruft `run_phase_8` mit Parametern aus `cfg.qwen`, `cfg.paths`, `cfg.pipeline.version` auf
- Prompts-Verzeichnis: `Path("prompts")` (relativ zum Repo-Root) oder via Config
- `_PHASE_DISPATCH[8] = _dispatch_phase_8` gesetzt
- `python -m pipeline run --phase 8 --dry-run` läuft ohne Fehler
- `python -m pipeline status` zeigt Phase 8 als „implementiert"

**Implementierungs-Hinweise:**

```python
def _dispatch_phase_8(cfg: PipelineConfig, force: bool) -> None:
    out = cfg.paths.pipeline_output
    drafts = cfg.paths.drafts
    qwen = cfg.qwen
    summary = run_phase_8(
        batches_dir=out / "batches",
        segments_path=out / "segments.jsonl",
        qwen_output_dir=out / "qwen",
        drafts_dir=drafts,
        endpoint=qwen.endpoint,
        model=qwen.model,
        context_window=qwen.context_window,
        prompt_version=qwen.prompt_version,
        prompts_dir=Path("prompts"),
        temperature_stage1=qwen.temperature.stage1_cluster_analysis,
        temperature_stage2=qwen.temperature.stage2_merge_proposal,
        temperature_stage3=qwen.temperature.stage3_synthesis,
        temperature_stage4=qwen.temperature.stage4_frontmatter,
        max_retries=qwen.max_retries,
        retry_backoff_seconds=qwen.retry_backoff_seconds,
        timeout_seconds=qwen.timeout_seconds,
        force=force,
        pipeline_version=cfg.pipeline.version,
    )
    console.print(
        f"[green]✓ Phase 8:[/green] {summary['batches_processed']} Batches verarbeitet, "
        f"{summary['concepts_drafted']} Konzepte, {summary['needs_human']} needs_human, "
        f"{summary['errors']} Errors ({summary['duration_seconds']}s)"
    )
```

**Tests:** keine neuen Tests nötig — `--dry-run`-Verifikation reicht. Optional: 1 Test in `test_cli.py` (falls existiert) der `_dispatch_phase_8` mockt.

**Out-of-Scope:** echter Qwen-Aufruf (das passiert in Block 8.A)

**Commit:** `feat(pipeline): phase 8 cli-wiring (--phase 8 + dispatch)`

### ⏸ App-Checkpoint nach 0F.2

```
Block: 0.F
Erledigt: 0F.1, 0F.2
Commit(s): <hashes>
Tests: <count> grün
Verifikation: `python -m pipeline run --phase 8 --dry-run` → output zeigen
Nächster Schritt: 0F.3 (merge_decisions-Vorrang)
Frage an App: keine
```

---

## Task 0F.3 — merge_decisions-Vorrang vor Cache (Bug B2)

**Datei:** `pipeline/phase_8_synthesis.py`

**Problem:** In `_run_stage2()` ist der Cache-Check (Z. 378) **vor** dem `merge_decisions.json`-Override (Z. 383). Konsequenz: Wenn Stage 2 cached, wird die menschliche Review-Gate-2-Entscheidung ignoriert.

**Akzeptanzkriterien:**
- Neue Reihenfolge in `_run_stage2()`:
  1. `merge_decisions.json` existiert? → zurückgeben (mit Log-Eintrag)
  2. Cache existiert + Hash passt? → zurückgeben
  3. Sonst: neu generieren
- Neuer Test: `test_merge_decisions_override_wins_over_cache`
  - Setup: Stage-2-Cache mit Hash X schreiben, `merge_decisions.json` mit anderem Inhalt schreiben
  - Erwartung: `_run_stage2` gibt `merge_decisions.json`-Inhalt zurück, nicht Cache
- Alle bestehenden Tests bleiben grün

**Hinweis:** Log-Event-Name konsistent mit bestehenden: `phase_8_merge_decisions_found` (existiert bereits) — nur Reihenfolge tauschen.

**Commit:** `fix(phase_8): merge_decisions.json überschreibt stage 2 cache`

---

## Task 0F.4 — max_tokens aus Config + Stage-3-Cap reduzieren (Bug B3)

**Dateien:** `pipeline/phase_8_synthesis.py`, `pipeline/config.py`, `pipeline/pipeline.config.yaml`

**Problem:** Aktuell hardcoded (Z. 46–49):
```python
_MAX_TOKENS_STAGE1 = 24000
_MAX_TOKENS_STAGE2 = 16000
_MAX_TOKENS_STAGE3 = 32000  # 65 % des 49K-Contexts nur für Output!
_MAX_TOKENS_STAGE4 = 12000
```
Bei Batch mit großem Input (z.B. cluster_proposals enthält 72 Batches, einer könnte 15K Tokens Input haben) plus Reasoning-Overhead-Output reißt das die 49K-Context-Cap.

### 🛑 App-Checkpoint vor 0F.4 — STOP

Bevor du 0F.4 angehst, in App-Konversation Empfehlung holen:

```
Block: 0.F
Schritt: 0F.4 vor Implementierung
Problem: Hardcoded max_tokens Stage 3 = 32000 (65% von 49152 Context)
Vorschlag: stage1=20000, stage2=14000, stage3=20000, stage4=10000
Frage: Werte okay oder anders konfigurieren?
```

Warte auf User-Entscheidung. Erst dann implementieren.

**Empfohlene Default-Werte (Standard-Vorschlag falls keine andere Anweisung):**

| Stage | Aktuell | Neu | Reasoning |
|---|---|---|---|
| 1 | 24000 | 20000 | Stage-1-Output JSON kompakt, Content ~2K + Reasoning |
| 2 | 16000 | 14000 | Stage-2-Output noch kompakter |
| 3 | 32000 | 20000 | **Reduktion!** Markdown-Body Content ~3K, Reasoning + Sicherheitsmarge |
| 4 | 12000 | 10000 | Frontmatter JSON, kurzes Content |

**Akzeptanzkriterien:**
- Neue Config-Sektion `qwen.max_tokens` mit `stage1`, `stage2`, `stage3`, `stage4` (int)
- Default-Werte aus User-Entscheidung
- `QwenMaxTokensConfig` Pydantic-Model in `config.py`
- `QwenConfig` ergänzt um `max_tokens: QwenMaxTokensConfig`
- `_QwenStageConfig` bekommt 4 Felder `max_tokens_stage1..4`, Stage-Funktionen nutzen diese
- Konstanten `_MAX_TOKENS_STAGE{1..4}` entfernt
- Bestehende Tests bleiben grün (Default-Werte beibehalten oder Test-Fixtures anpassen)
- Neuer Test: `test_max_tokens_loaded_from_config`

**Commit:** `refactor(phase_8): max_tokens aus config (stage 3 cap reduziert)`

### ⏸ App-Checkpoint nach 0F.4

```
Block: 0.F
Erledigt: 0F.1–0F.4
Commit(s): <hashes>
Tests: <count> grün
Nächster Schritt: 0F.5 (Halluzinations-Logging)
Frage an App: keine
```

---

## Task 0F.5 — Halluzinierte Segment-IDs loggen (Bug B4)

**Datei:** `pipeline/phase_8_synthesis.py`

**Problem:** In `_build_stage3_user_message()` Z. 430–431:
```python
for chunk_id in concept.get("source_chunks", []):
    seg = seg_map.get(chunk_id)
    if not seg:
        continue   # ← stummes Skip
```
Wenn Qwen halluzinierte Segment-IDs liefert, werden sie still verworfen. Stage 3 läuft mit verarmten Quellen, ohne dass es auffällt.

**Akzeptanzkriterien:**
- Nicht-aufgelöste Segment-IDs werden gelogged: `log.warning("phase_8_segment_id_not_found", segment_id=chunk_id, ck_id=concept.get("ck_id"))`
- Zähler im selben Loop: wie viele aufgelöst vs. fehlend
- Wenn **alle** Source-Chunks fehlen → Eintrag in `needs_human.jsonl` mit reason `all_source_chunks_missing`, Stage 3 bricht für dieses Konzept ab (return None)
- Wenn ≥50% fehlen → `confidence: low` für dieses Konzept signalisieren (Mechanismus: Marker im concept-Dict, Stage 4 berücksichtigt)
- Neuer Test: `test_stage3_logs_missing_segment_ids` (via `caplog`)
- Neuer Test: `test_stage3_aborts_when_all_chunks_missing`

**Commit:** `fix(phase_8): halluzinierte segment-ids werden geloggt und gezählt`

---

## Task 0F.6 — used_slugs persistieren (Bug B5)

**Datei:** `pipeline/phase_8_synthesis.py`

**Problem:** `_QwenStageConfig.used_slugs: set` ist In-Memory. Bei Crash-Resume werden Slugs neu vergeben → potentielle Kollision mit bereits geschriebenen `CK_*.md`.

**Akzeptanzkriterien:**
- Beim Phase-8-Start: `drafts_dir` scannen, alle existierenden `CK_*` (Body, Frontmatter, kombiniert) → Slugs extrahieren → `used_slugs`
- Pattern: `CK_<slug>.md`, `CK_<slug>.body.md`, `CK_<slug>.frontmatter.json`
- Slug-Extraktion mit Regex: `^CK_(.+?)(\.body|\.frontmatter)?\.(md|json)$`
- Wenn `force=True`: `used_slugs` startet leer (bestehende Drafts werden überschrieben)
- Neuer Test: `test_used_slugs_loaded_from_existing_drafts`

**Commit:** `fix(phase_8): used_slugs aus bestehenden drafts laden`

---

## Task 0F.7 — config.py vollständig (Bug B8)

**Datei:** `pipeline/config.py`

**Problem:** YAML enthält `vault`, `tags`, `logging`, `idempotency`, `memory_watch` — diese fehlen im Pydantic-Modell. Werte werden via `extra="ignore"` silently ignoriert. Konfig-Drift unsichtbar.

### 🛑 App-Checkpoint vor 0F.7 — STOP

```
Block: 0.F
Schritt: 0F.7 vor Implementierung
Frage: extra-Strategie für PipelineConfig — "ignore" (silent), "forbid" (Fehler bei unbekanntem Feld), oder "allow" (durchreichen)?
Empfehlung: "forbid" — sonst bleibt Drift unsichtbar
```

Warte auf Entscheidung.

**Akzeptanzkriterien (Standard-Vorschlag):**
- Neue Pydantic-Modelle in `config.py`:
  - `VaultConfig(use_cluster_number_prefix: bool, generate_cluster_index: bool, validate_wikilinks: bool, attic_folder: str, unsorted_folder: str)`
  - `TagsConfig(vocabulary_file: Path, strict_vocabulary: bool, max_tags_per_article: int, min_tags_per_article: int)`
  - `LoggingConfig(level: str, console_rich: bool, file_json: bool, file_path: Path, log_meta_files: bool)`
  - `MemoryWatchConfig(enabled: bool, warn_threshold_percent: int, pause_threshold_percent: int, check_interval_seconds: int)`
- `IdempotencyConfig` ist bereits vorhanden — verifizieren
- `PipelineConfig` ergänzt um `vault`, `tags`, `logging`, `memory_watch`, `idempotency`
- `${data_root}`-Substitution in `tags.vocabulary_file` und `logging.file_path` muss funktionieren — Test schreiben
- `extra="ignore"` in `PipelineConfig.model_config` durch User-Entscheidung ersetzen
- Bestehende Tests bleiben grün
- Neue Tests:
  - `test_config_loads_vault_section`
  - `test_config_loads_tags_section`
  - `test_config_loads_logging_section`
  - `test_config_loads_memory_watch_section`
  - `test_config_substitutes_data_root_in_tag_vocabulary_path`

**Commit:** `feat(config): alle yaml-sections im pydantic-modell`

### ⏸ App-Checkpoint nach 0F.7

```
Block: 0.F
Erledigt: 0F.1–0F.7
Commit(s): <hashes>
Tests: <count> grün (+5 neue)
Nächster Schritt: 0F.8 (CLAUDE.md Quick-Ref) und 0F.9 (README)
```

---

## Task 0F.8 — CLAUDE.md Quick-Reference fixen (Bug B6)

**Datei:** `/CLAUDE.md` (Root)

**Problem:** Sektion 11 listet:
```bash
python -m pipeline run --confirm
python -m pipeline validate
```
Beides existiert nicht in `__main__.py`.

**Akzeptanzkriterien:**
- `--confirm` aus den Beispielen entfernen
- `validate`-Command:
  - Variante A: aus CLAUDE.md entfernen
  - Variante B: in 0H als separater Task implementieren
  - **Hier:** Variante A (Entfernung). Implementierung wird in Block 0.H entschieden
- `--phase 8` als Beispiel hinzufügen (nach 0F.2 Wiring)
- `--dry-run` als Beispiel hinzufügen
- Verweis auf `docs/06b_tool_routing.md` in Sektion 2 ergänzen
- Änderungs-Log-Eintrag

**Commit:** `docs(claude): quick-reference an cli-realität anpassen + tool-routing verlinken`

---

## Task 0F.9 — README.md Quickstart validieren

**Dateien:** `README.md`, evtl. `pyproject.toml`

**Workflow:**
1. Temporäres Verzeichnis: `/tmp/pkm-quickstart-test`
2. Quickstart aus README durchspielen:
   ```bash
   gh repo clone muentemuente/PKM-rebuild /tmp/pkm-quickstart-test
   cd /tmp/pkm-quickstart-test
   mise install
   mise use python@3.12
   pip install -e .
   python -m pipeline --version
   python -m pipeline status
   ```
3. Schritte die NICHT laufen → README anpassen
4. Fehlende Schritte → ergänzen
5. Test-Verzeichnis löschen: `rm -rf /tmp/pkm-quickstart-test`

**Akzeptanzkriterien:**
- Jeder Befehl im README läuft auf frischem Klon ohne Anpassung
- Falls Änderungen nötig: kurze Begründung in Commit-Message
- README-Verweis auf `docs/tasks/README.md` ergänzen (für Tasks-Übersicht)

**Commit:** `docs(readme): quickstart auf frischem klon validiert`

### 🛑 App-Checkpoint nach 0F.9 — STOP (Block-Abschluss)

```
Block: 0.F ABGESCHLOSSEN
Erledigt: 0F.1–0F.9
Commit(s): <hashes>
Tests: <count> grün (Erwartung ≥226, +4 neue)
Verifikation:
  - `python -m pipeline status` zeigt 1-8 als implementiert
  - `python -m pipeline run --phase 8 --dry-run` läuft
  - `ruff check . && ruff format .` grün
  - `mypy pipeline/` ≤17 Fehler (kein neuer)
  - README-Quickstart auf frischem Klon getestet

Nächster Block: 0.G oder 0.H (parallel möglich)
Frage an App: Block 0.F freigeben für Push? Welcher Block als nächstes?
```

---

## Definition of Done für Block 0.F

- [ ] Alle 9 Tasks 0F.1–0F.9 abgeschlossen
- [ ] `pytest` grün (mind. 226 Tests, +4 neue für Bugfixes)
- [ ] `ruff check . && ruff format .` grün
- [ ] `mypy pipeline/` zeigt keinen neuen Fehler (≤17)
- [ ] `python -m pipeline status` listet Phase 8 als implementiert
- [ ] `python -m pipeline run --phase 8 --dry-run` läuft ohne Fehler
- [ ] PROJECT_STATUS aktualisiert
- [ ] CLAUDE.md aktualisiert
- [ ] README-Quickstart verifiziert
- [ ] User-Freigabe für `git push`
- [ ] `status` im Frontmatter dieses Files auf `done`, Notiz im Body-Footer

## Out-of-Scope für 0.F

- Echter Qwen-Aufruf (Block 8.A)
- `validate`-Command implementieren (Block 0.H, separat)
- Mypy-Schulden in Phasen 2, 3, 6 abtragen (eigener Task, kein Phase-9-Blocker)
- Phase-Reflexionen schreiben (Block 0.H)

---

## Änderungs-Log

- 2026-05-28 — Initial-Version
