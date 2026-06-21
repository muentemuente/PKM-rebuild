#!/usr/bin/env python3
"""validate_vault.py — Pflichtfelder/Enums/Category/Slug + Vokabular im gebauten Vault."""
import re, sys, unicodedata
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths  # noqa: E402
from scripts._pkm_common import (  # noqa: E402  # Enum/Slug-SSoT (kein Re-Define)
    ALLOWED_CATEGORIES as CATS,
    ALLOWED_TYPE as TYPE,
    SLUG_RE as SLUG,
)
VAULT = _paths.OUTPUT
ASSETS = VAULT / "_assets"
FM = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
EMBED = re.compile(r"!\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]+)?\]\]")
# REQ: bewusst lokale Teilmenge (ohne last_synthesized/prompt_version) — der
# gebaute Vault verlangt diese zwei nicht; Angleich an REQUIRED_FIELDS wäre eine
# Verhaltensänderung, daher nicht konsolidiert.
REQ={"title","slug","summary","type","doc_role","category","sources_docs","source_chunks",
 "status","review_status","confidence","doc_version","created","updated"}
vs=set()
ts=VAULT/"00_Meta"/"tag-system.md"
if ts.exists():
    vs={m for m in re.findall(r"^\s*-\s+`([a-z0-9][a-z0-9-]*)`", ts.read_text(encoding="utf-8"), re.M)}
issues=0; files=0
for p in VAULT.rglob("*.md"):
    if p.name=="_index.md" or "00_Meta" in p.parts or "_assets" in p.parts: continue
    files+=1
    txt=p.read_text(encoding="utf-8")
    # Asset-Vollständigkeit (WP3): jedes ![[…]]-Embed muss in output/_assets/ liegen
    for name in EMBED.findall(txt):
        name=name.strip()
        if name and not (ASSETS/name).exists():
            print(f"  {p.name}: fehlendes Asset {name}"); issues+=1
    m=FM.match(txt)
    if not m: print(f"  no_frontmatter: {p.relative_to(VAULT)}"); issues+=1; continue
    try: d=yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e: print(f"  yaml_error {p.name}: {e}"); issues+=1; continue
    miss=REQ-set(d)
    if miss: print(f"  {p.name}: fehlende Felder {sorted(miss)}"); issues+=1
    if d.get("type") not in TYPE: print(f"  {p.name}: type={d.get('type')}"); issues+=1
    if d.get("category") not in CATS: print(f"  {p.name}: category={d.get('category')}"); issues+=1
    sl=d.get("slug","")
    if not isinstance(sl,str) or not SLUG.match(sl): print(f"  {p.name}: slug={sl}"); issues+=1
    if vs:
        bad=[t for t in (d.get("tags") or []) if t not in vs]
        if bad: print(f"  {p.name}: tags außerhalb Vokabular {bad}"); issues+=1
print(f"validate_vault: {files} Files, {issues} Issues")
sys.exit(1 if issues else 0)
