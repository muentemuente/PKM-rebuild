# Redundancy-Report (WP2 — Detection, kein Merge)

> **generiert/stale (Stand 2026-06-25).** Tool-Output, regenerierbar via `pkm redundancy-scan` (Detection-only, kein Vault-Write).

<!-- input_hash: 6215598fa4da788b · reproduzierbar, kein Wall-Clock im Body -->

- Docs gescannt: **166** (Korpus-Filter: 21 ausgeschlossen)
- Embeddings: **ja (mpnet)**
- Schwellen: TF-IDF≥0.72 · emb-dup≥0.85 · thematic∈[0.7, 0.85)

| Band | Paare |
|---|---:|
| exact | 0 |
| near-dup | 0 |
| semantic-dup | 1 |
| thematic | 39 |

## Dubletten (exact / near / semantic)

| Band | Slug A | Slug B | TF-IDF | Embedding | sources_docs (A→B) | Qwen |
|---|---|---|---:|---:|---|---|
| semantic-dup | `nlp-grundlagen-und-named-entity-recognition` | `nlp-pkm-grundlagen` | 0.260 | 0.929 | D_nlp-01-grundlagen-und-ner → D_nlp-pkm-grundlagen | — |

## Korpus-Filter — 21 Docs ausgeschlossen (Nicht-Wissensartikel)

| Slug | Grund |
|---|---|
| `WAYFINDING` | Ordner 00_Meta |
| `artikel-template-grundlagen` | Ordner 00_Meta |
| `artikel-template-kompaktreferenz` | Ordner 00_Meta |
| `artikel-template-prozessdokument` | Ordner 00_Meta |
| `asset-management` | Ordner 00_Meta |
| `changelog` | Ordner 00_Meta |
| `diagramm-standard` | Ordner 00_Meta |
| `dokumentationsstandard` | Ordner 00_Meta |
| `frontmatter-standard` | Ordner 00_Meta |
| `git-github-introduction` | Ordner _attic |
| `git-setup-and-concepts` | Ordner _attic |
| `git-workflow-im-alltag` | Ordner _attic |
| `naming-conventions` | Ordner 00_Meta |
| `persoennliches-ci-design-system-macos` | Ordner _attic |
| `quellenbewertung` | Ordner 00_Meta |
| `readme` | Ordner 00_Meta |
| `regex-text-processing` | Ordner _attic |
| `review-prozess` | Ordner 00_Meta |
| `tag-system` | Ordner 00_Meta |
| `taxonomie` | Ordner 00_Meta |
| `themenstraenge-debatten` | Ordner _attic |

