# CLAUDE.md — `pipeline/` Subverzeichnis

Working Conventions für Python-Code in diesem Verzeichnis. Die Regeln aus `/CLAUDE.md` (root) gelten zusätzlich.

---

## 1. Pflicht-Lektüre vor jedem Code-Task

In dieser Reihenfolge:

1. `docs/00_persona_muente.md` — Kommunikations- und Lernpräferenzen
2. `docs/02_pipeline_spec.md` — Pipeline-Phasen, Schemas, CLI, Failure-Handling
3. `docs/03_vault_standard.md` — wenn Frontmatter, Vault-Output oder Naming betroffen
4. `pipeline/pipeline.config.yaml` — aktuelle Schwellwerte, Pfade, Settings

---

## 2. Tech-Stack

| Bereich | Tool |
|---|---|
| Python-Version | 3.12 (via `mise`) |
| Schema-Validation | Pydantic v2 |
| In-Memory-Records | Dataclasses (intern), Pydantic (extern/serialisiert) |
| CLI-Framework | `click` |
| Logging | `rich` (Konsole) + `structlog` (JSON-File) |
| Tests | `pytest` |
| Linting + Formatting | `ruff` (Lint + Format) |
| Type-Checking | `mypy` (strict mode) |
| Markdown-Parsing | `mistune` |
| Embeddings | `sentence-transformers` |
| TF-IDF | `scikit-learn` |
| Datenformat | JSONL für Streams, Parquet für Embeddings |
| Qwen-Client | OpenAI-kompatibel via `openai`-Lib gegen LM-Studio |

---

## 3. Code-Konventionen

### 3.1 Type-Hints

Type-Hints sind in allen Funktions-Signaturen vorhanden. Built-ins werden bevorzugt: `list[str]` statt `List[str]`, `str | None` statt `Optional[str]`. Imports aus `typing` nur, wenn nötig.

### 3.2 Pydantic vs. Dataclasses

| Pydantic | Dataclasses |
|---|---|
| Daten von außen (JSON, YAML, User-Input) | Reine Interna ohne Validation |
| Persistierte Daten (JSONL, Parquet) | Kurze lokale Records in einer Funktion |
| Schema-Validation gebraucht | Performance-kritisch bei großen Mengen |
| Default-Values mit Logik | Trivial-Defaults |

### 3.3 Imports

Reihenfolge: Standard-Library → Third-Party → Lokal (`from pipeline.x import y`), mit Leerzeile zwischen Gruppen. `ruff` erzwingt die Reihenfolge.

### 3.4 Naming

- Module: `snake_case`
- Klassen: `PascalCase`
- Funktionen, Variablen: `snake_case`
- Konstanten: `UPPER_SNAKE_CASE`
- Private Hilfen: führender Unterstrich `_helper_function`

### 3.5 Docstrings

Docstrings sind Pflicht für alle öffentlichen Funktionen und Klassen. Format: Google-Style oder reStructuredText, konsistent innerhalb einer Datei. Sprache: Deutsch (Konsistenz mit Persona Sektion 9).

```python
def normalize_document(raw_text: str) -> str:
    """Normalisiert einen Markdown-Text.

    Args:
        raw_text: Roher Markdown-Inhalt als String.

    Returns:
        Normalisierter Text mit LF-Line-Endings, ohne Trailing-Whitespace.

    Raises:
        ValueError: Wenn Input nicht dekodiert werden kann.
    """
```

### 3.6 Logging statt `print()`

Konsolen-Output läuft über `rich`, strukturierte Logs über `structlog`. `print()` hat im Pipeline-Code keine Verwendung — es bricht JSON-Logs und macht Output schwer filterbar.

### 3.7 Pfade über `pathlib.Path`

Pfade werden mit `pathlib.Path` konstruiert, nicht über `os.path`. Hardcoded-Pfade existieren nicht — alle Pfade werden relativ zu `paths.data_root` aus der Config abgeleitet.

### 3.8 HTTP über `httpx`

Synchrone und asynchrone HTTP-Calls laufen über `httpx`. `requests` wird nicht verwendet (Konsistenz mit modernem Stack, Async-fähig).

---

## 4. Hard Constraints (unveränderbar)

Diese Regeln schützen Datenintegrität, Idempotenz und Reproduzierbarkeit. Sie gelten ausnahmslos.

- **Originaldateien in `input/` werden niemals beschrieben, modifiziert oder gelöscht.** Lesen ja, schreiben nein.
- **Pipeline-Outputs werden nur mit `--force`-Flag überschrieben.** Ohne Flag wird bei existierenden Outputs mit gleichem Input-Hash übersprungen (Idempotenz-Regel).
- **Phase-Logik wird so geschrieben, dass jede einzelne Phase isoliert wiederholt werden kann.** Verschachtelte Abhängigkeiten, die das verhindern, sind nicht zulässig.
- **Pydantic-Schemas werden nicht ohne gleichzeitige Aktualisierung von `docs/02_pipeline_spec.md` Sektion 7 geändert.** Schema-Drift zwischen Code und Doku führt zu falschen Validierungen in der Pipeline.
- **Neue CLI-Befehle oder neue Flags werden nicht ohne Aktualisierung von `docs/02_pipeline_spec.md` Sektion 4 eingeführt.**

---

## 5. Idempotenz-Regel

Jede Phase folgt diesem Muster:

1. **Vor Lauf:** Hash der Inputs berechnen
2. **Prüfen:** Existiert Output + `<output>.meta.json` mit gleichem Input-Hash?
   - Ja → skip mit Log-Eintrag, Exit-Code 0
   - Nein → ausführen
3. **Nach Lauf:** Output + `<output>.meta.json` schreiben

**Format `<output>.meta.json`:**
```json
{
  "phase": "phase_4_segmentation",
  "input_hash": "sha256:...",
  "output_hash": "sha256:...",
  "created_at": "2026-05-25T14:30:00Z",
  "duration_seconds": 12.5,
  "pipeline_version": "0.1.0",
  "config_snapshot": { /* nur Phasen-relevante Settings */ }
}
```

**Test:** Zweimaliger Lauf auf gleichem Input erzeugt identische Output-Hashes.

---

## 6. Logging-Standards

### 6.1 Format

- Konsole: `rich` mit Farben + Progress-Bars (für interaktive Sessions)
- File: `structlog` JSON Lines → `work/pipeline.log`

### 6.2 Event-Struktur

```python
import structlog
log = structlog.get_logger()

log.info(
    "exact_duplicate_found",
    phase="phase_5_redundancy",
    doc_ids=["D_yaml-frontmatter", "D_yaml-fm-copy"],
    similarity=1.0,
)
```

### 6.3 Level-Disziplin

| Level | Verwendung |
|---|---|
| `DEBUG` | Innere Schleifen, Detail-Werte, nur on-demand |
| `INFO` | Phasen-Übergänge, Datei-Counts, Hauptergebnisse |
| `WARNING` | Skip-Cases, ungewöhnliche Werte, leere Cluster |
| `ERROR` | Failures pro File (Pipeline läuft weiter), ungültige Inputs |
| `CRITICAL` | Pipeline-Abbruch (Endpoint weg, kritischer Konfig-Fehler) |

---

## 7. Tests (`pytest`)

### 7.1 Struktur

```
tests/
├── conftest.py                       # Fixtures
├── fixtures/
│   ├── sample_corpus/                # 10 synthetische .md
│   └── qwen_clusters/                # Test-Cluster für Prompt-Tests
├── test_phase_1_inventory.py
├── test_phase_2_normalize.py
├── ...
├── test_phase_9_vault.py
├── test_schemas.py
├── test_idempotency.py
└── test_cli.py
```

### 7.2 Pflicht-Test-Cases

- Schema-Validation (Pydantic): gültige + ungültige Inputs
- Normalisierung: Code-Blöcke bleiben hash-identisch
- Segmentierung: keine zerrissenen Code-Blöcke
- ID-Generierung: Slug-Kollision → Suffix `_2`, `_3`
- Idempotenz: zweimaliger Lauf identische Outputs (Hash-Vergleich)
- Sample-Modus: läuft auf 10 Fixture-Files durch
- CLI: jeder Befehl bricht mit hilfreichem Fehler bei fehlenden Argumenten ab

### 7.3 Coverage

Ziel: >80% für Pipeline-Code. Tool: `pytest --cov=pipeline --cov-report=html`.

---

## 8. CLI-Patterns

### 8.1 Befehl-Struktur

```python
# pipeline/__main__.py
import click

@click.group()
def cli():
    """PKM-rebuild Pipeline."""
    pass

@cli.command()
@click.option("--sample", type=int, help="Sample-Modus mit N Files")
@click.option("--phase", type=int, help="Nur diese Phase")
@click.option("--from-phase", type=int, help="Ab dieser Phase bis Ende")
@click.option("--force", is_flag=True, help="Cache ignorieren, alles neu")
@click.option("--dry-run", is_flag=True, help="Plan zeigen, nichts schreiben")
@click.option("--config", type=click.Path(exists=True), default="pipeline/pipeline.config.yaml")
def run(sample: int | None, phase: int | None, from_phase: int | None,
        force: bool, dry_run: bool, config: str):
    """Pipeline-Lauf starten."""
    ...
```

### 8.2 Output

Tabellen über `rich.table.Table`. Bei Fehlern: Exit-Code != 0, klare Fehlermeldung auf STDERR. `--dry-run` zeigt, was passieren würde, schreibt aber nichts.

---

## 9. Konfigurations-Disziplin

Alle Pipeline-Schwellwerte und Parameter leben in `pipeline/pipeline.config.yaml`. Der Code liest sie über eine Pydantic-Settings-Klasse:

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class SegmentationConfig(BaseModel):
    min_words_per_segment: int
    max_words_per_segment: int
    target_words_per_segment: int
    preserve_code_blocks: bool
    preserve_tables: bool
    preserve_lists: bool

class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file="pipeline/pipeline.config.yaml"
    )
    paths: PathsConfig
    segmentation: SegmentationConfig
    redundancy: RedundancyConfig
```

Wenn ein Config-Wert fehlt, schlägt die Pydantic-Validation fehl. Stille Default-Werte im Code sind ein Anti-Pattern — die Pipeline soll bei fehlender Konfiguration laut werden.

---

## 10. Failure-Handling

Aus `docs/02_pipeline_spec.md` Sektion 9:

| Fehler | Verhalten |
|---|---|
| Einzelne Datei nicht lesbar | `errors.jsonl`-Eintrag, Pipeline läuft weiter |
| Qwen-Endpoint weg | Retry mit Backoff (3x), dann Pipeline-Pause + Snapshot |
| Qwen-Output Schema-Validation-Fail | `confidence: low` setzen, in `needs_human.jsonl`, weiterlaufen |
| Memory-Pressure detected (psutil) | User-Prompt: „RAM knapp, weiter?" |
| Critical Config-Fehler | Pipeline-Abort vor Lauf, klare Fehlermeldung |

Globaler State: `work/pipeline_state.json` mit aktueller Phase + Position für Resume.

---

## 11. Eskalation bei Unsicherheit

Reihenfolge:

1. `docs/02_pipeline_spec.md` für die betroffene Phase prüfen
2. Bestehende Phase-Implementierung als Vorlage ansehen
3. `pipeline.config.yaml` für relevante Defaults
4. Test-Fixture in `tests/fixtures/` für erwartetes Input/Output
5. User fragen — mit konkreter Optionsliste

Pydantic-Modelle „auf gut Glück" zu erweitern, Schemas ohne Doku-Update zu ändern oder Magic Numbers einzubauen sind keine Optionen.

---

## 12. Quick-Reference Befehle

```bash
# go-forward (kanonisch, O1)
python -m pipeline process --source pkm-pipeline/input/   # universelle Erstverarbeitung → review_ready
python -m pipeline review-ingest --sheet <sheet>.xlsx     # Owner-Entscheidungen einlesen
python -m pipeline promote --draft <draft> --execute      # D4-Vault-Write (Owner-Gate)

# Option-B-Linie / Legacy
python -m pipeline run                                    # input/ → Review-Gates → output/
python -m pipeline ingest [--dry-run]                     # Phasen 1-4 + 8 (Option B)
python -m pipeline corpus-run --phase 1                   # Legacy-Vollkorpus (auch --from-phase / --sample N)
python -m pipeline build-vault [--dry-run]

# Status & Reports
python -m pipeline status
python -m pipeline reports [--force]

# Tests
pytest -v
pytest tests/test_phase_5_redundancy.py -v

# Qualität
ruff check pipeline/ tests/ && ruff format pipeline/ tests/
mypy pipeline/
```

---

## Änderungs-Log

- 2026-05-25 — Initial-Version (faktisch-deklarativ, Hard Constraints abgegrenzt)
- 2026-06-25 — §12 Quick-Reference auf reale CLI (kanonisch `process`/`review-ingest`/`promote`; `run`/`ingest`/`corpus-run` getrennt; nicht-existentes `validate` entfernt)
