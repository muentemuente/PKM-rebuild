---
title: PKM-rebuild Tool-Routing
slug: 06b-tool-routing
status: stable
created: 2026-05-28
updated: 2026-06-25
---

# Tool-Routing — Zed/Claude Code, App-Konversation, Ghostty

Praktische Anleitung, wann welches Tool benutzt wird und wie man sauber wechselt. Ergänzung zu `docs/06_claude_code_workflow.md`.

---

## 1. Die drei Modi

| Modus | Tool | Mental-Modell | Hauptzweck |
|---|---|---|---|
| **Mache** | Zed + Claude Code | „Werkstatt" | Code, Files, Tests, Skript-Generierung, konkrete Änderungen am Repo |
| **Denke** | App-Konversation (claude.ai) | „Bürotisch" | Strategie, Bewertung, Kuratierung, Reviews, Trade-offs |
| **Inspect** | Ghostty + zsh | „Messgerät" | Befehle, Status-Checks, Git-Operationen, lokale Tools, Diagnose |

Plus während Phase 8: **LM Studio** als Qwen-Engine — eigenständiger Modus, läuft im Hintergrund.

---

## 2. Wann welches Tool — Entscheidungstabelle

| Frage / Aufgabe | Tool | Warum |
|---|---|---|
| „Schreibe / fixe Code in Datei X" | Zed-CC | Diff-Inspektion, Multi-File, Test-Integration |
| „Generiere Skelett-Files / Doku" | Zed-CC | Boilerplate mit Frontmatter, Konventionen |
| „Was wäre die beste Strategie für Y?" | App | Trade-offs ausarbeiten, keine Code-Aktion nötig |
| „Reviewe Plan / Architektur / Output" | App | Bewertung, nicht Ausführung |
| „Welche Entscheidung treffen?" | App | Mensch entscheidet bewusst |
| „Lief der Test grün?" | Ghostty | `pytest -v` — kein KI-Tool nötig |
| „Wie viele Zeilen / Files / Cluster?" | Ghostty | `wc -l`, `jq`, `find`, `du -sh` |
| „Commit-Übersicht" | Ghostty | `git log --oneline`, `git diff --stat` |
| „Status-Check Pipeline" | Ghostty | `python -m pipeline status` |
| „Curl-Test Qwen-Endpoint" | Ghostty | direkter API-Test |
| „Lass Qwen einen Batch synthetisieren" | LM Studio (Chat) | manueller Single-Stage-Test |
| „Tag-Vokabular kuratieren" | App | inhaltliche Kuratierung |
| „Cluster-Bericht reviewen" | App | Gate-1-Entscheidung |
| „Bug B1 fixen + Test schreiben" | Zed-CC | klares Engineering |
| „Ist meine Erklärung korrekt?" | App | Sparring, kein File-Edit |

---

## 3. Übergangs-Trigger

### Von Zed-CC zu App

CC signalisiert via App-Checkpoint im Task-File. Typische Trigger:

- **Block-Ende:** Tests grün, Commit gemacht — User reviewt Diff/Stand bevor weiter
- **Architektur-Entscheidung:** zwei valide Optionen, User muss wählen
- **Inhaltliche Kuratierung:** Boilerplate fertig, Mensch füllt
- **Quality-Review:** Output produziert, User bewertet Qualität
- **Unklarheit:** CC ist sich nicht sicher, will keine Annahme treffen

**Workflow:** CC pausiert, gibt kurzen Status-Block aus, User kopiert in App-Konversation.

### Von App zu Zed-CC

App signalisiert via klarem Auftrag mit Verweis auf Task-File:

> "In Claude Code: Block 0.F.3 ausführen laut `docs/tasks/0F_code_fixes_status_doku.md`. Stop nach Checkpoint NN."

User wechselt nach Zed, öffnet Claude-Code-Panel, gibt Auftrag mit Datei-Referenz.

### Von beiden zu Ghostty

Wann immer einfacher Befehl reicht. Beispiele:

```bash
# Status-Sanity-Check
python -m pipeline status

# Vault-Artikel zählen (Brain-Vault #3)
find "$HOME/Zentrale/09_Brain-Vault" -name '*.md' | wc -l

# Letzte Pipeline-Work-Outputs (#2)
ls -lt "$HOME/projects/aktiv/pkm-pipeline/work/" | head

# Letzte 5 Commits
git log --oneline -5

# Tests laufen lassen
pytest -v
```

Diese Antworten sollten nicht über CC oder App gehen — Ghostty ist schneller und token-frei.

### Von Ghostty zurück

Wenn Ergebnis weitere Interpretation braucht:

- "Hier ist der Output, was schließe ich daraus?" → App
- "Output zeigt Fehler, fixe ihn" → Zed-CC

---

## 4. Workflow-Muster

### Muster A — Engineering-Block (autonom durch CC)

```
1. App: Task-File durchgehen, Verständnis klären
2. Zed-CC: Block starten, Aufgabe + Datei-Referenz übergeben
3. Zed-CC: arbeitet bis Checkpoint
4. Ghostty: optional `pytest`, `git diff` zur eigenen Inspektion
5. App: Checkpoint-Status zeigen, "weiter" oder Korrektur
6. Schritt 3–5 wiederholen bis Block-Ende
7. App: Block-Abschluss, Reflexion-Notiz
```

### Muster B — Hybrid-Block (Kuratierung)

```
1. Zed-CC: Skelett / Heuristik-Output generieren
2. Ghostty: Output sichten (z.B. `cat`, `bat`, `less`)
3. App: gemeinsam kuratieren, finale Version schreiben
4. Zed-CC oder Editor: finale Version ins Repo legen
5. Ghostty: commit + push
```

### Muster C — Smoke-Test / Echtlauf (interaktiv)

```
1. Ghostty: Pre-Flight-Checks (LM Studio läuft? Pfade OK?)
2. App-Hygiene aktivieren (Browser/Mail/Slack zu)
3. Aktivitätsanzeige öffnen (Memory-Pressure)
4. Ghostty oder Zed-CC: Pipeline-Befehl starten
5. Aktivitätsanzeige + LM Studio: Live beobachten
6. Bei Erfolg: Outputs in Zed/Ghostty sichten
7. App: Qualität bewerten, nächsten Schritt entscheiden
```

---

## 5. App-Checkpoint-Pattern (für Task-Files)

Ein App-Checkpoint im Task-File ist eine Stopp-Anweisung an Claude Code. Format:

````markdown
### 🛑 App-Checkpoint — STOP

Bevor du weitermachst, gib folgenden Block in der Session aus:

```
Block: <id>
Erledigt: <task-ids>
Tests: <count> grün / fehlgeschlagen: <count>
Commit(s): <hash(es)>
Nächster geplanter Schritt: <task-id>
Frage an App: <konkret / keine>
Memory-Watch: <falls relevant>
```

Pausiere danach und warte auf User-Bestätigung in der nächsten Session.
````

Drei Typen:

| Symbol | Typ | Verhalten |
|---|---|---|
| 🛑 | STOP | CC pausiert vollständig, User muss in App entscheiden, neuer CC-Run mit Auftrag |
| ⏸ | REVIEW | CC bleibt in Session, wartet auf "ok" / Korrektur, dann weiter |
| ℹ | STATUS | nicht-blockierend, CC notiert Info und arbeitet weiter |

---

## 6. Typische Anti-Patterns

| Anti-Pattern | Stattdessen |
|---|---|
| Schnelle `ls`-Frage über App stellen (kostet Tokens) | Ghostty |
| Architektur-Diskussion in Claude Code (kein Code) | App |
| Sample-File-Inhalt von Zed kopieren in App lesen | App lokal kann nicht — gezielt fragen + zeigen |
| Memory-Watch während Qwen-Lauf vergessen | LM Studio + Aktivitätsanzeige beide offen |
| Browser auf während Qwen 27B läuft | App-Hygiene-Protokoll, Browser zu |
| Doku-Frage an CC, der Doku ändern will obwohl nur Antwort gewünscht | Frage in App, kein File-Edit |
| Mehrere Phasen-Blöcke parallel im selben CC-Run | ein Block pro Session, Reflexion dazwischen |

---

## 7. Token-Budget-Bewusstsein

Claude Pro hat ein gemeinsames Token-Budget für Claude Code + App-Konversation (gleicher Bucket). Routing-Effekt auf Tokens:

| Aktion | Token-Kosten |
|---|---|
| `ls`, `cat`, `git status` in Ghostty | 0 (kein Claude beteiligt) |
| Kurze Status-Frage in App | gering |
| Multi-File-Code-Generation in Zed-CC | hoch |
| Lange Strategie-Session in App | mittel |
| Code-Review mit Diff-Multi-File | hoch |

**Faustregel:** Vor jedem Tool-Wechsel kurz fragen: „Geht das auch in Ghostty?" Wenn ja, dort lösen.

---

## 8. Memory-Pressure-Regel (während Qwen-Läufen)

Aus `docs/00_persona_muente.md` Sektion 6: bei aktivem Qwen 27B sind ~4 GB RAM für macOS frei.

**Offen während Qwen-Lauf:** Zed, Ghostty, LM Studio, Aktivitätsanzeige.
**Zu:** Browser, Mail, Slack, Spotify, andere Editoren, Cloud-Sync-Apps.

**Zed-CC während Qwen-Lauf:** OK (läuft remote bei Anthropic), aber keine schweren lokalen Tasks parallel (großes Test-Suite, Linting in großem Repo).

---

## 9. Quick-Reference Tabelle

| Situation | Tool |
|---|---|
| Code editieren | Zed-CC |
| Diff prüfen | Zed-CC oder Ghostty (`git diff`) |
| Test laufen lassen | Ghostty |
| Commit | Ghostty oder Zed-CC |
| Push | Ghostty (manuell, nach User-OK) |
| Status prüfen | Ghostty (`python -m pipeline status`) |
| Datei-Inhalt sichten | Ghostty (`bat`, `cat`) oder Zed |
| Strategy / Plan | App |
| Quality-Review | App |
| Architektur-Entscheidung | App |
| Tag-Vokabular | App |
| Tag-Inventar generieren | Zed-CC |
| Smoke-Test ausführen | Ghostty + LM Studio + Aktivitätsanzeige |
| Smoke-Test bewerten | App |
| Reflexion schreiben | Zed-CC (Skelett) + App (Lessons) |

---

## 10. Änderungs-Log

- 2026-05-28 — Initial-Version, basierend auf Praxis-Lücke vom 28.05.2026
- 2026-06-25 — Ghostty-Beispiele auf aktuelle Pfade (`pkm-pipeline/` #2, Brain-Vault #3) statt toter `data/0X`-Legacy + verworfenem Clustering
