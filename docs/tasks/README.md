---
title: Aufholarbeit bis Phase 9 — Master-Plan
slug: tasks-readme
status: living-document
created: 2026-05-28
updated: 2026-05-28
---

# Aufholarbeit bis Phase 9 — Master-Plan

Konsolidierte Tasks aus dem Review v2 vom 28.05.2026. Ziel: alle offenen Fragen, Bugs, fehlenden Dokumente und Standards sauber aufholen, bevor Phase 8 erstmals gegen den echten Korpus läuft und Phase 9 startet.

Dieses Verzeichnis ist die Single Source of Truth für alle Tasks bis Phase 9. Pro Block ein File. Status-Updates werden in den jeweiligen Block-Files gepflegt, nicht hier.

---

## 1. Ausgangslage (Stand 28.05.2026)

- **Phasen 1–7:** Code + Tests fertig, **echt gegen 203 Korpus-Files gelaufen** (Outputs in `data/02_pipeline_output/` ab 27.05. 19:25).
- **Phase 8:** Code + Tests fertig, **CLI-Wiring fehlt komplett** (`__main__.py` listet Phase 8 nicht in `_IMPLEMENTED_PHASES`). **Noch nie gegen echten Korpus gelaufen.** `data/03_drafts/` ist leer.
- **Phase 9 + 10:** noch nicht implementiert.
- **Vault-Foundations:** `00_Meta/` leer, kein Tag-Vokabular, keine Templates.
- **Backup-DoD:** Time Machine kaputt (Mount-Code 18), zweites Medium nicht entschieden.
- **Reflexionen:** nur `PHASE_00_setup.md` vorhanden.

---

## 2. Pflicht-Lektüre vor jedem Block

In dieser Reihenfolge:

1. `/CLAUDE.md` (Root)
2. `docs/00_persona_muente.md`
3. `docs/01_strategy.md`
4. Block-spezifisch: `docs/02_pipeline_spec.md`, `docs/03_vault_standard.md`, `docs/04_qwen_prompts.md`, `docs/06_claude_code_workflow.md`, `docs/07_backup_strategy.md`
5. `docs/PROJECT_STATUS.md`

---

## 3. Verteilung App vs. Claude Code

Inhaltlich-kuratierte und strategische Tasks bleiben in der App-Konversation (Mensch-im-Loop). Engineering-Tasks mit klaren Akzeptanzkriterien laufen autonom in Claude Code.

| Kategorie | In der App (Mensch + Claude Pro) | In Claude Code (autonom im Repo) |
|---|---|---|
| Code-Bugs Phase 8 (B1–B8) | — | ✅ |
| CLI-Wiring (Phase 8 + 10) | — | ✅ |
| Doku-Hygiene (Quick-Ref, README) | — | ✅ |
| Berichte-Generator (Phase 10 vorgezogen) | — | ✅ |
| Template-Skelette für `00_Meta/` | Finalisierung | Skelett-Generierung |
| Tag-Inventar-Heuristik | — | ✅ |
| Tag-Vokabular kuratieren | ✅ | — |
| Tag-Vokabular-Validation (Code) | — | ✅ (nach App-Output) |
| Phase-Reflexionen 1–7 | Lessons inhaltlich | Skelett + Output-Stats |
| 15_Gedanken-Sonderpfad | Architektur-Diskussion | Implementierung |
| Cluster-Review (Gate 1) | ✅ | Bericht-Generierung |
| `merge_decisions.json` schreiben | ✅ | — |
| Backup 2. Medium entscheiden | ✅ | — |
| Smoke-Test-Quality-Review | ✅ | Helper-Skript |
| Memory-Pressure-Beobachtung | ✅ | — |
| `PROJECT_STATUS`-Endredaktion | Freigabe | Diff-Vorschlag |

---

## 4. Block-Übersicht

| Block | Titel | Owner | Parallel zu | Datei | Priorität |
|---|---|---|---|---|---|
| 0.F | Code-Fixes Phase 8 + Status + Doku-Hygiene | CC | 0.G, 0.H, 0.I | `0F_code_fixes_status_doku.md` | P0 |
| 0.G | Vault-Foundations (Vokabular, Templates, Gedanken) | App + CC | 0.F, 0.H, 0.I | `0G_vault_foundations.md` | P1 |
| 0.H | Gate-1-Bericht + Berichte-Generator + Reflexionen | CC + App | 0.F, 0.G, 0.I | `0H_gate1_reports_reflections.md` | P1 |
| 0.I | Backup-DoD-Aufholung | App | alle | `0I_backup_dod.md` | P1 |
| 8.A | Phase 8 — Smoke-Test (1 Batch) | Interaktiv | — | `8A_phase8_smoke_test.md` | P0 nach 0.F+0.G+0.H |
| 8.B | Phase 8 — Voll-Lauf (72 Batches) | Interaktiv | — | entsteht nach 8.A | — |
| 8.C | Phase 8 — Reflexion | CC + App | — | entsteht nach 8.B | — |
| 9 | Vault-Aufbau | Implementierung später | — | siehe `docs/02_pipeline_spec.md` | — |

---

## 5. Abhängigkeitsgraph

```
0.F ─┐
0.G ─┼─→ 8.A ─→ 8.B ─→ 8.C ─→ 9
0.H ─┘
0.I (Sidetask, muss vor 9 fertig sein)
```

Innerhalb 0.G ist Reihenfolge bindend (Tag-Inventar → Kuratierung → Validation-Code).

---

## 6. Phasen-Disziplin (ADHS-Schutz)

Jeder Block in max. 4–6h-Sessions. Bei Token-Limit-Nähe sauberer Stop, Snapshot, Resume in nächster Session. Während Qwen-Läufen (8.A, 8.B, 8.C) gilt das App-Hygiene-Protokoll aus `docs/00_persona_muente.md` Sektion 6 (Browser/Mail/Slack zu, nur Zed + Ghostty + LM Studio offen).

---

## 7. Definition of Done — "bereit für Phase 9"

- [ ] Block 0.F: alle Commits gepusht, Tests grün, `python -m pipeline run --phase 8 --dry-run` läuft
- [ ] Block 0.G: `00_Meta/` befüllt, Tag-Vokabular aktiv, 15_Gedanken-Pfad implementiert
- [ ] Block 0.H: drei Reports vorhanden, Gate-1-Entscheidung dokumentiert, 7 Reflexionen vorhanden (mind. Skelett + Stats)
- [ ] Block 0.I: Time Machine läuft, zweites Medium entschieden + gedrillt
- [ ] Block 8.A: 1 Smoke-Batch erfolgreich, Qualität reviewt, Smoke-Reflexion vorhanden
- [ ] Block 8.B + 8.C abgeschlossen, `data/03_drafts/` befüllt, Reflexion vorhanden

---

## 8. Wichtige Conventions für Claude Code

- Commits folgen Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
- Vor `git push`: explizites User-OK in der Session abwarten (siehe `/CLAUDE.md` Sektion 5)
- Bei Unsicherheit: Doku lesen, dann fragen — nicht raten
- Jeder Block wird mit einem oder mehreren Commits abgeschlossen, Block-File-Status auf `done` setzen, kurze Notiz im Body-Footer
- Tests sind Pflicht für Bugfixes (mindestens 1 neuer Test, der den Bug reproduziert hätte)

---

## 9. Änderungs-Log

- 2026-05-28 — Initial-Version basierend auf Review v2
