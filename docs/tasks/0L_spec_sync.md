---
title: Task 0L Spec-Sync — Docs auf Option B angleichen
slug: 0L-spec-sync
status: stable
created: 2026-05-29
updated: 2026-05-29
block: 0.L-Spec-Sync (Phase I.1)
branch: docs/spec-sync-option-b
---

# Task 0.L Spec-Sync — Projekt-Docs auf Option B angleichen

**Kontext für CC:** Strategie-Entscheidung Block 0.L ist gefallen → **Option B (Pro-Doc-Veredelung)**. Cross-Doc-Synthese ist verworfen (Korpus hat keine inhärente Cluster-Struktur, siehe `data/02_pipeline_output/clustering_analysis.md` + `docs/learnings/GATE_1_review_2026-05-28.md`). Drei führende Docs beschreiben aber noch die alte Cross-Doc-Vision. Dieser Task gleicht sie an.

**Warum dieser Block zuerst:** alle folgenden (autonomen) CC-Blöcke bauen gegen diese Specs. Sie müssen vorher die Wahrheit abbilden.

**Arbeitsmodus:** Dieser Block erfordert menschliches Urteil. CC erstellt Änderungs-**Vorschläge** als Diff, stoppt an jedem 🛑, wartet auf Freigabe. **Keine autonome Umschreibung.**

---

## Pflicht-Lektüre vor Start

1. `/CLAUDE.md`
2. `docs/00_persona_muente.md`
3. `docs/01_strategy.md` (Ziel-Doc 1)
4. `docs/02_pipeline_spec.md` (Ziel-Doc 2)
5. `docs/04_qwen_prompts.md` (Ziel-Doc 3)
6. `docs/03_vault_standard.md` (Referenz, NICHT ändern — bleibt gültig)
7. `docs/tasks/0L_roadmap_option-b.md` (Strategie-Begründung)

---

## Grundprinzip Option B (gilt für alle drei Docs)

| Alt (Cross-Doc-Vision) | Neu (Option B) |
|---|---|
| Phase 8 = 4 Stages (Analyse → Merge → Synthese → Frontmatter) | Phase 8 = **Stage 3 + Stage 4** pro Doc |
| Stage 1 Cluster-Analyse | **entfällt** |
| Stage 2 Merge-Vorschlag | **entfällt** |
| Stage 3 Synthese (mehrere Docs → 1 Concept) | **Stage 3 Pro-Doc-Veredelung** (1 Doc → 1 veredelter Body, KEIN Merge) |
| Stage 4 Frontmatter | unverändert (pro Doc) |
| Review-Gate 2 (Merges) | **entfällt** |
| Review-Gate 3 | bleibt, aber leichter (prüft Veredelung statt Cross-Doc-Korrektheit) |
| `merged_from` befüllt | **immer leer** |
| Cluster = Synthese-Basis | Cluster = reine **Ablage-Heuristik** für Vault-Ordner |

**Stage 3 neu definiert:** nimmt EIN Dokument (alle seine Segmente), normalisiert + strukturiert es nach dem `type`-passenden Template aus `00_Meta/`, verbessert Lesbarkeit. Führt NICHT mehrere Docs zusammen. Code-Blöcke 1:1 erhalten (Regel B4).

---

## 🛑 GATE A — Änderungsplan vorlegen

CC liest die drei Docs, erstellt eine **Liste aller betroffenen Abschnitte** (Doc + Sektion + Art der Änderung) und legt sie vor. **Stop. Warten auf Freigabe**, bevor editiert wird.

Erwartete Treffer (CC ergänzt/korrigiert):

### `docs/01_strategy.md`
- §2 Out of Scope → „Cross-Doc-Synthese / automatisches Merging mehrerer Docs" ergänzen
- §3 DoD Primary → Kriterium „Keine Cluster < 3 Artikel" **entschärfen** (Cluster = Ablage, Mikrocluster/`unsortiert/` erlaubt); NEU: „`merged_from` in allen Vault-Files leer"
- §7 Risiken → R1 (Qwen halluziniert in Synthese) auf Pro-Doc-Kontext entschärfen
- §9 Phasen-Übersicht → Phase 8 von „4 Stages" auf „Stage 3+4 pro Doc" ändern, Zeit-Schätzung anpassen (Stage 1/2 + Gate 2 entfallen)
- §10 → ggf. Erfolgskriterien-Bezug auf Synthese justieren

### `docs/02_pipeline_spec.md`
- §1 Architektur-Diagramm → Stage 1, Stage 2, Review-Gate 2 entfernen; Pfad Phase 7 → Stage 3 → Stage 4
- §6 Phase 8 Detail → Stage 1/2-Blöcke als „entfällt (Option B)" markieren oder entfernen; Stage 3 umdefinieren (Pro-Doc); Akzeptanzkriterien anpassen (`merged_from` leer statt befüllt)
- §10 Review-Gates → Gate 2 entfernen, Tabelle auf 2 Gates reduzieren
- §7 Schema `FrontmatterDraft` → `merged_from` bleibt als Feld (Abwärtskompatibilität), Default `[]`, Kommentar „immer leer in Option B"

### `docs/04_qwen_prompts.md`
- §3 Stage-Übersicht → Stage 1/2 als deaktiviert markieren
- §7 Stage-Details → Stage 1 + Stage 2 Abschnitte entfernen oder als „nicht aktiv (Option B)" kennzeichnen; Stage 3 neu definieren (1 Doc → 1 Body, kein Merge, keine `merged_from`)
- §7 Stage 4 → `aliases`-Herleitung aus `merged_from` streichen (gibt es nicht mehr); Aliases nur aus alternativen Bezeichnungen im Source-Doc
- Review-Gate-2-Erwähnungen entfernen
- Prompt-Dateien `prompts/v1/stage1_*.md` + `stage2_*.md`: **nicht löschen**, sondern Header-Status auf `deprecated: option-a` setzen (Provenance für Lernprojekt)

---

## Änderungs-Regeln (verbindlich)

- **Keine Löschung von Prompt-Files** — deprecated markieren, nicht entfernen (Lernprojekt-Wert)
- `03_vault_standard.md` bleibt **unverändert** (Frontmatter-Schema gilt weiter)
- Jede Änderung mit kurzer Begründung im jeweiligen `## Änderungs-Log`
- Querverweise zwischen Docs nach Änderung prüfen (keine toten Verweise auf Stage 1/2)
- `updated:` im Frontmatter aller geänderten Docs auf 2026-05-29

---

## 🛑 GATE B — Diff-Review pro Doc

Nach Umsetzung: pro Doc `git diff` vorlegen. Mensch prüft, bevor Commit. Drei Commits (einer pro Doc) oder ein gebündelter — Mensch entscheidet an Gate B.

---

## Abschluss

- [ ] Drei Docs konsistent Option B
- [ ] Keine Verweise mehr auf Stage 1/2 / Review-Gate 2 / Cross-Doc-Merge (außer als „deprecated/historisch" markiert)
- [ ] `prompts/v1/stage1_*.md` + `stage2_*.md` als deprecated markiert, nicht gelöscht
- [ ] Querverweise intakt (`rg "Stage 1|Stage 2|Gate 2|merged_from"` zur Kontrolle)
- [ ] Änderungs-Logs aktualisiert
- [ ] Commit(s) auf Branch `docs/spec-sync-option-b`
- [ ] 🛑 finaler Merge nach `main` erst nach Mensch-Freigabe

---

## Nach diesem Block

→ Phase I.2/I.3 (0J.8 Rest + 0.M Reports-Bug), dann Phase II (0.N Autonomie + 0.L-Impl).
Reihenfolge: `docs/tasks/0L_roadmap_option-b.md` §3.

---

## Änderungs-Log

- 2026-05-29 — Initial
