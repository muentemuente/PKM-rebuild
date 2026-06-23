---
title: v3-WP0 Phase C — Altlast-Referenz-Checks (G-B, Freigabe ausstehend)
slug: v3-wp0-phasec-altlast
status: stable
created: 2026-06-23
updated: 2026-06-23
plan: Projektplan_pipeline-v3.md
zweck: Referenz-Checks der 3 Audit-Lösch-Kandidaten (Phase C). Ergebnis steuert STOP-Gate G-B — keine Löschung ohne Owner-Freigabe.
---

# Phase C — Altlast: Referenz-Checks (Belege)

**Kernbefund: KEIN Kandidat ist sauber unreferenziert. Die Referenz-Checks widerlegen bzw. qualifizieren das Audit (Task-Regel „nicht blind dem Audit trauen"). → Keine Löschung; G-B-Freigabe abwarten.**

---

## Kandidat 1 — `pipeline/ingest_md_download.py` (~401 LOC, Audit D12 „toter Code, entfernen")

**Befund: NICHT tot.** Eigenständiger, dokumentierter Modul-CLI-Entrypoint.

| Beleg | Fundstelle |
|---|---|
| Eigene `@click.command()` `main(...)` | `pipeline/ingest_md_download.py:372–386` |
| **Aktiver Schritt 1 des go-forward-Runbooks** | `docs/RUNBOOK_new_files.md:44–45` (`python -m pipeline.ingest_md_download`) + `:54` („erst `ingest_md_download`, dann `ingest`") |
| Im Vault-Standard als Ingest-Pfad referenziert | `docs/03_vault_standard.md:512` |
| Tests vorhanden | `tests/test_ingest_md_download.py` |
| Audit-Grundlage (nur Import-Graph) | `audit-report_phase-2-ist.md:176` — „außerhalb Tests nicht importiert; kein Treffer in `__main__.py`" |

Das Audit stuft als „tot" ein, weil die Datei **nicht** in `pipeline/__main__.py` registriert ist und nicht importiert wird. Sie wird aber als **eigenständiges Modul** (`python -m pipeline.ingest_md_download`) ausgeführt und ist der dokumentierte **Vorprozessor** (`_ingest/` → `input/`). **Löschen würde das RUNBOOK brechen.**

**Konflikt (Owner-Entscheidung):** Audit („entfernen") ↔ RUNBOOK („kanonischer Schritt 1"). Optionen:
- **A (empfohlen):** behalten + Docstring/Doku schärfen (es ist der bewusste Vorprozessor, kein Scraping-Wildwuchs). Audit-D12-Verdikt als „durch Referenz-Check widerlegt" vermerken.
- **B:** Vorprozessor-Schritt bewusst aufgeben → dann Datei **und** RUNBOOK-Schritt 1 + `03_vault_standard:512` gemeinsam retten/entfernen. Größerer Eingriff in den dokumentierten Workflow.

---

## Kandidat 2 — `corpus-run` (`pipeline/__main__.py`, Audit D16 „Altlast")

**Befund: registrierter Legacy-CLI, bereits als Legacy gekennzeichnet.**

| Beleg | Fundstelle |
|---|---|
| Registrierung | `pipeline/__main__.py:381` `@cli.command(name="corpus-run")` |
| In Doku als Legacy markiert | `docs/RUNBOOK_new_files.md:154` („Im go-forward-Flow nicht genutzt"); `CLAUDE.md §11` (Legacy-Block) |

Kein aktiver Workflow nutzt es; es ist der archivierte Vollkorpus-Erstlauf (Phasen 1–10). **Entfernen ist invasiv** (hängt am gesamten Legacy-Phasenpfad).

**Empfehlung:** **nicht löschen.** Leichteste konforme Maßnahme: Docstring um „Legacy/Archiv" ergänzen (steht in aktiver Doku bereits als Legacy). Vollentfernung nur auf expliziten Owner-Wunsch.

---

## Kandidat 3 — `viz`-Extra (`pyproject.toml`: umap-learn, hdbscan, plotly; Audit D16 „verworfene Phase 7b")

**Befund: gespalten — `umap-learn` + `plotly` ungenutzt; `hdbscan` von einem bewusst behaltenen Lern-Artefakt genutzt.**

| Beleg | Fundstelle |
|---|---|
| Extra-Definition | `pyproject.toml:57–61` (`viz = [umap-learn, hdbscan, plotly]`) |
| mypy-Overrides (lösen die „unused section"-Note aus) | `pyproject.toml:124–125` (`umap.*`, `hdbscan.*`) |
| **Einziger** Code-Use: `import hdbscan` (lazy) | `scripts/clustering_analysis.py:169` |
| `umap` / `plotly` im Code | **0 Treffer** (ungenutzt) |
| `clustering_analysis.py` ist bewusst behaltenes Lern-Artefakt | `docs/05_glossary.md:63`, `docs/02_pipeline_spec.md:637`, `docs/REBUILD_inventory.md:86` („Code bleibt als Lern-Artefakt") + `tests/test_clustering_analysis.py` |
| Installationsstatus | `umap` nein · `hdbscan` ja · `plotly` nein |

**Empfehlung (kleinster sauberer Schnitt):**
- `umap-learn` + `plotly` aus dem `viz`-Extra **entfernen** (nirgends importiert) und den verwaisten mypy-Override `umap.*` entfernen → beseitigt die „unused section"-Note.
- `hdbscan` **behalten** (vom dokumentiert-behaltenen Lern-Artefakt `clustering_analysis.py` genutzt; Override `hdbscan.*` bleibt nötig, solange der lazy Import steht).
- Alternativ ganz behalten + Extra-Kommentar „Archiv/Lern-Artefakt" — schon vorhanden (`# Phase 7b (optional, …)`).

---

## G-B — Entscheidungsbedarf (keine Löschung ohne Freigabe)

| Kandidat | CC-Empfehlung | Owner-Freigabe nötig für |
|---|---|---|
| `ingest_md_download.py` | **behalten** (Audit widerlegt) | Bestätigung „behalten" ODER bewusster Retire inkl. RUNBOOK |
| `corpus-run` | **behalten** + Docstring „Legacy" | ggf. Vollentfernung |
| `viz`-Extra | `umap-learn`+`plotly`+`umap.*`-Override **trimmen**, `hdbscan` behalten | Freigabe des Trim (pyproject-Edit) |

**Status (2026-06-23, Freigabe erteilt — Option 1 umgesetzt, Commit `88c0adc`):**
- `viz`-Extra getrimmt: `umap-learn` + `plotly` + `umap.*`-mypy-Override entfernt; `hdbscan` bleibt.
- `corpus-run`-Docstring als bewusst behaltener Legacy-Pfad geschärft.
- `ingest_md_download.py` **behalten** (Audit-D12-Verdikt widerlegt).
- Audit-Label-Korrektur D12/D16 in `audit-report_phase-4-drift.md` vermerkt.
- **Keine Datei gelöscht/archiviert.** Gates nach Umsetzung: 738 Tests grün, ruff clean, mypy `pipeline/` clean.
