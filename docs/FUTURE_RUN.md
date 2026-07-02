---
title: FUTURE_RUN — Inkrementeller Standard-Workflow
slug: future-run
status: stable
created: 2026-06-04
updated: 2026-07-02
---

# FUTURE_RUN — Inkrementeller Standard-Workflow

Der Projekt-Erstlauf ist abgeschlossen (181 Artikel + 5 MOC im Vault). Dieses
Dokument ist der **Standard-Workflow für laufende, inkrementelle Verarbeitung**:
neue Notizen erfassen, vault-ready machen, prüfen, in den Vault übernehmen.

Bestehende Artikel werden dabei **nie** erneut verarbeitet (Hash-/Slug-Skip).

> **Orte (s. `WAYFINDING.md`):** #1 Repo `~/projects/aktiv/PKM-rebuild/` · #2 Daten
> `~/projects/aktiv/pkm-pipeline/{input,work,drafts,review,output,archive}` · #3
> Produktiv-Vault `~/Zentrale/09_Brain-Vault/`. CC/Pipeline schreibt nie autonom in #3.

---

## Kanonischer go-forward: `pkm process` (O1)

`process` ist der **primäre** Weg — jedes File (egal welcher Ausgangszustand: fertig,
gescrapt, copy-paste, unformatiert) läuft durch dieselbe feste Stage-Kette bis
`review_ready`. Kein Vorab-Filter, kein Vault-Write, resume-fähig.

```
ingested → normalize → restructure → tags → assets → links → review_ready
         → [human_reviewed] → promoted     ← Owner-Gates, außerhalb des Laufs
```

```
1. Files      neue Roh-.md → pkm-pipeline/input/   (oder beliebiger Quell-Ordner)
2. process    python -m pipeline process --source pkm-pipeline/input/
              → Stage-Kette je File bis review_ready
              → Drafts + Review-Sheet (.xlsx); State: pkm-pipeline/work/process/state.jsonl
              → Wiederaufnahme nach Abbruch: --resume
3. ⏸ REVIEW   Review-Sheet ausfüllen (Mensch): accept / reject / edit je Draft
4. ingest     python -m pipeline review-ingest --sheet <sheet>.xlsx
              → accept → review_status: human_reviewed; reject → archive; edit → Flag
5. 🛑 PROMOTE  python -m pipeline promote --draft <draft>            (dry-run)
              python -m pipeline promote --draft <draft> --execute   (D4-Owner-Gate)
              → Snapshot + Write nach #3 + Index-Regen + Draft-Archivierung
```

**Eigenschaften:** idempotent (unveränderte Datei überspringt erledigte Stages),
resilient (Einzelfehler → Datei `needs_human`, Lauf fährt fort). `process` ruft
**keinen** echten LLM-Call im Orchestrator und schreibt **nie** in den Vault — die
Live-Mutation passiert ausschließlich im gegateten `promote` (D4).

> **Synthese ist nachgelagert,** nicht Teil des Ingest: MOCs/Synthese-Dokumente
> (`pkm synthesize-moc`, Option B) laufen auf bereits vault-ready Files — separates
> WP mit eigenen Gates (D6, additiv).

---

## Vokabular-Pflege (vor/bei Review)

Neue `category` (→ Vault-Ordner) oder neuer Tag tauchen im Review auf. Governed
growth über die Taxonomie-SSoT (`config/`):

| Befehl | Wirkung |
|---|---|
| `python -m pipeline taxonomy add-category <name>` | neue category in `config/categories.yaml` + Vault-Ordner (idempotent, `--dry-run`) |
| `python -m pipeline taxonomy add-tag <tag> --reason "…"` | Tag ins YAML-SSoT (`config/tag_vocabulary.yaml`) + `tag-system.md`-Sync |
| `python -m pipeline taxonomy rename <category\|tag> <old> <new>` | umbenennen + Bestand migrieren (Frontmatter + Ordner + Index) |
| `python3 scripts/manage_vocab.py list \| validate` | Vokabular anzeigen / Drift prüfen (fehlende Ordner, OOV-Tags) |

Alternativ Draft auf bestehende category/Tags umbiegen (Frontmatter-Edit /
`scripts/apply_category_mapping.py`), statt das Vokabular zu erweitern.

---

## Alternative: Option-B Synthese-Linie (`ingest` / `run`)

Die ältere, staging-basierte Linie. Sinnvoll für Batch-/Cluster-Synthese, **nicht**
der kanonische Einzelfile-Ingest.

| Command | Verhalten |
|---|---|
| `python -m pipeline ingest [--dry-run]` | neue .md aus `input/` durch Phasen 1–4 + 8 (Option B) → neue Drafts in `pkm-pipeline/drafts/`; isoliertes Work-Dir, Korpus-Outputs unberührt; Bestands-Slugs übersprungen |
| `python -m pipeline run` | go-forward `input/` → Review-Gates (decisions.md, A–D) → `output/` |
| `python -m pipeline build-vault` | Phase 9: Drafts → `output/<NN_Cluster>/<slug>.md` (Staging) |
| `python -m pipeline corpus-run` | **Legacy** Vollkorpus-Erstlauf (Archiv, nicht go-forward) |

Diese Linie endet in `output/` (Staging); der Übertrag nach #3 ist ein manueller
Schritt (s. `MANUAL_STEPS.md`). `ingest` konsumiert **nicht** die Phasen 5/6/7
(Embedding-Clustering verworfen, R9).

**Voraussetzung realer (nicht-dry) Läufe mit LLM:** LM Studio läuft mit dem
konfigurierten Qwen-Modell (`qwen.endpoint`), übrige Apps geschlossen
(Memory-Pressure, Persona §6).

---

## Backlog — geparkte Erstlauf-Reste

Aus dem Erstlauf, über denselben Workflow nachziehbar.

### 19 `_hold`-Gedanken (`pkm-pipeline/drafts/_hold/`)
Zurückgestellte Gedanken-Drafts, `type: gedanke`. Schema akzeptiert den Wert (E1).
Manifest: `_hold/HOLD_MANIFEST.md`. Verarbeitung über den Gedanken-Sonderpfad
(Minimal-Frontmatter, kein Stage 3).

### 2 Hangs (im `_excluded/`-Set)
- `Prompt-Verbesserung.md` · `prompts_text_stil_grammatik.md`
- **Root-Cause:** Meta-/Prompt-Inhalt triggert im Stage-3-Call einen Reasoning-Loop.
- **Mitigation (H3 gelandet, PR #54):** `_run_text_stage` cappt `max_tokens` je Stage-3-Call
  (`max_tokens_stage3`, config-driven); ein abgeschnittener Output (`finish_reason=length`)
  wird nicht mehr still übernommen, sondern → `needs_human` (reason `output_truncated`), kein
  Draft. Der Hang wird damit zu einem sauberen Skip statt Endlos-Loop. Alternativ weiter: hart
  auf `passthrough` routen. Timeout-Hochsetzen wirkt nicht.

> `denkschulen_ueberblick_und_einfuehrung.md` ist ein bewusst exkludiertes Survey-Doc
> (15.770 Wörter, 394 H2) — **kein** Hang, bleibt außerhalb der Pipeline.

---

## Änderungs-Log

- 2026-06-04 — Initial-Version (Re-Run-Set: 19 Gedanken + 2 Hangs)
- 2026-06-05 — Umgeschrieben zum inkrementellen Standard-Workflow (AP3): `ingest` + `manage_vocab` + Übernahme-Pfad
- 2026-06-25 — Auf **`pkm process` als kanonischen go-forward** umgestellt (O1, code-verifiziert): Stage-Kette → Review-Sheet → `review-ingest` → `promote` (D4). `ingest`/`run` als Option-B-Synthese-Linie eingeordnet; Synthese als nachgelagert klargestellt; tote `data/0X`-Pfade → `pkm-pipeline/`-Layout; Count 180→181; `taxonomy`-CLI ergänzt
- 2026-07-02 — Hangs-Mitigation auf H3-Ist-Stand nachgeführt (PR #54): `max_tokens`-Cap + Truncation→`needs_human` ist implementiert, nicht mehr nur Vorschlag
