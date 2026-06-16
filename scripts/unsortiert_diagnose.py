#!/usr/bin/env python3
"""unsortiert_diagnose.py — Diagnose der Artikel in output/unsortiert/.

Read-only. Verschiebt NICHTS — die finale Zuordnung ist eine menschliche
Kuratierungs-Entscheidung (⏸ Review). Erzeugt
`work/unsortiert_diagnose.md` mit einer Tabelle:
slug · category · Grund · Empfehlung.

Hintergrund: `category` dieser Artikel ist `unsortiert`, weil ihre Ist-Kategorie
(Qwen Stage 4) im R3-Mapping (`r3_category_mapping_proposal.md`) auf `unsortiert`
abgebildet wurde — Business-/Personal-Domänen ohne eigenen 16-Ordner. Dieses
Skript leitet die Domäne heuristisch aus den Tags ab und empfiehlt:
Domänen mit >= 2 Artikeln → eigenen Ordner / Mapping-Eintrag erwägen;
Singletons → manuell zuordnen oder belassen.

Aufruf:  python3 scripts/unsortiert_diagnose.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import _paths, taxonomy  # noqa: E402
from scripts._pkm_common import parse_yaml_text, split_md  # noqa: E402

# Realer Ordnername aus der Taxonomie-SSoT (config/categories.yaml: "17_unsortiert"),
# nicht hardcodiert — vorher zeigte dies auf das nicht existente "output/unsortiert/"
# und das Diagnose-Tool fand nie etwas (Drift behoben, pipeline-v2 P1).
UNSORTED_DIR = _paths.OUTPUT / taxonomy.CATEGORY_TO_FOLDER["unsortiert"]
OUTPUT = _paths.WORK / "unsortiert_diagnose.md"


def unsorted_dir(vault_dir: Path) -> Path:
    """Pfad des 17_unsortiert-Ordners unter einem Vault (Ordnername aus SSoT)."""
    return vault_dir / taxonomy.CATEGORY_TO_FOLDER["unsortiert"]


def count_unsorted(vault_dir: Path) -> int:
    """Read-only: Anzahl Artikel-``.md`` in 17_unsortiert (ohne ``_index.md``).

    Passives Surfacing für ``pkm build-vault`` (kein P4) — verschiebt/ändert nichts.
    """
    folder = unsorted_dir(vault_dir)
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.glob("*.md") if p.name != "_index.md")

# Tag-Keyword → Domäne (heuristisch; nur für Diagnose/Empfehlung, nicht autoritativ)
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "E-Commerce / Shop": ("ecommerce", "product-listing", "product-data", "shop", "onlineshop"),
    "CRM / ERP / Business": ("crm", "erp", "sage-erp", "order-management", "business-process"),
    "HR / Psychologie": ("hr", "profiling", "assessment", "psychology", "recruiting"),
    "Gesundheit / Ernährung": (
        "nutrition", "vitamins", "minerals", "adhd", "elvanse", "lisdexamfetamine", "health",
    ),
    "Zukunft / Gesellschaft": (
        "thought-leaders", "future-studies", "ai-ethics", "political-economy",
    ),
}


def _infer_domain(tags: list[str]) -> str:
    """Ordnet einen Artikel anhand seiner Tags einer Domäne zu (erste Übereinstimmung)."""
    tagset = {t.lower() for t in tags}
    best = ""
    best_hits = 0
    for domain, kws in _DOMAIN_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in tagset)
        if hits > best_hits:
            best, best_hits = domain, hits
    return best or "unklar"


def _load_articles() -> list[dict[str, object]]:
    arts: list[dict[str, object]] = []
    if not UNSORTED_DIR.exists():
        return arts
    for p in sorted(UNSORTED_DIR.glob("*.md")):
        if p.name == "_index.md":
            continue
        fm_text, _ = split_md(p.read_text(encoding="utf-8"))
        fm, err = parse_yaml_text(fm_text or "")
        if fm is None:
            continue
        tags = list(fm.get("tags") or [])
        arts.append(
            {
                "slug": fm.get("slug", p.stem),
                "title": fm.get("title", ""),
                "category": fm.get("category", ""),
                "tags": tags,
                "sources": list(fm.get("sources_docs") or []),
                "domain": _infer_domain(tags),
            }
        )
    return arts


def main() -> int:
    arts = _load_articles()
    domain_counts: Counter[str] = Counter(str(a["domain"]) for a in arts)
    by_domain: dict[str, list[dict[str, object]]] = defaultdict(list)
    for a in arts:
        by_domain[str(a["domain"])].append(a)

    lines = [
        "---",
        "title: Diagnose unsortiert/",
        "slug: unsortiert-diagnose",
        "type: report",
        "status: stable",
        "---",
        "",
        "# Diagnose — `output/unsortiert/`",
        "",
        f"**{len(arts)} Artikel** ohne eindeutige 16-Ordner-Zuordnung "
        "(`category: unsortiert`). Verschoben wird **nichts** — finale Zuordnung "
        "ist menschliche Kuratierungs-Entscheidung (⏸ Review).",
        "",
        "**Grund (generell):** Die Ist-Kategorie (Qwen Stage 4) wurde im "
        "R3-Mapping auf `unsortiert` abgebildet — Business-/Personal-Domänen ohne "
        "eigenen thematischen Ordner. Domäne unten heuristisch aus Tags abgeleitet.",
        "",
        "## Artikel",
        "",
        "| Slug | Domäne (Tag-Heuristik) | Grund | Empfehlung |",
        "|---|---|---|---|",
    ]
    for a in sorted(arts, key=lambda x: (str(x["domain"]), str(x["slug"]))):
        domain = str(a["domain"])
        multi = domain_counts[domain] >= 2
        grund = f"Business-/Personal-Domäne ohne 16-Ordner (Tags: {', '.join(a['tags'][:3])})"  # type: ignore[index]
        if multi:
            empf = f"**Ordner/Mapping-Eintrag erwägen** ({domain}, {domain_counts[domain]} Artikel)"
        else:
            empf = "manuell zuordnen oder belassen (Singleton)"
        lines.append(f"| `{a['slug']}` | {domain} | {grund} | {empf} |")

    lines += ["", "## Domänen-Verteilung", ""]
    for domain, n in domain_counts.most_common():
        flag = " → Ordner erwägen" if n >= 2 else ""
        lines.append(f"- **{domain}**: {n}{flag}")
    lines += [
        "",
        "## Nächster Schritt (manuell, muente)",
        "",
        "Pro Artikel entscheiden: (a) neuen Ist→Vault-Mapping-Eintrag in "
        "`r3_category_mapping_proposal.md` ergänzen und Vault neu bauen, "
        "(b) Datei manuell in einen bestehenden 16-Ordner verschieben, oder "
        "(c) in `unsortiert/` belassen. Kein automatischer Move durch die Pipeline.",
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Diagnose geschrieben: {OUTPUT}")
    print(f"  {len(arts)} Artikel, Domänen: {dict(domain_counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
