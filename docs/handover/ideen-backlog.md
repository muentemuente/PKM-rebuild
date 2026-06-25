---
title: Ideen-Backlog (out-of-scope Vorhaben)
slug: ideen-backlog
status: review
created: 2026-06-24
updated: 2026-06-24
plan: Projektplan_pipeline-v3.md
---

# Ideen-Backlog

Vorhaben, die bewusst **außerhalb** des aktuellen WP-Scopes geparkt sind. Kein
Commitment, keine Reihenfolge — Owner zieht bei Bedarf in ein eigenes WP.

## B-Monolith → nlp-Serie zerlegen (additiv, eigenes WP)

**Out of WP4** (Owner-Entscheid 2026-06-24). Herkunft: WP4-T2a (`docs/_archive/handover/wp4-t2a-nlp.md`).

- **Befund:** `nlp-pkm-grundlagen` (B, 3953 W) ist ein monolithisches End-to-End-How-To,
  das inhaltlich die **gesamte** kuratierte `nlp-*`-Serie überlappt — nicht nur
  `nlp-grundlagen-und-named-entity-recognition` (A). Serie im KI-Ordner:
  `nlp-grundlagen-und-named-entity-recognition`, `nlp-embeddings`,
  `nlp-topic-modeling`, `nlp-praktische-tools-und-roadmap`, `multimodal-nlp-systems`.
- **WP4-Stand:** A↔B als **(D) distinkt** bestätigt (wechselseitig `related` +
  via `00_Maps/moc-nlp-grundlagen` gebündelt). Keine Mutation.
- **Idee (eigenes WP):** B **additiv** in die Serie zerlegen — Setup/Preprocessing,
  POS, Topic-Modeling, Embeddings/Semantic-Search, Auto-Tagging, Workflows den
  passenden Serien-Bausteinen zuordnen bzw. neue Bausteine anlegen; B danach
  als MOC/Einstieg oder `deprecated` führen.
- **Constraints:** additiv & reversibel, **kein** stiller Content-Verlust
  (Unique-Content-Flag aus T2a), O4-Backup, eigene Gates. Restructure-Scope (≈T4-Natur,
  aber als separates WP, nicht in WP4).
