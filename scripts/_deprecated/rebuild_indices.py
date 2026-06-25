#!/usr/bin/env python3
"""rebuild_indices.py — DEPRECATED (WP4-T5a / D-WP4-2).

NICHT mehr verwenden. Gründe:
- Ziel war ``_paths.OUTPUT`` (Legacy-Staging, leer), nicht der Live-``BRAIN_VAULT``.
- Direkter Write ohne dry-run / archive-before, abweichendes Index-Format.

Ersatz: phase_9-Generator ``pipeline.phase_9_vault_build._render_index`` /
``_write_indexes`` gegen ``BRAIN_VAULT`` (Adapter, byte-identisch + idempotent,
exkludiert ``00_Meta``/Schutzbereiche). Nur archiviert für Nachvollziehbarkeit.
"""
import re, sys, unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths  # noqa: E402
VAULT = _paths.OUTPUT
FM = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
def fm(p: Path) -> dict[str, Any]:
    m = FM.match(p.read_text(encoding="utf-8"))
    if not m: return {}
    try: return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError: return {}
n=0
for d in sorted(VAULT.iterdir()):
    if not d.is_dir() or d.name=="00_Meta": continue
    arts=[p for p in sorted(d.glob("*.md")) if p.name!="_index.md"]
    if not arts: continue
    tagc: Counter[str] = Counter(); rows=[]
    for p in arts:
        f=fm(p)
        rows.append((f.get("title",p.stem), f.get("slug",p.stem), f.get("status","draft")))
        for t in (f.get("tags") or []): tagc[t]+=1
    L=[f"# {d.name}","",f"Cluster-Index. Automatisch generiert {date.today().isoformat()}.","",
       f"**Artikel:** {len(arts)}","","## Artikel","","| Titel | Slug | Status |","|---|---|---|"]
    for ti,sl,st in sorted(rows): L.append(f"| {ti} | `{sl}` | {st} |")
    L+=["","## Tag-Häufigkeiten",""]
    if tagc:
        L+=["| Tag | Anzahl |","|---|--:|"]
        for t,c in tagc.most_common(): L.append(f"| `{t}` | {c} |")
    else: L.append("_keine_")
    L.append("")
    (d/"_index.md").write_text("\n".join(L),encoding="utf-8"); n+=1
print(f"_index.md regeneriert: {n}")
