---
title: "Asset-Management — Bilder & Dateien einbetten"
slug: "asset-management"
status: stable
created: 2026-06-13
updated: 2026-06-13
---

# Asset-Management

> **Master-Datei.** Ziel-Ablage: `09_Brain-Vault/00_Meta/asset-management.md`.
> Diese Anleitung ist eigenständig lesbar — sie braucht keine weiteren Repo-Docs.

So werden Bilder, PDFs und andere Dateien (zusammen: **Assets**) in den Vault eingebettet. Eine Regel, kein Sonderfall.

---

## Die eine Regel

1. **Wohin:** jedes Asset in den Ordner `_assets/` im Vault-Root. Flach, keine Unterordner.
2. **Wie benannt:** `<note-slug>__<original-name>.ext` — der Slug der Note, dann zwei Unterstriche, dann der ursprüngliche Dateiname.
3. **Wie eingebettet:** mit doppelten eckigen Klammern und Ausrufezeichen — `![[name]]`. **Nie** mit Pfad.

---

## Schritt für Schritt: Bild einfügen

Angenommen, du schreibst die Note `http-https.md` und willst `handshake.png` einbetten.

1. **Benenne** die Bilddatei um:
   `handshake.png` → `http-https__handshake.png`
   (Note-Slug `http-https` + `__` + Originalname.)
2. **Lege** sie in `_assets/` ab.
3. **Bette** im Note-Body ein:
   ```markdown
   ![[http-https__handshake.png]]
   ```
4. Fertig. Obsidian rendert das Bild. Kein Pfad nötig.

> **Tipp:** Wenn die Obsidian-Settings (unten) gesetzt sind, legt Obsidian eingefügte Anhänge automatisch in `_assets/` ab — dann musst du nur noch korrekt umbenennen.

---

## Beispiel-Embed

```markdown
## Der TLS-Handshake

![[http-https__handshake.png]]

Der Ablauf in vier Schritten …
```

---

## Warum so? (kurz)

- **Pfad-frei** (`![[name]]` statt `![](pfad)`): Note und Bild bleiben **frei verschiebbar**. Du kannst eine Note in einen anderen Ordner ziehen oder das Asset umsortieren — der Embed bricht nicht, weil er nur den (eindeutigen) Dateinamen kennt, nicht den Ort.
- **Eindeutiger Name** (`<note-slug>__…`): Weil der Embed über den Dateinamen auflöst, darf es keine zwei gleich benannten Assets geben. Das Schema macht jeden Namen vault-weit eindeutig.
- **Ein flacher Pool** (`_assets/`): Kein Suchen in Cluster-Ordnern, keine verwaisten Bilder. Der Unterstrich zeigt: nicht-inhaltlich, gehört nicht zu den nummerierten Wissens-Clustern.

---

## Do / Don't

| ✅ Do | ❌ Don't |
|---|---|
| `![[http-https__handshake.png]]` | `![](_assets/handshake.png)` |
| Asset nach `_assets/` | Asset neben die Note in den Cluster-Ordner |
| `<note-slug>__<original>.ext` | Originalname (`screenshot.png`) unverändert |
| ein flacher Pool | Unterordner `_assets/webentwicklung/…` |

---

## Obsidian-Settings (einmalig setzen)

Einstellungen → *Files & Links*:

| Setting | Wert |
|---|---|
| Use `[[Wikilinks]]` | **on** |
| Automatically update internal links | **on** |
| Default location for new attachments | `_assets` |
| New link format | **Shortest path when possible** |

Danach landen neu eingefügte Anhänge automatisch in `_assets/`, und Embeds bleiben pfad-frei.

> **Settings sichern:** `.obsidian/` wird nicht versioniert. Kopiere mindestens `.obsidian/app.json` nach `00_Meta/obsidian-settings-backup.json`, damit die Einstellungen reproduzierbar sind.

---

## Diagramme sind keine Assets

Strukturierte Diagramme werden **nicht** als Bild eingebettet, sondern als Mermaid-Text in den Note-Body geschrieben. Siehe `00_Meta/diagramm-standard.md`.
