---
title: Projektplan pkm-pipeline v2 — File- & Vault-Qualität + Anpassbarkeit
slug: projektplan-pipeline-v2-quality
status: superseded
superseded_by: Projektplan_pipeline-v3.md
created: 2026-06-15
updated: 2026-06-23
zweck: Optimierung der bestehenden Pipeline. Primär P1 (Taxonomie-SSoT) + P5 (Redundanz/Synthese-Erkennung); danach P2 (Formatierung) + P3 (Vault-Audit/Repair); P4 konditional; P6 gestrichen.
scope_basis: erweitert die bestehende pkm-pipeline (Option B), kein From-Scratch-Rebuild
---

> [!warning] Archiviert — superseded
> Dieser Plan ist **abgelöst durch `docs/Projektplan_pipeline-v3.md`** (2026-06-23). v3 übernimmt die offenen v2-Aufgaben und ergänzt additive Synthese (D6) + Bestands-Remediation. **Nur v3 ist aktiv.** Dieses Dokument bleibt als Historie erhalten.

# Projektplan pkm-pipeline v2

**Charakter:** Erweiterung des bestehenden Repos, nicht Neubau. Bestehende Architektur (Pro-Doc-Veredelung, slug-IDs, Pydantic, Phasen 1–10, `scripts/`) bleibt tragend.
**Rollen:** Claude (App) = Architect/PM/Mastermind (Plan, Entscheidungen, Reviews, Scope-Warnungen). Claude Code (CC) in Zed = autonome Umsetzung im Repo.
**Stand-Vorbehalt:** Alle Zahlen aus `PROJECT_KNOWLEDGE` (2026-06-15), nicht live verifiziert → WP0 verifiziert zuerst.

---

## 0. Scope

| In Scope | Out of Scope |
|---|---|
| P1 Taxonomie-SSoT + governed growth + Migration | P6 (Content-/Asset-Anreicherung) — gestrichen |
| P5 Redundanz-/Synthese-**Erkennung + Report** | Auto-Merge / automatische Synthese (`merged_from` bleibt leer) |
| P2 deterministische Formatierung + stage3-Re-Run | Vector-DB (Qdrant/LanceDB) — bei Korpusgröße unnötig |
| P3 Vault-`audit`/`repair`/`review`-Modus | Polyglot Node-Toolchain als Pflicht (s. D3) |
| P4 **konditional** (Gate nach WP1–4) | hierarchische Slash-Kategorien (s. D1) |

**Unangetastet:** E1–E5 (locked), Pro-Doc-Routing (passthrough/stage3/gedanken), Daten außerhalb Git, PR-Workflow.

---

## 1. Architektur-Entscheidungen (für diesen Plan verbindlich)

| ID | Entscheidung | Begründung |
|---|---|---|
| **D1** | **Ein SSoT** `pipeline/taxonomy.yaml` → generiert `ALLOWED_CATEGORIES`, `CATEGORY_TO_FOLDER`, Tag-Vokabular, Validierung. Pydantic wechselt von `Literal`-Enum auf **Runtime-Membership-Check** gegen SSoT. `category` bleibt **flach + single** (governed growth), `gedanke`-Type erhalten. | tötet 3-Stellen-Drift (`categories.yaml`↔`CATEGORY_TO_FOLDER`↔`check_frontmatter`) **strukturell**; Erweiterung = 1 Edit ohne Code-Change. Flach statt Slash-Hierarchie = kein Taxonomie-Wildwuchs, kompatibel mit Naming-Convention. |
| **D2** | **P5 = Detection + Report only.** Reuse Hash (Phase 5) + TF-IDF (Phase 5) + **Reaktivierung Embedding-Code** (Phase 6) für *paarweise* Similarity. **Kein** Vector-DB → `numpy`/`scikit-learn` in-memory. Kein Auto-Merge, `merged_from` leer. | bei ~200–400 Files ist Vector-DB Over-Engineering. Detection ≠ das verworfene Auto-Clustering → 96,5 %-Finding entkräftet Erkennung nicht. **Erfordert Strategy-Doc-Update (Teil-Reversal Option B, R12).** |
| **D3** | **P2 deterministisch via `mdformat`** (+`mdformat-gfm`, +`mdformat-frontmatter`) — pure Python, idempotent-by-design. Obsidian-Syntax (Callouts/Wikilinks/Embeds/Codeblöcke) als **Schutzbereiche**. Semantische Restrukturierung = **stage3-Re-Run-Pfad**, kein neues LLM-Stage. | pure-Python vermeidet Polyglot-Risiko (Persona = Python). `mdformat`-Idempotenz adressiert die Tool-Konflikt-/Idempotenz-Spannung direkt. stage3 kann Restrukturierung bereits. |
| **D4** | **Vault-Mutation (P2/P3) nur über 3-State raw/work/export** + Snapshot-before + **Safe-auto vs. Unsafe-Review**-Trennung. | Vault liegt außerhalb Git und enthält manuelle Reviews → Datenintegrität ist das höchste Risiko. |
| **D5** | **P4 konditional**: Gate nach WP1–4. Nur Verbesserung der bestehenden Stage-4-Klassifikation + Confidence-Review, kein neues Klassifikationssystem. | Modell-Ceiling: reduzierbar, nicht eliminierbar. Erst messen, ob nach P1/P5 noch Potenzial offen ist. |

---

## 2. Zu bestätigen (nur Owner — STOP für CC bis Freigabe)

| # | Frage | Architect-Default |
|---|---|---|
| O1 | **Option-B-Teil-Reversal** für P5 (Erkennung+Report, kein Auto-Merge) freigegeben? | ja |
| O2 | `category` bleibt **flach/single** (D1)? | ja |
| O3 | Formatierung **pure-Python `mdformat`** statt Node-Toolchain (D3)? | ja |
| O4 | **2. Backup-Medium** (offener Backup-DoD-Rest) wird **vor** der ersten vault-mutierenden Ausführung (WP3) hergestellt? | Pflicht, ja |

Ohne O1–O4 startet CC nur WP0 + WP1-Design (beide vault-non-mutierend).

---

## 3. WP0 — Vorbedingungen (vault-non-mutierend)

| Aufgabe | Kommando / Ergebnis |
|---|---|
| Stand verifizieren | `python3 scripts/pkm_triage.py \| tail -15`, `check_frontmatter.py`, `git status` (main clean) |
| **F1 prüfen** | `check_frontmatter.py` → `ALLOWED_TYPE` enthält `gedanke`? Wenn nein = reale Enum-Drift, in WP1 mit SSoT subsumiert |
| Snapshot | `bash scripts/snapshot.sh` (Korpus + Vault + State) |
| Backup-2nd-Medium | O4 herstellen + Recovery-Stichprobe (DoD-Rest schließen) |
| Strategy-Doc | `docs/01_strategy.md`: Scope-Update P5 (Option-B-Teil-Reversal dokumentieren, R12) |
| Branch | `git switch -c feat/pipeline-v2-foundation` |

**REVIEW-Gate 0:** Stand grün + O1–O4 freigegeben → WP1.
**Sessions:** ~1 (Backup-Medium ggf. separat).

---

## 4. WP1 — P1: Taxonomie-SSoT (primär)

**Ziel:** Kategorien + Tags zentral, generiert, billig erweiterbar; Drift strukturell beseitigt.

| Aspekt | Inhalt |
|---|---|
| **CC-Aufgaben** | 1. `pipeline/taxonomy.yaml` (16 Kategorien + Ordner-Mapping + 149 Tags + Synonym-Map). 2. `pipeline/taxonomy.py` Loader → exposiert Enums/Mapping/Vokabular. 3. Pydantic `FrontmatterDraft`: `Literal`→Runtime-Validator gegen Loader; `gedanke` aufnehmen. 4. `scripts/_pkm_common.py` extrahieren (Backlog: Dup-Helfer + Enums) → alle Skripte importieren aus SSoT. 5. `pkm taxonomy add-category/add-tag/rename` CLI inkl. Migration (Frontmatter + Ordner-Move + `_index.md`-Regen + Validierung gem. §10-Regeln). 6. Tests. |
| **Out** | freie/hierarchische Kategorien; automatische Tag-Erfindung ohne SSoT-Eintrag |
| **Akzeptanz** | SSoT einzige Quelle; `check_frontmatter` + Pydantic + Mapping importieren daraus (0 Dup-Enum); neue Kategorie/Tag = 1 YAML-Edit + Migration grün; alle Bestands-Tests + neue Tests grün; `pkm_triage` 0 Orphans |
| **Risiken** | Runtime-Validator vs. statische Typprüfung (mypy) → Membership-Check sauber typisieren |
| **STOP** | Merge nach main |
| **Sessions** | 2–3 |

**REVIEW-Gate 1:** SSoT + Migration an einer Test-Kategorie verifiziert.

---

## 5. WP2 — P5: Redundanz-/Synthese-Erkennung (primär)

**Ziel:** Korpus/Vault auf Dubletten + Synthese-Potenzial prüfbar machen — als Report, nie als Auto-Aktion.

| Aspekt | Inhalt |
|---|---|
| **CC-Aufgaben** | 1. Phase 5 reuse (exakt = SHA-256, near = TF-IDF). 2. Embedding-Code (Phase 6) reaktivieren → paarweise Cosine, Schwellen aus `config`. 3. Klassifikation: exakte/Near/semantische Dublette · thematische Überschneidung · Synthese-Kandidat (≥3 verwandte). 4. Optional Qwen-Bewertung pro Kandidaten-Paar (low temp, JSON, Schema-validiert). 5. Reports: `redundancy_report.md`, `synthesis_candidates.md` (mit Provenance, Scores, Vorschlag-Status). 6. Tests inkl. Fixtures. |
| **Out** | Auto-Merge, automatisches Löschen, `merged_from`-Autofill, Vector-DB |
| **Akzeptanz** | Reports reproduzierbar/idempotent; jeder Kandidat mit Score + Quellen; 0 stille Vault-Änderung; Qwen-Bewertung (falls an) Schema-valide; Strategy-Doc-Scope aktualisiert |
| **Risiken** | Embedding-Qualität DE (mpnet multilingual ok, Fallback TF-IDF); Qwen-Hangs (json_mode=false / max_tokens-Cap als Mitigation); Memory-Hygiene bei Qwen-Lauf |
| **STOP** | Merge nach main; Schwellen-Tuning als Architektur-Weiche (Gate 1-Style) |
| **Sessions** | 3–4 |

**REVIEW-Gate 2:** Du prüfst Reports an Stichprobe — sind Kandidaten plausibel? Schwellen okay?

---

## 6. WP3 — P2: Einheitliche Formatierung (folgend, **erste vault-mutierende Stufe**)

**Ziel:** „unsaubere" Files deterministisch normalisieren; prosa-lastige optional via stage3 restrukturieren.

| Aspekt | Inhalt |
|---|---|
| **CC-Aufgaben** | 1. `mdformat`-Integration (+gfm,+frontmatter), Config + Obsidian-Schutzbereiche (Callouts/Wikilinks/Embeds/Code). 2. 3-State raw/work/export (D4): Original → Arbeitskopie → geprüfter Export. 3. Safe-auto (Whitespace/Header/Listen/Fences/YAML-Sort) direkt; Unsafe (Heading-Änderung, Strukturumbau, Codeblock-Edit) → Patch-Vorschlag. 4. stage3-Re-Run-Pfad für `stage3`-geroutete Files: bumpt `doc_version`/`last_synthesized`, Status bleibt draft/review (kein Auto-stable). 5. `diff_report.md`. 6. Idempotenz-Test (2. Lauf = keine/nur Status-Änderung). |
| **Out** | globales blindes Prettier; Auto-stable; Format-Eingriff in Schutzbereiche |
| **Akzeptanz** | Idempotenz nachgewiesen; Schutzbereiche unverändert; Unsafe nie ohne Review; Snapshot-before zwingend; alle Wikilinks danach auflösbar |
| **Risiken** | mdformat kennt Obsidian-Syntax nicht → Schutzbereiche hart testen (Golden-File-Fixtures); Datenintegrität (vault-mutierend) |
| **STOP** | Merge nach main; **jede** vault-schreibende Ausführung erst nach Snapshot + Review-Gate |
| **Sessions** | 2–3 |

**REVIEW-Gate 3:** Diff/Patch-Vorschläge freigegeben → Export.

---

## 7. WP4 — P3: Vault-Audit/Repair/Review-Modus (folgend)

**Ziel:** Bestehenden Vault halbautomatisch bereinigen statt manuell — Engine zeigt auf `04_vault`.

| Aspekt | Inhalt |
|---|---|
| **CC-Aufgaben** | 1. Modi: `audit` (read-only Befund), `repair` (Safe-auto), `review` (Patch-Vorschläge Unsafe). 2. Bestehende Phasen (Lint/Frontmatter/Link/Format aus WP3) auf Vault-Input umlenken. 3. `audit_report.md` + Datei-Statusliste + `quarantine`-Pfad für nicht-parsebare Files. 4. Reuse WP1-Validierung + WP3-3-State. 5. Tests. |
| **Out** | autonome Bulk-Promotion draft→stable; Löschen ohne Review (archive-before-delete) |
| **Akzeptanz** | `audit` ändert nichts; `repair` nur Safe-Set; `review` erzeugt nachvollziehbare Patches; Snapshot-before; SHA-256-Dubletten 0; `pkm_triage` 0 Orphans |
| **Risiken** | höchste Datenintegritäts-Exposition → Guardrails (D4) non-negotiable |
| **STOP** | Merge nach main; jede `repair`/Export-Ausführung erst nach Snapshot + Gate |
| **Sessions** | 3–4 |

**REVIEW-Gate 4:** Audit-Report + Repair-Diff freigegeben.

---

## 8. WP5 — P4: Klassifikations-Optimierung (KONDITIONAL)

**Trigger:** nur wenn WP1–4 funktionsfähig **und** Messung (WP2-Reports + Re-Klassifikations-Stichprobe) zeigt offenes Potenzial.

| Aspekt | Inhalt |
|---|---|
| **CC-Aufgaben** | Stage-4-Prompt-Iteration (Few-Shot, SSoT-Vokabular in-context) + Confidence-Gate (low → Review) + Re-Classification-Audit-Report; optional schmaler Embedding-Nearest-Category-Assist |
| **Akzeptanz** | messbar reduzierte Fehlzuweisung an Validierungs-Stichprobe; kein neues System |
| **Sessions** | 1–2 |

**REVIEW-Gate 5:** Vorher/Nachher-Vergleich an Stichprobe.

---

## 9. Sequenz & Abhängigkeiten

```
WP0 (Vorbedingungen)
   └─ Gate0 + O1–O4
        ├─ WP1 (P1 SSoT)  ──┐  (unblockt WP5)
        └─ WP2 (P5 Detection)│  (unabhängig, parallel reviewbar)
                             ▼
                   WP3 (P2 Format)  ← erste Vault-Mutation, braucht O4
                             ▼
                   WP4 (P3 Audit/Repair)
                             ▼
                   WP5 (P4) — nur wenn Trigger
```

| WP | Hängt ab von | Vault-mutierend |
|---|---|---|
| WP0 | — | nein |
| WP1 | WP0 | nein |
| WP2 | WP0 (WP1 empfohlen für saubere Report-Labels) | nein |
| WP3 | WP1, O4 | **ja** |
| WP4 | WP3 | **ja** |
| WP5 | WP1–WP4 + Trigger | ja (klein) |

**Realistic gesamt (ohne WP5):** ~11–15 Sessions à 4–6 h.

---

## 10. Risiken & Gegenmaßnahmen

| ID | Risiko | Gegenmaßnahme |
|---|---|---|
| RV1 | Vault-Datenverlust (außerhalb Git, manuelle Reviews) | Snapshot-before · 3-State · Safe/Unsafe-Trennung · O4-2nd-Medium · archive-before-delete |
| RV2 | Idempotenz-Bruch durch Formatierung | `mdformat` idempotent-by-design · Idempotenz-Test als Akzeptanz · Schutzbereiche |
| RV3 | Option-B-Reversal unbemerkt zu weit | P5 hart auf Detection+Report begrenzt · `merged_from` leer · Strategy-Doc-Update |
| RV4 | Enum-Drift kehrt zurück | SSoT als einzige Quelle · `_pkm_common` · Test gegen Mehrfach-Definition |
| RV5 | Qwen-Hangs / Memory-Pressure | json_mode=false bei Hang · max_tokens-Cap · App-Hygiene-Protokoll |
| RV6 | Regel-Drift in langen CC-Sessions | SessionStart-Hook · Checkpoint-Files · Sessions ≤6 h |

---

## 11. Definition of Done (Gesamt)

- [ ] SSoT: Kategorie/Tag-Erweiterung = 1 Edit + Migration; 0 Dup-Enum; F1 behoben
- [ ] `redundancy_report.md` + `synthesis_candidates.md` reproduzierbar, scored, provenance-tragend; Strategy-Doc-Scope aktualisiert
- [ ] Formatierung idempotent, Obsidian-Schutzbereiche intakt, Unsafe nur per Review
- [ ] Vault-Modi `audit`/`repair`/`review` funktionsfähig, vault-sicher (Snapshot + Gate)
- [ ] Bestehende + neue Tests grün, mypy + ruff clean
- [ ] 0 SHA-256-Dubletten, `pkm_triage` 0 Orphans, alle Wikilinks auflösbar
- [ ] Reflexionsdoku je WP in `docs/learnings/`
- [ ] WP4 alle WPs per PR auf main (`gh pr create --fill` + `gh pr merge --merge --delete-branch`)

---

## 12. CC-Arbeitsanweisungen (verbindlich)

| Regel | Inhalt |
|---|---|
| Autonomie | autonom innerhalb Security-Grenzen; **STOP** nur bei: Merge/Push main · Architektur-Weiche · irreversible Löschung nicht-archivierter Daten · echter Blocker |
| Branch/PR | Feature-Branch je WP, Conventional Commits; main-Merge braucht Freigabe |
| Pre-Commit | `pytest` + `ruff check` + `ruff format --check` grün; CC iteriert selbst |
| Shell | nie `~` in Variablen-Assignments → `$HOME`/absolute Pfade |
| Daten | archive-before-delete für alles in `data/`; Snapshot vor vault-mutierenden Läufen |
| Token | State-/Per-Slug-Logs statt Pipeline-Source lesen; Output `> file 2>&1`, kein `\| head` mid-flight; Status 1×/h |
| Checkpoints | Task-Files mit STOP / REVIEW / STATUS; Architektur/Kuratierung/Strategie zurück in App-Chat |
| Kontext-Hygiene | Session-Kontextgröße in Editor UND Chat aktiv überwachen. Vor jedem WP-/Task-Wechsel oder bei Token-Warnung: Stand in ein committetes Handover-Doc (`docs/handover/`) destillieren (Stand, offene Schritte, Learnings), DANN erst `/clear` bzw. neue Session, Resume mit Projektplan + `WAYFINDING.md` + jüngstem Handover. Commits/Reports bewahren das Ergebnis, nicht den Entscheidungs-Thread. Keinen WP-Wechsel in überladener Session beginnen (Regel-Drift, RV6). |

---

## Änderungs-Log
- 2026-06-15 — Initial. Scope: P1+P5 primär, P2+P3 folgend, P4 konditional, P6 gestrichen.
