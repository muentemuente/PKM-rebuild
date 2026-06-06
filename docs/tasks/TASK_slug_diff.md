# TASK — Slug-Diff Vault ↔ Drafts (read-only Herkunfts-Klärung)

**Zweck:** Klären, woher die 191 Vault-Artikel stammen — finaler Build aus den 180 reviewten Drafts oder veralteter Build. Triage meldet nur 27 IN_VAULT bei 191 Vault-Files; dieser Widerspruch wird hier faktisch aufgelöst. Output = **ein** Markdown-Report.

## Arbeitsregeln
- **Read-only.** Keine Datei ändern/löschen. Einzige Schreiboperation: der Report.
- `$HOME` statt `~` in Assignments. Output `>> "$REPORT" 2>&1`, kein mid-flight `| head`.
- Slug-Vergleich **NFC-normalisiert** (macOS-NFD-Falle, vgl. WP1-Bug). Dafür Python statt reinem bash.
- Autonom, **kein** STOP. Am Ende `ℹ STATUS` (≤10 Zeilen) in den App-Chat. Keine Folgeaktion einleiten.

## Setup
```bash
REPO="$HOME/projects/aktiv/PKM-rebuild"
DATA="$HOME/projects/aktiv/PKM_rebuild/data"
TS=$(date +%Y%m%d_%H%M)
REPORT="$REPO/docs/SLUG_DIFF_${TS}.md"
echo "# Slug-Diff Vault ↔ Drafts $TS" > "$REPORT"
```

---

## Block A — Slug-Mengen + Diff (NFC-normalisiert)
```bash
cd "$REPO"
DATA="$DATA" python3 - >> "$REPORT" 2>&1 <<'PY'
import os, unicodedata
from pathlib import Path
DATA = Path(os.environ["DATA"])
VAULT, DRAFTS = DATA/"04_vault", DATA/"03_drafts"

def nfc(s): return unicodedata.normalize("NFC", s)

# Vault-Artikel (ohne _index, nur Cluster-Ebene), exkl. 00_Meta
vault = set()
for p in VAULT.rglob("*.md"):
    if p.name == "_index.md": continue
    if "00_Meta" in p.parts: continue
    vault.add(nfc(p.stem))

drafts = {nfc(p.stem) for p in DRAFTS.glob("*.md") if not p.name.endswith(".body.md")}
hold   = {nfc(p.stem) for p in (DRAFTS/"_hold").glob("*.md")} if (DRAFTS/"_hold").exists() else set()

inter   = vault & drafts
only_v  = vault - drafts          # nur im Vault = Altlast-Verdacht
only_d  = drafts - vault          # Drafts ohne Vault-Pendant = nicht migriert
v_hold  = vault & hold            # geparkte Gedanken trotzdem im Vault?

print("## A. Mengen (NFC-normalisiert)")
print(f"- Vault-Artikel:           {len(vault)}")
print(f"- Drafts (ready):          {len(drafts)}")
print(f"- _hold (Gedanken):        {len(hold)}")
print(f"- Schnittmenge Vault∩Drafts: {len(inter)}")
print(f"- NUR im Vault (Altlast?):   {len(only_v)}")
print(f"- NUR in Drafts (nicht migriert?): {len(only_d)}")
print(f"- Vault∩_hold (sollte 0):    {len(v_hold)}")
print()
print("### A.1 NUR im Vault (erste 40)")
for s in sorted(only_v)[:40]: print(f"  - {s}")
print()
print("### A.2 NUR in Drafts (erste 40)")
for s in sorted(only_d)[:40]: print(f"  - {s}")
print()
print("### A.3 Vault∩_hold (alle)")
for s in sorted(v_hold): print(f"  - {s}")
PY
```

## Block B — Build-Datum/Lauf-Herkunft (Frontmatter-Stichprobe)
```bash
echo "## B. Herkunfts-Marker im Vault-Frontmatter" >> "$REPORT"
echo '```' >> "$REPORT"
echo "--- Verteilung last_synthesized (welcher Lauf?) ---" >> "$REPORT"
grep -rh '^last_synthesized:' "$DATA/04_vault"/*/*.md 2>/dev/null | sort | uniq -c | sort -rn >> "$REPORT"
echo "--- Verteilung created ---" >> "$REPORT"
grep -rh '^created:' "$DATA/04_vault"/*/*.md 2>/dev/null | sort | uniq -c | sort -rn >> "$REPORT"
echo "--- Verteilung prompt_version ---" >> "$REPORT"
grep -rh '^prompt_version:' "$DATA/04_vault"/*/*.md 2>/dev/null | sort | uniq -c | sort -rn >> "$REPORT"
echo "--- Datei-mtime-Spanne der Vault-Artikel ---" >> "$REPORT"
find "$DATA/04_vault" -name '*.md' ! -name '_index.md' -mindepth 2 -exec stat -f '%Sm' -t '%Y-%m-%d' {} \; 2>/dev/null | sort | uniq -c >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block C — Tag-Stand im Vault (bereinigt oder alt?)
```bash
echo "## C. Tag-Stand im gebauten Vault" >> "$REPORT"
echo '```' >> "$REPORT"
echo "tag-system.md vorhanden: $([ -f "$DATA/04_vault/00_Meta/tag-system.md" ] && echo JA || echo NEIN)" >> "$REPORT"
echo "--- Existieren im Vault Tags, die laut Review gedroppt werden sollten? (Stichprobe) ---" >> "$REPORT"
for t in funktioniert mehrere gut output workflows code haeufige meta best-practices format language; do
  c=$(grep -rl "[\"' ]$t[\"',]" "$DATA/04_vault"/*/*.md 2>/dev/null | wc -l | tr -d ' ')
  echo "  drop-Kandidat '$t' in $c Vault-Files" >> "$REPORT"
done
echo "(>0 bei mehreren = Vault läuft mit unbereinigten Tags = Build vor Tag-Arbeit)" >> "$REPORT"
echo '```' >> "$REPORT"
```

## Block D — Korpus-Hidden-File-Diskrepanz aufklären
```bash
echo "## D. Korpus-Zähldiskrepanz (199 vs 203)" >> "$REPORT"
echo '```' >> "$REPORT"
echo "sichtbare .md:        $(find "$DATA/01_corpus_input" -name '*.md' ! -name '.*' 2>/dev/null | wc -l)" >> "$REPORT"
echo "AppleDouble ._*.md:   $(find "$DATA/01_corpus_input" -name '._*.md' 2>/dev/null | wc -l)" >> "$REPORT"
echo ".DS_Store gesamt:     $(find "$DATA/01_corpus_input" -name '.DS_Store' 2>/dev/null | wc -l)" >> "$REPORT"
echo "--- die 4 'extra' Files konkret (alle .md, inkl. hidden) ---" >> "$REPORT"
find "$DATA/01_corpus_input" -name '*.md' 2>/dev/null | sort >> "$REPORT"
echo '```' >> "$REPORT"
```

## Abschluss
```bash
echo "Report: $REPORT" ; echo "Zeilen: $(wc -l < "$REPORT")"
```

**ℹ STATUS an App-Chat (≤10 Zeilen):**
1. Schnittmenge Vault∩Drafts (A) — Kernzahl
2. NUR-im-Vault-Count + NUR-in-Drafts-Count
3. Vault∩_hold (Gedanken fälschlich migriert?)
4. dominantes `last_synthesized`/`created` + mtime-Spanne (B) → ein Lauf oder gemischt?
5. Tag-Stand: drop-Kandidaten im Vault vorhanden? (C)
6. Korpus-Diskrepanz: AppleDouble/DS_Store erklärt? (D)
7. **Schlussindiz: Vault = finaler Build aus 180 Drafts JA/NEIN/UNKLAR**
8. Report-Pfad

**Diagnose endet hier.** Entscheidung Neubau + Pfad-Merge zurück im App-Chat.
