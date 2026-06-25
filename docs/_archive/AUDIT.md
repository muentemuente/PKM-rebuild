# AUDIT: Drift-Prüfung PKM-rebuild

**Zweck:** Soll-Ist-Abgleich. Prüfen, ob Implementierung noch den ursprünglichen
Projektzielen entspricht oder ob ein Drift (Scope / Goal / Usage / Komplexität) eingesetzt hat.

**Soll-Maßstab:** `Zielbeschreibung_PKM-Pipeline_rebuilt.md` (im Repo ablegen).
Diese Datei ist die verbindliche Baseline – nicht der Code, nicht die README.

---

## Grundregeln für Claude Code (gelten in ALLEN Phasen)

- **Read-only.** Nichts ändern, refaktorieren oder „aufräumen". Nur lesen + berichten.
- **Belegpflicht.** Jede Aussage mit Quelle (Datei:Zeile, Commit-Hash, Zitat). Kein Raten ohne Kennzeichnung.
- **Reihenfolge einhalten.** Phasen sequenziell. Output jeder Phase als Input der nächsten anhängen.
- **Baseline zuerst.** Phase 1 vor Phase 2 lesen, sonst werden Ziele rückwärts aus dem Code abgeleitet → kein Drift mehr messbar.

---

## Soll-Anker (verdichtet aus der Zielbeschreibung)

**Was das Tool SEIN soll:** Qualitäts-, Analyse- und Kuratierungspipeline für ein Markdown-/PKM-Archiv.
Kontrollierter Eingang → prüfen, bereinigen, vereinheitlichen, semantisch analysieren, Wissen verdichten.

**Was das Tool NICHT sein soll (Abschnitt 12 – kritische Drift-Wächter):**
- ❌ keine reine Scraping-Pipeline
- ❌ kein einfacher Markdown-Formatter
- ❌ kein bloßes Tagging-Skript

**3 Qualitätsebenen, gegen die geprüft wird:**
1. **Technische Korrektheit** – Markdown-Syntax, YAML, Pfade, Links, Assets, Tabellen, Codeblöcke, Reproduzierbarkeit.
2. **Dokumentarische Qualität** – Struktur, Lesbarkeit, Dokumenttyp, Metadaten, Quellenstatus, Überschriftenlogik, Standards.
3. **Wissensorganisatorische Qualität** – Taxonomie, Tags, Redundanzprüfung, semantische Ähnlichkeit, Synthese, interne Verlinkung, Themencluster.

**10 auditfähige Zielkriterien (Abschnitt 13):**
1. Markdown-Syntax + Dokumentstruktur prüfen/normalisieren
2. Frontmatter nach Schema validieren/ergänzen
3. Links, Assets, Tabellen, Codeblöcke zuverlässig erkennen + erhalten
4. Dokumenttyp, Thema, Begriffe, semantische Struktur analysieren
5. Tags/Kategorien/Metadaten nach kontrollierter Taxonomie vorschlagen
6. Redundanzen + semantisch ähnliche Dokumente erkennen
7. Synthese-/Verknüpfungspotenziale sichtbar machen
8. Qualitätsberichte + Prüfhinweise erzeugen
9. Automatische Änderungen nachvollziehbar protokollieren (Audit Trail)
10. Originalinhalt nicht unkontrolliert verfälschen/beschädigen

**Querschnitt-Prinzip:** Human-in-the-loop. Trennung zwischen sicheren Auto-Korrekturen,
KI-Vorschlägen und manueller Prüfung. Änderungen protokolliert + reversibel.

---

## Phase 1 — Baseline rekonstruieren

> Du bist Auditor, nicht Entwickler. Ändere nichts.
>
> Verbindliche Baseline ist `Zielbeschreibung_PKM-Pipeline_rebuilt.md`. Lies sie vollständig.
> Ergänze sie mit der real dokumentierten Historie:
> - README (älteste Version via `git log -p -- README*`) + aktueller Stand
> - Erste 10–15 Commits (`git log --reverse --stat`), Messages + Diffs
> - Vorhandene Design-/Konzept-Docs, frühe Issues/TODOs
>
> Liefere:
> 1. Tabelle „Ursprüngliche Ziele" (Ziel | Quelle | Beleg/Zitat) — gespeist primär aus der
>    Zielbeschreibung, abgeglichen mit der Commit-Historie.
> 2. Wo Zielbeschreibung und frühe Historie auseinandergehen: explizit als „Widerspruch Baseline ↔ Historie" markieren.
> 3. Die intendierte Nutzung (Wer? Welcher Use Case? Welcher Output je Datei?).
>
> Keine Bewertung. Nur Faktenlage.

---

## Phase 2 — Ist-Zustand erfassen

> Read-only. Erfasse den IST-Zustand objektiv, ohne Bezug zu den Zielen herzustellen.
>
> 1. **Entrypoints:** Alle CLI-Befehle (insb. `apply_to_vault`), main-Funktionen, exponierte APIs.
> 2. **Realer Datenfluss:** Input → welche Transformationen in welcher Reihenfolge → Output. Pro Transform: was tut er konkret?
> 3. **Feature-Inventar:** Was kann das Tool heute? Eine Zeile pro Fähigkeit.
> 4. **Komplexitätssignale:** Modul-/Dateianzahl, größte Dateien, Abhängigkeiten (requirements/pyproject),
>    toter/ungenutzter Code, nie aufgerufene Transforms.
> 5. **Schreibverhalten:** Welche Stellen verändern Dateien? Gibt es Logging/Protokollierung der Änderungen?
>    Sind Änderungen reversibel? Gibt es Human-in-the-loop-Punkte?
>
> Strukturierte Liste. Keine Interpretation der Absicht — nur Beobachtung mit Datei:Zeile.

---

## Phase 3 — Soll-Ist-Abgleich

> Vergleiche Baseline (Phase 1) mit Ist-Zustand (Phase 2).
>
> **A) Pro auditfähigem Zielkriterium (1–10 aus dem Soll-Anker):**
> Kriterium | Soll | Ist | Status [erfüllt / teilweise / verfehlt / übererfüllt] | Beleg
>
> **B) Pro Qualitätsebene (technisch / dokumentarisch / wissensorganisatorisch):**
> Abdeckungsgrad einschätzen. Welche Ebene ist über-, welche unterentwickelt?
> (Typische PKM-Falle: technische Ebene wuchert, wissensorganisatorische bleibt zurück.)
>
> **C) Listen:**
> - „Verwaiste Ziele": laut Baseline geplant, im Code nicht/kaum vorhanden.
> - „Ungeplante Features": im Code vorhanden, kein Bezug zu einem Baseline-Ziel.

---

## Phase 4 — Drift klassifizieren & bewerten

> Klassifiziere jede Abweichung aus Phase 3.
>
> **Drift-Typ:**
> - Scope-Drift (Umfang wächst/schrumpft)
> - Goal-Drift (Zweck verschiebt sich)
> - Usage-Drift (andere Nutzung als intendiert)
> - Komplexitäts-Drift (Aufwand übersteigt Nutzen)
>
> **Abgrenzungs-Check (Abschnitt 12 — kritisch):** Prüfe explizit, ob das Tool zu einem der
> verbotenen Muster driftet:
> - reine Scraping-Pipeline?
> - bloßer Markdown-Formatter (nur Phase „technisch", keine Semantik/Kuration)?
> - bloßes Tagging-Skript?
> Jeder Treffer = kritischer Goal-Drift.
>
> **Pro Eintrag:** Typ | Schweregrad [kritisch/moderat/kosmetisch] | Richtung [Reduktion/Wucherung] |
> Problem oder legitime Evolution? (kurze Begründung)
>
> **Abschluss:**
> - Top-3-Risiken
> - Pro Risiko eine Empfehlung: reparieren / dokumentieren & legitimieren (Baseline anpassen) / akzeptieren
> - Gesamturteil: Ist die Pipeline noch eine Kuratierungspipeline — oder bereits abgedriftet?

---

## Ausführung

1. `Zielbeschreibung_PKM-Pipeline_rebuilt.md` ins Repo legen.
2. In Claude Code: diese `AUDIT.md` öffnen, Phasen 1→2→3→4 nacheinander als Prompt geben.
3. Output jeder Phase speichern und der nächsten als Kontext anhängen.
4. Bei Kontextverlust: Soll-Anker (oben) erneut mitgeben.
