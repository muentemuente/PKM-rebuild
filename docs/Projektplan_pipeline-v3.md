---
title: Projektplan pkm-pipeline v3 — Wissensqualität (Synthese · Tags · Reformatierung) + Stabilisierung
slug: projektplan-pipeline-v3-knowledge-quality
status: abgeschlossen
created: 2026-06-23
updated: 2026-06-25
zweck: Optimierungs-Zyklus auf der FERTIGEN Basis-Pipeline. Hebt die wissensorganisatorische Ebene (additive Synthese/MOC), härtet Tags (SSoT-Remediation) und Format (Bestands-Pass), schließt das Audit-Reparatur-Backlog. Ersetzt Projektplan_pipeline-v2.
scope_basis: Erweiterung des bestehenden Repos (Option B + dokumentiertes Teil-Reversal); kein From-Scratch-Rebuild
supersedes: Projektplan_pipeline-v2.md (2026-06-15)
---

# Projektplan pkm-pipeline v3

> [!success] Closeout (Stand 2026-06-25) — **Plan erfüllt.**
> WP0–WP4 abgeschlossen + auf `main` gemergt (WP2 **entfällt** — D1 war bereits
> erfüllt). **WP5 nicht getriggert** (keine Fehlzuweisung in der Re-Klassifikations-
> Stichprobe). Kanonischer Stand: **181 Artikel + 5 MOC**, 149 Tags (SSoT), 760 Tests
> grün, `mypy pipeline/` clean. Owner-Gates O1/O4/O5 ratifiziert; D-Entscheidungen
> D1/D2/D3/D4/D6/D7 + D-WP4-1/2/3 in Code/Doku verankert.
> **Dieses Dokument bleibt als Referenz-Plan (Living), wird nicht archiviert.**
> Folge-Arbeit (**Monolith-B** — `nlp`-Serie zerlegen) ist **nicht** Teil dieses Plans
> → `docs/handover/ideen-backlog.md`. Aktueller Detailstand: `docs/handover/post-wp4-stand.md`
> + `docs/PROJECT_STATUS.md`.

**Charakter:** Korrektur + Fortführung eines laufenden Optimierungs-Zyklus auf einem **abgeschlossenen** Produkt (Basis-Pipeline Phasen 0–12 done, **181 Vault-Artikel + 5 MOC**, 760 Tests grün, mypy clean). Kein Neubau.
**Rollen:** Claude (App) = Architect/PM/Mentor (Plan, Entscheidungen, Reviews, Scope-Warnungen). Claude Code (CC) in Zed = autonome Umsetzung im Repo.
**Stand-Vorbehalt:** v2 ist teil-umgesetzt (WP3-restructure 21.06., `pkm process`-Orchestrator 22.06.). Welche v2-WPs real fertig sind, ist **nicht verifiziert** → WP0 verifiziert zuerst, bevor irgendetwas Neues startet.
**Owner-Entscheidungen (fix):** F1 additive Synthese = voll · F2 Bestands-Remediation Tags+Format = voll · F3 ein einziger Plan (dieser).

---

## 0. Scope

| In Scope | Out of Scope |
|---|---|
| **Stabilisierung:** Audit-Reparatur-Backlog (structlog, tote/Altlast-Code, Doku-/Pfad-Drift) | destruktiver Cross-Doc-Merge · `merged_from` befüllen · Quell-File-Löschung durch Synthese |
| **Synthese additiv (F1):** Detection+Report **und** LLM-generierte MOC-/Übersichtsdokumente als NEUE Vault-Artikel, HITL-reviewed | Auto-Promotion `draft→stable` · Vector-DB |
| **Tags (F2):** SSoT-Remediation über alle Bestands-Artikel (strict gegen Vokabular, Low-Confidence→Review) | automatisches Re-Tagging ohne Review · freie/hierarchische Kategorien |
| **Reformatierung (F2):** Bulk `mdformat` safe-auto über Bestand + LLM-restructure **nur triage-geflaggt** | blindes globales Prettier · restructure blind über alle 186 (s. G-1) · Eingriff in Schutzbereiche |
| optionale Klassifikations-Optimierung (konditional) | Polyglot-Node-Toolchain als Pflicht |

**Unangetastet:** bestehende Pro-Doc-Veredelung, slug-IDs, Pydantic, Phasen 1–10, `pkm process`-Ingest, Daten außerhalb Git, PR-Workflow.

---

## 1. Architektur-Entscheidungen (verbindlich)

> **Stand 2026-06-25:** D1–D7 **ratifiziert + in Code/Doku verankert** (D1 SSoT
> `config/*.yaml`+`pipeline.taxonomy`; D2 `redundancy_scan.py`; D3 `format_vault.py`;
> D4 Snapshot/3-State im Build+`promote`; D6 additive MOC live, `merged_from` leer;
> D7 WP4 als einmaliger gegateter Pass abgeschlossen). Spätere D-WP4-1/2/3 → §7.

| ID | Entscheidung | Begründung |
|---|---|---|
| **D1** | **Ein SSoT** → generiert Kategorien, Ordner-Mapping, Tag-Vokabular, Validierung; Pydantic = Runtime-Membership-Check. `category` flach + single, `gedanke`-Type erhalten. | tötet Enum-Drift strukturell; Erweiterung = 1 Edit. **Pfad-Korrektur (WP4-T0):** der realisierte SSoT ist `config/categories.yaml` (18 Kategorien) + `config/tag_vocabulary.yaml` (149 Tags), geladen über das Modul `pipeline.taxonomy` — **nicht** ein einzelnes `pipeline/taxonomy.yaml` (existiert nicht). |
| **D2** | **P5 = Detection + Report.** Hash + TF-IDF + paarweise Embedding-Similarity, in-memory (numpy/sklearn), kein Vector-DB. | bei ~186 Files ist Vector-DB Over-Engineering. |
| **D3** | **Format deterministisch via `mdformat`** (+gfm,+frontmatter), Obsidian-Syntax als Schutzbereiche. Semantische Restrukturierung = bestehender `restructure.py`/stage3-Pfad, kein neues LLM-Stage. | pure-Python (Persona), idempotent-by-design. Engine existiert bereits (WP3c). |
| **D4** | **Jede Vault-Mutation nur über 3-State raw/work/export + Snapshot-before + Safe-auto/Unsafe-Review-Trennung.** Non-negotiable. | Vault außerhalb Git, enthält manuelle Reviews → Datenintegrität = höchstes Risiko. |
| **D6 (neu)** | **Synthese ist additiv.** MOC-/Übersichtsdokumente entstehen als NEUE Artikel (`status: draft`, `review_status: ai_drafted`, eigener `doc_type: moc`/`synthesis`). Quell-Artikel werden **nie** verändert oder gelöscht; `merged_from` bleibt leer. | hebt die §12-erodierte wissensorg. Ebene, ohne die Gründe anzutasten, aus denen Merge verworfen wurde (Halluzination R1, Hardware, Solo-Review). **= dokumentiertes Teil-Reversal Option B → 01_strategy-Update Pflicht.** |
| **D7 (neu)** | **Bestands-Remediation ist ein einmaliger, gegateter, snapshot-gesicherter Vault-weiter Pass**, keine Dauerautomatik. Tags strict + Format safe-auto = Bulk; alles Unsafe + LLM-restructure = Review-/Triage-gated. | Mass-Mutation auf produktivem Bestand braucht maximale Guardrails + Reversibilität. |

---

## 2. Zu bestätigen (Owner — STOP für CC bis Freigabe)

> **Alle ratifiziert (2026-06-25).** O1 + O4 zusätzlich in der Post-WP4-Doku-Konsolidierung bestätigt.

| # | Frage | Default | Stand |
|---|---|---|---|
| O1 | **Option-B-Teil-Reversal** für additive Synthese (D6) in `01_strategy` dokumentiert + freigegeben? | ja | ✅ ratifiziert |
| O2 | `category` bleibt flach/single (D1)? | ja | ✅ ratifiziert |
| O4 | **2. Backup-Medium hergestellt + Recovery-Stichprobe** — jetzt **harte Vorbedingung** vor jeder vault-mutierenden Stufe (WP4)? | **Pflicht, ja** | ✅ erfüllt (Time Machine, s. `07_backup_strategy`) |
| O5 (neu) | **G-1 akzeptiert:** LLM-restructure am Bestand nur für triage-geflaggte Files, nicht blind alle 186? | ja (sonst Vollpass = Owner-Entscheid) | ✅ ratifiziert (WP4-T4: Cap-25-Triage) |

Ohne O1/O4/O5 startet CC nur WP0 + WP1 + WP2-Detection (alle nicht vault-mutierend). — *historisch; alle Gates inzwischen frei.*

---

## 3. WP0 — Vorbedingungen & Realstand-Verifikation (nicht-mutierend)

| Aufgabe | Ergebnis |
|---|---|
| **v2-Realstand** | Pro v2-WP feststellen: fertig / teilweise / offen. Belege: `git log --oneline`, gemergte Branches, vorhandene Module (`taxonomy.py`, `restructure.py`, `process_orchestrator.py`). Ergebnis → `docs/handover/v3-startstand.md` |
| **Stand verifizieren** | `pkm_triage.py`, `check_frontmatter.py`, `manage_vocab validate`, `git status` (main clean), `pytest`/`ruff`/`mypy` grün |
| **Doku-Drift fixen** | EIN verbindlicher Zählstand (180 vs ~186) + EIN Vokabular-Stand (47 vs 149); PROJECT_STATUS/CLAUDE.md/README angleichen |
| **Pfad-Drift fixen** | Legacy-Layout `PKM_rebuild/data/0X` in `02_pipeline_spec` als „Archiv/deprecated" markieren oder entfernen; nur aktuelles Layout + `BRAIN_VAULT` gilt |
| **Backup O4** | 2. Medium + Recovery-Stichprobe → DoD-Rest schließen |
| **Strategy-Update** | `01_strategy`: D6 (additive Synthese, Teil-Reversal Option B, R12) dokumentieren |
| Branch | `git switch -c feat/pipeline-v3-foundation` |

**REVIEW-Gate 0:** Startstand-Doc + O1/O4/O5 freigegeben. **Sessions:** ~1–2.

---

## 4. WP1 — Stabilisierung / Audit-Reparatur-Backlog (überwiegend nicht-mutierend)

**Ziel:** sauberer, konsistenter Ist-Stand vor jedem Ausbau. Quelle: Audit Phase 4 (R-B/R-C, D12/D16/D19).

| Aufgabe | Audit-Bezug | Art |
|---|---|---|
| `structlog.configure` + File-Sink `work/pipeline.log` verdrahten | D19/R-C | reparieren (billig, hoher Hebel — „auditierbar" ist Selbstanspruch) |
| `ingest_md_download.py` (401 LOC) entfernen **oder** explizit als Archiv markieren | D12 | toter Code, widerspricht §3 |
| `corpus-run`-Legacy + `viz`-Extra (UMAP/HDBSCAN/plotly) entfernen oder als Archiv kennzeichnen | D16 | Altlast verworfener Phasen |
| `pkm process` vs `run`/`ingest`: Entrypoint-Redundanz dokumentieren (welcher Weg ist kanonisch?) | D11 | Klärung, kein Code |

**Out:** keine neuen Features. **Akzeptanz:** Tests grün, mypy/ruff clean, `archive-before-delete` für alles Entfernte. **STOP:** Merge nach main. **Sessions:** 1–2.
**REVIEW-Gate 1:** Diff der Entfernungen freigegeben.

---

## 5. WP2 — Taxonomie-SSoT finalisieren (nicht-mutierend, **konditional auf WP0-Befund**)

> [!note] **WP2 entfällt (2026-06-25).** WP0 hat gezeigt, dass **D1 bereits vollständig
> erfüllt** war: SSoT = `config/categories.yaml` (18) + `config/tag_vocabulary.yaml` (149),
> geladen über `pipeline.taxonomy`, Pydantic-Runtime-Check aktiv, `pkm taxonomy
> add-category/add-tag/rename` vorhanden. Die untenstehende WP2-Spezifikation ist damit
> **nicht ausgeführt** (gegenstandslos) — als Referenz erhalten.

**Nur falls WP0 zeigt, dass D1 noch nicht vollständig erfüllt ist.** Sonst entfällt WP2.

| Aspekt | Inhalt |
|---|---|
| CC-Aufgaben | `taxonomy.yaml` als alleinige Quelle; Loader exposiert Enums/Mapping/Vokabular; Pydantic Runtime-Check; `pkm taxonomy add-category/add-tag/rename` inkl. Migration; alle Skripte importieren aus SSoT |
| Akzeptanz | 0 Dup-Enum; neue Kategorie/Tag = 1 YAML-Edit + Migration grün; `pkm_triage` 0 Orphans |
| Sessions | 2–3 |

**REVIEW-Gate 2:** SSoT + Migration an Test-Kategorie verifiziert.

---

## 6. WP3 — Synthese: Detection + additive MOC-Generierung (vault-**additiv**)

**Ziel (F1 voll):** wissensorganisatorische Ebene heben — erst Potenzial sichtbar machen, dann daraus neue Übersichtsdokumente erzeugen. Niemals Quellen anfassen (D6).

### 6a — Detection + Report
| Aspekt | Inhalt |
|---|---|
| CC-Aufgaben | Hash/TF-IDF/Embedding-paarweise (D2); Klassifikation exakt/near/semantisch/thematische-Überschneidung/Synthese-Kandidat (≥3 verwandt); Reports `redundancy_report.md` + `synthesis_candidates.md` (Score + Provenance) |
| Out | Auto-Merge, `merged_from`-Autofill |
| Akzeptanz | reproduzierbar, jeder Kandidat mit Score + Quellen, 0 stille Vault-Änderung |

**REVIEW-Gate 3a:** Du prüfst Kandidaten an Stichprobe — plausibel? Schwellen ok?

### 6b — Additive MOC-/Synthesedokumente (LLM, HITL)
| Aspekt | Inhalt |
|---|---|
| CC-Aufgaben | Aus freigegebenen Kandidaten-Clustern via Qwen (restructure-Sampler, Reasoning aus, WP3c-3) ein **neues** Übersichts-/MOC-Dokument generieren: Einleitung + thematische Gliederung + **Wikilinks auf die Quell-Artikel** (keine Inhalts-Kopie). `doc_type: moc`/`synthesis`, `status: draft`, `confidence` Pflicht, Quellen in Frontmatter referenziert |
| Out | Inhalt aus Quellen wegmergen; Quell-Artikel verändern/löschen; Auto-stable |
| Akzeptanz | MOC verlinkt nur (kein Duplikat-Body); alle Wikilinks auflösbar; Quell-Artikel byte-unverändert (Test); Low-Confidence → `needs_human` |
| Risiken | Halluzination in MOC-Prosa (R1) → kurzer Prosa-Anteil, Schwerpunkt Verlinkung; Memory-Hygiene bei Qwen-Lauf |

**REVIEW-Gate 3b:** Jedes MOC einzeln freigegeben, bevor es in den Vault geht. **Sessions:** 3–5.

---

## 7. WP4 — Bestands-Remediation: Tags strict + Reformat (vault-**mutierend** — höchstes Risiko)

**Vorbedingung hart: O4 (2. Backup) + Snapshot-before. Ohne diese kein WP4.**

| Tier | Inhalt | Modus |
|---|---|---|
| **Safe-auto (Bulk)** | `mdformat` über alle ~186; Whitespace/Header/Listen/Fences/YAML-Sort; Tag-Mapping strict gegen SSoT-Vokabular, Synonyme auflösen, Freitext-Tags → Vorschlag | direkt, idempotent, Snapshot-before |
| **Review (gated)** | Heading-Umbau, Strukturänderung, Tag-Drops ohne klares Mapping, **LLM-restructure nur für triage-geflaggte Low-Quality-Files (G-1)** | Patch-Vorschlag → Owner-Freigabe |

| Aspekt | Inhalt |
|---|---|
| CC-Aufgaben | Bestehende `format-vault`/`vault-repair`/`vault-review`/`restructure` auf Brain-Vault umlenken; 3-State (D4); `diff_report.md`; Idempotenz-Test (2. Lauf = nur Status-Änderung); Tag-Remediation-Report (vorher/nachher gegen Vokabular) |
| Out | Bulk-Promotion `draft→stable`; restructure blind über alle (G-1); Eingriff in Schutzbereiche |
| Akzeptanz | Idempotenz nachgewiesen; Schutzbereiche unverändert; Unsafe nie ohne Review; 0 SHA-Dubletten; alle Wikilinks nach Pass auflösbar; Tag-Vokabular-Konformität messbar gestiegen |
| Risiken | Mass-Mutation auf produktivem Bestand → D4 + Snapshot + archive-before-delete non-negotiable |

**REVIEW-Gate 4:** Diff/Patch + Tag-Remediation-Report freigegeben → Export. **Sessions:** 3–5 (Review-lastig).

### Realstand WP4 (2026-06-25, abgeschlossen — `feat/wp4-t1-klassifikation` / PR #39)

Die obige Tier-Annahme (mdformat-Bulk + Tag-strict über alle) traf so **nicht** zu;
verifiziert statt unterstellt (T0). Tatsächlicher Verlauf, Detail in `docs/handover/wp4-abschluss.md`:

- **T1 (Klassifikation):** 7 Frontmatter-Fixes; 5 Projekt-Artefakte → `00_Meta/_projektdoku/`
  (`process-document`/`meta`), 2 type-only. Synthese-Ausschluss live (166/26), 7/7 Body byte-identisch.
- **T2 (NLP-Dublette):** als **(D) distinkt** bestätigt, keine Mutation; Monolith-B-Dekomposition → Ideen-Backlog.
- **T3 (Tags/Format):** Tag-strict = **No-op** (Content-Korpus 100 % konform; T0-„12 OOV" lagen alle in `00_Meta`).
  `mdformat` = **STOP-FLAG** (zerstört Wikilinks: `[[x]]`→`\[[x]\]`) → **deferred Backlog**.
- **T4 (restructure):** Cap-25-Triage; **1** echter Defekt (`datenaufnahme-und-verarbeitung`, 6×H1→H2), kein Qwen nötig.
- **T5 (Indizes):** 3 stale Indizes regeneriert.

**Neue Design-Punkte (in Code/Doku verankert):**
- **D-WP4-1:** restructure-Triage = kalibrierte Norm (H1=1, summary 100 %, Wortzahl-P75) statt fixer Schwellen.
- **D-WP4-2:** `scripts/rebuild_indices.py` deprecated → committetes Modul `pipeline/regenerate_indices.py`
  (`pkm regenerate-indices`, phase_9-Format, getestet, idempotent).
- **D-WP4-3:** Vault-Mutation per archive-before + Snapshot + Body-Byte-Test, Live-Write nur per Owner-`!`-Lauf.

**Deferred (eigene WPs/Backlog):** mdformat wikilink-safe machen; `00_Meta`-Governance-Tag-Vokabular;
Monolith-B → nlp-Serie zerlegen (`docs/handover/ideen-backlog.md`).

---

## 8. WP5 — Klassifikations-Optimierung (KONDITIONAL)

**Trigger:** nur wenn nach WP3/WP4 die Re-Klassifikations-Stichprobe noch Fehlzuweisung zeigt. Stage-4-Prompt-Iteration (Few-Shot, SSoT in-context) + Confidence-Gate. Kein neues System. **Sessions:** 1–2.
**REVIEW-Gate 5:** Vorher/Nachher an Stichprobe.

---

## 9. Sequenz & Abhängigkeiten

```
WP0 (Verifikation + Backup O4 + Strategy-Update)
   └─ Gate0 + O1/O4/O5
        ├─ WP1 (Stabilisierung)        nicht-mutierend
        ├─ WP2 (SSoT, konditional)     nicht-mutierend
        └─ WP3 (Synthese 3a→3b)        additiv
                             ▼
                   WP4 (Bestands-Remediation)  ← erste Mass-Mutation, braucht O4
                             ▼
                   WP5 (Klassifikation) — nur wenn Trigger
```

| WP | Hängt ab von | Vault-mutierend |
|---|---|---|
| WP0 | — | nein |
| WP1 | WP0 | nein |
| WP2 | WP0 | nein |
| WP3 | WP0 (WP2 empfohlen) | **additiv** (neue Artikel) |
| WP4 | WP0+O4, WP2 | **ja (Bestand)** |
| WP5 | WP3+WP4 + Trigger | klein |

**Realistic gesamt:** ~12–17 Sessions à 4–6 h.

---

## 10. Risiken & Gegenmaßnahmen

| ID | Risiko | Gegenmaßnahme |
|---|---|---|
| RV1 | Vault-Datenverlust (außerhalb Git) | Snapshot-before · 3-State · O4-2nd-Medium · archive-before-delete |
| RV2 | Idempotenz-Bruch durch Formatierung | `mdformat` idempotent · Idempotenz-Test als Akzeptanz · Schutzbereiche |
| RV3 | Synthese-Reversal driftet zu weit (Richtung Merge) | D6 hart additiv · `merged_from` leer (Test) · Quell-Byte-Stabilität (Test) |
| RV5 | Qwen-Hangs / Memory-Pressure (MOC + restructure) | Reasoning aus (WP3c-3) · max_tokens-Cap · App-Hygiene · Timeout→kein Draft |
| RV6 | Regel-/Kontext-Drift in langen CC-Sessions | Handover-Doc vor WP-Wechsel · Sessions ≤6h · Resume mit Plan+WAYFINDING+Handover |
| **RV12** | **Scope-Creep („nur noch eine Sache") — durch F1/F2-„voll" aktiv hoch** | G-1 (restructure nur triage-geflaggt) · Out-of-Scope-Liste verbindlich · jede Erweiterung braucht Plan-Update |
| RV13 (neu) | MOC-Halluzination als Pseudo-Wissen | Schwerpunkt Verlinkung statt Prosa · `confidence` Pflicht · Gate-3b pro MOC |

---

## 11. Definition of Done (Gesamt) — ✅ erfüllt (2026-06-25)

- [x] WP0: ein Zählstand + ein Vokabular-Stand verbindlich; Pfad-Drift weg; Backup O4 + Recovery-Stichprobe grün; `01_strategy` mit D6
- [x] WP1: `structlog` verdrahtet (`work/pipeline.log` lebt); tote/Altlast-Module entfernt/archiviert; Entrypoint-Redundanz geklärt
- [x] WP2: **entfällt** — D1 bereits erfüllt (s. §5)
- [x] WP3: `redundancy_report.md` + `synthesis_candidates.md` scored+provenance; 5 additive MOC reviewed im Vault; Quell-Artikel byte-unverändert; `merged_from` leer
- [x] WP4: Tag-strict = No-op (Content-Korpus 100 % konform); Format-Pass deferred (mdformat wikilink-unsafe, Backlog); Schutzbereiche intakt; 0 SHA-Dubletten; Wikilinks auflösbar; Unsafe nur per Review
- [x] Tests grün (760), mypy + ruff clean; Reflexionsdoku je WP in `docs/learnings/` + `docs/handover/`
- [x] alle WPs per PR auf main (zuletzt PR #39/#40/#41)

> WP5 (Klassifikations-Optimierung, §8) **nicht getriggert** — keine Fehlzuweisung in der Stichprobe.

---

## 12. CC-Arbeitsanweisungen (verbindlich)

| Regel | Inhalt |
|---|---|
| Autonomie | autonom innerhalb Security-Grenzen; **STOP** nur bei: Merge/Push main · Architektur-Weiche · irreversible Löschung nicht-archivierter Daten · jede vault-mutierende Ausführung (WP4) · echter Blocker |
| Branch/PR | Feature-Branch je WP, Conventional Commits; main-Merge braucht Freigabe |
| Pre-Commit | `pytest` + `ruff check` + `ruff format --check` + `mypy` grün; CC iteriert selbst |
| Daten | archive-before-delete für alles in `data/`/Vault; Snapshot vor vault-mutierenden Läufen |
| Vault | WP3 additiv → neue Artikel ok ohne Mass-Snapshot; WP4 → Snapshot+O4 zwingend, Gate pro Export |
| Token/Kontext | State-/Per-Slug-Logs statt Source lesen; vor WP-Wechsel Handover nach `docs/handover/`, dann `/clear`; kein WP-Wechsel in überladener Session (RV6) |
| Checkpoints | Architektur/Kuratierung/Strategie zurück in App-Chat |

---

## Änderungs-Log
- 2026-06-23 — Initial v3. **Ersetzt v2 (2026-06-15).** Anlass: Basis-Pipeline fertig + v2 teil-umgesetzt; Owner-Entscheidung F1 additive Synthese voll / F2 Bestands-Remediation voll / F3 ein Plan. Neu ggü. v2: WP1 Stabilisierung (Audit-Backlog), D6 additive Synthese (Teil-Reversal Option B), D7 + WP4 Bestands-Remediation, G-1 restructure-Begrenzung, RV12/RV13.
- 2026-06-25 — **Closeout: Plan erfüllt.** Frontmatter `status: draft→abgeschlossen`; Closeout-Banner (WP0–WP4 done, WP2 entfällt, WP5 nicht getriggert, 181+5 MOC / 760 Tests); §1-Header-Counts (186/399 → 181+5 MOC/760); §1 D1–D7 als ratifiziert+verankert markiert; §2 O1/O4/O5 ratifiziert; §5 WP2 als entfallen (D1 erfüllt) gekennzeichnet; §11 DoD vollständig abgehakt + Folge-WP Monolith-B (→ ideen-backlog) als planextern ausgewiesen. **Nicht archiviert** (bleibt Living-Referenz).
