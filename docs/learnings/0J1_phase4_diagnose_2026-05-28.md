---
title: "0J.1 Diagnose — Phase 4 Merge-Logik"
slug: 0j1-phase4-diagnose-2026-05-28
status: stable
created: 2026-05-28
updated: 2026-05-28
---

# 0J.1 Diagnose — Phase 4 Merge-Logik

## Quantitativer Befund

| Metrik | Wert |
|---|---|
| Segmente gesamt | 5.368 |
| Segmente < 30 Wörter | 2.353 (43.8 %) |
| Segmente < 50 Wörter | 3.333 (62.1 %) |
| Segmente < 150 Wörter | 4.977 (92.7 %) |
| `denkschulen_ueberblick` Segmente | 585 (!) |
| Zweitgrößtes File (`proportionen-...`) | 100 Segmente |

## Root Cause

`pipeline/phase_4_segment.py` → `_segment_document()`:

1. `_parse_raw_sections(body)` teilt bei **jeder** Überschrift — inklusive Überschriften ohne nachfolgenden Body-Text
2. `_split_section_lines(lines, max_words)` teilt lange Sektionen → korrekt
3. **Merge-Logik existiert nicht.** Der Parameter `min_words` wird an `_segment_document()` übergeben, aber innerhalb der Funktion nie ausgewertet. Er hat null Effekt auf das Ergebnis.

```python
# pipeline/phase_4_segment.py, Zeile 184–222
def _segment_document(
    doc_id, body, source_path, min_words, max_words  # min_words wird übergeben...
) -> list[SegmentRecord]:
    raw_sections = _parse_raw_sections(body)
    split_sections = [...]  # nur max-split, kein merge
    records = [SegmentRecord(...) for ...]  # min_words nie geprüft
    return records  # <- kein Post-Processing
```

## Konkrete Beispiele Heading-only-Segmente

```
2 Wörter  D_befriffssammlung-...-S0008  ## Tag-Sammlung
2 Wörter  D_befriffssammlung-...-S0009  ### Tech
4 Wörter  D_css-test-...-S0004          ## Überschriften-Test
```

Heading-only-Segmente entstehen, wenn auf eine Überschrift sofort die nächste Überschrift folgt (kein Body-Text dazwischen). `_parse_raw_sections()` emittiert sie als eigene Section.

## Vorgeschlagener Fix (zur Freigabe)

Neue Post-Processing-Funktion `_merge_undersized_segments(records, min_words)` nach Zeile 222:

1. **Heading-only-Segment**: erstes non-blank Token nach der Heading-Zeile fehlt → immer mit nächstem Segment mergen (unabhängig von `min_words`)
2. **Untergrößiges Segment** (`word_count < min_words`): mit nächstem gleichberechtigten Segment mergen (falls vorhanden); sonst mit vorherigem
3. **Kette**: Wiederholung bis kein Segment mehr unter `min_words` liegt
4. **Edge-Case letztes Segment**: wenn unter `min_words` und kein Nachfolger → mit Vorgänger mergen; wenn erstes und einziges Segment → unverändert lassen (keine Alternative)
5. **Code-Blöcke/Tabellen**: `contains_code` + `contains_table` Flags im gemergten Segment werden per OR kombiniert

Heading-Pfad beim Merge: Pfad des ersten (führenden) Segments bleibt erhalten.

## Nicht-Überraschungen

- Die Logik für max_words (lange Sektionen splitten) funktioniert korrekt
- Code-Block-Erkennung (_has_code_block, _has_table) funktioniert korrekt
- `_classify_lines` und `_group_into_blocks` sind in Ordnung
- Das Problem ist **ausschließlich** das fehlende Post-Merge-Schritt

## Erwartete Wirkung der geplanten Fixes (0J.2 + 0J.3 + 0J.4 + 0J.5)

| Fix | Erwartete Wirkung |
|---|---|
| Merge-Logik (`min_words`=150) | ~4.977 Mini-Segmente auf <<1.000 reduziert |
| `denkschulen_ueberblick` Book-Pfad (H1/H2, max=5000) | 585 → ca. 15–30 Segmente |
| Gesamt Segment-Count | 5.368 → geschätzt 800–1.500 |
| Ø Wörter/Segment | ~60 → geschätzt 200–400 |
