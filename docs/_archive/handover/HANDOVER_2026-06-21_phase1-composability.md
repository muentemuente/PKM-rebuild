---
title: Handover — Phase 1 Composability komplett (S1–S6) → CLI-Exposure von apply_to_vault
slug: handover-2026-06-21-phase1-composability
status: aktiv
created: '2026-06-21'
updated: '2026-06-21'
zweck: Übergabe nach Abschluss des Phase-1-Composability-Kerns (PRs #17–#21, S1–S6). Festhalten von Build-Hooks, Library-API, Entscheidungen, offenen Phase-1-Gaps und Invarianten. Einstieg für die CLI-Exposure von apply_to_vault.
---

# Handover — Phase 1 Composability (S1–S6) komplett · CLI-Exposure next

App=Architect, CC=Executor. Single-Thread, STOP an Merges/Forks.

## STATUS — Phase 1 Composability-Kern KOMPLETT (PRs #17–#21, S1–S6)

### Build-Hooks (in `_finalize_body`, single-pass am Build-Chokepoint, Default true, abschaltbar)

- **S1 / G1** — `repair-safe` (`repair_text`) auf jeden Body vor `_render_article`
  (Config `vault.repair_on_build`).
- **S2 / G2** — `format-safe` (`format_body_safe`, mdformat) **nach** repair
  (Reihenfolge **repair→format**); Übernahme nur wenn nicht `unsafe` **und** Fences/Tabellen
  byte-identisch (Config `vault.format_on_build`).
- **S3 / G4** — read-only `audit_build_output` über das gebaute `output/` (kein
  Doc-Count-Reconcile); Summary `audit_safe_tier_rest` (erwartet 0), `audit_parse_errors`,
  `audit_dangling` (Config `vault.audit_on_build`).

Alle drei wirken **nur** auf `output/`, nie auf Live-Vault oder Quell-Drafts.

### Library (Composability-API)

- **S4** — Transform-Protokoll + Registry (`pipeline/transforms.py`): `Transform`-Protocol,
  `FunctionTransform`, `register`/`get`/`names`, Tiers `safe`/`review`/`audit`,
  `DEFAULT_CHAIN = ("repair-safe", "format-safe")` (Entscheidung 2A).
- **S5** — Chain-Driver `run_chain` (`pipeline/driver.py`): non-mutating, text→text,
  verkettet Transforms, merged Reports.
- **S6** — D4-Driver `apply_to_vault` (`pipeline/driver.py`): mutating-fähig, tier-gegated,
  `execute=False` Default (dry-run/Diff). `execute=True` = Snapshot → Canary (1 Write +
  idempotent-Verify) → Mass-Write → Verify (Audit-Pass); Rollback via `restore_snapshot`.
  Frontmatter byte-stabil (`_split_for_body`). **Live-Vault bisher unberührt** (nur
  Library + Tests auf tmp_path).

## ENTSCHEIDUNGEN

- **1A** — `--apply` lebt in Code (Build-Hooks) **und** im D4-Driver (`apply_to_vault`).
- **2A** — Chain konfigurierbar, Default `repair-safe → format-safe`.

## OFFEN — Phase 1

- **CLI-Exposure von `apply_to_vault`** (dieser Task): `pkm vault-apply`, default dry-run,
  `--execute` mit hartem Owner-Gate (Bestätigung + Snapshot + O4-Backup-Präsenz).
- **G5** — `categories.yaml` / `CATEGORY_TO_FOLDER` → SSoT.
- **G6** — Doc-count-Baseline (genehmigt **165,6**).
- **G8** — `17_unsortiert` `_index.md`.

## ROADMAP-REST

- **Phase 2** — WP3c semantische (Re)Strukturierung (Qwen, opt-in/File, draft+confidence+provenance).
- **Phase 3** — P4 Klassifikations-Optimierung (konditional, Gate = Phase-0-Befund).
- **Phase 4** — FUTURE_RUN (19 `_hold` + 2 Hangs; single-pass vs two-stage final).

## INVARIANTEN

- **Vault git-extern → kein PR.** D4: Snapshot + Canary + Verify + Owner-Gate.
- **Code → PR + Gates** (pytest / ruff / ruff format / mypy strict).
- **Shell:** `$HOME` / `git -C`, **nie** `~` in Assignments.
- **Frontmatter byte-stabil** außer Zielfeld.
- **Single-Thread:** ein Task → Report/STOP → nächster, keine Queues.
</content>
</invoke>
