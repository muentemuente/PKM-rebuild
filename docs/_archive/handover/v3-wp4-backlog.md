---
title: v3 — WP4-Backlog (aus WP3b-Befunden)
slug: v3-wp4-backlog
status: review
created: 2026-06-24
plan: Projektplan_pipeline-v3.md
quelle: TASK_wp3b_synthese-moc.md (Gate A)
---

# WP4-Backlog — aus WP3b abgeleitet

Befunde aus der Synthese (WP3b), die **nicht** additiv lösbar sind und in die
Bestands-Remediation (WP4, vault-mutierend, O4-Backup-Pflicht) gehören.

## 1. Git-Cluster konsolidieren (Redundanz, nicht Synthese)

Der freigegebene Git-Cluster zerfiel im gefilterten Re-Scan: 3 der 4 Git-Docs
(`git-github-introduction`, `git-setup-and-concepts`, `git-workflow-im-alltag`)
lagen bereits in `_attic/` (aussortierte Dubletten), übrig bleibt `git-referenz`
in `14_Automatisierung-…`. **Kein MOC** (D6 additiv löst keine Dubletten).

→ **WP4:** Entscheiden, ob die `_attic`-Git-Docs endgültig entfernt werden und ob
`git-referenz` die kanonische Git-Seite bleibt. Reine Konsolidierung/Cleanup,
keine Synthese.

## 2. Dublette NLP (im MOC vermerkt, hier offen)

`nlp-grundlagen-und-named-entity-recognition` ↔ `nlp-pkm-grundlagen`
(Embedding-Cosine 0.93, semantic-dup). Im MOC `moc-nlp-grundlagen` als
„zu konsolidieren (→ WP4)" markiert, **nicht** aufgelöst.

→ **WP4:** Konsolidierung oder bewusste Trennung entscheiden.

## 3. Wurzelursache Korpus-Filter — Fehlklassifikation (Daten-Qualität)

Der Synthese-Korpus-Filter (WP3b) konnte Projekt-/Eigendokumente **nicht** sauber
ausschließen, weil sie als `type: knowledge-article` in echten Content-Kategorien
liegen — nur Titel/Slug verraten ihre Natur:

| Slug | type (ist) | category | sollte |
|---|---|---|---|
| `metadata-pipeline-project-summary` | knowledge-article | automatisierung-… | Projektdok |
| `metadata-processor-pipeline` | knowledge-article | datenarchitektur-… | Projektdok |
| `metadaten-toolkit-komplette-anleitung` | knowledge-article | datenarchitektur-… | Projektdok |
| `metadata-analyzer-projektauftrag` | knowledge-article | automatisierung-… | Projektdok |
| `metadaten-pipeline-projektauftrag` | knowledge-article | automatisierung-… | Projektdok |
| `metadata-analyzer-idea` | knowledge-article | automatisierung-… | Projektdok/Idee |
| `erweiterte-tag-sammlung` | knowledge-article | wissensmodellierung-… | Vokabular-Sammlung |
| `quotes-idioms-expressions` | knowledge-article | grundlagen | Zitat-Dump |

Folge: diese Docs bilden im Scan Junk-/Projekt-Cluster (vom Owner verworfen),
ließen sich aber per `doc_type`/`category` **nicht** herausfiltern (Slug-Filter
untersagt; Re-Tagging = Vault-Mutation, in WP3b verboten).

→ **WP4:** Im Rahmen der Tag-/Frontmatter-Remediation den `type`/`doc_role` dieser
Dokumente korrigieren (z. B. eigener `doc_type`/Markierung für Projekt-/Meta-Dokumente),
damit Synthese-Folgeläufe sie sauber per Kategorie ausschließen können. Vault-mutierend
→ O4-Backup-Pflicht, Gate.
