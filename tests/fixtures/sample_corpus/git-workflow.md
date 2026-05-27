# Git-Workflow

Standardisierter Workflow für Feature-Entwicklung mit Git.

## Branches

- `main` — stabiler Produktions-Branch
- `feature/<name>` — neue Features
- `fix/<name>` — Bugfixes
- `docs/<name>` — Dokumentation

## Schritte

1. Vom main-Branch einen neuen Feature-Branch erstellen
2. Änderungen committen (Conventional Commits)
3. Push zum Remote
4. Pull Request erstellen
5. Code-Review abwarten
6. Merge nach Approval

## Conventional Commits

```
feat: neues Feature hinzufügen
fix: Bug in Authentifizierung beheben
docs: README aktualisieren
refactor: Datenbank-Abfragen optimieren
test: Tests für Phase 1 hinzufügen
chore: Abhängigkeiten aktualisieren
```

## Häufige Fehler

- Direkt in `main` committen
- Zu große, unübersichtliche Commits
- Fehlende Commit-Messages
