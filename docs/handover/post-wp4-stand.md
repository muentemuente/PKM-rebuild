---
title: Post-WP4 — Stand + Backlog-Dispositionen (Clean-Slate-Handover)
slug: post-wp4-stand
status: review
created: 2026-06-25
updated: 2026-06-25
plan: Projektplan_pipeline-v3.md
---

# Post-WP4 — Stand für die nächste Session

WP4 (Bestands-Remediation) **abgeschlossen + gemergt**. Dieser Pass (`chore/post-wp4-backlog`)
hat den Rest-Backlog pragmatisch disponiert.

## Stand
- `main` trägt WP4 (PR #39) + Prune (PR #40) + diesen Pass. Vault idempotent (`pkm regenerate-indices` = 0/14).
- Vault: 181 Artikel + 5 MOC. **760 Tests** grün, `pipeline/` ruff/mypy clean.

## Backlog-Dispositionen (dieser Pass)

| Item | Disposition | Grund |
|---|---|---|
| **A** merged Branch `feat/wp4-t1-klassifikation` | **gelöscht** (lokal + remote) | verify-first: voll in `main` |
| **B** mdformat wikilink-safe | **DECLINED** | `mdformat-obsidian` 0.1.0 getestet → escaped Alias-Wikilinks **trotzdem** (218→110, 108× `[[x\|y]]`→`\[[x\|y]\]`, identisch zu plain gfm). Wikilink-safe nicht billig erreichbar; **kein** Protect/Restore-Wrapper (nicht pragmatisch). **Vault bleibt unformatiert — funktional ok.** |
| **C** 00_Meta-Governance-Tags | **CLOSED** | 12 OOV-Tags (changelog/naming/review/template/style/…) sind **kohärent + konsistent**, nicht chaotisch; nur in `00_Meta` (außerhalb des 149-Content-Vokabulars **by design**), 0 funktionale Wirkung. Eigenes Meta-Vokabular = niedriger Wert/Overhead → nicht definiert. |
| **OUT** Monolith-B → nlp-Serie | **deferred** (eigenes Synthese-WP) | `docs/handover/ideen-backlog.md`; additiv, kein Dedupe |

## Human-Items (Owner-Sache, stehen)
- **Qualitätsstufe-2-Review** der Artikel (draft → review/stable; CC macht **kein** Auto-Promote).
- **Backup 2. Medium (O4):** während WP4-T1b vom Owner als **vorliegend bestätigt**. Time-Machine-Verifikation (früherer Mount-Fehler Code 18) bleibt Owner-Check.

## Werkzeuge / Konventionen (Erinnerung)
- **Index-Regen:** `pkm regenerate-indices [--apply]` (phase_9-Format, idempotent, exkl. 00_Meta/_attic/15_Gedanken, archive-before). Ersetzt das deprecatete `scripts/_deprecated/rebuild_indices.py`.
- **Vault-Write (D-WP4-3):** Schreiben nach `BRAIN_VAULT` ist Harness-gesperrt → nur per Owner-`!`-Lauf; CC verifiziert danach read-only. Snapshot + archive-before bei jeder Vault-Mutation.

## So startest du die nächste Session
1. Lies `CLAUDE.md` (§2 Pflicht-Lektüre) + `docs/PROJECT_STATUS.md` + dieses Doc.
2. Offene echte Arbeit: **keine** im WP4-Scope. Optionen für ein nächstes WP:
   - Monolith-B → nlp-Serie zerlegen (Synthese-WP, `ideen-backlog.md`).
   - Konditionales WP5 (Klassifikations-Optimierung) nur falls Stichprobe Fehlzuweisung zeigt.
3. Vault-Mutationen weiterhin nur per `!`-Lauf, Gates heilig, kein Auto-Merge nach `main`.
