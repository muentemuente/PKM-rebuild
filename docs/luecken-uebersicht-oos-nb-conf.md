---
title: Lücken-Übersicht — OoS, NB & Conf-bedingte Fehlstellen
slug: luecken-uebersicht-oos-nb-conf
status: review
created: 2026-06-25
updated: 2026-06-25
leitdokument: Zielbeschreibung_PKM-Pipeline_rebuilt.md
abgeleitet_aus: ziel-implementierungs-matrix.md
basis: Post-WP4 — live-verifiziert 2026-06-26 (gate_nb-verify, HEAD c02acdd)
---

# Lücken-Übersicht — OoS, NB & Conf

Detaillierte Auflistung aller Fehlstellen aus der Ziel-Implementierungs-Matrix,
gefiltert auf die drei Gründe **`[OoS]`** (out of scope), **`[NB]`** (nicht gebaut)
und **`[Conf]`** (Qwen-Fähigkeit unzureichend). **Nicht** enthalten: `[OptB]`,
`[R9]`, `[Syntax]` — diese sind separate Scope-/Architektur-Entscheidungen.

> **Verifikationsbasis:** **Live-verifiziert am 2026-06-26** gegen den Repo (HEAD
> `c02acdd`, Gate-Report `gate_nb-verify`): 14/15 `[NB]` bestätigt, NB-5 präzisiert.
> `[Conf]`-Begründungen stammen aus dokumentierten Befunden (Spec Block 8.A.1,
> WP3c-3, redundancy-scan-Hinweis, `pipeline.config.yaml`) und waren **nicht** Teil
> dieser Code-Verifikation (separat, empirisch belegt).

---

## Teil A — Bewusst nicht enthalten: `[OoS]` (out of scope)

Funktionen, die **nie als Arbeitspaket geplant** waren. Keine technische Blockade —
eine bewusste Scope-Grenze. Charakter: **Designentscheidung**.

| ID | Zielabschnitt | Soll-Funktion | IST-Zustand | Grund (OoS) |
|---|---|---|---|---|
| OoS-1 | 5 / 9 | Eingebundene Bilder/Grafiken/Dateien inhaltlich prüfen | Nur Embed-/Wikilink-**Syntax** wird erhalten + auf Auflösbarkeit geprüft; **keine** Prüfung, ob die referenzierte Datei real existiert oder ein gültiges Bild ist | Datei-/Binär-Inspektion nie als WP geplant; Pipeline ist text-zentriert |
| OoS-2 | 9 | Assets sinnvoll benannt / abgelegt | Keine Namens-/Ablage-Konventionsprüfung für `_assets/` | Asset-Hygiene nie als WP geplant |
| OoS-3 | 9 | Fehlende Bildunterschriften / Kontext erkennen | Keine Erkennung | erfordert Bild-↔-Text-Verständnis; nie geplant |
| OoS-4 | 9 / 11 | Hinweis: „würde von Diagrammen/Visualisierungen profitieren" | Kein Vorschlagsmechanismus | generativer Visual-Gap-Vorschlag nie geplant |
| OoS-5 | 9 | Assets semantisch zum Inhalt passend prüfen | Keine semantische Bild-↔-Text-Bewertung | erfordert multimodales Modell; nie geplant |
| OoS-6 | 11 | Hinweise auf fehlende Grafiken / Tabellen / Visuelles | Kein Mechanismus | s. OoS-4; generativer Visual-Gap nie geplant |

**Gemeinsamer Nenner:** Der gesamte Block **Asset-Semantik / Visual-Gap-Analyse**
(Zielabschnitt 9 + visuelle Teile von 11) wurde bewusst ausgeklammert. Die Pipeline
**erhält** Assets strukturell verlustfrei, **bewertet** sie aber inhaltlich nicht.

---

## Teil B — Echte offene Lücken: `[NB]` (nicht gebaut)

Funktionen, die **im Ziel gefordert**, aber **nicht implementiert** sind und **keine
bewusste Scope-Entscheidung** darstellen. Charakter: **Backlog-Kandidat**. Sie liegen
gebündelt im Bereich **inhaltlich-semantische Tiefe**.

### B.1 Formal-strukturell (Abschnitt 5)

| ID | Soll-Funktion | IST-Zustand | Grund (NB) |
|---|---|---|---|
| NB-1 | Doppelte Absätze / verrutschte Textblöcke erkennen | Korruptions-Scan fängt PUA / `turn…`-Leaks / URL-Mashups; **doppelte Absätze nicht explizit** | kein Detektor gebaut |
| NB-2 | Störelemente markieren/entfernen (alte Fußnoten, Navi-Reste, Werbereste) | Scraping-**Korruption** wird erkannt; klassische Navi-/Werbung-Heuristik fehlt | kein Detektor gebaut |

### B.2 Semantische Analyse (Abschnitt 6)

| ID | Soll-Funktion | IST-Zustand | Grund (NB) |
|---|---|---|---|
| NB-3 | Zentrale Begriffe / Entitäten / Methoden / Konzepte **extrahieren** | Nur `parent_concept`/`child_concepts` als Felder (manueller Qwen-Vorschlag); **kein** Entity-/Keyphrase-Extraktor | keine NER-/Keyphrase-Stage gebaut |
| NB-4 | Kernaussagen identifizieren | Kein Feld / keine Stage | nicht gebaut |
| NB-5 | Unklare / widersprüchliche Passagen markieren | `needs_human` flaggt nur **Verarbeitungs**fehler; Feld `contradictions` existiert **latent** im deprecated Option-A-Stage-1-Prompt (`prompts/v1/`), im aktiven v2-Pfad nicht verdrahtet → keine Artikel-Markierung | 🟡 **latent/deprecated** statt `[NB]` (Code-verifiziert 2026-06-26) |
| NB-6 | Fehlende Kontextinformationen erkennen | Keine Erkennung | nicht gebaut |
| NB-7 | Inhaltliche Lücken sichtbar machen | Nur `frontmatter-audit` (Metadaten-Lücken); **inhaltliche** Gap-Analyse fehlt | kein Content-Gap-Detektor |

### B.3 Metadaten-Felder (Abschnitt 7)

| ID | Soll-Feld | IST-Zustand | Grund (NB) |
|---|---|---|---|
| NB-8 | Erkannte Entitäten | Kein Feld, kein Extraktor | s. NB-3 |
| NB-9 | Erkannte Konzepte | Felder vorhanden, **kein Extraktor** | manueller Vorschlag statt Extraktion |
| NB-10 | Offene Fragen | Kein Feld | nicht gebaut |
| NB-11 | Potenzielle Weiterverarbeitung | Kein Feld | nicht gebaut |

### B.4 Redundanz-/Beziehungs-Klassifikation (Abschnitt 8)

| ID | Soll-Unterscheidung | IST-Zustand | Grund (NB) |
|---|---|---|---|
| NB-12 | Veralteter Wissensstand erkennen | Kein Aktualitäts-/Veraltet-Check | nicht gebaut |
| NB-13 | Widersprüchliche Information erkennen | Nicht erkannt | s. NB-5 |
| NB-14 | Fragmentarisches Rohmaterial klassifizieren | Nicht klassifiziert | nicht gebaut |

### B.5 Audit-Kriterium (Abschnitt 13.4)

| ID | Soll | IST-Zustand | Grund (NB) |
|---|---|---|---|
| NB-15 | „zentrale Begriffe" als Teil der semantischen Strukturanalyse | Typ/Thema ✅, Begriffsextraktion schwach | identisch zu NB-3 (Entity/Keyphrase) |

**NB-Verdichtung — sechs Lücken-Cluster:**

1. Entity-/Keyphrase-Extraktion (NB-3, NB-8, NB-9, NB-15)
2. Kernaussagen (NB-4)
3. Widerspruchs-/Veraltet-/Fragment-Erkennung (NB-5 *(latent, s. B.2)*, NB-12, NB-13, NB-14)
4. Inhaltliche Gap-/Kontext-Analyse (NB-6, NB-7)
5. Metadaten-Felder „offene Fragen" / „Weiterverarbeitung" (NB-10, NB-11)
6. Formal-strukturelle Reste: doppelte Absätze, Navi-/Werbung-Heuristik (NB-1, NB-2)

---

## Teil C — Qwen-bedingt nicht möglich: `[Conf]`

Funktionen, deren **automatisierte Umsetzung eine verlässliche LLM-Bewertung
voraussetzen würde** — die das lokale Qwen-Modell jedoch **nicht verlässlich liefern
kann**. Charakter: **technische Blockade durch Modell-Limit**, nicht bloß „nicht gebaut".

### C.0 Die konkreten Qwen-Limitierungen (warum es nicht möglich war/ist)

| # | Dokumentierter Befund | Quelle | Konsequenz |
|---|---|---|---|
| Q1 | **Confidence-Miskalibrierung:** Qwen liefert hohe `confidence`-Werte **trotz unvollständiger/falscher Outputs** (Smoke-Test) | Spec Block 8.A.1 | `confidence` ist als **Auto-Triage-/Quality-Gate-Signal unbrauchbar**; **alle** Drafts brauchen menschliches Review unabhängig vom Wert |
| Q2 | **Kontextfenster 49 152 Token (~50K)**, lokales Single-Model `qwen3.6-27b` (LM Studio) | `pipeline.config.yaml`, Persona | Keine Vollkorpus-/breite Cross-Doc-Bewertung; Token-Cap-Segmentierung nötig — globale Kohärenz-/Aktualitäts-Urteile nicht zuverlässig fundierbar |
| Q3 | **Reasoning-Steuerung instabil:** `enable_thinking:false` und `/no_think` werden ignoriert, nur `reasoning_effort:"none"` wirkt; Thinking-Modus **~11× langsamer** (1666s vs. 150s/Doc) | WP3c-3 | Tiefe, zuverlässige Reasoning-Bewertung pro Doc ist **instabil und teuer** → für Bewertungs-Stages nicht praktikabel |
| Q4 | **Optionale Qwen-Paarbewertung per Default AUS** wegen **Hang-Risiko** | Spec (`redundancy-scan --qwen`) | Semantische Beziehungs-Klassifikation (complementary / widersprüchlich) ist **nicht verlässlich automatisierbar** |
| Q5 | **Kein spezialisiertes Modell** (NER, Keyphrase, Kohärenz-Scoring) — alles über dasselbe generative Modell, dessen Output nicht validierbar verlässlich ist | Architektur | Bewertungs-Outputs wären nicht prüfbar verlässlich → kein vertrauenswürdiges Scoring |

### C.1 Direkt Conf-blockierte Funktionen (Quality-Chain)

Diese Funktionen würden auf eine **vertrauenswürdige Qualitäts-Selbsteinschätzung**
oder ein **LLM-gestütztes semantisches Urteil** angewiesen sein — beides durch Q1/Q3/Q5
blockiert. Deshalb ist die Qualität **human-gated** statt berechnet.

| ID | Zielabschnitt | Soll-Funktion | IST-Zustand | Warum mit Qwen nicht möglich |
|---|---|---|---|---|
| Conf-1 | 7 | Qualitätsstatus (maschinell verwertbar) | Nur `status` (Lifecycle) + `confidence`; letzteres unzuverlässig | Q1: `confidence` korreliert nicht mit echter Qualität → kein belastbarer Status ableitbar |
| Conf-2 | 10 / 11 / 13.8 | Qualitäts**bericht** / Qualitätsberichte + Prüfhinweise (Scoring) | Audit-Reports (Defekt-Detektion) vorhanden; **kein** Pro-File-Qualitäts-**Score** | Q1/Q5: ein Score bräuchte verlässliche LLM-Urteile; Selbsteinschätzung unbrauchbar |
| Conf-3 | 10 | Manueller Prüfbedarf (automatisch markieren) | `needs_human`/`confidence`-Flag, aber unzuverlässig | Q1: hohe confidence trotz Mängeln → Flag verpasst echte Problemfälle → **bewusst** alles ins Review |

### C.2 Conf-latente NB-Dimensionen (Quality-Scoring, Abschnitt 10)

Diese Qualitätsdimensionen sind in der Matrix als `[NB]` geführt (kein Detektor
gebaut), ihre **Automatisierung ist aber durch denselben Conf-Grund blockiert** —
ihr Bau wurde deshalb **nicht verfolgt**. Sie erfordern semantisches Urteil, das nur
ein LLM liefern könnte (Q5), dessen Verlässlichkeit hier aber nicht gegeben ist (Q1/Q3).

| ID | Dimension | Warum LLM-gebunden + Conf-blockiert |
|---|---|---|
| Conf-4 | Lesbarkeit | Erfordert qualitatives Sprach-Urteil → nur LLM; Q1/Q5 machen es unbelastbar |
| Conf-5 | Logische Kohärenz | Erfordert inhaltliches Schließen über den ganzen Text → Q2 (Kontext) + Q3 (Reasoning instabil) |
| Conf-6 | Thematische Geschlossenheit | Erfordert semantisches Gesamturteil → Q2/Q5 |
| Conf-7 | Aktualitätsrisiko | Erfordert Welt-/Zeitwissen-Abgleich → lokales Modell ohne aktuelle Quellen, Q2/Q5 |

### C.3 Wichtige Abgrenzung — was **nicht** an Qwen liegt

Ehrlichkeitshalber: Ein Teil der Quality-Dimensionen (Abschnitt 10) ist
**deterministisch ohne LLM berechenbar** und **scheitert nicht an Qwen**, sondern
ist schlicht als **Scoring-Layer nicht gebaut** (→ eigentlich `[NB]`, nicht `[Conf]`):

| Dimension | Lage |
|---|---|
| Formale Markdown-Qualität | Defekte werden deterministisch erkannt (`vault-audit`); ein **Zahlen-Score** wurde nur nicht gebaut — **kein** Qwen-Limit |
| Strukturqualität | Heading-/Fence-Audit deterministisch vorhanden; Score nicht gebaut — **kein** Qwen-Limit |
| Metadatenvollständigkeit | **Vollständig deterministisch gelöst** (`frontmatter-audit`, 0/165 Lücken) — kein Defizit |
| Quellenlage / Redundanzgrad / Verknüpfbarkeit / Synthesepotenzial | Rohdaten deterministisch vorhanden; nur **kein Pro-Doc-Aggregat-Score** — **kein** Qwen-Limit |

→ Für diese Dimensionen ist ein **deterministischer Scoring-Layer** der realistische
Weg (kein LLM nötig). Nur **Conf-4 bis Conf-7** sind **echt** Qwen-/LLM-gebunden.

---

## Teil D — Gesamtbilanz der drei Gründe

| Grund | Anzahl | Charakter | Auflösbarkeit |
|---|---|---|---|
| `[OoS]` (A) | 6 | bewusste Scope-Grenze (Asset-Semantik/Visual) | nur via neuem, multimodalem WP — kein Versehen |
| `[NB]` (B) | 15 | echte offene Lücken (14 bestätigt abwesend + NB-5 latent/deprecated) | deterministisch oder via robusterer LLM-Stage baubar |
| `[Conf]` direkt (C.1) | 3 | Modell-Blockade (confidence unzuverlässig) | erfordert **anderes/validierbares** Bewertungsverfahren |
| `[Conf]` latent (C.2) | 4 | LLM-gebunden + blockiert | erfordert verlässlicheres Modell/Verfahren |
| (Abgrenzung C.3) | 7 Dim. | **kein** Qwen-Limit — Scoring-Layer fehlt | rein deterministisch baubar |

### Kernaussage

- **`[OoS]`** = Asset-Semantik & Visual-Gap: bewusst nie geplant.
- **`[NB]`** = inhaltlich-semantische Tiefe: gefordert, nicht gebaut, baubar.
- **`[Conf]`** = das **einzige** Cluster mit echter **technischer Blockade**: die
  semantische Qualitäts-/Beziehungsbewertung scheitert an der **Miskalibrierung und
  Nicht-Validierbarkeit des lokalen Qwen-Modells** (Q1) plus dessen **Kontext-/
  Reasoning-/Stabilitäts-Grenzen** (Q2–Q4) und dem **Fehlen spezialisierter Modelle**
  (Q5). Deshalb ist die Qualität in der Pipeline **bewusst human-gated** — nicht aus
  Bequemlichkeit, sondern weil ein automatisches LLM-Quality-Gate auf diesem Stack
  **nachweislich unzuverlässig** wäre.

---

## Teil E — Folgeschritt (verify-first) — erledigt 2026-06-26

Der Abgleich gegen den Live-Code (HEAD `c02acdd`) ist erfolgt (Gate-Report
`gate_nb-verify`): 14/15 `[NB]`-Einträge bestätigt, NB-5 → 🟡 (latent/deprecated).
**Keine** `[NB]`-Lücke war ein Doku-Artefakt. Die **`[Conf]`**-Befunde (Q1–Q5)
bleiben separat, empirisch belegt und stabil. Offene Folge: R-1-Fix (mdformat lazy
import — *erledigt in diesem Lauf*) + Roadmap-/Priorisierungs-Matrix.
