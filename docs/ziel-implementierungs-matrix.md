---
title: Ziel → Implementierungs-Matrix (Bestandsaufnahme PKM-Pipeline)
slug: ziel-implementierungs-matrix
status: review
created: 2026-06-25
updated: 2026-06-25
leitdokument: Zielbeschreibung_PKM-Pipeline_rebuilt.md
quellen:
  - 02_pipeline_spec.md
  - 03_vault_standard.md
  - post-wp4-stand.md
basis: Post-WP4 — live-verifiziert 2026-06-26 (gate_nb-verify, HEAD c02acdd, PR #43); 721 Tests grün, Vault idempotent
---

# Ziel → Implementierungs-Matrix

Bestandsaufnahme des IST-Zustands der PKM-Pipeline, gemessen **strikt gegen die
Zielbeschreibung** als Leitdokument. Jede im Ziel genannte Funktion wird einzeln
geführt: implementiert / teilweise / nicht — und bei Lücken mit konkretem Grund.

> **Geltungsbereich / Verifikationsbasis:** Stand Post-WP4, **live-verifiziert am
> 2026-06-26** gegen den Repo (HEAD `c02acdd`) via Gate-Report `gate_nb-verify`.
> Ergebnis: 14/15 `[NB]`-Lücken bestätigt, NB-5 präzisiert (s. §3). Ground-Truth
> nachgeführt: 37 Module / 16 133 Zeilen, 23 CLI-Commands, **721 Tests** (Richtwert
> 760 korrigiert), 24 `FrontmatterDraft`-Felder, 149 Tags, 18 Kategorien. `[Conf]`-
> Befunde (Qwen) sind nicht Teil dieser Verifikation (separat, empirisch belegt).

---

## 0. Legende

**Status:** ✅ implementiert · 🟡 teilweise · ❌ nicht implementiert

**Grund-Codes** (nur bei 🟡 / ❌):

| Code | Bedeutung | Charakter |
|---|---|---|
| `[OptB]` | Option-B-Architektur: kein Cross-Doc-Merge / Split | Scope-Entscheidung (bewusst) |
| `[R9]` | Embedding-Clustering verworfen — kein Cluster-Signal im Korpus | empirisch verworfen |
| `[Conf]` | `confidence` = Qwen-Selbsteinschätzung, unzuverlässig → kein Auto-Scoring | bewusst |
| `[OoS]` | bewusst out of scope, nie als WP geplant | Scope-Entscheidung |
| `[Syntax]` | nur Syntax-/Struktur-Ebene, keine inhaltliche/externe Prüfung | Tiefe begrenzt |
| `[NB]` | nicht gebaut / kein WP — echte offene Lücke | Backlog-Kandidat |

---

## 1. Überblick entlang der 13 Zielabschnitte

| # | Zielabschnitt | Status | Kurzbefund |
|---|---|---|---|
| 1 | Ausgangsidee | ✅ | Halbautomatische MD-Pipeline → Brain-Vault; Primärweg `pkm process` |
| 2 | Übergeordnetes Ziel (kontrollierter Eingang/Filter) | ✅ | Universeller Ingest + Review-Gates A–D + Tier-System |
| 3 | Primärer Anwendungsbereich (nur Markdown) | ✅ | Ausschließlich `.md`; Konvertierung vorgelagert |
| 4 | Dokumenttypen / Heterogenität | 🟡 | Typ-bewusst, aber aktiver `type`-Enum nur 4 Werte (process-document, knowledge-article, compact-reference, gedanke) |
| 5 | Formale/strukturelle Verarbeitung | ✅ | Normalize + repair/format-safe + vault-audit/-repair |
| 6 | Semantische/inhaltliche Analyse | 🟡 | Klassifikation/Tags/Summary/Redundanz/Synthese ja; Entity/Kernaussagen/Widerspruch nein |
| 7 | Metadaten/Taxonomie | 🟡→✅ | Kontrollierte Taxonomie-SSoT erfüllt; einzelne Soll-Felder fehlen |
| 8 | Redundanz-/Syntheseprüfung | 🟡 | Detektion stark; Merge/Split + Widerspruch/Veraltet fehlen |
| 9 | Asset-/Medienprüfung | 🟡 | nur Syntax/Link-Integrität; keine Asset-Semantik |
| 10 | Qualitätsbewertung | 🟡 | manuelle Stufen/Status; kein berechnetes Multi-Dimensions-Scoring |
| 11 | Gewünschtes Ergebnis | 🟡 | Kern-Artefakte ja; Qualitätsbericht/Split/Visual-Gap fehlen |
| 12 | Abgrenzung | ✅ | 3-Wege-Unterscheidung (safe / KI-Vorschlag / manuell) realisiert |
| 13 | Auditfähige Zieldefinition | 🟡 | techn. Korrektheit erfüllt; dok./wissensorg. Qualität teilweise |

Abschnitte 1–4 + 12 sind überwiegend konzeptionell/architektonisch erfüllt; die
funktionale Detailprüfung folgt für die Abschnitte **5–10** (§2–§5), Abschnitt
**11/13** als Roll-up (§6).

---

## 2. Abschnitt 5 — Formale/strukturelle Verarbeitung

| Funktion (Soll) | Status | Engine / Grund |
|---|---|---|
| YAML-Frontmatter prüfen + normalisieren | ✅ | Phase 2 + `FrontmatterDraft` + `frontmatter-audit` |
| Fehlende Metadaten ergänzen | ✅ | Stage 4 (LLM) + mechanische Felder |
| Dokumenttitel vereinheitlichen | ✅ | `title`-Feld, H1-Fallback (Phase 3) |
| Konsistente Heading-Hierarchie | ✅ | `vault-audit` / `-repair` (Heading-Defekte) |
| Saubere Absatzstruktur | ✅ | `format-safe` (mdformat) |
| Defekte Markdown-Syntax bereinigen | ✅ | `repair-safe` |
| Listen / Tabellen / Zitate / Callouts standardisieren | 🟡 | Listen ✅; Callouts/Wikilinks **geschützt** (nicht normalisiert), Tabellen byte-stabil erhalten statt aktiv vereinheitlicht `[Syntax]` |
| Codeblöcke + Language Identifier | ✅ | `vault-repair` Fence-Tagging-Heuristik v2 |
| Doppelte Absätze / verrutschte Blöcke / Konvertierungsartefakte | 🟡 | Korruptions-Scan (PUA, `turn…`-Leaks, URL-Mashups) erkennt Artefakte; doppelte Absätze nicht explizit `[NB]` |
| Interne/externe Links normalisieren | 🟡 | `links`-Stage (Wikilink-Syntax) + Auflösbarkeit; externe HTTP-Validierung fehlt `[Syntax]` |
| Asset-Verweise erhalten + prüfen | 🟡 | Embeds extrahiert + erhalten; Prüfung nur Wikilink-Resolve `[Syntax]` |
| Eingebundene Bilder/Grafiken/Dateien prüfen | 🟡 | nur Embed-Resolve; keine Datei-Existenz-/Bildprüfung `[OoS]` |
| Störelemente entfernen/markieren (Fußnoten/Navi/Werbung/Scraping-Dupes) | 🟡 | Korruptions-Scan fängt Scraping-Reste; klassische Navi-/Werbung-Heuristik fehlt `[NB]` |

---

## 3. Abschnitt 6 — Semantische/inhaltliche Analyse

| Funktion (Soll) | Status | Engine / Grund |
|---|---|---|
| Hauptthema erkennen | ✅ | Stage 3/4 (Qwen) |
| Dokumenttyp + Wissensfunktion bestimmen | ✅ | Type-Resolver (WP3c-4) + `doc_role` |
| Tags vorschlagen / erzeugen | ✅ | Stage 4 + `tags`-Stage |
| Kategorien / Themenbereiche zuweisen | ✅ | `category` (Stage 4 + det. Mapping) |
| Zentrale Begriffe / Entitäten / Methoden / Konzepte extrahieren | ❌ | Keine dedizierte Entity-/Keyphrase-Extraktion; nur `parent_concept`/`child_concepts` (manueller Vorschlag) `[NB]` |
| Zusammenfassungen / Abstracts erzeugen | ✅ | `summary`-Feld (Stage 4) |
| Kernaussagen identifizieren | ❌ | Kein Feld / Stage `[NB]` |
| Unklare / widersprüchliche Passagen markieren | 🟡 | `needs_human` flaggt nur Verarbeitungsfehler; Feld `contradictions` existiert **latent** im deprecated Option-A-Stage-1-Prompt (`prompts/v1/`), im aktiven v2-Pfad nicht verdrahtet → keine Artikel-Markierung `[NB→latent, verifiziert 2026-06-26]` |
| Fehlende Kontextinformationen erkennen | ❌ | nicht implementiert `[NB]` |
| Inhaltliche Lücken sichtbar machen | 🟡 | nur `frontmatter-audit` (Metadaten); inhaltliche Gap-Analyse fehlt `[NB]` |
| Redundanzen gegenüber Bestand erkennen | ✅ | `redundancy-scan` (exact / near-dup) |
| Semantisch ähnliche Dateien identifizieren | ✅ | Embeddings (`semantic-dup`-Band) |
| Thematische Cluster bilden | ❌ | Embedding/HDBSCAN ohne brauchbares Signal (0.85→0, 0.65→Mega-Cluster) `[R9]` |
| Synthesepotenziale erkennen | ✅ | `synthesis_candidates` (thematische Komponenten ≥ N) |
| Vorschläge für MOC/Index/Synthese | ✅ | `synthesize-moc` (additiv, D6) |
| Querverlinkungen vorschlagen | ✅ | Cross-Link-Kandidaten (`vault-audit` Regel 8) + `related` |

---

## 4. Abschnitt 7 — Metadaten / Taxonomie

| Soll-Feld / -Anforderung | Status | Engine / Grund |
|---|---|---|
| Titel · Dokumenttyp · Themenbereich · Status · Quelle · created/updated · Tags · Kategorien · verwandte Dokumente · Zusammenfassung | ✅ | `FrontmatterDraft` (Pydantic-SSoT) |
| Bearbeitungsstatus | ✅ | `review_status` |
| Qualitätsstatus | 🟡 | `status` + `confidence`; letzteres unzuverlässig `[Conf]` |
| Erkannte Entitäten | ❌ | Kein Feld, kein Extraktor `[NB]` |
| Erkannte Konzepte | 🟡 | `parent/child_concepts` vorhanden, aber kein Extraktor (manueller Vorschlag) `[NB]` |
| Offene Fragen | ❌ | Kein Feld `[NB]` |
| Potenzielle Weiterverarbeitung | ❌ | Kein Feld `[NB]` |
| Kontrollierte Taxonomie statt Freitext | ✅ | SSoT: 149-Tag-Vokabular + `categories`/`enums.yaml`, governed growth (`pkm taxonomy`) |

> **Kernanforderung erfüllt:** „nicht beliebige Tags, sondern kontrolliert mit
> definierter Taxonomie" ist durch die SSoT-Architektur (Vokabular + Merge-Map +
> Runtime-Enum-Validierung) klar umgesetzt. Die fehlenden Felder sind Erweiterungen.

---

## 5. Abschnitt 8 — Redundanz- und Syntheseprüfung

### 5.1 Dokument-Prüfungen

| Prüfung (Soll) | Status | Engine / Grund |
|---|---|---|
| Existiert bereits ähnlich | ✅ | near-dup / semantic-dup |
| Überschneidet sich mit anderen | ✅ | overlap-Verdict |
| Ergänzt bestehendes Thema | 🟡 | `thematic`-Band; „complementary" nur via optionalem `--qwen` |
| Redundant **oder veraltet** | 🟡 | redundant ✅; veraltet ❌ (kein Aktualitäts-Check) `[NB]` |
| Teil eines Themenclusters | 🟡 | thematische Komponente, kein echtes Clustering `[R9]` |
| In Synthesedoc integrierbar | ✅ | `synthesis_candidates` → MOC |
| Eigenständig bleiben | 🟡 | implizit via „keep-separate"-Verdict (optional Qwen) |
| Aufgeteilt / zusammengeführt / neu strukturiert | 🟡 | neu strukturieren ✅ (`restructure`, single-file); aufteilen/zusammenführen ❌ `[OptB]` |

### 5.2 Soll-Unterscheidung der Beziehungstypen

| Beziehungstyp | Status | Engine / Grund |
|---|---|---|
| Exakte Dublette | ✅ | `exact` (SHA-256) |
| Inhaltliche Teilüberschneidung | ✅ | near-dup / overlap |
| Thematische Nähe | ✅ | `thematic`-Band |
| Ergänzender Kontext | 🟡 | „complementary" nur optional (Qwen per Default aus) |
| Widersprüchliche Information | ❌ | nicht erkannt `[NB]` |
| Veralteter Wissensstand | ❌ | nicht erkannt `[NB]` |
| Fragmentarisches Rohmaterial | ❌ | nicht klassifiziert `[NB]` |
| Synthetisierbarer Baustein | ✅ | synthesis candidate |

---

## 6. Abschnitt 9 — Asset- und Medienprüfung

| Funktion (Soll) | Status | Grund |
|---|---|---|
| Asset-Verweise gültig | 🟡 | Wikilink-/Embed-Auflösbarkeit (`vault-audit`) `[Syntax]` |
| Bilder korrekt eingebunden | 🟡 | Embed-Syntax ✅; keine Bilddatei-Existenzprüfung `[OoS]` |
| Assets sinnvoll benannt / abgelegt | ❌ | `[OoS]` |
| Lokale / externe Links funktionieren | 🟡 | lokale Wikilinks ✅; externe HTTP ❌ `[Syntax]` |
| Fehlende Bildunterschriften / Kontext | ❌ | `[OoS]` |
| Würde von Diagrammen / Visuals profitieren | ❌ | `[OoS]` |
| Assets semantisch passend | ❌ | `[OoS]` |

> **Schwächster Bereich.** Alle ❌ teilen denselben Grund: Asset-Semantik /
> Visual-Gap-Analyse wurde nie als WP geplant. Umgesetzt ist nur die
> strukturelle Erhaltung + Wikilink-Integrität.

---

## 7. Abschnitt 10 — Qualitätsbewertung (12 Dimensionen)

| Qualitätsdimension | Status | Grund |
|---|---|---|
| Formale Markdown-Qualität | 🟡 | Defekt-Detektion (`audit`), kein Score `[Conf]` |
| Metadatenvollständigkeit | ✅ | `frontmatter-audit` (Ist-Stand 0/165 Lücken) |
| Strukturqualität | 🟡 | Heading-Audit, kein Score `[Conf]` |
| Lesbarkeit | ❌ | `[NB]` |
| Logische Kohärenz | ❌ | `[NB]` |
| Thematische Geschlossenheit | ❌ | `[NB]` |
| Quellenlage | 🟡 | `sources_docs` vorhanden/leer messbar, kein Score |
| Redundanzgrad | 🟡 | Paar-Liste, kein Pro-Doc-Score |
| Verknüpfbarkeit | 🟡 | Cross-Link-Kandidaten, kein Score |
| Synthesepotenzial | 🟡 | Candidate-Mitgliedschaft, kein Score |
| Aktualitätsrisiko | ❌ | `[NB]` |
| Manueller Prüfbedarf | 🟡 | `needs_human` / `confidence`-Flag, unzuverlässig `[Conf]` |

> **Kein berechnetes Multi-Dimensions-Scoring.** Qualität ist manuell modelliert
> (4 Qualitätsstufen + Status-Lifecycle `draft → review → stable → deprecated`,
> `03_vault_standard.md`) und human-gated. `confidence` (Qwen-Selbsteinschätzung)
> wurde im Smoke-Test als unzuverlässig erkannt → bewusst **kein** Auto-Triage.

---

## 8. Roll-up — Abschnitt 11 (Ergebnis) & 13 (Audit)

### 8.1 Gewünschte Ergebnis-Artefakte (Abschnitt 11)

| Soll-Output | Status | Grund |
|---|---|---|
| Bereinigte / normalisierte MD-Datei | ✅ | — |
| Ergänztes / korrigiertes Frontmatter | ✅ | — |
| Qualitätsbericht | 🟡 | Audit-Reports, kein Pro-File-Qualitätsbericht `[Conf]` |
| Tag- und Kategorie-Vorschläge | ✅ | — |
| Liste empfohlener interner Links | ✅ | Cross-Link-Kandidaten |
| Hinweise auf ähnliche / redundante Dateien | ✅ | Redundanz-Report |
| Vorschläge zur Aufteilung / Zusammenführung | ❌ | `[OptB]` |
| Erkannte Lücken / offene Fragen | 🟡 | nur Frontmatter-Lücken `[NB]` |
| Vorschläge für Synthesedokumente | ✅ | synthesis candidates + MOC |
| Hinweise auf fehlende Grafiken / Tabellen / Visuelles | ❌ | `[OoS]` |
| Nachvollziehbar / protokolliert / reversibel | ✅ | Snapshot, D4, archive-before, JSON-Logs |

### 8.2 Auditfähige Zieldefinition (Abschnitt 13, 10 Kriterien)

| # | Kriterium | Status | Beleg |
|---|---|---|---|
| 1 | MD-Syntax/Struktur prüfen + normalisieren | ✅ | Phase 2, repair/format-safe |
| 2 | Frontmatter Schema validieren + ergänzen | ✅ | `FrontmatterDraft`, Stage 4 |
| 3 | Links/Assets/Tabellen/Code erkennen + erhalten | ✅ | Phase 3 + Protected-Fingerprint (byte-stabil) |
| 4 | Typ/Thema/zentrale Begriffe/semantische Struktur | 🟡 | Typ/Thema ✅; „zentrale Begriffe"-Extraktion schwach `[NB]` |
| 5 | Tags/Kategorien/Metadaten kontrollierte Taxonomie | ✅ | SSoT-Taxonomie |
| 6 | Redundanzen + semantisch ähnliche erkennen | ✅ | `redundancy-scan` |
| 7 | Synthese-/Verknüpfungs-/Ergänzungspotenzial sichtbar | 🟡 | Synthese + Cross-Link ✅; „Ergänzung" schwach |
| 8 | Qualitätsberichte + Prüfhinweise | 🟡 | Audit-Reports ✅; Qualitäts-Scoring ❌ `[Conf]` |
| 9 | Automatische Änderungen protokollieren | ✅ | Snapshots, archive-before, JSON-Logs |
| 10 | Inhalt nicht unkontrolliert verfälschen | ✅ | Tier-Gates, byte-stabile Garantien, Dry-run-Default |

### 8.3 Drei-Ebenen-Audit

| Ebene | Status | Begründung |
|---|---|---|
| Technische Korrektheit | ✅ | Syntax, Frontmatter, Pfade, Links, Assets, Tabellen, Code, Reproduzierbarkeit abgedeckt |
| Dokumentarische Qualität | 🟡 | Struktur/Typ/Metadaten/Standards ✅; Lesbarkeit/Kohärenz nicht bewertet |
| Wissensorganisatorische Qualität | 🟡 | Taxonomie/Redundanz/Ähnlichkeit/Synthese/Verlinkung ✅; Clustering verworfen, Entitäten/Tiefe begrenzt |

---

## 9. Zusätzliche Fähigkeiten (über die Zielbeschreibung hinaus)

Im Ziel nicht gefordert, aber implementiert:

| Fähigkeit | Engine |
|---|---|
| D4 3-State-Vault-Mutation (Snapshot → Canary → Mass-Write → Audit-Verify) mit Owner-Gate + O4-Backup-Präsenz-Check | `vault-apply`, `promote`, `driver.py` |
| Vaultweite Idempotenz-Garantie | `pkm regenerate-indices` (0/14) |
| Resume- / Resilienz-Mechanik (Einzelfehler → `needs_human`, Lauf läuft weiter) | `pkm process --resume` |
| Composability-Kern (Transform-Registry + Chain-Driver) | `transforms.py`, `driver.py` |
| Review-Sheet-Workflow (xlsx, Decision-Dropdowns) | `restructure-batch`, `review-ingest` |
| Passthrough-Schwelle (byte-verbatim bei gut strukturierten Files, kein Genre-Shift) | `restructure` (WP3c-4) |
| Promotion-Update-Modell mit Kollisions-Strategien (abort/replace/suffix) | `promotion.py` |
| Governed-growth-Taxonomie-Migration (Rename zieht Bestand nach) | `pkm taxonomy rename` |

---

## 10. Verdichtung: Warum die Lücken bestehen

| Grund | Betroffene Funktionen | Charakter |
|---|---|---|
| `[OptB]` | Aufteilen/Zusammenführen, Cross-Doc-Merge | **Scope-Entscheidung** (bewusst) |
| `[R9]` | Thematisches Clustering | **Empirisch verworfen** (kein Signal) |
| `[Conf]` | Qualitäts-Scoring (alle Dimensionen) | **Bewusst** (Qwen-confidence unzuverlässig) |
| `[OoS]` | Asset-Semantik, Visual-Gap, Bild-/Datei-Prüfung | **Nie geplant** |
| `[Syntax]` | externe Link-Validierung, Tabellen/Callout-Vereinheitlichung | **Tiefe begrenzt** |
| `[NB]` | Entity-/Keyphrase-Extraktion, Kernaussagen, Widerspruchs-/Veraltet-/Fragment-Erkennung, inhaltliche Gap-Analyse, offene Fragen, doppelte Absätze, Navi-/Werbung-Heuristik | **Echte offene Lücken** (Backlog-Kandidaten) |

### Echte offene Lücken (`[NB]`) — verdichtet

Die einzigen Lücken, die **keine** bewusste Scope-Entscheidung sind, liegen
gebündelt im Bereich **inhaltlich-semantische Tiefe**:

1. Entity-/Keyphrase-Extraktion (Abschnitt 6, 7, 13.4)
2. Kernaussagen-Identifikation (Abschnitt 6)
3. Widerspruchs-, Veraltet- und Fragment-Erkennung (Abschnitt 6, 8)
4. Inhaltliche (nicht nur Frontmatter-) Gap-Analyse (Abschnitt 6, 11)
5. Felder „offene Fragen" / „potenzielle Weiterverarbeitung" (Abschnitt 7)
6. Externe HTTP-Link-Validierung + Navi-/Werbung-Heuristik (Abschnitt 5)

---

## 11. Bilanz

- **Technisch-formale Ebene (Abschnitte 5, 13.1):** weitgehend vollständig.
- **Metadaten/Taxonomie (Abschnitt 7):** Kernanforderung (kontrollierte SSoT) erfüllt.
- **Redundanz/Synthese-Detektion (Abschnitt 8):** stark; Mutation (Merge/Split) bewusst ausgeklammert.
- **Semantische Tiefe (Abschnitt 6) + Qualitäts-Scoring (Abschnitt 10) + Asset-Semantik (Abschnitt 9):** die drei systematischen Schwachstellen.

Die Pipeline erfüllt ihre Kernrolle als **Eingangskontrolle + formale/strukturelle
Qualitätssicherung + kontrollierte Verschlagwortung + Redundanz-/Synthese-Detektion**.
Die im Ziel beschriebene **tiefere inhaltlich-semantische Analyse und automatisierte
Qualitätsbewertung** sind nur teilweise bzw. nicht realisiert — teils bewusst
(verworfen/out of scope), teils als echte offene Lücke.

---

## 12. Folgeschritt (verify-first) — erledigt 2026-06-26

Der Abgleich gegen den Live-Repo (HEAD `c02acdd`) ist erfolgt (Gate-Report
`gate_nb-verify`): 14/15 `[NB]`-Lücken durch den Code-Stand bestätigt, NB-5 von
`[NB]` → 🟡 (latent/deprecated) präzisiert. **Keine** `[NB]`-Lücke war ein
Doku-Artefakt. Offene Folge-Schritte: (1) R-1-Fix (lazy `mdformat`-Import,
CLI-Blockade — *erledigt in diesem Lauf*), (2) Roadmap-/Priorisierungs-Matrix
für die NB-Cluster + Conf-C.3 (NB-3/9/15 als **ein** Block „Term/Concept/Entity").
