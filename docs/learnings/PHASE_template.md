---
title: PHASE_<NN> — <slug>
slug: phase-<nn>-<slug>
type: phase-reflection
status: draft
phase_number: <NN>
phase_name: ""
session_started: "YYYY-MM-DD HH:MM"
session_ended: "YYYY-MM-DD HH:MM"
duration_minutes: 0
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
---

# Phase <NN>: <Phase-Name>

Reflexionsdokument nach Abschluss der Phase. Pflicht laut `docs/01_strategy.md` Sektion 8 (Lernziele).

> **Hinweis zum Ausfüllen:** Stichpunkte reichen. Vollständige Sätze nur, wo sie etwas hinzufügen. Ehrlichkeit > Performance — auch „lief nicht" ist eine gültige Antwort.

---

## 1. Was war geplant?

> Ziel der Phase, definiert in `docs/02_pipeline_spec.md` Sektion 6 für diese Phase.

- Erwartete Outputs:
- Akzeptanzkriterien (aus Spec):
- Geschätzte Dauer (Realistic-Wert aus Strategy):

---

## 2. Was ist tatsächlich passiert?

### 2.1 Outputs

| Erwartet | Tatsächlich | Bemerkung |
|---|---|---|
| | | |

### 2.2 Akzeptanzkriterien — Status

- [ ] (Kriterium 1)
- [ ] (Kriterium 2)
- [ ] ...

### 2.3 Dauer

- Tatsächliche Arbeit: __ min
- Inkl. Pausen / Wartezeiten: __ min
- Abweichung von Schätzung: +/- %

---

## 3. Probleme & Blocker

> Ehrliche Auflistung. Was hat aufgehalten? Was hat länger gedauert als erwartet?

- Problem 1:
  - Symptom:
  - Lösung / Workaround:
  - Zeit verbraucht: __ min
- Problem 2:
  - ...

### 3.1 Ungelöste Probleme (→ TODO)

- [ ] (Problem, das in nächste Phase mitgenommen wird)

---

## 4. Was wurde gelernt?

> Welche Konzepte, Tools, Patterns sind durch diese Phase besser verstanden? Verknüpfung zu Lernzielen aus `docs/01_strategy.md` Sektion 8.

### 4.1 Technisch
-

### 4.2 Workflow / Methodik
-

### 4.3 Über Claude Code / Qwen / Tooling
-

---

## 5. Was würde ich nächstes Mal anders machen?

- Konkrete Verhaltensänderung 1:
- Konkrete Verhaltensänderung 2:

> Diese Punkte fließen in zukünftige Phasen ein. Wenn sie wiederkehren, gehören sie eventuell in `docs/00_persona_muente.md` als dauerhafte Regel.

---

## 6. Token-Verbrauch (Claude Code)

> Grobe Schätzung. Genaue Werte gibt `claude usage` (falls verfügbar) oder Anthropic-Settings.

| Wert | Schätzung |
|---|---|
| Anzahl Sessions | |
| Geschätzte Input-Tokens | |
| Geschätzte Output-Tokens | |
| 5h-Limit erreicht? | ja / nein, wie oft |
| Weekly-Cap-Druck? | ja / nein |

---

## 7. Memory-/Hardware-Beobachtungen

> Nur wenn Phase mit Qwen-Lauf verbunden war (Phasen 6, 8).

- Memory-Pressure während Lauf:
- Andere Apps geschlossen?
- Probleme mit LM Studio / Qwen-Stabilität:
- Geschätzte Inferenz-Geschwindigkeit (Tokens/Sekunde, falls beobachtbar):

---

## 8. Folgende TODOs / offene Fragen

> Was kommt als nächstes? Was muss noch geklärt werden, bevor die nächste Phase beginnen kann?

- [ ]
- [ ]
- [ ]

---

## 9. Cross-Reference

| Bereich | Verweis |
|---|---|
| Spec für diese Phase | `docs/02_pipeline_spec.md` Sektion 6 |
| Vorherige Reflexion | `docs/learnings/PHASE_<NN-1>_*.md` |
| Vault-Standard (falls relevant) | `docs/03_vault_standard.md` |
| Pipeline-State zum Phasen-Ende | `data/02_pipeline_output/pipeline_state.json` |

---

## 10. Gesamtbewertung der Phase

> Eine Zeile, kurz und ehrlich.

**Lief gut wenn:** _____
**Lief schlecht wenn:** _____

---

## Änderungs-Log

- YYYY-MM-DD — Initial-Notizen während Phase
- YYYY-MM-DD — Finale Bearbeitung nach Phasen-Ende
