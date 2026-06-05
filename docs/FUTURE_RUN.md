---
title: FUTURE_RUN — Inkrementeller Standard-Workflow
slug: future-run
status: stable
created: 2026-06-04
updated: 2026-06-05
---

# FUTURE_RUN — Inkrementeller Standard-Workflow

Der Projekt-Erstlauf ist abgeschlossen (180 Drafts → Vault). Dieses Dokument ist
der **Standard-Workflow für laufende, inkrementelle Verarbeitung**: neue Notizen
in die Inbox legen, durch die Per-Doc-Pipeline (Option B) schicken, Vokabular
pflegen, in den Vault übernehmen.

Die 180 bestehenden Drafts/Vault-Artikel werden dabei **nie** erneut verarbeitet
(Hash-/Slug-Skip).

---

## Standard-Ablauf (inkrementell)

```
1. Files          neue Roh-.md → data/00_inbox/
2. ingest         python -m pipeline ingest
                  → Phasen 1-4 (isoliert) + Phase 8 (Option B) → neue Drafts in 03_drafts/
                  → data/02_pipeline_output/ingest_report.md
3. ⏸ REVIEW       ingest_report.md lesen (Mensch):
                  - neue category (🆕)? → scripts/manage_vocab.py add-category <name>
                  - neue tags (🆕)?     → scripts/manage_vocab.py add-tag <tag> --reason "…"
                  - ODER Draft auf bestehende category/Tags umbiegen
                    (Frontmatter-Edit / scripts/apply_category_mapping.py)
4. build-vault    python -m pipeline build-vault   (ergänzt nur neue Drafts)
5. reports        python -m pipeline reports --force
6. Docs           updated:-Frontmatter der berührten Docs ziehen
7. Korpus         verarbeitete Inbox-Files → data/01_corpus_input/ verschieben
                  (werden Teil des Korpus), danach pkm_triage zum Reconcile
```

**Vorab prüfen (kein Schreiben):** `python -m pipeline ingest --dry-run` zeigt,
welche Inbox-Files verarbeitet würden, ruft kein Qwen auf, schreibt nichts.

**Voraussetzung für den realen (nicht-dry) Lauf:** LM Studio läuft mit dem
konfigurierten Qwen-Modell (`qwen.endpoint`), übrige Apps geschlossen
(Memory-Pressure, Persona §6).

### Was `ingest` macht — und was nicht

| Phase | im ingest? | Grund |
|---|---|---|
| 1 Inventar · 2 Normalisierung · 3 Struktur · 4 Segmentierung | ✅ | nötig für Per-Doc-Synthese |
| 5 Redundanz · 6 Embeddings · 7 LLM-Batches | ❌ | Option B konsumiert sie nicht; Embedding-Clustering verworfen (R9) |
| 8 Qwen-Veredelung (passthrough / stage3 / gedanken) | ✅ | erzeugt die Drafts |

Die Phasen 1-4 schreiben in ein **isoliertes** Work-Dir
(`02_pipeline_output/ingest/`); die korpus-weiten Outputs bleiben unberührt.
Phase 8 schreibt neue Drafts nach `03_drafts/`, bestehende Slugs werden
übersprungen. Zweiter Lauf ohne neue Files = no-op.

### Vokabular-Pflege (`scripts/manage_vocab.py`)

| Befehl | Wirkung |
|---|---|
| `list` | aktuelle Kategorien (→ Ordner) + Tag-Vokabular |
| `validate` | Drift: fehlen Vault-Ordner? Tags außerhalb des Vokabulars? |
| `add-category <name>` | neue category an allen Stellen: `CATEGORY_TO_FOLDER` (+ nächste `NN_`-Nummer), `ALLOWED_CATEGORIES` (abgeleitet), Vault-Ordner, Doku §4. *Appendix-A-Tabelle ggf. manuell.* |
| `add-tag <tag> --reason "…"` | Tag mit Begründung ins Kern-Vokabular (`00_Meta/tag-system.md`) |

`add-*` sind idempotent (bestehende Einträge = no-op) und unterstützen `--dry-run`.

---

## Backlog — geparkte Erstlauf-Reste

Diese Posten stammen aus dem Erstlauf und können über denselben Inbox-Workflow
nachgezogen werden (Inbox-File anlegen bzw. aus `_hold`/`_excluded` ziehen).

### 19 `_hold`-Gedanken (`03_drafts/_hold/`)
Zurückgestellte Gedanken-Drafts, `type: gedanke`. Schema akzeptiert den Wert
(E1). Manifest: `03_drafts/_hold/HOLD_MANIFEST.md`. Verarbeitung über den
Gedanken-Sonderpfad (Minimal-Frontmatter, kein Stage 3).

### 2 Hangs (`01_corpus_input/_excluded/`)
- `Prompt-Verbesserung.md` (`prompt-verbesserung`)
- `prompts_text_stil_grammatik.md` (`prompts-text-stil-grammatik`)

**Root-Cause:** Meta-/Prompt-Inhalt triggert im Stage-3-Call einen
Reasoning-Loop. **Mitigation:** hart auf `passthrough` routen **oder**
Reasoning/`max_tokens` je Call cappen. Timeout-Hochsetzen wirkt nicht.

> `denkschulen_ueberblick_und_einfuehrung.md` ist ein bewusst exkludiertes
> Survey-Doc (15.770 Wörter, 394 H2) — **kein** Hang, bleibt außerhalb der Pipeline.

---

## Änderungs-Log

- 2026-06-04 — Initial-Version (Re-Run-Set: 19 Gedanken + 2 Hangs; E1/E2/Runner-Voraussetzungen; offene Schulden)
- 2026-06-05 — Umgeschrieben zum **inkrementellen Standard-Workflow** (AP3): `00_inbox/` + `pipeline ingest` + `manage_vocab` + Übernahme-Pfad. Erstlauf-Reste als Backlog. Offene Schulden (`_pkm_common`, stage1/2-Config-Prune) sind erledigt (Phase 11).
