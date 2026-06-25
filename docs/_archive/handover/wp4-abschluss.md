---
title: WP4 — Abschluss (Bestands-Remediation)
slug: wp4-abschluss
status: review
created: 2026-06-25
updated: 2026-06-25
plan: Projektplan_pipeline-v3.md
pr: 39
---

# WP4 — Abschluss

Bestands-Remediation des Brain-Vaults, verifiziert statt unterstellt (Audit = Hypothese).
Vault liegt außerhalb Git; alle Mutationen live exportiert (Owner-`!`-Lauf, archive-before,
Snapshot) und read-only verifiziert.

## Tier-Ergebnisse

| Tier | Inhalt | Ergebnis |
|---|---|---|
| **T0** Verifikation | Tools/SSoT/Triage/Dubletten real geprüft | Tools real auf BRAIN_VAULT; SSoT = `config/*.yaml`; Drift-Flags dokumentiert |
| **T1** Klassifikation | 7 fehlklassifizierte Projekt-/Meta-Docs | 5 → `00_Meta/_projektdoku/` (`process-document`/`meta`), 2 type-only; Synthese 166/26; **7/7 Body byte-identisch** |
| **T2** NLP-Dublette | A↔B | **(D) distinkt** (keine saubere K-Richtung); unmutiert, cross-linked |
| **T3** Tags + Format | strict + mdformat | Tags = **No-op** (Content 100 % konform); mdformat = **STOP-FLAG** (Wikilink-Schaden) → deferred |
| **T4** restructure | kalibrierte Triage (Cap 25) | Roh 26 → geschärft **1** echter Defekt (`datenaufnahme-…`, 6×H1→H2); kein Qwen |
| **T5** Indizes | Staleness nach T1-Moves | 3 regeneriert (phase_9-Adapter), 0 stale, idempotent |

## Verifikation (Close-out)
7/7 Body byte-identisch · `_attic` 0 Diffs · **0 neue broken Wikilinks** (167==Snapshot) ·
192 Artikel · **757 Tests grün** · `pipeline/` ruff/mypy clean.

## Design-Punkte
- **D-WP4-1** restructure-Triage kalibriert (Norm aus Korpus: H1=1, summary 100 %, P75-Wortzahl).
- **D-WP4-2** `rebuild_indices.py` deprecated → `pipeline/regenerate_indices.py` (`pkm regenerate-indices`,
  getestet, idempotent, Schutzbereiche exkl.).
- **D-WP4-3** Vault-Write-Pattern: archive-before + Snapshot + Body-Byte-Test, Live-Write nur per `!`-Lauf.

## Deferred → Backlog
- **mdformat wikilink-safe** machen (Plugin/Protect-Restore) bevor Format läuft.
- **`00_Meta`-Governance-Tags** (changelog/naming/…) — eigenes Meta-Vokabular?
- **Monolith B** → nlp-Serie zerlegen (`docs/handover/ideen-backlog.md`).

## Offen
- Owner-Merge PR #39.
- Pre-existing `docs/_archive`-Working-Tree-Löschungen — separater Commit (nicht WP4-Scope).
