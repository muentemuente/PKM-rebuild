---
title: Handover WP3a — Deterministische Vault-Formatierung
slug: handover-2026-06-17-wp3a
status: aktiv
created: 2026-06-17
updated: 2026-06-17
zweck: Resume-Kontext nach Canary-Export. Stand, offene Schritte, Learnings für die Fortsetzung von WP3a (Rest-Export + Merge) ohne den ursprünglichen Entscheidungs-Thread.
---

# Handover — WP3a (P2 deterministische Formatierung)

## 1. Stand (2026-06-17)

| WP | Status |
|---|---|
| WP1 (P1 Taxonomie-SSoT) | **auf `main`** (PR #6) |
| WP2 (P5 Redundanz/Synthese-Erkennung) | **auf `main`** (PR #7) |
| **WP3a (P2 Format, Dry-Run + Canary)** | **Branch `feat/pipeline-v2-formatting`, NICHT gemergt** |

**Branch-Commits** (`main` = `7ddcbdd`):

- `e17315b` — WP3a-Basis: Engine `pipeline/format_vault.py`, CLI `pkm format-vault` (Dry-Run), Schutzbereiche, Tier-Split, Golden-Fixtures
- `1aeefd0` — E1: Thematic-Break-Stil `---` behalten (kein `___`)
- `00d6408` — Export-Funktion + Klassifikator-Präzision (Code-Fence/Heading-WS)
- `37f8379` — mypy-Fix (HEAD)

**Canary exportiert (5/5 in `~/Zentrale/09_Brain-Vault`), idempotent verifiziert (+0/-0):**

1. `00_Meta/quellenbewertung.md` (Tabelle+Liste+Wikilink)
2. `06_Methoden-und-Prozesse/teams-keyboard-shortcuts.md` (GFM-Tabelle+Liste)
3. `16_Kunst-Kultur/gestaltgesetze-in-der-kunst.md` (Liste+Wikilink)
4. `00_Meta/asset-management.md` (Tabelle+Liste+Wikilink+Embeds)
5. `01_Grundlagen/markdown-reference.md` (Tabelle+Liste+Wikilink+Code)

**Blast-Radius (186 Docs):** 7 unchanged (inkl. 5 Canary) · **159 safe** · **20 unsafe**.
Snapshot vor Canary: `pkm-pipeline/archive/backups/vault_2026-06-17_141145.tar.gz` (28 MB, Hash `5607f3d…`).
Reports/Triage: `~/projects/aktiv/pkm-pipeline/work/format/{diff_report.md,unsafe_triage.md}` (gitignored).

## 2. Offene Schritte (in Reihenfolge)

1. **Rest-Export (154 Safe-Files)** = 159 safe − 5 Canary. Vorher **erneuter Snapshot** (`bash scripts/backup_vault.sh`). Über `pipeline.format_vault.export_formatted(BRAIN_VAULT, relpaths)` (schreibt nur `safe`, refuse bei `unsafe`).
2. **Idempotenz-Verify am geschriebenen Vault**: Re-Scan → exportierte Files alle `unchanged` (+0/-0).
3. **WP3a mergen** (`gh pr create --fill` + merge) — erst nach Owner-OK auf die Vault-Sichtung.
4. **Folge-Task „indented→fenced"**: die 18 LEAVE-Files (s.u.) manuell von 4-Space-indented Code auf gefencte Blöcke umstellen, dann werden sie safe.
5. **WP4 (P3 Vault-Audit/Repair/Review-Modus)** gem. Projektplan §7.

## 3. Learnings (verbindlich für die Fortsetzung)

- **mdformat escaped Wikilinks/Embeds** (`[[x]]` → `\[[x]\]`, `![[x]]` → `!\[[x]\]`). Lösung: vor dem Formatieren **maskieren** (alphanumerisches Sentinel) + danach restaurieren. Golden-Test bewacht das.
- **Thematic Break**: mdformat rendert `---`/`***`/`___` als 70× `_`. E1-Entscheidung = **`---` behalten** → fence-aware Post-Processing (`_restore_thematic_breaks`) setzt es zurück (Code-Blöcke unberührt).
- **Indented Code ist die Gefahrenquelle**: mdformat reduziert 4-Space-indented Code (z. B. in Listen-Kontext) auf 2 Space → der Block **zerfällt** in `# Comment`-Heading + Prosa (bestätigt an `sql-grundlagen-sqlite-abfragen.md`). → **18 der 20 unsafe** sind genau das (LEAVE; Fix = indented→fenced). Diese NIE auto-formatieren.
- **Klassifikator-Guards repräsentations-agnostisch halten**: Code via **mistune-AST** vergleichen (indented↔fenced = gleicher Inhalt = safe, lt. Spec); Heading-Whitespace kollabieren (`# H  X` → `# H X` = safe); nur **echte** Inhalts-/Text-Änderungen = unsafe. (Erste naive Guards gaben 39 Fehlalarm-lastige unsafe → präzisiert auf 20 genuine.)
- **Schutzbereiche byte-genau intakt** über alle 186: kein unsafe-Grund war Wikilink/Embed/Callout/Frontmatter-Wert (nur heading-text, = indented-Code-Korruption bzw. Beispiel-FM in HTML-Kommentaren).
- **3-State (D4)**: raw (#3 read-only) → Arbeitskopie `work/` (#2) → **geprüfter** Export (#3). Export ist Gate-3-pflichtig; CLI `format-vault` ist non-mutating.

## 4. Unsafe-Triage (20, nichts angewandt)

- **18 × LEAVE** — mdformat korrumpiert indented Code (4→2 Space → Heading/Prosa). Fix: manuell indented→fenced, dann safe. (u. a. `sql-grundlagen-sqlite-abfragen`, `python-introduction`, `git-setup-and-concepts`, `artikel-template-grundlagen`, `markdown-syntax`, …)
- **2 × REVIEW** — Beispiel-Frontmatter in HTML-Kommentaren reflowt: `artikel-template-prozessdokument.md`, `system-script-management-symlinks.md`. Manuell prüfbar, meist anwendbar.

Vollständige Liste: `pkm-pipeline/work/format/unsafe_triage.md`.

## 5. Resume-Kontext

Lies zum Wiedereinstieg: `docs/Projektplan_pipeline-v2.md` (WP-Plan + §12 CC-Regeln) · `WAYFINDING.md` (3 Orte: #1 Repo PKM-rebuild, #2 pkm-pipeline Daten, #3 Brain-Vault) · **dieses Handover**.

Kanonische Pfade: Repo `~/projects/aktiv/PKM-rebuild` · Daten/Reports `~/projects/aktiv/pkm-pipeline` · Live-Vault `~/Zentrale/09_Brain-Vault` (186 Docs). `python3` = das `.venv` (mdformat/mistune installiert).
