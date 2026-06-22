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

**stage4_frontmatter_json.md:** unverändert aus v1 übernommen (kein Verhaltens-Change
am Frontmatter; nur self-contained-Version).

## Re-Run

Bestehende Drafts werden NICHT retroaktiv migriert (`prompt_version` im Frontmatter
bleibt erhalten). Neu: `pkm restructure --file <path>` erzeugt v2-Drafts mit den
Feldern `type_source` und `restructure_action` in Frontmatter/provenance.
