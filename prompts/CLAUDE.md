# CLAUDE.md — `prompts/` Subverzeichnis

Working Conventions für Qwen-Prompt-Files in diesem Verzeichnis. Die Regeln aus `/CLAUDE.md` (root) gelten zusätzlich.

---

## 1. Pflicht-Lektüre vor jeder Prompt-Arbeit

In dieser Reihenfolge:

1. `docs/00_persona_muente.md` — Kommunikations- und Arbeitsweise
2. `docs/04_qwen_prompts.md` — Stage-Übersicht, Schemas, Versionierung
3. `docs/03_vault_standard.md` — Frontmatter-Schema und Vokabular-Quelle
4. Bei Schema-Anpassungen zusätzlich: `docs/02_pipeline_spec.md` Sektion 7 (Pydantic-Modelle)

---

## 2. Versionierungs-Schema

| Änderung | Vorgehen |
|---|---|
| Tippfehler, Wortwahl, Klarstellung | Gleiche Version, Git-Commit |
| Neues optionales Feld im Output-Schema | Minor-Bump (z.B. `v1` → `v1.1`), Schema-File aktualisieren |
| Breaking Change am Schema | Neuer Ordner `v2/`, alte Version bleibt erhalten |
| Neue Stage hinzufügen | Major-Bump in neuem Ordner |

Existierende Drafts werden nicht retroaktiv migriert. Ihre `prompt_version` im Frontmatter bleibt erhalten.

Bei einem Major-Bump entsteht ein Migrations-Hinweis in `prompts/v<n>/MIGRATION.md` mit Diff zur Vorversion und Re-Run-Anleitung.

---

## 3. Sprach-Konventionen für Prompts

| Element | Sprache | Begründung |
|---|---|---|
| System-Prompt-Text | Deutsch | Konsistenz mit Korpus und Output |
| Beispiel-Inputs/-Outputs | Deutsch (Inhalt), Englisch (Schema-Keys) | Realistische Beispiele |
| JSON-Schema-Keys | Englisch | Frontmatter-Schema-Konsistenz |
| Enum-Werte | Englisch | `knowledge-article`, `stable`, etc. |
| Stage-Datei-Namen | Englisch (snake_case) | `stage1_cluster_analysis.md` |

Tech-Begriffe werden nicht ohne Not übersetzt: „API-Endpunkt" ja, „Endbenutzeranwendungs-Schnittstelle" nein.

---

## 4. Hard Constraints (unveränderbar)

Diese Regeln schützen Schema-Konsistenz und Reproduzierbarkeit. Sie gelten ausnahmslos.

- **Stage-Output-Schemas werden nicht ohne gleichzeitige Anpassung der Pydantic-Modelle in `pipeline/schemas.py` geändert.** Schema-Drift zwischen Prompt und Pipeline produziert ungültige Outputs, die durch die Validation fallen.
- **`pipeline.config.yaml → qwen.prompt_version` wird erst umgestellt, wenn die neue Version existiert UND gegen alle drei Test-Cluster grün gelaufen ist.**
- **Few-Shot-Beispiele zeigen Goldstandard, nicht Low-Confidence-Outputs.** Schwache Beispiele trainieren schwache Antworten.
- **Output-Format-Beispiele in Prompts sind immer konsistent mit den existierenden `.schema.json`-Files** — nicht „aus dem Bauch" formuliert.

---

## 5. Prompt-File-Struktur

Jedes Prompt-File hat ein YAML-Frontmatter und Sektionen in dieser festen Reihenfolge:

**Frontmatter:**
- `prompt_id`, `prompt_version`, `created`, `updated`
- `target_model`, `expected_input`, `expected_output`
- `output_schema` (Pfad zu `.schema.json`)
- `temperature`

**Sektionen:**
1. `# System-Prompt` — Rolle, Kontext, Verhaltensregeln
2. `# Task` — Konkrete Aufgabe
3. `# Input-Format` — Beschreibung der Input-Struktur
4. `# Output-Format` — JSON-Schema-Auszug + Beispiel-Output
5. `# Beispiele` — 1–3 Few-Shot
6. `# Constraints` — harte Regeln (JSON-only, keine Erläuterungen, etc.)
7. `# Failure-Hinweise` — wie reagiert Qwen bei unklarem Input

Abweichungen von der Reihenfolge brauchen einen expliziten Grund im Commit-Text.

---

## 6. Schema-Konsistenz

Jeder Stage-Output hat eine zugehörige `.schema.json` in `prompts/v<n>/schemas/`. Validierung läuft mit JSON Schema Draft 2020-12.

**Source of Truth:** Pydantic-Modelle in `pipeline/schemas.py`. Die `.schema.json`-Files dokumentieren das Pydantic-Modell maschinenlesbar. Bei Diskrepanz gewinnt Pydantic — die Schema-Datei wird angepasst.

---

## 7. Test-Workflow

### 7.1 Vor Aktivierung einer neuen Version

```bash
# Schema-Test
pytest tests/test_prompt_schemas.py -v

# Regression-Test gegen alle drei Test-Cluster
python -m pipeline test-prompts --version v1.1 --cluster small_clear_cluster
python -m pipeline test-prompts --version v1.1 --cluster large_mixed_cluster
python -m pipeline test-prompts --version v1.1 --cluster contradictory_cluster
```

Alle drei müssen grün sein. Zusätzlich erfolgt eine manuelle Inspektion der Outputs.

### 7.2 Test-Cluster

Drei synthetische Cluster in `tests/fixtures/qwen_clusters/`:
- `small_clear_cluster/` — 3 Segmente, klares Thema
- `large_mixed_cluster/` — 30 Segmente, gemischte Themen
- `contradictory_cluster/` — 5 Segmente mit Widersprüchen

---

## 8. Iterations-Workflow

Beim Verbessern eines Prompts läuft folgender Zyklus:

1. **Hypothese:** „Output X ist zu unspezifisch — Prompt sagt nicht klar genug, dass …"
2. **Snapshot:** aktuellen Prompt + Output kopieren nach `tests/fixtures/qwen_clusters/_baselines/`
3. **Klein-Test:** Prompt anpassen, Re-Run auf einem Test-Cluster
4. **Diff:** `git diff` Prompt + `diff` der Outputs
5. **Entscheidung:** Verbesserung → commit. Verschlechterung → revert.
6. **Reflexion:** Kurz-Notiz in `docs/learnings/PHASE_08_<datum>.md`

Mehrere Änderungen gleichzeitig machen die Ursache-Wirkung unklar — also pro Iteration nur eine logische Änderung.

---

## 9. Eskalation bei Unsicherheit

Reihenfolge:

1. Schema in `prompts/v<n>/schemas/` prüfen
2. Existierende Beispiele in `prompts/v<n>/examples/` lesen
3. Pydantic-Modell in `pipeline/schemas.py` checken
4. User fragen — kompakt, mit konkreter Optionsliste

Prompts „auf Verdacht" zu ändern oder Schemas eigenmächtig zu erweitern sind keine Optionen.

---

## 10. Quick-Reference Befehle

```bash
# Aktive Prompt-Version anzeigen
grep prompt_version pipeline/pipeline.config.yaml

# Versions-Vergleich
diff -r prompts/v1/ prompts/v2/

# Schema gegen Pydantic vergleichen
python -m pipeline validate-prompt-schemas --version v1

# Einzelne Stage manuell testen
python -m pipeline test-stage --stage 1 --batch <path-to-batch> --version v1
```

---

## Änderungs-Log

- 2026-05-25 — Initial-Version (faktisch-deklarativ, Hard Constraints abgegrenzt)
