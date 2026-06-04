---
title: PKM-rebuild Claude Code Workflow
slug: 06-claude-code-workflow
status: stable
created: 2026-05-25
updated: 2026-06-04
sources_external:
  - https://docs.claude.com/en/docs/claude-code/overview
  - https://code.claude.com/docs/en/hooks
  - https://zed.dev/blog/claude-code-via-acp
---

# Claude Code Workflow

Setup, Nutzung, Token-Management und Automatisierungs-Patterns für Claude Code in diesem Projekt.

**Geltungsbereich:** Stand 25. Mai 2026. Anthropic ändert Limits und Features regelmäßig. Bei Diskrepanz: offizielle Quellen sind führend.

> **Shell-Commands in autonomen Läufen:** In Bash-Variablen-Zuweisungen `$HOME` statt `~` verwenden — eine Tilde im Assignment-Value (`VAR=~/...`) triggert den Claude-Code-Security-Wrapper und blockiert die autonome Ausführung. Vollständige Regel + Beispiele: `CLAUDE.md` §12.

---

## 1. Setup

### 1.1 Zed-Integration (primärer Workflow)

Zed integriert Claude Code seit Q1 2026 nativ über das Agent Client Protocol (ACP) — ein offenes Protokoll, das IDE-zu-Agent-Kommunikation entkoppelt. Zed bündelt `claude-code-acp` als Adapter — keine zusätzliche Installation nötig. Integration läuft über Zeds Agent-Panel.

**Erstmaliges Setup:**
1. Zed öffnen → Agent-Panel (Sidebar rechts oder `cmd-?`)
2. Bei erstmaligem Öffnen: Provider „Claude Code" wählen (**nicht** „BYOK Anthropic API")
3. OAuth-Login mit Claude Pro Account
4. Optional: Settings in `~/.config/zed/settings.json`

**Settings-Beispiel:**
```json
{
  "agent": {
    "default_profile": "claude-code",
    "always_allow_tool_actions": false
  }
}
```

**Wann Zed-ACP vs. CLI:**

| Aufgabe | Tool |
|---|---|
| Code editieren, Doku schreiben | Zed-ACP (Diff-Inspektion direkt im Editor) |
| Multi-File-Refactor mit Live-Diffs | Zed-ACP |
| Headless / batch / scriptbar | Claude Code CLI (`claude -p`) |
| Lange Recherche-Sessions | beide gleich gut |
| In Pipeline-Skripten | Claude Code CLI |

### 1.2 Claude Code CLI (parallel)

Native installer empfohlen, kein Node.js mehr nötig seit März 2026.

```bash
# Installation
curl -fsSL https://claude.com/install.sh | bash

# Verifikation
claude --version

# Login (einmalig)
claude login
```

**Binary-Pfad:** `~/.local/bin/claude` (sicherstellen, dass `~/.local/bin` im `$PATH` ist).

**Updates:** auto-update aktiv per default.

---

## 2. CLAUDE.md-Patterns in diesem Projekt

### 2.1 Drei-Ebenen-Struktur

| File | Geltungsbereich | Inhalt |
|---|---|---|
| `/CLAUDE.md` | Projektweit | Working Rules, Hard Constraints, Pflichtlektüre, Pipeline-Phasen-Übersicht |
| `/pipeline/CLAUDE.md` | Python-Code | Python-Konventionen, Pydantic-Disziplin, Logging |
| `/prompts/CLAUDE.md` | Qwen-Prompts | Versionierung, Schema-Konsistenz, Test-Disziplin |

**Cascading-Logik:** Claude Code liest beim Session-Start die nächste `CLAUDE.md` (working directory) + alle Eltern-CLAUDE.md hierarchisch. Subdirectory-CLAUDE.md überschreiben nichts, sie **ergänzen**.

### 2.2 CLAUDE.md schreiben — Anti-Pattern beachten

Den Text als faktische Aussagen formulieren statt als imperative System-Instruktionen. Formulierungen wie „Das Deployment-Ziel ist Production" oder „Dieses Repo nutzt bun test" lesen sich als Projekt-Information. Text, der wie out-of-band System-Befehle wirkt, kann Claudes Prompt-Injection-Defenses auslösen, was dazu führt, dass Claude den Text dir gegenüber zeigt statt ihn als Kontext zu behandeln.

**Gute Formulierung:**
> Dieses Projekt nutzt Pydantic für Schema-Validation. Logging läuft strukturiert über `structlog`.

**Schlechte Formulierung:**
> Du MUSST Pydantic für alle Schemas nutzen. NIEMALS `print()` verwenden!

### 2.3 CLAUDE.md ≠ garantierte Beachtung

CLAUDE.md wird als Teil des Kontexts gelesen, aber Attention ist nicht uniform — das Modell gewichtet verschiedene Teile des Inputs unterschiedlich, und diese Gewichtung verschiebt sich, je länger die Konversation wird.

**Konsequenz:** Bei langen Sessions kann Claude Regeln aus CLAUDE.md „vergessen". Lösung: SessionStart-Hooks (siehe Sektion 8) oder periodische Erinnerung.

---

## 3. Session-Management

### 3.1 Befehle (Stand v2.1.76+, März 2026)

```bash
# Neue Session in aktuellem Working Directory
claude

# Benannte Session
claude -n "phase-5-redundancy"

# Letzte Session fortsetzen
claude --resume

# Spezifische Session per ID
claude --resume abc123def

# Spezifische Session per Name
claude --resume "phase-5-redundancy"

# Alle Sessions auflisten
claude --list

# Headless / Single Prompt
claude -p "fasse pipeline_state.json zusammen"

# Letzten Kontext fortsetzen (ohne Session-ID)
claude --continue
```

### 3.2 Naming-Convention für Sessions in diesem Projekt

| Präfix | Verwendung |
|---|---|
| `phase-NN-<slug>` | Pro Pipeline-Phase | `phase-5-redundancy` |
| `prompts-v<N>-<change>` | Prompt-Iteration | `prompts-v1.1-merge-improve` |
| `docs-<topic>` | Doku-Arbeit | `docs-strategy-update` |
| `setup-<topic>` | Setup-/Infrastruktur | `setup-mise-python` |
| `debug-<symptom>` | Debug-Session | `debug-qwen-json-fail` |

Vermeiden: `work`, `test`, `temp`, Datums-only-Names.

### 3.3 Wann neue Session, wann resume?

| Situation | Befehl |
|---|---|
| Phase wechselt, Kontext irrelevant | `claude -n "phase-N-..."` (neu) |
| Gleicher Task, später am Tag | `claude --resume <name>` |
| Token-Limit-Reset abgewartet, weiter wie vorher | `claude --resume` |
| Context wirkt „verworren", Antworten driften | `/clear` in Session oder neue Session |

---

## 4. Token-Kontingente (Claude Pro, Stand Mai 2026)

Claude Code wendet zwei sich überlappende Counter an: das 5-Stunden-Rolling-Window, das mit der ersten Nachricht einer Session beginnt und jedes konsumierte Token über die folgenden 300 Minuten zählt, sowie die wöchentliche Cap, ein Computing-Hour-Budget, das alle sieben Tage neu startet.

### 4.1 Limits

| Limit | Wert (Pro Plan, Mai 2026) |
|---|---|
| 5h-Rolling-Window | am 6. Mai 2026 verdoppelt — vorher ~45 Messages/5h, jetzt ~90 |
| Weekly Cap | unverändert (introduced Aug 2025) |
| Shared Bucket | Claude Code + Claude.ai chat + Cowork teilen sich denselben Bucket |
| Peak-Hour-Penalty | entfernt am 6. Mai 2026 |

**Wichtig:** Exakte Zahlen ändern sich. Verlässliche Quelle: `claude usage` Befehl (sobald verfügbar) oder offizielle Anthropic-Dokumentation.

### 4.2 Token-Verbrauchsmuster (Schätzungen)

Pro typischer Pipeline-Phase mit Claude Code:

| Phase | Tokens (Größenordnung) |
|---|---|
| Code-Generation (Pipeline-Skripte) | 30–80K input, 5–15K output |
| Doku-Schreiben (lange Files) | 20–60K input, 10–30K output |
| Bug-Fixing mit Multi-File-Read | 50–150K input, 5–15K output |
| Prompt-Iteration (kurze Zyklen) | 10–30K input, 2–8K output |

**Risiko:** Pipeline-Phasen mit großen File-Reads (z.B. Strategy + Spec + Vault-Standard zusammen ≈ 100K Token) verbrauchen schnell.

### 4.3 Limit-Hit-Verhalten

Max-Subscriber können zusätzliche Nutzung zu Standard-API-Raten kaufen, sobald sie Limits erreichen. Pro Plan kann ebenfalls Pay-as-you-go-Erweiterung aktivieren.

**Praktisch:**
1. Bei drohendem 5h-Limit: Session sauber beenden, Snapshot ablegen (siehe 5.1)
2. Warten bis Reset
3. `claude --resume <name>` weitermachen
4. Bei Weekly-Cap-Hit: ggf. auf Qwen lokal ausweichen (siehe 7.)

---

## 5. Recovery-Patterns

### 5.1 Context-Snapshot vor erwarteter Unterbrechung

Vor Token-Limit / Pausenende / Phasenende:

```bash
# In Claude Code Session:
> Erstelle .claude-context-snapshot.md mit folgendem Inhalt:
> - aktueller Stand (welche Files geändert)
> - offene TODOs
> - nächster konkreter Schritt
> - relevante Dateien zum Wieder-Einlesen
> - bekannte Probleme/Fragen
```

Beim Resume:
```bash
claude --resume <name>
> Lese .claude-context-snapshot.md und arbeite weiter
```

### 5.2 PreCompact-Hook (für lange Sessions)

PreCompact mit Matcher `auto` oder `manual` — wenn Kontext komprimiert wird, vorher Snapshot schreiben.

In `~/.claude/settings.json` global oder `.claude/settings.json` lokal:
```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "claude -p 'erstelle pre-compact-snapshot.md mit aktuellem Stand' > .claude/snapshots/pre-compact-$(date +%Y%m%d-%H%M).md"
          }
        ]
      }
    ]
  }
}
```

### 5.3 SessionStart-Hook für Git-Status (Quick Win)

Quick Win: SessionStart-Hook der Git-Kontext bei jedem Start in den Chat lädt. Konkret in `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '## Git-Status' && git branch --show-current && git status --short | head -20 && echo '## Letzte Commits' && git log --oneline -5"
          }
        ]
      }
    ]
  }
}
```

**Warum nützlich:** Claude weiß immer, in welchem Branch + welche uncommitted Changes existieren — ohne dass es danach fragen muss.

---

## 6. Routing — was an welches Tool?

| Aufgabe | Tool | Begründung |
|---|---|---|
| Pipeline-Code schreiben | Claude Code | Editor-Integration, Multi-File |
| Doku schreiben/iterieren | Claude Code | gleiche Begründung |
| Qwen-Prompts schreiben | Claude Code (initial), dann manuell iterieren | Schema-Disziplin |
| Korpus-Inhalte synthetisieren | **Qwen lokal** | Token-Sparen + Privacy |
| Batch-Verarbeitung Korpus | **Qwen lokal** | nicht durch Pro-Limits begrenzt |
| Ad-hoc-Fragen, Konzepte | Web-Claude (claude.ai) | gleicher Bucket, aber UI passt |
| Recherche im Internet | Claude Code (mit WebSearch) | direkt im Workflow |
| Refactoring größerer Module | Claude Code | Diff-Inspektion |
| Code-Review | Claude Code | `git diff` als Kontext |

**Faustregel:**
- Strukturelle / kreative Arbeit am Code/Doku: Claude Code (Pro-Bucket)
- Inhaltliche Massenverarbeitung des Korpus: Qwen lokal (kein Bucket-Verbrauch)
- Sensible/private Inhalte (Vault): Qwen lokal (bleibt offline)

---

## 7. Automatisierung

### 7.1 Bash-Aliases

In `~/.zshrc` oder `~/.zshrc.local`:

```bash
# Schnellzugriff auf Phasen-Sessions
alias cp1='cd ~/projects/aktiv/PKM-rebuild && claude -n "phase-1-inventory"'
alias cp5='cd ~/projects/aktiv/PKM-rebuild && claude -n "phase-5-redundancy"'
alias cp8='cd ~/projects/aktiv/PKM-rebuild && claude -n "phase-8-qwen"'

# Letzte Session in PKM-rebuild fortsetzen
alias cpkm='cd ~/projects/aktiv/PKM-rebuild && claude --resume'

# Headless-Status-Check
alias pkm-status='cd ~/projects/aktiv/PKM-rebuild && claude -p "lese data/02_pipeline_output/pipeline_state.json und gib Status"'
```

### 7.2 Makefile

```makefile
# In Projekt-Root
.PHONY: status sample run clean test

status:
	@python -m pipeline status

sample:
	@python -m pipeline run --sample 10

run:
	@python -m pipeline run

test:
	@pytest -v

claude-snapshot:
	@claude -p "erstelle .claude/snapshots/manual-$(shell date +%Y%m%d-%H%M).md mit aktuellem Stand"

backup-vault:
	@bash scripts/backup_vault.sh
```

### 7.3 Headless-Mode (`claude -p`)

Für scriptbare Einzelfragen ohne interaktive Session:

```bash
# Single Prompt → STDOUT
claude -p "fasse die letzten 5 commits zusammen"

# Aus Skript
RESULT=$(claude -p "ist der Sample-Run grün? Antworte nur ja/nein.")

# Mit Resume eines bestehenden Kontexts
claude -p --resume "phase-5-redundancy" "wie viele Duplikate gefunden?"
```

### 7.4 Hooks-Inventar für dieses Projekt

In `.claude/settings.json` (projekt-lokal, **gitignored**):

| Hook | Zweck |
|---|---|
| `SessionStart` | Git-Status + Pipeline-Status in Kontext laden |
| `PreCompact` | Snapshot vor Auto-Compaction |
| `PostToolUse` | bei `git commit`: kurz validieren, dass Conventional Commits |
| `Stop` | bei Session-Ende: Snapshot + letzten Stand notieren |

Konkrete Implementierungen kommen in Phase 0 (Setup).

---

## 8. Memory Workflow (während Qwen-Läufen)

Aus `docs/00_persona_muente.md` Sektion 6: bei aktivem Qwen 3.6 27B sind nur ~4 GB RAM für macOS verfügbar.

**Protokoll vor Qwen-Lauf:**
1. Browser schließen (auch Hintergrund-Tabs)
2. Mail, Slack, Spotify schließen
3. Aktivitätsanzeige öffnen → Memory-Pressure-Indikator beobachten
4. Wenn Pressure gelb/rot: weitere Apps schließen
5. **Zed bleibt offen** (Editor wird gebraucht), aber keine zusätzlichen Tabs/Projekte
6. **Ghostty bleibt offen** (Terminal-Output beobachten)
7. **LM Studio bleibt offen** (Qwen-Runner)

**Während Lauf:**
- Keine zusätzlichen Apps starten
- Bei Memory-Pressure-Anstieg: Qwen pausieren (LM Studio Stop), App-Hygiene, neu starten

**Claude Code während Qwen-Lauf:**
- ✅ OK, läuft entfernt bei Anthropic
- ⚠️ Aber: nicht parallel große Code-Tasks, die zusätzliche RAM brauchen (Tests, Linting in großem Repo)

---

## 9. Debugging-Workflow

### 9.1 Diff-First-Pattern

Vor jeder größeren Änderung:
```bash
# In Zed
git status              # Was hat sich geändert?
git diff --stat         # Welche Files / wie viele Zeilen?
git diff <file>         # Konkreter Diff
```

Erst bei klarem Diff-Verständnis: in Claude Code Session beschreiben + Fix anfordern.

### 9.2 Multi-Buffer-Inspektion in Zed

Zed öffnet bei Claude-Code-Änderungen automatisch geänderte Files in Tabs. Workflow:

1. Claude Code macht Änderung
2. Zed öffnet Tab automatisch
3. **Diff-View aktivieren** (`cmd-shift-D` oder Git-Panel)
4. Manuell durchgehen, akzeptieren oder zurückweisen
5. Erst dann `git add` + commit

### 9.3 Tests vor Commit (Pflicht in diesem Projekt)

```bash
# Vor jedem commit
pytest -v
ruff check .
ruff format --check .
```

Bei Failures: Output in Claude-Code-Session werfen, fixen lassen.

---

## 10. Wenn etwas nicht funktioniert

### 10.1 Checkliste bei Fehlern

| Symptom | Erste Prüfung |
|---|---|
| Claude Code startet nicht in Zed | Setup-Status: `claude --version` im Terminal ok? |
| Sessions nicht auffindbar | `claude --list` aufrufen, `~/.claude/` Inhalt prüfen |
| Token-Limit unerwartet | `claude usage` (falls verfügbar) oder claude.ai Settings |
| CLAUDE.md wird „ignoriert" | SessionStart-Hook einbauen (Sektion 5.3) |
| Auto-Compaction verliert Context | PreCompact-Hook (Sektion 5.2), oder `/clear` + Manual-Snapshot |
| Hook-Fehler beim Session-Start | `~/.claude/settings.json` validieren (JSON-Parse) |

### 10.2 Offizielle Quellen (für aktuelle Limits/Features)

- Claude Code Docs: https://docs.claude.com/en/docs/claude-code/overview
- Hooks Reference: https://code.claude.com/docs/en/hooks
- Claude.ai Support: https://support.claude.com
- Anthropic News: https://www.anthropic.com/news

---

## 11. Aktualisierungs-Routine

Dieses Doc wird gepflegt bei:
- Anthropic-Feature- oder Limit-Änderungen
- Neuen Hooks-Patterns aus eigener Praxis
- Lessons Learned aus Reflexionsdokumenten

**Wichtig:** Anthropic ändert Limits und Features mehrfach pro Jahr. Bei großen Änderungen: kompletten Re-Check der Sektionen 4, 5, 7.

---

## Änderungs-Log

- 2026-05-25 — Initial-Version, Recherche-Stand Mai 2026 (Limit-Verdoppelung 6. Mai, Peak-Hour-Penalty entfernt)
