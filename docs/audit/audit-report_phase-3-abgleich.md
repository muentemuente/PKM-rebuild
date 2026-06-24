# Audit Phase 3 — Soll-Ist-Abgleich

**Grundlage:** `docs/audit/phase-1-baseline.md` (Soll) ↔ `docs/audit/phase-2-ist.md` (Ist).
**Soll-Anker A:** auditfähige Zieldefinition, Zielbeschreibung §13, Kriterien 1–10.
**Status-Skala:** erfüllt · teilweise · verfehlt · übererfüllt.

---

## A) Pro auditfähigem Zielkriterium (1–10)

| # | Kriterium (Soll, §13) | Ist (Beobachtung) | Status | Beleg |
|---|---|---|---|---|
| 1 | Markdown-Syntax + Dokumentstruktur prüfen + normalisieren | Phase-2-Normalisierung, Phase-3-Struktur, `format-vault` (mdformat), `vault-audit` (9 Regeln), `fence-indented`, Transforms `repair-safe`/`format-safe` | **übererfüllt** | `phase_2_normalize.py`, `phase_3_structure.py`, `format_vault.py`, `vault_audit.py` (1165 LOC), `transforms.py:191-204` |
| 2 | Frontmatter nach Schema validieren + ergänzen | Pydantic-Schemas, Stage-4 `frontmatter.json` Pydantic-validiert, `frontmatter-audit` (deterministisch) | **erfüllt** | `schemas.py`, `phase_8_synthesis.py:812`, `frontmatter_audit.py` |
| 3 | Links, Assets, Tabellen, Codeblöcke erkennen + erhalten | Phase 3 erkennt Links/Wikilinks/Tabellen/Code+Sprache/Bilder; Segmentierung schützt Code/Tabellen; Frontmatter byte-stabil | **erfüllt** (Erkennen+Erhalten); Asset-*Gültigkeitsprüfung* nur als Stub/Script | `phase_3_structure.py`, `phase_4_segment.py`, `driver.py:16-18`; Asset: `process_orchestrator.py:190`, `scripts/publish_assets.py` |
| 4 | Dokumenttyp, Thema, zentrale Begriffe, semantische Struktur analysieren | `doc_type_guess` (Heuristik, 11 Typen) + Qwen-Synthese (Thema/Tags/Frontmatter) | **teilweise** — Typ heuristisch, Thema/Tags per LLM; dedizierte Entity-/Keyphrase-Extraktion nicht als eigenes Feature belegt | `phase_3_structure.py` (Typ), `phase_8_synthesis.py` (Stage 3/4) |
| 5 | Tags, Kategorien, Metadaten nach kontrollierter Taxonomie | `config/`-SSoT, `taxonomy`-Commands, `_stage_tags` mappt gegen Vokabular, löst Synonyme auf, droppt Freitext | **erfüllt** | `taxonomy.py`, `taxonomy_migrate.py`, `process_orchestrator.py:173`, `config/` |
| 6 | Redundanzen + semantisch ähnliche Dokumente im Bestand erkennen | Phase 5 (Hash + TF-IDF), Phase 6 (mpnet-Embeddings), `redundancy-scan` über Vault | **erfüllt** | `phase_5_redundancy.py`, `phase_6_embeddings.py`, `redundancy_scan.py` |
| 7 | Synthese-, Verknüpfungs-, Ergänzungspotenziale sichtbar machen | `redundancy-scan` meldet Synthese-Potenzial; `_index.md` je Ordner; `_stage_links`. **Cross-Doc-Merge verworfen**, `merged_from` immer leer (Option B) | **teilweise** — Potenzial wird im Report *sichtbar*, aber Synthese-/Merge-*Output* entfällt | `redundancy_scan.py`; Phase-1 W2; `phase_9_vault_build.py` (`_index.md`) |
| 8 | Qualitätsberichte + Prüfhinweise erzeugen | Phase-10-Reports (corpus/duplicate/cluster), `vault-audit`, `frontmatter-audit`, `diff_report.md`, `redundancy-scan` | **erfüllt** (Berichte); per-Datei-Quality-*Scoring* über 12 Dimensionen fehlt (nur `confidence`) | `phase_10_reports.py`, `vault_audit.py`, `__main__.py:620` |
| 9 | Automatische Änderungen nachvollziehbar protokollieren | structlog-Events (`apply_*`), `<output>.meta.json` (Input-Hash), Diff-Reports, D4-Snapshots | **teilweise** — Mechanismen vorhanden, aber **kein `structlog.configure`** → konfigurierte `work/pipeline.log` nicht verdrahtet; kein dediziertes Change-Log-File | `driver.py:198,207,244,250`; Phase-2 §4.5/§5.5 |
| 10 | Ursprünglichen Inhalt nicht unkontrolliert verfälschen/beschädigen | Input read-only, Dry-run-Default, Tier-Gate, D4 (Snapshot→Canary→Verify), Rollback, Frontmatter byte-stabil | **übererfüllt** | `driver.py:175-255`, `promotion.py:296-304`, `__main__.py:882,1245` |

**Zusammenfassung A:** erfüllt/übererfüllt: 1, 2, 3, 5, 6, 8, 10 (7×). teilweise: 4, 7, 9 (3×). verfehlt: keines vollständig. Die drei „teilweise" liegen sämtlich auf der semantisch-/wissensorganisatorischen bzw. Protokoll-Seite.

---

## B) Pro Qualitätsebene — Abdeckungsgrad

Ebenen-Definition aus Zielbeschreibung §13.

| Ebene | Soll-Umfang | Ist-Abdeckung | Einschätzung |
|---|---|---|---|
| **Technisch** | Markdown-Syntax, YAML, Pfade, Links, Assets, Tabellen, Codeblöcke, reproduzierbare Verarbeitung | Normalisierung, Strukturextraktion, mdformat-Formatierung, 9-Regel-Audit, Repair/Patch-Vorschläge, fence-Konvertierung, Idempotenz, D4-Composability-Kern (Snapshot/Canary/Verify) | **hoch — über-entwickelt.** Größte Module dienen dieser Ebene (`vault_audit.py` 1165, `format_vault.py`, `driver.py`, `transforms.py`); eigene Architektur-Schicht (S4–S6) nur hierfür |
| **Dokumentarisch** | Struktur, Lesbarkeit, Dokumenttyp, Metadaten, Quellenstatus, Gliederung, Überschriftenlogik, einheitliche Standards | Doc-Typ-Heuristik (11 Typen), Frontmatter-Schema + -Audit, Heading-Checks, Stage-4-Metadaten | **mittel.** Kernfunktionen vorhanden; Quellenstatus + per-Datei-Qualitätsscoring schwach |
| **Wissensorganisatorisch** | Taxonomie, Tags, Kategorien, Redundanz, semantische Ähnlichkeit, Synthese, interne Verlinkung, Themencluster, langfristige Einordnung | Taxonomie-SSoT (stark), Tag-Mapping, Redundanz (Hash/TF-IDF/Embeddings), Ordner-Einordnung, `_index.md`. **Clustering verworfen** (W1), **Cross-Doc-Synthese/Merge verworfen** (W2), Embeddings auf Redundanz reduziert (W3), Knowledge-Graph out-of-scope (W7) | **niedrig–mittel — unter-entwickelt** relativ zur Baseline-Ambition |

**Befund zur typischen PKM-Falle:** Bestätigt. Die **technische Ebene wuchert** (dedizierter Composability-Kern, 1165-LOC-Audit-Engine, mehrere Formatier-/Repair-Werkzeuge), während die **wissensorganisatorische Ebene zurückgebaut** wurde (drei Kern-Soll-Elemente — Cluster, Cross-Doc-Synthese, Embedding-Retrieval — sind verworfen/reduziert, dokumentiert in Phase-1 W1–W3). Die dokumentarische Ebene liegt dazwischen.

---

## C) Listen

### C.1 Verwaiste Ziele (Baseline geplant → im Code nicht/kaum vorhanden)

| Ziel (Baseline) | Soll-Quelle | Ist-Befund |
|---|---|---|
| Thematische Cluster-Bildung | Z11, §6 | verworfen — „Korpus ohne inhärente Cluster-Struktur" (W1); Ordnerstruktur ersetzt Cluster |
| Cross-Doc-Wissenssynthese / Merge | Z12, §6/§8 | verworfen (Option B); `merged_from` immer leer (W2) |
| Synthesedokument-Vorschläge als Output | §11 | nur Potenzial-Report (`redundancy-scan`), kein generiertes Synthesedokument |
| Embedding-based Retrieval als semantischer Kern | §6, §13-Fachbegriffe | auf Redundanz-Erkennung reduziert (W3) |
| Asset-/Medienprüfung als Pipeline-Schritt + Vorschläge für visuelle Ergänzungen | Z14, §9 | kein automatisierter Pipeline-Schritt; nur `_stage_assets`-Stub + Script `publish_assets.py` (W4); Grafik-/Visualisierungs-Vorschläge fehlen ganz |
| Per-Datei-Qualitätsscoring über 12 Dimensionen | Z15, §10 | nur `confidence` (Qwen); kein mehrdimensionaler Score |
| Gap Analysis / inhaltliche Lücken sichtbar machen | §6 | kein Feature belegt |
| MOC / Map-of-Content + Querverlinkungs-Vorschläge | Z13, §6 | nur `_index.md` je Ordner; keine MOC-/Link-Vorschlags-Logik |
| Knowledge-Graph-Enrichment / Ontology Mapping | §6, §13 | in Strategy explizit out-of-scope (W7) — verwaist by design |

### C.2 Ungeplante Features (im Code → kein/loser Bezug zu Baseline-Ziel)

| Feature | Ort | Bezug zu Baseline |
|---|---|---|
| Transform-Composability-Kern S4–S6 (Protokoll/Registry/Chain/D4) | `transforms.py`, `driver.py` | **kein direktes Ziel.** Loser Bezug zu Z16 (reversibel/protokolliert); Architektur-Tiefe (Tier-Gate, Canary, Idempotenz-Verify) ungeplant |
| `pkm process` Universal-Erstverarbeitungs-Orchestrator (Stage-Kette) | `process_orchestrator.py` | **kein** Baseline-Architektur-Ziel; dient Z1/Z2 funktional, Form ungeplant |
| Browser-Download-Ingest von `.md` | `ingest_md_download.py` (401 LOC) | **widerspricht** §3 („Formate werden extern/vorgelagert konvertiert"); zudem außerhalb Tests nicht verdrahtet (Phase-2 §4.4) |
| xlsx-Review-Sheet-Workflow | `batch_restructure.py`, `review-ingest`, `openpyxl` | **kein** Baseline-Ziel; Tooling für HITL |
| Taxonomie-Rename mit Bestands-Migration | `taxonomy_migrate.py` (420 LOC) | über Z9 („kontrollierte Taxonomie") hinaus; Governance-Tooling ungeplant |
| 9-Regel-Vault-Audit + vault-repair/-review Patch-Vorschläge | `vault_audit.py` (1165), `vault-review` | teilweise Z1/Z8; Umfang/Tiefe ungeplant |
| `corpus-run` Legacy-Erstlauf + `viz`-Extra (UMAP/HDBSCAN/plotly) | `__main__.py:400`, `pyproject.toml:58-61` | Reste verworfener Phasen (7b); im Code belassen |

---

## Gesamtbild (faktisch)

- **7 von 10** Audit-Kriterien erfüllt/übererfüllt, **3** teilweise (4, 7, 9). Kein Kriterium vollständig verfehlt.
- Übererfüllung konzentriert auf Kriterium 1 + 10 (technische Korrektheit, Schreibsicherheit).
- Die drei Teilerfüllungen + alle verwaisten Ziele liegen auf der **wissensorganisatorischen Ebene** (Synthese, Cluster, Gap-Analyse, MOC, Asset-Semantik) bzw. der **Protokoll-Verdrahtung** (Kriterium 9).
- Ungeplante Features sind überwiegend **technische Infrastruktur** (Composability-Kern, Audit-Engine, Orchestratoren) — derselbe Gradient wie in B).

---

## Datengrundlage

`docs/audit/phase-1-baseline.md`, `docs/audit/phase-2-ist.md` (beide diese Audit-Serie). Belege zu Code-Stellen referenziert auf die in Phase 2 erhobenen Datei:Zeile-Fundstellen.
