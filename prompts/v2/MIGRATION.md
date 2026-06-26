# MIGRATION v1 → v2 (Stage 3 restructure)

**Grund:** Typ-bewusstes restructure (WP3c-4). v1 presste jeden Input in das
`knowledge-article`-Erklär-Template → funktionale/kompakte Artefakte (z.B. ein
direkt nutzbarer Prompt) wurden zu *Dokumentation über das Artefakt* umgeschrieben
(Genre-Shift, Funktionsverlust).

**Scope:** Nur der **restructure-Pfad** (`pipeline/restructure.py`, CLI `pkm restructure`)
nutzt v2. Die Phase-8-Synthese bleibt unverändert auf v1 (`qwen.prompt_version: v1`).
v2 wird ausschließlich über `qwen.restructure.prompt_version: v2` aktiviert.

## Diff zu v1

| | v1 | v2 |
|---|---|---|
| Eingabe | Konzept-JSON + Quell-Segmente | `Ziel-type` + Quell-Body (Einzel-File) |
| Struktur | implizit knowledge-article | **type-konditionale Direktive** je `type` |
| `compact-reference` | knapp erwähnt | **verbatim-Nutzbarkeit erhalten, KEINE Umschreibung** |
| `gedanke` | n/a | minimal-invasiv, nicht „ausformulieren" |
| Sampler | temp 0.4 | non-thinking (temp 0.7/top_p 0.8/presence_penalty 1.5, `reasoning_effort:none`) |

**stage4_frontmatter_json.md:** zunächst unverändert aus v1 übernommen (kein
Verhaltens-Change; nur self-contained-Version). **Delta v2 (WP-N2, 2026-06-26):**
drei **additive** Output-Felder ergänzt — `key_points` (NB-4), `open_questions`
(NB-10), `next_steps` (NB-11), jeweils JSON-Array von Strings, **leeres Array erlaubt**.
Prompt-`prompt_version` v1 → v2 gebumpt. Abwärtskompatibel: fehlen die Felder im
Qwen-JSON, mappt das Parsing auf Default-leer (kein Hard-Fail). Das deterministische
`keyphrases`-Feld (NB-3/9/15) wird **nicht** von Qwen erzeugt, sondern von
`pipeline.keyphrase` (KeyBERT) — kein Prompt-Bestandteil.

## Re-Run

Bestehende Drafts werden NICHT retroaktiv migriert (`prompt_version` im Frontmatter
bleibt erhalten). Neu: `pkm restructure --file <path>` erzeugt v2-Drafts mit den
Feldern `type_source` und `restructure_action` in Frontmatter/provenance.
