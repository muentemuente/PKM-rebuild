# Redundancy-Report (WP2 — Detection, kein Merge)

<!-- input_hash: 3838696a9cfb358c · reproduzierbar, kein Wall-Clock im Body -->

- Docs gescannt: **187**
- Embeddings: **ja (mpnet)**
- Schwellen: TF-IDF≥0.72 · emb-dup≥0.85 · thematic∈[0.7, 0.85)

| Band | Paare |
|---|---:|
| exact | 0 |
| near-dup | 3 |
| semantic-dup | 3 |
| thematic | 52 |

## Dubletten (exact / near / semantic)

| Band | Slug A | Slug B | TF-IDF | Embedding | sources_docs (A→B) | Qwen |
|---|---|---|---:|---:|---|---|
| near-dup | `persoennliches-ci-design-system-macos` | `personal-ci-design-system-macos` | 0.757 | 0.944 | D_design-system-research-1 → D_design-system-research-2,D_design-system-research-1 | — |
| near-dup | `git-github-introduction` | `git-referenz` | 0.801 | 0.871 | D_github-einrichten → D_github-einrichten,D_software-projekt-04-git-konzept-und-setup,D_software-projekt-05-git-workflow | — |
| near-dup | `themenstraenge-debatten` | `wissen-macht-sense-making-infrastrukturen` | 0.845 | 0.720 | D_wissen-macht-sense-making-infrastrukturen → D_denkschulen-und-konzepte | — |
| semantic-dup | `nlp-grundlagen-und-named-entity-recognition` | `nlp-pkm-grundlagen` | 0.264 | 0.929 | D_nlp-01-grundlagen-und-ner → D_nlp-pkm-grundlagen | — |
| semantic-dup | `artikel-template-grundlagen` | `artikel-template-kompaktreferenz` | 0.671 | 0.882 | — → — | — |
| semantic-dup | `regex-text-processing` | `regex-text-transformation` | 0.338 | 0.863 | D_python-05-regex-textverarbeitung → D_python-regex-grundlagen,D_python-05-regex-textverarbeitung | — |

