# Audit Phase 4 — Drift-Klassifikation

**Grundlage:** `phase-1-baseline.md` · `phase-2-ist.md` · `phase-3-abgleich.md`.
**Drift-Typen:** Scope (Umfang ↕) · Goal (Zweck verschoben) · Usage (andere Nutzung) · Komplexität (Aufwand > Nutzen).
**Schweregrad:** kritisch / moderat / kosmetisch. **Richtung:** Reduktion / Wucherung.

---

## 1. Klassifikation — verwaiste Ziele (Phase-3 C.1, Richtung Reduktion)

| # | Abweichung | Typ | Schwere | Richtung | Problem oder legitime Evolution? |
|---|---|---|---|---|---|
| D1 | Thematische Cluster-Bildung verworfen | Scope | moderat | Reduktion | **legitim** — empirisch begründet (R9: Korpus ohne Cluster-Struktur), dokumentiert; Ordnerstruktur als Ersatz funktional |
| D2 | Cross-Doc-Synthese / Merge verworfen | **Goal** | **kritisch** | Reduktion | **Problem-Tendenz, teil-legitimiert.** Trifft das Baseline-Alleinstellungsmerkmal („aktive Wissensverdichtung", §1/§8). Durch Hardware (50K) + Option-B begründet, aber nicht in der Baseline als akzeptierte Scope-Reduktion nachgezogen → bislang *stiller* Goal-Shift |
| D3 | Synthesedokument-Output fehlt | Goal | moderat | Reduktion | Folge aus D2; ohne D2 kein eigenständiges Problem |
| D4 | Embedding-Retrieval auf Redundanz reduziert | Scope | moderat | Reduktion | **legitim** — Konsequenz aus D1; Embeddings bleiben für Redundanz aktiv |
| D5 | Asset-/Medienprüfung als Pipeline-Schritt fehlt (+ visuelle Vorschläge) | Scope | moderat | Reduktion | **Problem** — ganze Baseline-Sektion (§9) ohne automatisierten Gegenpart; nur Stub + Script. Aufschiebbar, aber unkennzeichnet |
| D6 | Per-Datei-Quality-Scoring (12 Dim.) fehlt | Scope | kosmetisch | Reduktion | teil-legitim — `confidence` deckt Teil ab; volle Mehrdimensionalität nie implementiert |
| D7 | Gap-Analyse / inhaltliche Lücken fehlt | Scope | kosmetisch | Reduktion | aufschiebbar; kein Schaden, aber Baseline-Versprechen offen |
| D8 | MOC / Querverlinkungs-Vorschläge schwach | Scope | moderat | Reduktion | **Problem** — nur `_index.md`; Verlinkung ist Kern der wissensorg. Ebene |
| D9 | Knowledge-Graph / Ontology out-of-scope | Scope | kosmetisch | Reduktion | **legitim by design** — in Strategy §2 von Anfang out-of-scope (W7) |

## 2. Klassifikation — ungeplante Features (Phase-3 C.2, Richtung Wucherung)

| # | Abweichung | Typ | Schwere | Richtung | Problem oder legitime Evolution? |
|---|---|---|---|---|---|
| D10 | Composability-Kern S4–S6 (Protokoll/Registry/Chain/D4) | **Komplexität** | moderat | Wucherung | **Grenzfall.** Hohe Architektur-Tiefe (Tier-Gate, Canary, Idempotenz-Verify) für Single-User/~186 Files; legitimierbar über Lernprojekt-Ziel (Strategy §8), aber Aufwand>unmittelbarer Nutzen |
| D11 | `pkm process` Universal-Orchestrator | Komplexität/Scope | moderat | Wucherung | **Grenzfall** — funktional sinnvoll (Z1/Z2), aber dritter Erstverarbeitungs-Pfad neben `run`/`ingest` → Redundanz mehrerer Entrypoints |
| D12 | Browser-Download-Ingest `ingest_md_download` (401 LOC) | **Goal/Scope** | **kritisch** | Wucherung | **Problem.** Widerspricht §3 („Formate extern/vorgelagert konvertiert"); Bewegung Richtung Scraping/Import; zudem **toter Code** (außerhalb Tests nicht verdrahtet) → Wartungslast ohne Nutzen |
| D13 | xlsx-Review-Sheet-Workflow | Komplexität | kosmetisch | Wucherung | **legitim** — dient HITL (Z16); geringe Tiefe |
| D14 | Taxonomie-Rename mit Bestands-Migration (420 LOC) | Komplexität | kosmetisch | Wucherung | **legitim** — Governance über Z9; vertretbar |
| D15 | 9-Regel-Audit + repair/review-Patches (`vault_audit.py` 1165 LOC) | **Komplexität** | moderat | Wucherung | **Grenzfall** — verstärkt technische Ebene massiv (Phase-3 B); nährt Formatter-Drift (siehe §4) |
| D16 | `corpus-run` Legacy + `viz`-Extra (UMAP/HDBSCAN) | Komplexität | kosmetisch | Wucherung | **Altlast** — Reste verworfener Phasen, im Code belassen; aufräumbar |

> [!note] Label-Korrektur (WP0, 2026-06-23 — Referenz-Checks)
> Die folgenden Audit-Verdikte sind durch die WP0-Phase-C-Referenz-Checks (`docs/handover/v3-wp0-phaseC-altlast.md`) **korrigiert**:
> - **D12 `ingest_md_download.py` — NICHT „toter Code".** Eigenständiger Modul-CLI (`python -m pipeline.ingest_md_download`), dokumentierter **Schritt 1** des go-forward-Runbooks (`RUNBOOK_new_files.md`), mit Tests. Das Audit beruhte allein auf dem Import-Graph (nicht in `__main__.py` registriert) und übersah die Modul-CLI-Nutzung. **Bewusst behalten.**
> - **D16 `corpus-run` — nicht „Altlast/aufräumbar", sondern bewusst behaltener Legacy-Pfad** (Docstring-„Legacy", in aktiver Doku als Legacy markiert). `viz`-Extra: `umap-learn` + `plotly` waren ungenutzt → entfernt; `hdbscan` bleibt (vom Lern-Artefakt `clustering_analysis.py` genutzt).

## 3. Klassifikation — Teilerfüllungen (Phase-3 A, Kriterien 4/7/9)

| # | Abweichung | Typ | Schwere | Richtung | Problem oder legitime Evolution? |
|---|---|---|---|---|---|
| D17 | K4 Analyse nur Heuristik+LLM, keine dedizierte Entity-/Keyphrase-Extraktion | Scope | kosmetisch | Reduktion | aufschiebbar; LLM-Frontmatter deckt Grundbedarf |
| D18 | K7 Synthese nur als Report sichtbar, kein Output | Goal | moderat | Reduktion | identisch mit D2/D3 |
| D19 | K9 Protokollierung: **kein `structlog.configure`** → `work/pipeline.log` nicht verdrahtet | Komplexität (Defekt) | moderat | — | **Problem** — untergräbt direkt das Audit-Trail-Ziel (Z16, §11 „protokolliert"); billig reparierbar, hoher Hebel für „auditierbar" |

---

## 4. Abgrenzungs-Check (Zielbeschreibung §12 — kritisch)

Geprüft, ob das Tool zu einem verbotenen Muster driftet.

| Verbotenes Muster | Treffer? | Befund |
|---|---|---|
| **Reine Scraping-Pipeline** | **Teil-Indikator, nicht dominant** | Nur `ingest_md_download` (D12) zeigt eine Scraping-/Download-nahe Tendenz — unverdrahtet, isoliert. System-weit **kein** Scraping-Charakter. Kein System-Treffer, aber Warn-Marker. |
| **Bloßer Markdown-Formatter** (nur technische Ebene, keine Semantik/Kuration) | **Stärkster Drift-Vektor** | Technische Ebene wuchert (D10/D15/D16; größte LOC), wissensorg. Ebene erodiert (D1–D3, D8). **Kombination** „Synthese weg + Formatier-/Audit-Tooling dominiert" zieht das Profil Richtung *Standardisierer/Formatter*. **Noch kein Voll-Treffer**, weil Taxonomie (Z5), Redundanz (Z6) und LLM-Restructure (K4) erhalten sind → Semantik/Kuration nicht vollständig entfallen. **Klassifikation: partieller kritischer Goal-Drift (Tendenz).** |
| **Bloßes Tagging-Skript** | **Nein** | Tagging ist eine von mehreren Funktionen; Restructure, Redundanz, Strukturextraktion, HITL-Promote vorhanden. Kein Treffer. |

**§12-Fazit:** Ein verbotenes Muster ist **nicht vollständig erreicht**, aber der Vektor „bloßer Formatter/Standardisierer" ist real und messbar (technische Wucherung + Synthese-Reduktion). Der Scraping-Marker (D12) ist isoliert und durch Entfernen neutralisierbar.

---

## 5. Top-3-Risiken + Empfehlung

| # | Risiko | Drift-Bezug | Empfehlung |
|---|---|---|---|
| **R-A** | **Aushöhlung der Wissensverdichtung** — Cross-Doc-Synthese entfallen; das §12-Unterscheidungsmerkmal zur Kuratierungspipeline schwindet (Formatter-Tendenz) | D2/D3/D18 (Goal, kritisch) | **dokumentieren & legitimieren** (primär): Baseline §8/§11/§13 um Option B als *bewusst akzeptierte* Scope-Reduktion ergänzen, damit der Goal-Shift nicht mehr still ist. **Optional reparieren:** minimalen Synthese-/Verlinkungs-Vorschlags-Pfad (D8) als kleinstes Gegenmittel wieder einführen |
| **R-B** | **Technische Wucherung vs. Nutzen** — Composability-Kern + 1165-LOC-Audit-Engine + Altlasten für Single-User/~186 Files | D10/D15/D16 (Komplexität, moderat) | **gespalten:** Lern-getriebene Tiefe **akzeptieren** (Strategy §8 deckt Lernziel) — aber **reparieren** beim toten/Altlast-Code: `ingest_md_download` (D12), `corpus-run`/`viz` (D16) entfernen oder explizit als „Archiv/geplant" markieren |
| **R-C** | **Protokoll-Lücke** — `structlog` nicht konfiguriert, Log-Datei nicht verdrahtet; untergräbt das Audit-Trail-/„auditierbar"-Ziel (Z16) | D19 (Defekt, moderat) | **reparieren** — billiger Fix (`structlog.configure` + File-Sink auf `work/pipeline.log`), hoher Hebel für ein Projekt, dessen Selbstanspruch „auditierbar/protokolliert" ist |

---

## 6. Gesamturteil

**Die Pipeline ist im Kern noch eine Kuratierungspipeline — aber mit erkennbarem, teils stillem Drift-Vektor Richtung Standardisierer/Formatter.**

Begründung (faktisch):
- **Erhalten** und damit kuratierungs-definierend: kontrollierte Taxonomie (Z5), Redundanz-Erkennung (Z6), LLM-Restructure/Analyse (K4), HITL-Gates + reversibler Promote (Z16/Z10). Diese heben das Tool über Formatter/Tagging-Skript hinaus.
- **Erodiert:** die wissensorganisatorische Verdichtung (Synthese/Merge/Cluster/MOC, D1–D3/D8) — genau die Ebene, die die Baseline als Abgrenzung zu „bloßer Formatter" benennt.
- **Gewuchert:** die technische Ebene (D10/D15) — derselbe Gradient wie in Phase-3 B.

**Kein** verbotenes §12-Muster ist vollständig erreicht; der gefährlichste Drift ist **partieller Goal-Drift** (R-A), getrieben durch eine *legitime, aber nicht in der Baseline nachgezogene* Hardware-/Option-B-Entscheidung. Damit ist der Hauptbefund weniger „falsch gebaut" als **„Baseline und Implementierung sind auseinandergelaufen, ohne dass die Baseline die Reduktion ratifiziert hat"** — primär ein Dokumentations-/Legitimierungs-Defizit, sekundär (R-C) ein konkreter reparierbarer Protokoll-Defekt und (R-B/D12/D16) aufräumbare Altlast.

---

## Datengrundlage

`docs/audit/phase-1-baseline.md`, `phase-2-ist.md`, `phase-3-abgleich.md`. Alle Drift-IDs (D1–D19) referenzieren die dort erhobenen Soll-/Ist-/Beleg-Fundstellen.
