---
title: Task 0.N — CC-Autonomie-Setup + Arbeitsvereinbarung
slug: 0N-autonomy-setup
status: stable
created: 2026-05-29
updated: 2026-05-29
block: 0.N (Phase II.1)
branch: chore/cc-autonomy
---

# Task 0.N — Autonomie-Setup + dauerhafte Arbeitsvereinbarung

**Zweck:** CC arbeitet ab jetzt maximal eigenständig. Freigaben gibt es nur noch für **inhaltliche / strategische / irreversible** Entscheidungen — **nie** für reinen Projektablauf (Commits, File-Erstellung, Tests, Refactors, Pipeline-Läufe). Dieser Block schreibt die Permissions, die das durchsetzen, und legt die Arbeitsvereinbarung fest, die für **alle** folgenden Blöcke gilt.

**Dieser Block ist selbst autonom ausführbar** — alle inhaltlichen Entscheidungen (Permission-Inhalte) sind unten vorgegeben. CC setzt um, testet, committet, berichtet am Ende. **Kein Zwischen-Gate.**

---

## 1. Permissions in `.claude/settings.json` (projekt-lokal, gitignored)

Exakte Schema-Syntax gegen offizielle Docs verifizieren (https://docs.claude.com/en/docs/claude-code/overview → Settings/Permissions) — das ist ein technischer Schritt, autonom. Inhalt der drei Listen:

### allow — kein Prompt, läuft durch
- alle File-Reads + File-Edits **innerhalb** `~/projects/aktiv/PKM-rebuild/`
- Schreiben in Daten-Outputs: `~/projects/aktiv/PKM_rebuild/data/02_pipeline_output/`, `/03_drafts/`, `/04_vault/`, `/backups/`
- `pytest`, `ruff check`, `ruff format`, `mypy`
- `git add`, `git commit`, `git status`, `git diff`, `git log`, `git branch`, `git checkout`, `git switch`, `git stash`
- `git push` **auf Feature-Branches** (nicht main — siehe ask)
- `python -m pipeline status|validate|reports`
- `python -m pipeline run --phase N` und `--from-phase N` (ohne `--force`)
- `python -m pipeline run --sample N`
- Hilfs-Tools: `rg`, `fd`, `bat`, `eza`, `jq`, `cat`, `ls`, `mkdir`, `touch`, `mv`/`cp` innerhalb der erlaubten Roots
- `gh pr create`, `gh pr view`, `gh pr list`

### ask — kurze Rückfrage (folgenreich/irreversibel)
- `git push` **auf `main`** + jeder Merge nach `main`
- `python -m pipeline run --force` (überschreibt Outputs)
- `pip install` / Änderung an `pyproject.toml`-Dependencies
- `git reset --hard`, `git rebase`, `git revert`
- `gh pr merge`

### deny — niemals
- `rm -rf` (jede rekursive Löschung)
- **jeder Schreibzugriff** auf `~/projects/aktiv/PKM_rebuild/data/01_corpus_input/` (Korpus read-only)
- jeder Pfad **außerhalb** `~/projects/aktiv/PKM-rebuild/` und `~/projects/aktiv/PKM_rebuild/data/`
- `git push --force` (jede Variante)
- `gh repo delete`, `gh repo archive`

---

## 2. Sicherheitsnetz (in diesem Block einrichten)

- [ ] Korpus-Ordner OS-seitig read-only: `chmod -R a-w ~/projects/aktiv/PKM_rebuild/data/01_corpus_input/` (zusätzlich zur deny-Regel)
- [ ] SessionStart-Hook (Doc 06 §5.3): lädt `git branch --show-current` + `git status --short` + letzte 5 Commits in den Kontext
- [ ] PreCompact-Hook (Doc 06 §5.2): Snapshot vor Auto-Compaction
- [ ] `scripts/snapshot.sh` lauffähig prüfen (Korpus + Vault)

---

## 3. ARBEITSVEREINBARUNG (gilt ab jetzt für ALLE Blöcke)

### Default: durchlaufen, nicht fragen
CC arbeitet einen Block vollständig durch — liest Pflicht-Docs, implementiert, hält Tests grün, committet auf Feature-Branch, berichtet am **Block-Ende**. Zwischen-Status nur wenn nötig.

### STOP nur bei (echte Gates):
1. **Inhaltliche Weiche** — mehrere fachlich tragfähige Wege, Entscheidung ändert das Ergebnis (z.B. Tag-Hierarchie, Merge-Konflikt-Auflösung)
2. **`main`-Push / Merge nach main** — immer Freigabe
3. **Irreversibel + datenrelevant** — `--force`, Löschungen, Schema-Migration mit Datenverlust-Risiko
4. **Menschliche Pflichtaufgaben** — Tag-Vokabular finalisieren, Wikilink-Bestätigung, `stable`-Promotion, Hardware (Time Machine, 2. Medium)
5. **Blocker** — Test rot und Ursache unklar, Spec widersprüchlich, Annahme nicht verifizierbar

### NIEMALS stoppen für (reiner Ablauf):
- Branch-Commits, Branch-Push, File-/Ordner-Erstellung
- Tests, Linting, Formatierung, Refactors mit grünen Tests
- Doku-Updates nach klarer Vorgabe
- Pipeline-Läufe ohne `--force`
- Task-Files für Folge-Blöcke selbst erstellen (nach Vorlage)
- Commit-Message-Stil, Datei-Benennung, Verzeichnis-Struktur

### Regeln, die bestehen bleiben
- Commit nur auf Feature-Branch, **nie direkt main** (Vorfall cd96f84 nicht wiederholen)
- Conventional Commits
- Tests grün vor Commit (`pytest`, `ruff`)
- Bei Unsicherheit über Fakten: `> [!question]` statt raten
- Reasoning intern, nur Ergebnis berichten

---

## 4. Block-Ende-Bericht (Format, knapp)
Pro abgeschlossenem Block genau das:
```
✅ Block X done
- Branch: <name> @ <hash>
- Tests: N grün / Ruff clean
- Geändert: <1-Zeilen-Liste>
- Gate erreicht? <nein / ja: welches>
- Nächster Block laut Roadmap: <ID>
```

---

## 5. Akzeptanz 0.N
- [ ] `.claude/settings.json` mit allow/ask/deny geschrieben + JSON-valide
- [ ] Test: ein allow-Befehl läuft ohne Prompt, ein deny-Befehl wird blockiert
- [ ] Korpus OS-read-only verifiziert (`ls -l`, Schreibversuch scheitert)
- [ ] SessionStart- + PreCompact-Hook aktiv
- [ ] Commit auf `chore/cc-autonomy`
- [ ] Diese Arbeitsvereinbarung als `docs/06b_tool_routing.md` ergänzt oder `docs/00b_arbeitsvereinbarung.md` neu — CC entscheidet Ablage, committet
- [ ] Block-Ende-Bericht

## 6. Nach 0.N — autonom weiterlaufen
Ohne erneute App-Freigabe direkt fortsetzen laut Roadmap §3:
**0J.8-Rest + 0.M (Reports-Bug)** → eigener Branch, durcharbeiten, am Ende Bericht. Nur bei einem der 5 STOP-Fälle melden.

---

## Änderungs-Log
- 2026-05-29 — Initial
