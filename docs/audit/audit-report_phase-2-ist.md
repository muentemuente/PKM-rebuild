# Audit Phase 2 — IST-Zustand (objektiv)

**Rolle:** Auditor (read-only). Reine Beobachtung mit Datei:Zeile. Keine Interpretation der Absicht, kein Soll-Abgleich.
**Baseline-Kontext gelesen:** `docs/audit/phase-1-baseline.md`.
**Erfassungsstand:** `git HEAD` (Branch `main`), Repo `pipeline/` (25 Module, 15.337 LOC).

---

## 1. Entrypoints

### 1.1 Konsolen-Entrypoints (`pyproject.toml:64-66`)

| Befehl | Ziel |
|---|---|
| `pipeline` | `pipeline.__main__:cli` |
| `pkm` | `pipeline.__main__:cli` (Alias) |

Beide zeigen auf dieselbe click-Group `cli()` (`__main__.py:336`).

### 1.2 CLI-Befehle (click-Group `cli`, alle in `__main__.py`)

| Befehl | Zeile | Funktion | Docstring (wörtlich) | Default-Write? |
|---|---|---|---|---|
| `run` | 348 | `run` | „go-forward: input/ → (Review-Gates) → output/" | schreibt Drafts/State |
| `corpus-run` | 400 | `corpus_run` | „Legacy-Erstlauf über den Gesamtkorpus (Phasen 1-10, Archiv/Alt-Lauf)" | schreibt work/ |
| `status` | 444 | `status` | „Aktuellen Pipeline-Status anzeigen" | read-only |
| `reports` | 478 | `reports` | „Kontroll-Berichte generieren (corpus, duplicate, cluster)" | schreibt `*_report.md` |
| `build-vault` | 493 | `build_vault` | „Phase 9: Vault aus Drafts aufbauen" | schreibt output/ |
| `ingest` | 508 | `ingest` | „Inkrementell: neue .md aus input/ durch Phasen 1-4 + 8" | schreibt Drafts |
| `review` | 556 | `review` | „Review-Gates: ohne --apply erzeugt es review/decisions.md, mit --apply wendet es an" | `--apply`-gated |
| `format-vault` | 602 | `format_vault_cmd` | „WP3a: Vault deterministisch formatieren — DRY-RUN (raw read-only → work/)" | nur work/ |
| `vault-audit` | 657 | `vault_audit_cmd` | „WP4: read-only Audit über den Vault (9 Regeln) → Befund-Report in work/" | nur work/ |
| `vault-repair` | 707 | `vault_repair_cmd` | „WP4: Safe-Tier-Repairs (raw read-only → work/), idempotent. Kein Vault-Write" | nur work/ |
| `vault-review` | 748 | `vault_review_cmd` | „WP4: Unified-Diff-Patch-Vorschläge für fixable Fälle (kein Auto-Write)" | nur work/ |
| `vault-apply` | 805 | `vault_apply_cmd` | „Phase 1: Transform-Chain auf den Vault anwenden (D4). Default = dry-run" | `--execute`-gated |
| `fence-indented` | 924 | `fence_indented_cmd` | „WP3b: indentierte Code-Beispiele → fenced — DRY-RUN (raw read-only → work/)" | nur work/ |
| `redundancy-scan` | 993 | `redundancy_scan` | „WP2: Vault (read-only) auf Redundanz + Synthese-Potenzial prüfen → Reports" | nur Reports |
| `taxonomy` (Group) | 1060 | `taxonomy` | „Taxonomie-SSoT pflegen (Kategorien/Tags)" | Subcommands |
| `taxonomy add-category` | 1067 | `taxonomy_add_category` | „Neue category in der SSoT anlegen (config + Vault-Ordner)" | `--dry-run`-gated |
| `taxonomy add-tag` | 1088 | `taxonomy_add_tag` | „Neuen Tag DIREKT ins YAML-SSoT aufnehmen" | `--dry-run`-gated |
| `taxonomy rename` | 1113 | `taxonomy_rename` | „OLD → NEW umbenennen und Bestand migrieren" | `--dry-run`-gated |
| `restructure` | 1166 | `restructure` | „review-only: erzeugt einen restructure-Draft via Qwen, schreibt NIE in den Vault" | nur Draft |
| `promote` | 1218 | `promote` | „Promotet einen human_reviewed Draft in den Live-Vault. Default = dry-run" | `--execute`-gated |
| `restructure-batch` | 1295 | `restructure_batch` | „Batch-restructure (review-Tier): erzeugt Drafts + Review-Sheet. KEIN Vault-Write" | nur Drafts/Sheet |
| `review-ingest` | 1356 | `review_ingest` | „Liest Owner-Entscheidungen: accept→human_reviewed … Kein Vault-Write" | Draft-Flags |
| `frontmatter-audit` | 1389 | `frontmatter_audit` | „Read-only Frontmatter-Lücken-Audit (deterministisch, kein LLM, kein Vault-Write)" | nur Report |
| `process` | 1449 | `process` | „Universelle Erstverarbeitung: jedes File → vault-ready bis review_ready. Kein Vault-Write" | nur Drafts/State |

### 1.3 Exponierte API-Funktionen (vom CLI aufgerufen)

| Funktion | Modul:Zeile | Aufgerufen von |
|---|---|---|
| `run_pipeline` | `orchestrator.py:122` | `run` (`__main__.py:351`) |
| `run_ingest` | `ingest.py:162` | `ingest` (`__main__.py:511`) |
| `run_synthesis_flow` | `run_flow.py:107` | `orchestrator`/`ingest` (Synthese-Engine) |
| `apply_to_vault` | `driver.py:259` | `vault-apply` (`__main__.py:822,842,882`) |
| `run_chain` | `driver.py:62` | Chain-Runner (S5), non-mutating |
| `execute_promotion` | `promotion.py:278` | `promote` |
| `process_all` | `process_orchestrator.py` (~257) | `process` |

### 1.4 `apply_to_vault` (explizit angefragt)

- Definition: `driver.py:259`. Signatur `apply_to_vault(target_dir, chain=DEFAULT_CHAIN, *, execute=False, backups_dir=None) -> ApplyReport`.
- **Default `execute=False` = dry-run** (`driver.py:286-294`): berechnet Diffs + Audit-Vorschau, schreibt nichts.
- Tier-Gate (`driver.py:175-185, 285`): `_chain_writable` blockt Write, wenn ein Transform `mutating and tier != TIER_SAFE` ist → dann nur Diff (`writable=False`).
- `execute=True` löst `_execute_d4` aus (`driver.py:220`): Snapshot → Canary (1 Write + Idempotenz-Verify) → bei grün Mass-Write → Audit-Verify.
- CLI-Anbindung: `vault-apply` ruft dry-run (`__main__.py:842`) bzw. mit `--execute` echten Write (`__main__.py:882`).
- Default-Chain `DEFAULT_CHAIN = ("repair-safe", "format-safe")` (`transforms.py:147`).

---

## 2. Realer Datenfluss

### 2.1 Go-forward (`pkm run` → `run_pipeline` → `run_synthesis_flow`)

Input: `.md` in `input/` (`orchestrator.py:70`). Schritte (`run_flow.py:131-230`):

| # | Transform | Was er konkret tut | Output |
|---|---|---|---|
| 1 | Inventar (Phase 1) | sammelt `.md`, SHA-256 + Stats, vergibt `doc_id` (Slug-Kollision → `_2/_3`) | `files_manifest.jsonl` |
| — | intra-run SHA-Dedup | erkennt byte-identische Inputs desselben Laufs über Manifest-SHA (`run_flow.py:60`) | Dedup-Sets |
| 2 | Normalisierung (Phase 2) | CRLF→LF, Tabs→Spaces (außer Code), Trailing-WS, max 3 Leerzeilen, FM-Extraktion, Body-SHA | `cleaned_documents.jsonl` |
| 3 | Struktur + Routing-Signale (Phase 3) | Headings H1–H6, Code-Fences + Sprach-Tag, Tabellen, Links/Wikilinks, Bilder, `doc_type_guess` | `documents_structured.jsonl` |
| 4 | Segmentierung (Phase 4) | Heading-pfad-bewusste Segmente, Token-Cap-Fallback, nie mid-code/table | `segments.jsonl` |
| 4/Qwen | Stage 3 / passthrough + Stage 4 | Routing je Doc → Body (passthrough 1:1 oder Stage-3-LLM-Veredelung) + Stage-4-Frontmatter | `drafts/CK_<slug>.{body.md,frontmatter.json,md}` |

Anschließend Review-Gates (`orchestrator.py`) und `build-vault` (Phase 9) → `output/<NN_Cluster>/<slug>.md`.

### 2.2 Transform-Chain-Kern (S4–S6)

| Schicht | Ort | Funktion |
|---|---|---|
| S4 Transform-Protokoll + Registry | `transforms.py` | `Body → TransformResult(text, changed, report)`; Registry mit `tier`/`mutating` |
| Registrierte Transforms | `transforms.py:191-204` | `repair-safe` (safe, mut.), `format-safe` (safe, mut.), `audit-readonly` (audit, read-only) |
| S5 `run_chain` | `driver.py:62` | verkettet Transforms (Output→Input), rein funktional, kein IO |
| S6 `apply_to_vault` | `driver.py:259` | dry-run/D4-Write auf Vault-Files, tier-gated |

Frontmatter bleibt byte-stabil; Transforms wirken nur auf den Body (`driver.py:16-18`).

### 2.3 Universal-Prozess (`pkm process` → `process_orchestrator.py`)

Stage-Kette (`process_orchestrator.py:56-65`): `ingested → normalize → restructure → tags → assets → links → review_ready`. Terminal = `review_ready` (`:65`), **kein** Vault-Write — Promotion bleibt separater Owner-Aufruf (`:19`).

| Stage | Zeile | Was er konkret tut |
|---|---|---|
| `_stage_normalize` | 153 | FM-Gerüst (Slug) + Body-Hygiene (repair-safe + format-safe) |
| `_stage_restructure` | 162 | typ-bewusstes restructure via Qwen → Draft (Passthrough wenn gut strukturiert) |
| `_stage_tags` | 173 | Tags gegen kontrolliertes Vokabular mappen (Synonyme auflösen, Freitext droppen) |
| `_stage_assets` | 190 | Asset-Behandlung |
| `_stage_links` | ~198 | Link-Behandlung |

---

## 3. Feature-Inventar (je Zeile eine Fähigkeit)

- Markdown-Inventar mit SHA-256, Stats und kollisionsfreier `doc_id`-Vergabe (`phase_1_inventory.py`).
- Body-Normalisierung: CRLF→LF, Tabs, Trailing-WS, Leerzeilen, Frontmatter-Extraktion (`phase_2_normalize.py`).
- Strukturextraktion: Headings, Code-Fences+Sprache, Tabellen, Links/Wikilinks, Bilder, Typ-Heuristik (`phase_3_structure.py`).
- Code-/Tabellen-sichere Segmentierung mit Token-Cap (`phase_4_segment.py`).
- Redundanz-Erkennung Hash + TF-IDF (`phase_5_redundancy.py`).
- Embedding-Erzeugung mpnet-base + Cluster-Vorschläge (`phase_6_embeddings.py`).
- LLM-Batch-Bildung mit Token-Budget-Splits (`phase_7_batches.py`).
- Qwen-Synthese: passthrough / Stage-3 / gedanken-Routing + Stage-4-Frontmatter (`phase_8_synthesis.py`).
- Vault-Aufbau in thematische Ordner inkl. `_index.md` (`phase_9_vault_build.py`).
- Kontroll-Berichte corpus/duplicate/cluster (`phase_10_reports.py`).
- Transform-Chain-Kern mit tier-Gating und D4-Apply (`transforms.py`, `driver.py`).
- Vault-Audit über 9 Regeln read-only (`vault_audit.py`).
- Safe-Tier-Vault-Repair + Unified-Diff-Patch-Vorschläge (`vault_audit.py`, `vault-review`).
- Deterministische Vault-Formatierung via mdformat (`format_vault.py`).
- Indentierte → fenced Code-Block-Konvertierung (`fence_indented.py`).
- Redundanz-/Synthese-Scan über bestehenden Vault (`redundancy_scan.py`).
- Taxonomie-SSoT-Pflege: Kategorie/Tag anlegen + rename mit Bestandsmigration (`taxonomy.py`, `taxonomy_migrate.py`).
- Frontmatter-Lücken-Audit deterministisch, kein LLM (`frontmatter_audit.py`).
- Einzel- und Batch-Restructure via Qwen mit Review-Sheet (`restructure.py`, `batch_restructure.py`).
- Owner-gegateter Draft→Vault-Promote mit Kollisions-Policy (`promotion.py`).
- Universal-Erstverarbeitung über Stage-Kette bis `review_ready` (`process_orchestrator.py`).
- Inkrementeller Ingest aus input/ mit Report (`ingest.py`).
- Browser-Download-Ingest von `.md` (`ingest_md_download.py`).
- Resume-fähiger State über `work/state.json` (`orchestrator.py:48-68`).
- Idempotenz pro Phase via `<output>.meta.json` Input-Hash (durchgängig).

---

## 4. Komplexitätssignale

### 4.1 Umfang

| Metrik | Wert |
|---|---|
| Python-Module in `pipeline/` | 25 (`.py`, ohne `__`) |
| LOC `pipeline/` gesamt | 15.337 |
| Module in `scripts/` | ~21 (zzgl. `.sh`) |
| Test-Dateien / Test-Funktionen | 46 / 699 |

### 4.2 Größte Dateien (`pipeline/`)

| LOC | Datei |
|---:|---|
| 1482 | `__main__.py` |
| 1394 | `phase_8_synthesis.py` |
| 1165 | `vault_audit.py` |
| 762 | `phase_10_reports.py` |
| 741 | `phase_4_segment.py` |
| 672 | `review.py` |
| 620 | `phase_9_vault_build.py` |
| 586 | `redundancy_scan.py` |

### 4.3 Abhängigkeiten (`pyproject.toml:19-46`)

Core: `pydantic`, `pydantic-settings`, `click`, `structlog`, `rich`, `httpx`, `pyyaml`. Markdown: `mistune`, `mdformat`+`-gfm`+`-frontmatter`. Daten/Embeddings: `sentence-transformers`, `scikit-learn`, `pyarrow`, `openpyxl`. LLM: `openai` (LM-Studio-Client). Monitoring: `psutil`.
Optional `viz` (`:58-61`): `umap-learn`, `hdbscan`, `plotly` — **separate Extra-Gruppe, nicht in Core-Deps**.

### 4.4 Toter / kaum verdrahteter Code (Beobachtungen)

- Kein `pipeline/`-Modul ist gänzlich import-los (Minimum: `ingest_md_download`, nur 1 Referenz).
- `ingest_md_download.py` (401 LOC): außerhalb seiner Tests **nicht** importiert; die 2 Treffer in `phase_3`/`phase_9` sind reine Kommentar-Erwähnungen (`phase_3_structure.py:34`, `phase_9_vault_build.py:71`), kein Funktionsaufruf. Kein CLI-Befehl ruft es auf (kein Treffer in `__main__.py`).
- `viz`-Extra (UMAP/HDBSCAN/plotly): in Phase-1-Baseline als „Phase 7b verworfen" vermerkt; im Code als optionale Dependency-Gruppe vorhanden, kein Core-Pfad.
- `corpus-run` (Legacy-Erstlauf, `__main__.py:400`): per eigenem Docstring „Archiv/Alt-Lauf".

### 4.5 Logging-Verdrahtung

- `pipeline.config.yaml:200` deklariert `file_path: "${work}/pipeline.log"`.
- **Kein `structlog.configure(...)`-Aufruf** in `pipeline/` auffindbar (grep leer) → `structlog.get_logger()` nutzt die Default-Konfiguration; die konfigurierte Log-Datei wird nicht nachweislich verdrahtet.

---

## 5. Schreibverhalten

### 5.1 Stellen, die Dateien verändern (Zähler je Modul, write_text/copy/move/unlink)

| Writes | Modul |
|---:|---|
| 8 | `review.py`, `phase_8_synthesis.py`, `__main__.py` |
| 7 | `phase_9_vault_build.py` |
| 6 | `taxonomy_migrate.py` |
| 4 | `process_orchestrator.py`, `phase_10_reports.py`, `format_vault.py`, `fence_indented.py`, `driver.py` |
| 3 | `phase_7_batches.py`, `ingest_md_download.py` |
| ≤2 | `redundancy_scan`, `promotion`, `phase_6`, `phase_5`, `batch_restructure`, `taxonomy`, `restructure`, `phase_4`, `phase_3`, `phase_2`, `phase_1`, `orchestrator`, `ingest` |

### 5.2 Schreibziele nach Klasse

| Ziel | Wer | Default-Verhalten |
|---|---|---|
| `work/` (Zwischendaten, Reports, Diffs) | Phasen 1–10, `format-vault`, `vault-audit/-repair/-review`, `fence-indented`, `redundancy-scan`, `frontmatter-audit` | schreibt direkt; Vault unberührt |
| `drafts/` (Qwen-Outputs) | `phase_8_synthesis.py:721,775,812`, `restructure`, `batch_restructure`, `process` | schreibt Drafts, kein Vault-Write |
| `output/`-Vault | `phase_9_vault_build.py`, `build-vault` | gebauter Staging-Vault |
| Live-Vault (#3) | nur `apply_to_vault` (`--execute`) und `execute_promotion` | **Owner-Gate erforderlich** |

### 5.3 Schutzmechanismen vor Live-Vault-Writes

- **Dry-run als Default:** `apply_to_vault` (`driver.py:286`) und `promote`/`execute_promotion` schreiben ohne `--execute`/`do_execute` nicht (`__main__.py:1245`).
- **Tier-Gate:** nur `safe`-Transforms sind auto-write-fähig; review/audit-mutierende Chains → nur Diff (`driver.py:175-185`).
- **D4-Sequenz vor Mass-Write:** Snapshot → Canary (1 Write + Idempotenz-Verify) → Mass-Write → Audit-Verify (`driver.py:220-255`). Bei rotem Canary Stopp nach 1 Write (`:237`).

### 5.4 Reversibilität / Snapshots

- `snapshot_vault` (`driver.py:188`): vollständige `copytree`-Kopie nach `<target>.parent/_apply_backups/apply_<name>_<ts>` (außerhalb Target).
- `restore_snapshot` (`driver.py:202`): `rmtree(target)` + `copytree(snapshot, target)` — vollständiger Rollback.
- `execute_promotion` legt vor dem Write einen Snapshot an und rollt bei Fehler zurück (`promotion.py:296,304`).
- Shell-Snapshot/Restore zusätzlich in `scripts/snapshot.sh` / `restore.sh`.

### 5.5 Protokollierung der Änderungen

- `structlog`-Events bei Mutation: `apply_snapshot_created` (`driver.py:198`), `apply_executed` (`driver.py:250`), `apply_canary_failed` (`driver.py:244`), `apply_rolled_back` (`driver.py:207`).
- Idempotenz-Protokoll: `<output>.meta.json` mit Input-Hash je Phase (z. B. `phase_8_synthesis.py:147`, `phase_10_reports.py:157`).
- Diff-/Befund-Reports nach `work/`: `diff_report.md` (`__main__.py:620`), Audit-/Redundanz-/Frontmatter-Reports.
- Beobachtung: kein dediziertes persistentes Change-Log-File gefunden; Change-Protokoll = strukturierte Log-Events + Diff-Reports + `.meta.json` (siehe §4.5 zur Log-Datei-Verdrahtung).

### 5.6 Human-in-the-loop-Punkte

| Punkt | Ort |
|---|---|
| Review-Gates `pkm run` | `orchestrator.py` / `review.py` → `review/decisions.md` ausfüllen, dann `review --apply` (`__main__.py:556-582`) |
| `vault-apply` Owner-Gate | `--execute` nötig (`__main__.py:882`) |
| `promote` Owner-Gate | `do_execute`/`--execute` nötig (`__main__.py:1217-1245`) |
| `restructure-batch` → Review-Sheet | `review-ingest` liest accept/reject/edit (`__main__.py:1356`) |
| `process` Terminal `review_ready` | kein Auto-Promote, Promotion separater Aufruf (`process_orchestrator.py:19`) |
| Taxonomie-Änderungen | `--dry-run`-Default bei add-category/add-tag/rename |

---

## Datengrundlage

`pyproject.toml`, `pipeline/__main__.py`, `pipeline/driver.py`, `pipeline/transforms.py`, `pipeline/run_flow.py`, `pipeline/orchestrator.py`, `pipeline/process_orchestrator.py`, `pipeline/ingest.py`, `pipeline/promotion.py`, `pipeline/phase_8_synthesis.py`, `pipeline/phase_10_reports.py`, `pipeline/pipeline.config.yaml`; `find`/`grep`/`wc`-Inventar über `pipeline/`, `scripts/`, `tests/`.
