---
title: CC-Arbeitsvereinbarung
slug: 00b-arbeitsvereinbarung
status: stable
created: 2026-05-29
updated: 2026-05-29
---

# CC-Arbeitsvereinbarung

Gilt ab Block 0.N für alle CC-Sessions in diesem Projekt. Ergänzt `docs/06b_tool_routing.md`.

---

## 1. Default: durchlaufen, nicht fragen

CC arbeitet einen Block vollständig durch — liest Pflicht-Docs, implementiert, hält Tests grün, committet auf Feature-Branch, berichtet am **Block-Ende**. Zwischen-Status nur wenn nötig.

---

## 2. STOP nur bei diesen 5 Gates

| # | Gate | Beispiel |
|---|---|---|
| 1 | **Inhaltliche Weiche** — mehrere fachlich tragfähige Wege, Entscheidung ändert das Ergebnis | Tag-Hierarchie, Merge-Konflikt-Auflösung |
| 2 | **`main`-Push / Merge nach `main`** — immer Freigabe | `git push origin main`, `git merge main` |
| 3 | **Irreversibel + datenrelevant** | `--force`, Löschungen, Schema-Migration mit Datenverlust-Risiko |
| 4 | **Menschliche Pflichtaufgaben** | Tag-Vokabular finalisieren, Wikilink-Bestätigung, `stable`-Promotion, Hardware-Entscheidungen |
| 5 | **Blocker** | Test rot und Ursache unklar, Spec widersprüchlich, Annahme nicht verifizierbar |

---

## 3. NIEMALS stoppen für (reiner Ablauf)

- Branch-Commits, Branch-Push auf Feature-Branches, File-/Ordner-Erstellung
- Tests, Linting, Formatierung, Refactors mit grünen Tests
- Doku-Updates nach klarer Vorgabe
- Pipeline-Läufe ohne `--force`
- Task-Files für Folge-Blöcke selbst erstellen (nach Vorlage)
- Commit-Message-Stil, Datei-Benennung, Verzeichnis-Struktur

---

## 4. Regeln, die immer gelten

- Commit nur auf Feature-Branch, **nie direkt `main`** (Vorfall cd96f84 nicht wiederholen)
- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- Tests grün vor Commit (`pytest`, `ruff`)
- Bei Unsicherheit über Fakten: `> [!question]` statt raten
- Reasoning intern — nur Ergebnis berichten

---

## 5. Block-Ende-Bericht (Format)

```
✅ Block X done
- Branch: <name> @ <hash>
- Tests: N grün / Ruff clean
- Geändert: <1-Zeilen-Liste>
- Gate erreicht? <nein / ja: welches>
- Nächster Block laut Roadmap: <ID>
```

---

## 6. Permissions-Setup (`.claude/settings.json`, gitignored)

Die Datei liegt lokal unter `.claude/settings.json` (gitignored) und wird nicht committed. Inhalt ist unten als Referenz-Template dokumentiert, damit sie nach einem Reset reproduzierbar ist.

### read-only-Konzept (3 Orte)

CC darf an genau definierten Stellen schreiben; Quellen und das Endprodukt sind geschützt:

| Ort | Regel |
|---|---|
| **#1** Repo `PKM-rebuild/` | `Read/Edit/Write(./**)` — voll |
| **#2** `pkm-pipeline/` | **Read** komplett; **Write** nur `input/ work/ drafts/ output/ review/ archive/` |
| **#2** `pkm-pipeline/_ingest/` | **read-only** (Quellen) — `deny` Write/Edit |
| **#2** `pkm-pipeline/archive/corpus_legacy/` | **read-only** (historischer Korpus) — `deny` Write/Edit |
| **#3** `09_Brain-Vault/` | **Read** ja, **Write/Edit `deny`** (generell read-only) |

`_ingest/` + `archive/corpus_legacy/` sind das go-forward-Analog zum früheren `01_corpus_input`-Schutz.

> **#3-Schreibausnahme (`_assets`, add-only):** Da bei Claude Code `deny` jede `allow` überstimmt, gibt es **kein** wirksames allow-unter-deny für `09_Brain-Vault/_assets/`. Der **einzige sanktionierte Vault-Write** läuft über `make publish-assets` (`scripts/publish_assets.py`, add-only via `shutil`) — ein Bash-Script, das vom Write/Edit-Tool-`deny` nicht betroffen ist. Direkte Tool-Writes in den Vault bleiben blockiert.

> **Delete-Schutz:** pfad-spezifischer Lösch-Schutz läuft über die globalen `Bash(rm -rf*|rm -r *|…)`-`deny`-Regeln (keine engeren Pfad-Muster nötig).

**Hook-Scripts** (gitgetrackt, ausführbar):
- `.claude/hooks/session-start.sh` — lädt Git-Kontext bei SessionStart
- `.claude/hooks/pre-compact.sh` — schreibt Snapshot nach `.claude/snapshots/` vor Auto-Compaction

**OS-Schutz Quellen** (zusätzlich zu den `deny`-Regeln):
```bash
chmod -R a-w ~/projects/aktiv/pkm-pipeline/_ingest/ ~/projects/aktiv/pkm-pipeline/archive/corpus_legacy/
```

### settings.json Referenz-Template

```json
{
  "permissions": {
    "allow": [
      "Read(./**)", "Edit(./**)", "Write(./**)",
      "Read(~/projects/aktiv/pkm-pipeline/**)",
      "Write(~/projects/aktiv/pkm-pipeline/input/**)",
      "Write(~/projects/aktiv/pkm-pipeline/work/**)",
      "Write(~/projects/aktiv/pkm-pipeline/drafts/**)",
      "Write(~/projects/aktiv/pkm-pipeline/output/**)",
      "Write(~/projects/aktiv/pkm-pipeline/review/**)",
      "Write(~/projects/aktiv/pkm-pipeline/archive/**)",
      "Read(~/Zentrale/09_Brain-Vault/**)",
      "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)",
      "Bash(git add *)", "Bash(git commit*)", "Bash(git branch*)",
      "Bash(git checkout*)", "Bash(git switch*)", "Bash(git stash*)",
      "Bash(git push origin *)", "Bash(git push -u origin *)",
      "Bash(git push --set-upstream origin *)",
      "Bash(pytest*)", "Bash(ruff*)", "Bash(mypy*)",
      "Bash(python -m pipeline status*)", "Bash(python -m pipeline validate*)",
      "Bash(python -m pipeline reports*)",
      "Bash(python -m pipeline run --phase *)",
      "Bash(python -m pipeline run --from-phase *)",
      "Bash(python -m pipeline run --sample *)",
      "Bash(python -m pipeline run --dry-run*)",
      "Bash(rg *)", "Bash(fd *)", "Bash(bat *)", "Bash(eza *)",
      "Bash(jq *)", "Bash(cat *)", "Bash(ls*)", "Bash(mkdir *)",
      "Bash(touch *)", "Bash(mv *)", "Bash(cp *)", "Bash(find *)",
      "Bash(echo *)", "Bash(wc *)", "Bash(head *)", "Bash(tail *)",
      "Bash(grep *)", "Bash(sort *)", "Bash(shasum *)",
      "Bash(date*)", "Bash(hostname*)", "Bash(du *)",
      "Bash(chmod *)", "Bash(bash *)",
      "Bash(gh pr create*)", "Bash(gh pr view*)", "Bash(gh pr list*)",
      "Bash(gh pr status*)", "Bash(gh pr checks*)"
    ],
    "ask": [
      "Bash(git push)", "Bash(git push origin main*)", "Bash(git push --tags*)",
      "Bash(python -m pipeline run --force*)",
      "Bash(pip *)", "Bash(uv add *)", "Bash(uv remove *)", "Bash(uv pip *)",
      "Bash(git reset --hard*)", "Bash(git rebase*)", "Bash(git revert*)",
      "Bash(gh pr merge*)"
    ],
    "deny": [
      "Write(~/Zentrale/09_Brain-Vault/**)",
      "Edit(~/Zentrale/09_Brain-Vault/**)",
      "Write(~/projects/aktiv/pkm-pipeline/_ingest/**)",
      "Edit(~/projects/aktiv/pkm-pipeline/_ingest/**)",
      "Write(~/projects/aktiv/pkm-pipeline/archive/corpus_legacy/**)",
      "Edit(~/projects/aktiv/pkm-pipeline/archive/corpus_legacy/**)",
      "Bash(rm -rf*)", "Bash(rm -r *)", "Bash(rm -fr*)", "Bash(rm -Rf*)",
      "Bash(git push --force*)", "Bash(git push -f *)", "Bash(git push -f)",
      "Bash(gh repo delete*)", "Bash(gh repo archive*)"
    ]
  },
  "hooks": {
    "SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "bash .claude/hooks/session-start.sh"}]}],
    "PreCompact": [{"matcher": "auto", "hooks": [{"type": "command", "command": "bash .claude/hooks/pre-compact.sh"}]}]
  }
}
```

---

## Änderungs-Log

- 2026-05-29 — Initial (Block 0.N)
