# CLAUDE.md — `prompts/` Subverzeichnis

Working Conventions für Qwen-Prompt-Files in diesem Verzeichnis. Die Regeln aus `/CLAUDE.md` (root) gelten zusätzlich.

> **Aktive Stages (Option B):** Nur **Stage 3** (Pro-Doc-Veredelung, mit Routing passthrough/stage3) + **Stage 4** (Frontmatter, inkl. Gedanken-Variante `stage4_frontmatter_gedanken.md`). Die früheren `stage1_cluster_analysis.md` und `stage2_merge_proposal.md` (Option A, Cross-Doc-Merge, R9) samt ihren `stage1_output.schema.json`/`stage2_output.schema.json` wurden **entfernt** (H1, 2026-07-01) — toter Code, kein aktiver Pfad. Details: `docs/04_qwen_prompts.md`.

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
- **`pipeline.config.yaml → qwen.prompt_version` wird erst umgestellt, wenn die neue Version existiert UND an echten Docs (`pkm process` / `pkm run`) manuell gegen die erwartete Struktur geprüft wurde.** (Eine automatisierte Test-Cluster-Suite existiert nicht — s. §7.)
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

> **Nicht implementiert (Stand 2026-06-25):** Es gibt **keinen** `pkm test-prompts`-/
> `test-stage`-Runner, **kein** `tests/test_prompt_schemas.py` und **keine**
> `tests/fixtures/qwen_clusters/`-Cluster. Diese Sektion beschrieb eine geplante,
> nie gebaute Regression-Suite. Was real existiert: die allgemeine pytest-Suite
> (`pytest`) und die Pipeline-seitige Pydantic-Validation jedes Qwen-Outputs
> (`docs/04_qwen_prompts.md` §8).

### 7.1 Vor Aktivierung einer neuen Version (faktischer Prozess)

```bash
# Gesamte Test-Suite grün?
pytest -q

# Neue Prompt-Version an 1–2 echten Docs erproben
python -m pipeline process --source <dir>     # bzw. pkm run
```

Danach **manuelle Inspektion** der erzeugten Drafts gegen die erwartete Struktur
(`docs/04_qwen_prompts.md` §7). Erst dann `qwen.prompt_version` umstellen.

---

## 8. Iterations-Workflow

Beim Verbessern eines Prompts läuft folgender Zyklus:

1. **Hypothese:** „Output X ist zu unspezifisch — Prompt sagt nicht klar genug, dass …"
2. **Snapshot:** aktuellen Prompt + erzeugten Draft kopieren (z.B. nach `scratch/`)
3. **Klein-Test:** Prompt anpassen, Re-Run auf 1–2 echten Docs (`pkm process`)
4. **Diff:** `git diff` Prompt + `diff` der Drafts
5. **Entscheidung:** Verbesserung → commit. Verschlechterung → revert.
6. **Reflexion:** Kurz-Notiz in `docs/learnings/PHASE_08_<datum>.md`

Mehrere Änderungen gleichzeitig machen die Ursache-Wirkung unklar — also pro Iteration nur eine logische Änderung.

---

## 9. Eskalation bei Unsicherheit

Reihenfolge:

1. Schema in `prompts/v<n>/schemas/` prüfen
2. Pydantic-Modell in `pipeline/schemas.py` checken (Source of Truth, §6)
3. Bestehende Prompt-Files derselben Version als Vorlage lesen (kein `examples/`-Verzeichnis vorhanden)
4. User fragen — kompakt, mit konkreter Optionsliste

Prompts „auf Verdacht" zu ändern oder Schemas eigenmächtig zu erweitern sind keine Optionen.

---

## 10. Quick-Reference Befehle

```bash
# Aktive Prompt-Version anzeigen
grep prompt_version pipeline/pipeline.config.yaml

# Versions-Vergleich
diff -r prompts/v1/ prompts/v2/

# Schema gegen Pydantic vergleichen (manuell — kein CLI-Helfer)
#   prompts/v<n>/schemas/*.schema.json  ↔  pipeline/schemas.py
#   (es gibt KEIN `pkm validate-prompt-schemas` und KEIN `pkm test-stage`)

# Prompt-Version an echtem Doc erproben (es gibt keinen isolierten Stage-Runner)
python -m pipeline process --source <dir>
```

---

## Änderungs-Log

- 2026-05-25 — Initial-Version (faktisch-deklarativ, Hard Constraints abgegrenzt)
- 2026-06-25 — Konsolidierung (verify-first gegen Repo): §7 Test-Workflow als **nicht implementiert** gekennzeichnet (kein `pkm test-prompts`/`test-stage`, kein `tests/test_prompt_schemas.py`, keine `qwen_clusters/`-Fixtures) + auf faktischen Prozess (pytest + manuelle Draft-Inspektion) umgestellt; §4 Aktivierungs-Gate entsprechend; §8/§9 Verweise auf `qwen_clusters/_baselines/` bzw. `examples/` entfernt; §10 Geister-CLIs (`validate-prompt-schemas`, `test-stage`) durch reale Befehle ersetzt
