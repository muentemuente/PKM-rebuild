---
title: "A2a — Owner-Sichtung: NB-Feld-Backfill der 9 Hub-Kandidaten"
slug: a2a-hub-backfill-review
status: review
created: 2026-07-01
updated: 2026-07-01
---

# A2a — Owner-Sichtung: NB-Feld-Backfill (9 Hub-Kandidaten)

Pflicht-Report vor Merge/Promote. Schließt NB-4 (`key_points`), NB-10
(`open_questions`), NB-11 (`next_steps`) für die 9 Q1b-Hub-Kandidaten. **Kein
Vault-Write, kein D4** — dieser Stand endet bei `review_ready` + vorbereiteten
`promote --dry-run`-Befehlen.

## 1. Verify-first-Befunde (relevant für die Bewertung)

- **Schema + v2-Prompt existierten bereits.** `FrontmatterDraft.key_points/
  open_questions/next_steps` (optional, Default `[]`), der Migrations-Test
  (`tests/test_nb_field_layer.py`) und die Felddefinitionen in
  `prompts/v2/stage4_frontmatter_json.md` waren schon da — die Feld-Infrastruktur
  (§4.1 des Tasks) ist bereits gebaut. Den 9 Notes fehlten nur die **Werte** (alle 9
  hatten `key_points`-Count 0).
- **Call-Punkt (§2.2): dedizierter Backfill-Prompt statt v2-Stage-4-Reuse.**
  v2-`stage4_frontmatter_json.md` sieht zwar den vollen Body, erwartet aber
  **Stage-2-Konzept-Metadaten** (`sources_docs`/`source_chunks`) und generiert das
  **komplette** Frontmatter — für einen reinen Feld-Backfill ohne Synthese-Lauf
  ungeeignet (es würde ein Voll-FM halluzinieren, das wir verwerfen müssten). Deshalb:
  `prompts/v2/backfill_nb_fields.md` — sieht denselben vollen Artikel-Body, produziert
  aber **nur** die drei Felder, mit expliziter „leer statt halluzinieren"-Anweisung.
- **Additiv statt Re-Synthese.** `restructure_file` würde das ganze Frontmatter
  **neu** generieren (destruktiv). Stattdessen: byte-chirurgischer additiver Insert
  wie A1b (`backfill_write.py`) — nur die 3 Felder werden ins Frontmatter eingefügt,
  Body + alle Bestandsfelder byte-identisch.

## 2. Owner-Sichtungs-Tabelle (9/9)

| Slug | key_points | open_questions | next_steps | Auffälligkeit |
|---|---:|---:|---:|---|
| moc-nlp-grundlagen | 3 | 0 | 1 | `next_steps` referenziert intern die bekannte WP4-Dublette (aus dem Body gezogen) — inhaltlich korrekt, aber Owner prüfen, ob Projekt-Prozess-Verweise ins FM sollen |
| api-grundlagen | 4 | 0 | 2 | sauber; `next_steps` leicht generisch („Postman-Übungen"), aber artikel-gestützt |
| cli-grundlagen-und-philosophie | 4 | 0 | 0 | sauber; `next_steps` bewusst leer (nichts Substanzielles) |
| gestaltgesetze-ui-ux | 4 | 0 | **6** | meiste `next_steps` (obere Grenze); alle spezifisch, keine Floskeln — Owner ggf. kürzen |
| nlp-pkm-grundlagen | 6 | 0 | 4 | dichter Artikel → 6 key_points (Maximum), alle grounded |
| natural-language-generation-nlg | 5 | 0 | 3 | sauber |
| nlp-grundlagen-und-named-entity-recognition | 6 | 0 | 3 | sauber; NER-Details korrekt |
| gestaltgesetze-design-kommunikation-kunst | 3 | **4** | 3 | einziger mit `open_questions` (4, plausibel); Qwen hat sonst korrekt leer gelassen |
| visual-communication-fundamentals | 5 | 0 | 2 | sauber |

**Aggregat:** key_points 3–6 (nie leer), `open_questions` nur bei 1/9 gesetzt (Qwen
hat die „leer statt halluzinieren"-Regel diszipliniert befolgt), `next_steps` 0–6.
**Keine** leeren `key_points`, **keine** offensichtlichen generischen Floskeln, kein
Halluzinations-Verdacht. Feldinhalte s. `pkm-pipeline/drafts/a2a-hub/*.md`.

### Explizit gemeldete Schwächen (nicht geglättet)
- `gestaltgesetze-ui-ux`: 6 `next_steps` — vollständig, aber am oberen Ende; einige
  überschneiden sich thematisch (Nähe/Figur-Grund/Dashboards).
- `api-grundlagen` / `nlp-pkm-grundlagen`: einzelne `next_steps` sind „Übung/Studium"-
  Vorschläge — actionable, aber näher an How-to als an Synthese-Hebel.
- Kein Draft mit leerem `key_points`, kein Draft mit erfundenen `open_questions`.

## 3. Lauf-Kosten (Live-Qwen, lokal)

- Modell: `qwen/qwen3.6-27b` @ LM Studio (`http://localhost:1234/v1`),
  `reasoning_effort: none`, temp 0.7 / top_p 0.8 / presence_penalty 1.5,
  `max_tokens: 2000` (restructure-Sampler wiederverwendet).
- Wall-Clock: **~17,2 min für 9 Files**, Ø ~115 s/File (Spanne 30–237 s; große Bodies
  wie `nlp-pkm-grundlagen` 4123 W / `nlg` 4372 W dominieren; erster Call inkl.
  Modell-Warmup). Lokales LM Studio → **keine Token-Abrechnung** (kein API-Kostenposten).
- 1 Fehlversuch vorab (YAML-Fold-Truncation-Bug), von `verify_additive` abgefangen —
  **kein** Draft geschrieben, Vault unberührt; Fix + Regressionstest committet.

## 4. `promote --dry-run`-Befehle (bereit für Owner-`!`-Lauf — NICHT ausführen von CC)

**Gate-Hinweis:** `pkm promote` akzeptiert nur `review_status ∈ {human_reviewed,
verified}`. Von den 9 Notes ist **nur `moc-nlp-grundlagen` `human_reviewed`**; die
übrigen 8 sind `ai_drafted`. Die Drafts sind **additiv-only** — sie tragen den
Original-`review_status` unverändert (kein Auto-Promote, Hard Constraint). Der Owner
setzt `review_status: human_reviewed` **nach** Sichtung der 3 Felder, dann greift
`promote`. Kollision ist erwartet (Note existiert) → `--on-collision replace` zeigt den
Diff = **nur** die 3 addierten Felder.

```bash
# Draft-Dir
D=~/projects/aktiv/pkm-pipeline/drafts/a2a-hub

# direkt promotebar (bereits human_reviewed):
python -m pipeline promote --draft "$D/moc-nlp-grundlagen.md" --on-collision replace   # dry-run
# → nach Sichtung + Review: dieselbe Zeile mit --execute (Owner-Gate, D4)

# erst nach Owner-Review (review_status im Draft auf human_reviewed setzen), dann:
python -m pipeline promote --draft "$D/api-grundlagen.md"                        --on-collision replace
python -m pipeline promote --draft "$D/cli-grundlagen-und-philosophie.md"        --on-collision replace
python -m pipeline promote --draft "$D/gestaltgesetze-ui-ux.md"                  --on-collision replace
python -m pipeline promote --draft "$D/nlp-pkm-grundlagen.md"                    --on-collision replace
python -m pipeline promote --draft "$D/natural-language-generation-nlg.md"       --on-collision replace
python -m pipeline promote --draft "$D/nlp-grundlagen-und-named-entity-recognition.md" --on-collision replace
python -m pipeline promote --draft "$D/gestaltgesetze-design-kommunikation-kunst.md"   --on-collision replace
python -m pipeline promote --draft "$D/visual-communication-fundamentals.md"     --on-collision replace
```

(Alle ohne `--execute` = dry-run: zeigen Plan + Diff, schreiben nichts. `--execute`
ist der bewusste Owner-`!`-Schritt und Harness-gesperrt für CC — D-WP4-3.)

## 5. Integritäts-Nachweis

- **Vault byte-identisch:** kein `*.md` im Brain-Vault in der Lauf-Zeit modifiziert
  (`find … -mmin`-Check leer).
- **Additiv byte-stabil:** für alle 9 Drafts gilt `strip_nb_blocks(draft) == Original`
  (Body + Bestandsfrontmatter unverändert, nur die 3 Felder additiv).
- Offline-Suite grün (840 passed / 2 skipped), `ruff`/`mypy` clean.

## 6. Nächster Schritt (Owner)

1. Die 9 Drafts in `pkm-pipeline/drafts/a2a-hub/` sichten (Feldinhalte oben tabelliert).
2. Bei OK: `review_status: human_reviewed` im jeweiligen Draft setzen.
3. `promote --dry-run` (Diff prüfen) → `promote --execute` (D4, `!`-Lauf).
4. Rest der ~156 Notes (nach Readiness gestaffelt) = Folge-Task **A2b**.
