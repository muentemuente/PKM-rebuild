# Audit Phase 1 — Baseline & dokumentierte Historie

**Rolle:** Auditor (read-only). Keine Bewertung. Nur Faktenlage.
**Soll-Maßstab:** `Zielbeschreibung_PKM-Pipeline_rebuilt.md` (verbindliche Baseline).
**Belege:** Datei:Zeile / Commit-Hash / Zitat.

---

## Vorbemerkung zur Quellenlage

| Quelle | Status | Datierung |
|---|---|---|
| `Zielbeschreibung_PKM-Pipeline_rebuilt.md` | **untracked** (`git status: ??`), kein Frontmatter-Datum | nachträglich abgelegt, postdatiert die frühe Historie |
| `README.md` (älteste) | Commit `282a9bd` | 2026-05-26, „Stand 2026-05-25" |
| `docs/01_strategy.md` (älteste) | Commit `282a9bd` | created 2026-05-25 |
| `docs/02_pipeline_spec.md` (älteste) | Commit `282a9bd` | created 2026-05-25 |

**Faktischer Befund:** Die als „verbindliche Baseline" deklarierte Zielbeschreibung ist das jüngste der Dokumente und nicht versioniert. Die Projekt-Historie (Commits ab 2026-05-26) referenziert sie nie. Divergenzen „Baseline ↔ Historie" sind deshalb teils Folge davon, dass die Baseline eine **spätere Re-Artikulation** der Ziele ist, nicht das Startdokument. Startdokumente waren `README` + `01_strategy` + `02_pipeline_spec`.

---

## 1. Ursprüngliche Ziele

| # | Ziel | Quelle | Beleg / Zitat |
|---|---|---|---|
| Z1 | (Halb)automatisierte Pipeline für wachsendes Markdown-PKM | Zielb. §1 | „Entwicklung einer (halb)automatisierten Verarbeitungspipeline für ein wachsendes Personal-Knowledge-Management-System auf Markdown-Basis." |
| Z2 | Kontrollierter Eingang / Qualitätsfilter vor dauerhafter Aufnahme | Zielb. §2 | „Jede Datei soll vor der dauerhaften Aufnahme … einen standardisierten Verarbeitungsprozess durchlaufen." |
| Z3 | Nur Markdown als Input; andere Formate vorgelagert konvertiert | Zielb. §3 | „verarbeitet zunächst ausschließlich Markdown-Dateien." |
| Z4 | Markdown-Normalisierung / Content Hygiene | Zielb. §5 | „normalisieren, bereinigen und an definierte Strukturstandards anpassen." → impl. Commit `7fd4ee3` (Phase 2: CRLF→LF, Tabs, Trailing-WS, Frontmatter-Extraktion) |
| Z5 | YAML-Frontmatter validieren + ergänzen (Schema) | Zielb. §5/§7/§13.2 | „Prüfung und Normalisierung von YAML-Frontmatter"; impl. `e1f3c35` (`schemas.py`, Pydantic Phase 1–8) |
| Z6 | Strukturextraktion (Headings, Code, Tabellen, Links, Bilder) | Zielb. §5 | impl. Commit `515a61a` (Phase 3: H1–H6, Code-Blöcke, Tabellen, Links, Wikilinks, Bilder) |
| Z7 | Dokumenttyp-/Wissensfunktion-Erkennung | Zielb. §6 | „Dokumenttyp und Wissensfunktion bestimmen" → `515a61a`: heuristische `doc_type_guess` (11 Typen) |
| Z8 | Semantische Analyse: Thema, Tags, Kategorien, Entitäten, Abstract | Zielb. §6 | „das Hauptthema … erkennen", „Tags vorschlagen", „Zusammenfassungen … erzeugen" → Phase 8 Qwen-Stages |
| Z9 | Kontrollierte Taxonomie / Ontologie statt beliebiger Tags | Zielb. §7 | „möglichst kontrolliert mit einer definierten Taxonomie … Ziel ist nicht maximale Verschlagwortung" → `config/` Taxonomie-SSoT (CLAUDE.md §9) |
| Z10 | Redundanz-Erkennung (exakt / near-dup / Ähnlichkeit) | Zielb. §6/§8 | „Redundanzen … erkennen", Hash + TF-IDF + Embeddings → Commit `d9cb420` (Phase 5), `74de985` (Phase 6) |
| Z11 | Thematische Cluster bilden | Zielb. §6 | „thematische Cluster bilden" → Phase 6/7 (`74de985`, `231a2ff`) |
| Z12 | Wissenssynthese / Synthesepotenziale / Cross-Doc-Merge | Zielb. §6/§8 | „Synthesepotenziale zwischen mehreren Dateien erkennen", „in ein bestehendes Synthesedokument integriert werden" → urspr. Phase 8 Stage 2 „Merge-Vorschläge" (`02_pipeline_spec` Gate 2) |
| Z13 | MOC / Index / Übersichtsdokumente + Querverlinkung | Zielb. §6 | „Vorschläge für neue Übersichts-, Index-, MOC- oder Synthesedokumente" → DoD „`_index.md` pro Cluster" (`01_strategy` §3) |
| Z14 | Asset-/Medienprüfung + Vorschläge für visuelle Ergänzungen | Zielb. §9 | „ob Asset-Verweise gültig sind … ob eine Datei von zusätzlichen Diagrammen … profitieren würde" |
| Z15 | Qualitätsbewertung / Quality Scoring je Datei | Zielb. §10 | „nachvollziehbaren Qualitätsstatus"; 12 Qualitätsdimensionen aufgezählt |
| Z16 | Human-in-the-loop, Audit-Trail, reversibel/protokolliert | Zielb. §11/§13.9 | „prüfbar, protokolliert und bei Bedarf reversibel"; impl. Review-Gates + Idempotenz (`7fd4ee3`) |
| Z17 | Reproduzierbarkeit / Idempotenz | Zielb. §13 + Strategy DoD | „reproduzierbar durch eine Pipeline"; impl. SHA-256-Input-Hash + `--force` durchgängig (`7fd4ee3`, `515a61a`, `5444ca3`) |
| Z18 | Ergebnis je Datei variabel (Bericht, Tags, Links, Merge-Vorschlag …) | Zielb. §11 | siehe Use-Case-Tabelle in Abschnitt 3 |

---

## 2. Widerspruch Baseline ↔ Historie

| # | Baseline (Soll) | Frühe/spätere Historie (Ist) | Beleg |
|---|---|---|---|
| **W1** | **Stabile Cluster-Struktur** als Vault-Organisationsprinzip; „thematische Cluster bilden" (Zielb. §6) | Clustering **verworfen** — „Korpus ohne inhärente Cluster-Struktur" (Risiko R9). Vault-Struktur stattdessen: 16 **kuratierte thematische Ordner** + deterministisches Mapping | CLAUDE.md §1 „Embedding-Clustering wurde verworfen"; Commit-Serie `546c121`/`22a40d6`/`12178f4` (similarity_threshold-Pendeln); urspr. DoD „Keine Cluster mit <3 Artikeln" (`01_strategy` §3) vs. heutiges README „15 genutzte Ordner" |
| **W2** | **Cross-Doc-Wissenssynthese / Merge** zwischen Dateien (Zielb. §6 „Synthesepotenziale zwischen mehreren Dateien", §8 „zusammengeführt") | **Option B = Pro-Doc, kein Cross-Doc-Merge.** „Gate 2 (Merge-Vorschläge) entfällt"; `merged_from` immer leer | CLAUDE.md §7 „kein Cross-Doc-Merge"; README aktuell „Kein Cluster-Merge, `merged_from` immer leer". Urspr. geplant: `02_pipeline_spec` Stage 2 „merge_proposals.json" + Review-Gate 2 |
| **W3** | **Embedding-based Retrieval / Embeddings** als semantisches Kernverfahren (Zielb. §6, §13-Fachbegriffe) | Embeddings nur noch für **Redundanz**; Cluster-Prep verworfen (R9). UMAP+HDBSCAN (Phase 7b) verworfen | CLAUDE.md §7 „Embeddings (mpnet-base) — nur Redundanz; Cluster-Prep VERWORFEN (R9)"; „[7b UMAP+HDBSCAN verworfen]" |
| **W4** | **Asset-/Medienprüfung** als eigenes Ziel (Zielb. §9: Verweise gültig, Bilder eingebunden, Vorschläge für visuelle Ergänzungen) | In früher Commit-Historie (Phasen 1–8) **kein eigener Asset-Prüf-Schritt**; Phase 3 zählt Bilder/Links nur extraktiv. Asset-Thema erst spät als manueller WP3-Schritt | Phase 3 `515a61a` (Bilder/Links nur erfasst); CLAUDE.md §9 „manueller Asset-Merge (WP3)" — nicht Pipeline-automatisiert wie in Zielb. §9 skizziert |
| **W5** | **128K-Kontext** angenommen (Strategy §6 Annahme) | **50K real** — Hardware-Test widerlegte Annahme | Commit `e1f3c35` „Kontext-Window 128K→50K" |
| **W6** | Output-Ziel „kuratierter, **deduplizierter** Vault" mit voller Synthese (README initial) | Vault entstand **pro-Doc passthrough/stage3**; 19 Gedanken `_hold`, 3 `_excluded` deferred — kein vollständiger Synthese-Durchlauf | README aktuell „180 Artikel … 19 `_hold` · 3 `_excluded`"; Option-B-Umstellung |
| **W7** | Baseline nennt **„Knowledge Graph Enrichment / Ontology Mapping"** als Ziele (§6, §13) | In Strategy explizit **Out of Scope 1.0**: „Knowledge-Graph-Visualisierung über Obsidian-Native hinaus" | `01_strategy` §2 Out of Scope vs. Zielb. §6/§13-Fachbegriffe |

**Hinweis zur Natur der Widersprüche:** W1–W3 sind keine stillen Drifts, sondern **dokumentierte, begründete Scope-Reduktionen** (Risiko R9, Hardware-Befund, Option-B-Entscheidung), niedergelegt in CLAUDE.md/PROJECT_STATUS. Sie widersprechen der Baseline nur, weil die Baseline den **ursprünglichen, ungekürzten Ambitionsstand** beschreibt und die Reduktionen nicht nachträgt.

---

## 3. Intendierte Nutzung

### Wer (Stakeholder, `01_strategy` §4)

| Rolle | Akteur |
|---|---|
| Owner / Reviewer / alle Entscheidungen | muente (Einzelperson, „interessierter Laie", ADHS-Schutz-Workflow) |
| Coding-Werkzeug | Claude Code |
| Synthese-Werkzeug | Qwen 3.6 27B lokal (4-bit, LM Studio/Ollama) |

Keine externen Stakeholder. Single-User, lokal, kein Multi-User/Sync/Mobile (`01_strategy` §2 Out of Scope).

### Use Case

- **Primär (1.0, Erstlauf):** Einmalige Bereinigung einer bestehenden Sammlung von **~200 heterogenen Markdown-Dateien** → ein kuratierter Obsidian-Vault (`README` initial, Zielb. §1).
- **Sekundär / langfristig:** **Eingangskontrolle** für neu hinzukommende Dateien — „kontrollierter Eingang, Qualitätsfilter und Analysewerkzeug" (Zielb. §2), realisiert als inkrementeller Workflow `data/00_inbox/` → `pipeline ingest` → Review → `build-vault` (README aktuell Stufe D).
- **Doppelzweck:** **Lernprojekt** (Pipeline-Engineering, lokale LLMs, GitHub-Workflow, PKM) parallel zum produktiven Output (`README` „Lernprojekt mit produktivem Output"; `01_strategy` §1, §8).

### Output je Datei (Zielb. §11 — „je nach Datei unterschiedlich")

| Output-Typ | Quelle |
|---|---|
| Bereinigte, normalisierte Markdown-Datei | Zielb. §11 |
| Ergänztes/korrigiertes Frontmatter | Zielb. §11 |
| Qualitätsbericht / Prüfhinweise | Zielb. §11, §10 |
| Tag- und Kategorie-Vorschläge | Zielb. §11 |
| Liste empfohlener interner Links | Zielb. §11 |
| Hinweise auf ähnliche/redundante Dateien | Zielb. §11 |
| Vorschläge zur Aufteilung/Zusammenführung | Zielb. §11 |
| Erkannte Lücken / offene Fragen | Zielb. §11 |
| Vorschläge für Synthesedokumente | Zielb. §11 |
| Hinweise auf fehlende Grafiken/Tabellen | Zielb. §11 |

**Faktischer Ist-Stand des Outputs** (README aktuell, abweichend von §11-Vollumfang): pro Doc genau **ein** Vault-Artikel über Routing `passthrough` | `stage3` | `gedanken`; Synthese-/Merge-/Asset-Vorschläge (Zielb. §11 unten) sind im realisierten Flow **nicht** als Pro-Datei-Output enthalten (siehe W2, W4).

---

## Datengrundlage

Erste 13 Commits (`282a9bd`…`d586cb8`), älteste `README`/`01_strategy`/`02_pipeline_spec` (Commit `282a9bd`), aktuelle `README`/`CLAUDE.md`, Zielbeschreibung vollständig. Keine separaten Design-/Konzept-/TODO-Docs oder Issues im Repo gefunden (`git log --all --diff-filter=A` auf `design|concept|todo|issue`: leer).
