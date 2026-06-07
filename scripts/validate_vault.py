#!/usr/bin/env python3
"""validate_vault.py — Pflichtfelder/Enums/Category/Slug + Vokabular im gebauten Vault."""
import re, sys, unicodedata
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths  # noqa: E402
VAULT = _paths.OUTPUT
FM = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CATS={"meta","grundlagen","webentwicklung","betriebssysteme","protokolle-und-standards",
 "dateitypen-und-konfiguration","methoden-und-prozesse","best-practices","cheatsheets",
 "ki-und-semantische-systeme","datenarchitektur-und-datenbanken","dokumentenverarbeitung-und-extraktion",
 "wissensmodellierung-und-knowledge-graphs","visualisierung-reporting-und-design-systeme",
 "automatisierung-scripting-und-pipelines","gedanken","kunst-kultur","unsortiert"}
TYPE={"process-document","knowledge-article","compact-reference","gedanke"}
STATUS={"draft","review","stable","deprecated"}; REV={"ai_drafted","human_reviewed","verified"}
CONF={"low","medium","high"}
REQ={"title","slug","summary","type","doc_role","category","sources_docs","source_chunks",
 "status","review_status","confidence","doc_version","created","updated"}
vs=set()
ts=VAULT/"00_Meta"/"tag-system.md"
if ts.exists():
    vs={m for m in re.findall(r"^\s*-\s+`([a-z0-9][a-z0-9-]*)`", ts.read_text(encoding="utf-8"), re.M)}
issues=0; files=0
for p in VAULT.rglob("*.md"):
    if p.name=="_index.md" or "00_Meta" in p.parts: continue
    files+=1
    m=FM.match(p.read_text(encoding="utf-8"))
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
