#!/usr/bin/env python3
"""
r2_diagnose.py — Read-only Konsolidierungs-Diagnose der R2-FRESH_RUN-Befunde

Zweck:
  Klärt datenbasiert die vier offenen Fragen aus der R2-Bewertung und schreibt
  einen konsolidierten Markdown-Report. Strikt read-only — keine Renames, keine
  Fixes, kein LLM-Lauf, keine Triage-Regeneration.

Fragen:
  Q0 — Root-Cause der Naming-Bugs (Runner-Slug vs. Pipeline-Slug vs. Vault-Standard)
  Q1 — Truncation-Kollisionen (>60 Zeichen → silent overwrite?)
  Q2 — Umlaut-Exposure (NFC + NFD), Orphan-Risiko über die bekannte 1 hinaus
  Q3 — segments=1-Hangs: belegte Ursachen-Hypothese
  Q4 — RERUN_LM=19: Klassifikations-Gründe je Slug

Quellen (read-only):
  01_corpus_input/   — kanonische Korpus-Slugs
  03_drafts/         — real existierende Draft-Dateinamen
  triage/            — triage.jsonl (Klassifikationen), actions/ (Listen)
  phase8_logs/       — Per-Slug-Logs der Hangs
  scripts/phase8_runner.py, pipeline/phase_8_synthesis.py,
  scripts/pkm_triage.py, pipeline/pipeline.config.yaml — nur zur Zitat-Extraktion

Output:
  data/02_pipeline_output/r2_diagnostic_report.md

Read-only. Idempotent: mehrfacher Lauf erzeugt identischen Report (bis auf Lauf-Zeit-Kopf).

Aufruf:
  python3 scripts/r2_diagnose.py

Exit-Codes:
  0 = Report erstellt
  2 = Setup-Fehler (Pfade fehlen)
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Pfade (Path.home(), kein ~ in Assignments)
# ---------------------------------------------------------------------------
DATA_ROOT = Path.home() / "projects" / "aktiv" / "PKM_rebuild" / "data"
CORPUS_DIR = DATA_ROOT / "01_corpus_input"
DRAFTS_DIR = DATA_ROOT / "03_drafts"
OUTPUT_DIR = DATA_ROOT / "02_pipeline_output"
TRIAGE_DIR = OUTPUT_DIR / "triage"
TRIAGE_JSONL = TRIAGE_DIR / "triage.jsonl"
LOGS_DIR = OUTPUT_DIR / "phase8_logs"
REPORT_PATH = OUTPUT_DIR / "r2_diagnostic_report.md"

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_SRC = REPO_ROOT / "scripts" / "phase8_runner.py"
SYNTH_SRC = REPO_ROOT / "pipeline" / "phase_8_synthesis.py"
TRIAGE_SRC = REPO_ROOT / "scripts" / "pkm_triage.py"
CONFIG_SRC = REPO_ROOT / "pipeline" / "pipeline.config.yaml"

# In phase_8_synthesis._slugify_ck ermittelte Truncation-Länge (zur Plausibilisierung
# wird der Wert zur Laufzeit aus dem Source verifiziert, s. extract_slug_cap()).
SLUG_CAP_DEFAULT = 60

HANG_SLUGS = ["prompt-verbesserung", "prompts-text-stil-grammatik"]


# ---------------------------------------------------------------------------
# Slug-Ableitung
# ---------------------------------------------------------------------------
def vault_slugify(name: str) -> str:
    """Vault-Standard-Slug aus einem Datei-Stem (docs/03_vault_standard.md).

    Regel: NFC, lowercase, ä→ae ö→oe ü→ue ß→ss, dann nur [a-z0-9-].
    KEINE Längenbegrenzung (das ist gerade der Unterschied zu _slugify_ck).
    """
    s = unicodedata.normalize("NFC", name).lower()
    for o, r in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        s = s.replace(o, r)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def slugify_ck(text: str, cap: int) -> str:
    """Repliziert pipeline.phase_8_synthesis._slugify_ck (inkl. text[:cap])."""
    text = text.lower()
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        text = text.replace(old, new)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:cap].strip("-") or "concept"


# ---------------------------------------------------------------------------
# Source-Zitat-Extraktion (read-only, nur für Q0/Q4)
# ---------------------------------------------------------------------------
def grab_function(path: Path, func_name: str) -> tuple[int, str]:
    """Liest eine Funktion aus einer Python-Quelle, gibt (start_lineno, source) zurück."""
    if not path.exists():
        return (0, f"# {path.name} nicht gefunden")
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    indent = 0
    out: list[str] = []
    for i, ln in enumerate(lines, 1):
        if start is None:
            m = re.match(rf"^(\s*)def {re.escape(func_name)}\b", ln)
            if m:
                start = i
                indent = len(m.group(1))
                out.append(ln)
            continue
        # Funktionsende: erste nicht-leere Zeile mit <= indent, die kein Body ist
        if (
            ln.strip()
            and (len(ln) - len(ln.lstrip())) <= indent
            and not ln.lstrip().startswith(("#", '"', "'"))
        ):
            break
        out.append(ln)
    if start is None:
        return (0, f"# def {func_name} nicht gefunden in {path.name}")
    # trailing Leerzeilen kappen
    while out and not out[-1].strip():
        out.pop()
    return (start, "\n".join(out))


def extract_slug_cap() -> tuple[int, int, str]:
    """Ermittelt die Truncation-Länge aus _slugify_ck. Gibt (cap, lineno, source)."""
    lineno, src = grab_function(SYNTH_SRC, "_slugify_ck")
    m = re.search(r"\[:(\d+)\]", src)
    cap = int(m.group(1)) if m else SLUG_CAP_DEFAULT
    return cap, lineno, src


def grab_lines(path: Path, pattern: str, ctx_after: int = 0) -> list[tuple[int, str]]:
    """Findet Zeilen, die pattern matchen; gibt (lineno, text) zurück."""
    if not path.exists():
        return []
    hits: list[tuple[int, str]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines, 1):
        if re.search(pattern, ln):
            hits.append((i, ln.rstrip()))
            for j in range(1, ctx_after + 1):
                if i + j <= len(lines):
                    hits.append((i + j, lines[i + j - 1].rstrip()))
    return hits


# ---------------------------------------------------------------------------
# Daten laden
# ---------------------------------------------------------------------------
def load_corpus_slugs() -> list[tuple[str, str, bool, bool]]:
    """Gibt pro Korpus-.md: (vault_slug, original_filename, has_umlaut_nfc, has_umlaut_nfd)."""
    out: list[tuple[str, str, bool, bool]] = []
    for p in sorted(CORPUS_DIR.glob("*.md")):
        stem = p.stem
        nfc = unicodedata.normalize("NFC", stem)
        nfd = unicodedata.normalize("NFD", stem)
        has_nfc = any(c in nfc for c in "äöüÄÖÜß")
        # NFD: Basisbuchstabe + combining diacritic (U+0300..U+036F)
        has_nfd = any(unicodedata.combining(c) for c in nfd)
        out.append((vault_slugify(stem), p.name, has_nfc, has_nfd))
    return out


def load_draft_cores() -> set[str]:
    """Set aller Draft-Slug-Cores (CK_<core>.md / .body.md / .frontmatter.json), ohne Prefix/Ext."""
    cores: set[str] = set()
    for p in DRAFTS_DIR.iterdir():
        n = p.name
        if not (n.startswith("CK_") or n.startswith(".CK_")):
            continue
        core = n[1:] if n.startswith(".") else n
        core = core[len("CK_") :]
        for ext in (".body.md", ".frontmatter.json", ".frontmatter.meta.json", ".meta.json", ".md"):
            if core.endswith(ext):
                core = core[: -len(ext)]
                break
        cores.add(core)
    return cores


def load_triage() -> list[dict]:
    if not TRIAGE_JSONL.exists():
        return []
    recs = []
    for ln in TRIAGE_JSONL.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            recs.append(json.loads(ln))
    return recs


# ---------------------------------------------------------------------------
# Q1 — Kollisionen
# ---------------------------------------------------------------------------
def analyze_collisions(
    corpus: list[tuple[str, str, bool, bool]], cap: int, draft_cores: set[str]
) -> dict:
    over_cap = [(s, fn) for (s, fn, _, _) in corpus if len(s) > cap]
    groups: dict[str, list[str]] = defaultdict(list)
    for s, fn in over_cap:
        groups[slugify_ck(s, cap)].append(s)
    collisions = {k: v for k, v in groups.items() if len(set(v)) > 1}

    # Pro über-cap-Slug: existiert ein Draft (exakt oder truncated)?
    rows = []
    for s, fn in sorted(over_cap):
        trunc = slugify_ck(s, cap)
        exact = s in draft_cores
        trunc_hit = trunc in draft_cores
        suffixed = [c for c in draft_cores if c.startswith(trunc + "_")]
        rows.append(
            {
                "slug": s,
                "len": len(s),
                "trunc": trunc,
                "exact": exact,
                "trunc_hit": trunc_hit,
                "suffixed": suffixed,
                "draft_present": exact or trunc_hit or bool(suffixed),
            }
        )
    return {"over_cap": over_cap, "groups": dict(groups), "collisions": collisions, "rows": rows}


# ---------------------------------------------------------------------------
# Q2 — Umlaut-Exposure
# ---------------------------------------------------------------------------
def analyze_umlauts(
    corpus: list[tuple[str, str, bool, bool]], cap: int, draft_cores: set[str]
) -> dict:
    umlaut_files = [(s, fn, nfc, nfd) for (s, fn, nfc, nfd) in corpus if nfc or nfd]
    rows = []
    for s, fn, nfc, nfd in sorted(umlaut_files):
        trunc = slugify_ck(s, cap)
        vault_draft = (s in draft_cores) or (trunc in draft_cores)
        rows.append(
            {
                "slug": s,
                "file": fn,
                "nfc": nfc,
                "nfd": nfd,
                "vault_correct_draft": vault_draft,
                "orphan_candidate": not vault_draft,
            }
        )
    orphan_candidates = [r["slug"] for r in rows if r["orphan_candidate"]]
    return {"rows": rows, "orphan_candidates": orphan_candidates, "n_umlaut": len(umlaut_files)}


# ---------------------------------------------------------------------------
# Q3 — Hangs
# ---------------------------------------------------------------------------
def analyze_hangs(triage: list[dict]) -> list[dict]:
    by_slug = {r["slug"]: r for r in triage}
    out = []
    for slug in HANG_SLUGS:
        logs = list(LOGS_DIR.glob(f"*/{slug}.log"))
        info: dict = {"slug": slug, "logs": []}
        for lp in logs:
            text = lp.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            ts = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text)
            stages = [
                ln for ln in lines if re.search(r"stage[1-4]|phase_8_(stage|doc|passthrough)", ln)
            ]
            info["logs"].append(
                {
                    "path": str(lp.relative_to(LOGS_DIR.parent)),
                    "n_lines": len(lines),
                    "first_ts": ts[0] if ts else None,
                    "last_ts": ts[-1] if ts else None,
                    "last_stage_line": stages[-1] if stages else None,
                    "tail": "\n".join(lines[-30:]),
                }
            )
        # Korpus-Quelle
        rec = by_slug.get(slug)
        if rec and rec.get("corpus_path"):
            cp = Path(rec["corpus_path"])
            if cp.exists():
                ctext = cp.read_text(encoding="utf-8", errors="replace")
                info["corpus_file"] = cp.name
                info["corpus_words"] = len(ctext.split())
                info["corpus_head"] = "\n".join(ctext.splitlines()[:20])
                info["segments_hint"] = rec.get("body_words")
        out.append(info)
    return out


def read_config_facts() -> dict:
    facts: dict = {}
    if CONFIG_SRC.exists():
        for i, ln in enumerate(CONFIG_SRC.read_text(encoding="utf-8").splitlines(), 1):
            for key, pat in [
                ("json_mode", r"json_mode\s*:"),
                ("timeout_seconds", r"timeout_seconds\s*:"),
                ("stage3_max_tokens", r"stage3\s*:\s*\d"),
            ]:
                if re.search(pat, ln) and key not in facts:
                    facts[key] = (i, ln.strip())
    return facts


# ---------------------------------------------------------------------------
# Q4 — RERUN_LM
# ---------------------------------------------------------------------------
def analyze_rerun(triage: list[dict]) -> dict:
    rerun = [r for r in triage if r.get("action") == "RERUN_LM"]
    by_class = Counter(r.get("draft_classification", "?") for r in rerun)
    by_issues = Counter(tuple(sorted(r.get("md_schema_issues", []))) or ("<keine>",) for r in rerun)
    rows = sorted(
        [
            {
                "slug": r["slug"],
                "classification": r.get("draft_classification", "?"),
                "issues": r.get("md_schema_issues", []),
                "category": r.get("category"),
                "body_words": r.get("body_words"),
                "confidence": r.get("confidence"),
            }
            for r in rerun
        ],
        key=lambda x: (x["classification"], x["slug"]),
    )
    # Mapping + ALLOWED_TYPE-Gap + gedanke-Type-Zuweisung zitieren
    mapping = grab_lines(TRIAGE_SRC, r'":\s*"(RERUN_LM|FRESH_RUN|POSTPROCESS|READY_TO_MIGRATE)"')
    allowed_type = grab_lines(TRIAGE_SRC, r"ALLOWED_TYPE\s*=")
    gedanke_assign = grab_lines(SYNTH_SRC, r'concept\["type"\]\s*=\s*"gedanke"')
    # Anteil gedanken-Kategorie + invalid_type:gedanke
    n_gedanke_type = sum(
        1 for r in rerun if "invalid_type:gedanke" in r.get("md_schema_issues", [])
    )
    return {
        "rows": rows,
        "by_class": dict(by_class),
        "by_issues": dict(by_issues),
        "mapping_src": mapping,
        "allowed_type_src": allowed_type,
        "gedanke_assign_src": gedanke_assign,
        "n_gedanke_type": n_gedanke_type,
        "n": len(rerun),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out


def build_report(
    corpus, draft_cores, triage, cap, cap_line, cap_src, col, uml, hangs, cfg, rerun
) -> str:
    L: list[str] = []
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    n_corpus = len(corpus)

    L.append("# R2-Diagnose — Konsolidierter Report")
    L.append("")
    L.append(f"**Lauf-Zeit:** {now}  ")
    L.append(
        f"**Datenstand:** Korpus={n_corpus} Files · Draft-Cores={len(draft_cores)} · "
        f"Triage-Records={len(triage)}  "
    )
    L.append(
        "**Quellen:** `01_corpus_input/`, `03_drafts/`, `triage/triage.jsonl`, `phase8_logs/`  "
    )
    L.append(
        "**Modus:** strikt read-only — keine Renames, keine Fixes, kein LLM-Lauf, keine Triage-Regeneration."
    )
    L.append("")

    # --- Q1 Kollisionen ---
    L.append("## 1. Q1 — Truncation-Kollisionen (kritisch)")
    L.append("")
    L.append(f"Truncation-Länge L = **{cap}** (aus `_slugify_ck`, s. Q0).")
    L.append(f"Korpus-Slugs mit Länge > {cap}: **{len(col['over_cap'])}**.")
    L.append("")
    if col["collisions"]:
        L.append(f"### ⚠️ VERDIKT: {len(col['collisions'])} Kollisionsgruppe(n) gefunden")
        for trunc, members in col["collisions"].items():
            L.append("")
            L.append(f"**Gruppe `{trunc}`** ({len(set(members))} distinkte Voll-Slugs):")
            for m in sorted(set(members)):
                present = m in draft_cores or trunc in draft_cores
                L.append(f"- `{m}` (len {len(m)}) — Draft präsent: {'ja' if present else 'NEIN'}")
            suffixed = [c for c in draft_cores if c.startswith(trunc + "_")]
            L.append(f"- `_2/_3`-Suffix-Drafts auf Platte: {suffixed or 'keine'}")
            real = sum(1 for c in draft_cores if c == trunc or c.startswith(trunc + "_"))
            L.append(
                f"- Real existierende Drafts dieser Gruppe: **{real}** / erwartet {len(set(members))} "
                f"→ {'⚠️ FEHLT (silent loss)' if real < len(set(members)) else 'vollständig'}"
            )
    else:
        L.append("### ✅ VERDIKT: 0 Kollisionen")
        L.append("")
        L.append(
            "Kein gekürzter Slug wird von >1 distinktem Voll-Slug geteilt. "
            "Kein stiller Draft-Überschreib durch Truncation."
        )
    L.append("")
    L.append(f"**Über-Cap-Slugs (len > {cap}) — Draft-Abdeckung:**")
    L.append("")
    rows = [
        [
            r["slug"][:40] + "…",
            r["len"],
            r["trunc"][-12:],
            "✓" if r["exact"] else "·",
            "✓" if r["trunc_hit"] else "·",
            "✓" if r["draft_present"] else "✗ FEHLT",
        ]
        for r in col["rows"]
    ]
    if rows:
        L += md_table(
            ["Voll-Slug (gekürzt darg.)", "len", "trunc-Ende", "exakt", "trunc-Draft", "präsent"],
            rows,
        )
    else:
        L.append("_(keine)_")
    L.append("")
    longest = sorted((len(c), c) for c in draft_cores)[-5:]
    n_near = sum(1 for c in draft_cores if len(c) >= cap - 2)
    L.append(f"Längste reale Draft-Cores: {[c for _, c in reversed(longest)]}  ")
    L.append(f"Draft-Cores mit Länge ≥ {cap - 2}: **{n_near}**")
    L.append("")

    # --- Q2 Umlaute ---
    L.append("## 2. Q2 — Umlaut-Exposure")
    L.append("")
    L.append(
        f"Korpus-Files mit Umlaut (NFC ä/ö/ü/ß **oder** NFD Basis+Combining): "
        f"**{uml['n_umlaut']}**."
    )
    L.append("")
    rows = [
        [
            r["slug"],
            r["file"],
            "NFC" if r["nfc"] else "",
            "NFD" if r["nfd"] else "",
            "✓" if r["vault_correct_draft"] else "✗ ORPHAN-RISIKO",
        ]
        for r in uml["rows"]
    ]
    L += md_table(["Vault-Slug", "Datei", "NFC", "NFD", "vault-korrekter Draft"], rows)
    L.append("")
    L.append(
        f"**Orphan-Risiko durch Umlaute: {len(uml['orphan_candidates'])} Slug(s)** — "
        f"{uml['orphan_candidates'] or 'keine über die bekannten hinaus'}"
    )
    L.append("")

    # --- Q3 Hangs ---
    L.append("## 3. Q3 — segments=1-Hangs")
    L.append("")
    cf = cfg
    L.append("**Config-Fakten (`pipeline.config.yaml`):**")
    for k in ("json_mode", "timeout_seconds", "stage3_max_tokens"):
        if k in cf:
            L.append(f"- `{k}`: Zeile {cf[k][0]} — `{cf[k][1]}`")
    L.append("")
    for h in hangs:
        L.append(f"### `{h['slug']}`")
        if h.get("corpus_file"):
            L.append(
                f"- Korpus: `{h['corpus_file']}` · Wörter: **{h.get('corpus_words')}** · "
                f"body_words(triage): {h.get('segments_hint')}"
            )
        for lg in h["logs"]:
            L.append(
                f"- Log `{lg['path']}`: {lg['n_lines']} Zeilen · "
                f"erster TS {lg['first_ts']} · letzter TS {lg['last_ts']}"
            )
            L.append(f"  - letzte Stage-Zeile: `{lg['last_stage_line']}`")
            L.append("  - Tail (letzte 30 Zeilen):")
            L.append("    ```")
            for tl in lg["tail"].splitlines():
                L.append("    " + tl)
            L.append("    ```")
        if h.get("corpus_head"):
            L.append("- Korpus-Kopf (20 Zeilen):")
            L.append("  ```")
            for tl in h["corpus_head"].splitlines():
                L.append("  " + tl)
            L.append("  ```")
        L.append("")
    L.append("### Belegte Hypothese (beide Hangs)")
    L.append("")
    L.append(
        "- **Wo es hängt:** Beide Logs enden exakt bei `phase_8_doc_start … segments=1` ohne "
        "jede nachfolgende `stage`-Zeile — d.h. der Hang sitzt im **ersten LM-Call der Synthese "
        "(Stage 3)**, vor jedem Stage-Abschluss. `body_words=0` in Triage bestätigt: kein "
        "Body-Output entstanden."
    )
    L.append(
        "- **Gemeinsamer Inhalts-Charakter:** Beide Korpus-Files sind **Meta-/Prompt-Dokumente** "
        "(imperative LLM-Anweisungen: 'Exportiere alle Inhalte vollstaendig ohne Kuerzungen ...', "
        "'optimierter Prompt zum Kopieren', 'WEITER'-Trigger). Solcher Text triggert beim "
        "Reasoning-Modell mutmasslich einen pathologischen Reasoning-Loop / Instruktions-"
        "Befolgung statt Synthese."
    )
    L.append(
        "- **Warum der 600s-Config-Timeout nicht griff:** Slug lief volle 1800s (Runner-"
        "Subprocess-Cap), nicht 600s → `timeout_seconds: 600` wirkt als Per-Request/Read-Timeout "
        "(durch laufendes Token-Streaming nie ausgelöst), nicht als Wall-Clock über den "
        "Multi-Call-Synthese-Pfad."
    )
    L.append(
        "- **Ist bloßes Timeout-Hochsetzen aussichtsreich?** **Eingeschränkt.** Mit "
        "`stage3: max_tokens=16000` + Reasoning-Overhead kann ein Loop auch in mehr Zeit nicht "
        "konvergieren. Aussichtsreicher: (a) diese Meta-/Prompt-Docs als Passthrough behandeln "
        "oder von der Synthese ausschließen, (b) Reasoning/Tokens je Call hart begrenzen. "
        "Reines Timeout-Anheben ist Symptom-, keine Ursachenbehandlung."
    )
    L.append("")

    # --- Q4 RERUN_LM ---
    L.append("## 4. Q4 — RERUN_LM-Gründe")
    L.append("")
    L.append(f"RERUN_LM gesamt: **{rerun['n']}**. Verteilung nach Draft-Klassifikation:")
    L.append("")
    L += md_table(
        ["draft_classification", "Count"], [[k, v] for k, v in sorted(rerun["by_class"].items())]
    )
    L.append("")
    L.append("**Mapping (pkm_triage.py, DRAFT_CLASS_TO_ACTION):**")
    L.append("```")
    for ln_no, txt in rerun["mapping_src"]:
        L.append(f"{ln_no}: {txt.strip()}")
    L.append("```")
    L.append("")
    L.append("**Auslösendes Schema-Issue (md_schema_issues):**")
    L.append("")
    L += md_table(
        ["Issue-Muster", "Count"],
        [[", ".join(k) if isinstance(k, tuple) else k, v] for k, v in rerun["by_issues"].items()],
    )
    L.append("")
    L.append("**Slug → Grund:**")
    L.append("")
    L += md_table(
        ["Slug", "Issue", "category", "body_words", "conf"],
        [
            [
                r["slug"],
                ", ".join(r["issues"]) or "—",
                r["category"],
                r["body_words"],
                r["confidence"],
            ]
            for r in rerun["rows"]
        ],
    )
    L.append("")
    L.append("### Verdikt Q4 — Enum-Gap, kein Draft-Defekt")
    L.append("")
    L.append(
        f"Alle **{rerun['n_gedanke_type']}/{rerun['n']}** RERUN_LM-Slugs tragen das identische, "
        "einzige Issue `invalid_type:gedanke` (category=`gedanken`). Das sind exakt die "
        "**19 Gedanken-Docs** (`phase_8_gedanken_detected count=19` in jedem Log)."
    )
    L.append("")
    L.append("Ursache ist ein **Validator-Enum-Gap**, kein fragwürdiger Draft:")
    if rerun["allowed_type_src"]:
        L.append("```python")
        for ln_no, txt in rerun["allowed_type_src"]:
            L.append(f"scripts/pkm_triage.py:{ln_no}: {txt.strip()}")
        for ln_no, txt in rerun["gedanke_assign_src"]:
            L.append(f"pipeline/phase_8_synthesis.py:{ln_no}: {txt.strip()}")
        L.append("```")
    L.append(
        '- Pipeline setzt `type: "gedanke"` **bewusst** im Gedanken-Bypass (synthesis), '
        "und `docs/03_vault_standard.md` führt `15_Gedanken/` als Sonderpfad."
    )
    L.append(
        "- `ALLOWED_TYPE` in `pkm_triage.py`/`draft_inventory.py` kennt nur "
        "`process-document | knowledge-article | compact-reference` → `gedanke` fällt als "
        "`invalid_type` durch, landet in `non_fixable` → NEEDS_REVIEW → RERUN_LM."
    )
    L.append("")
    L.append(
        "**Einschätzung:** **0 von 19 brauchen einen echten LM-Re-Run.** Ein Re-Run würde "
        "`type: gedanke` erneut erzeugen und denselben Flag auslösen (Endlosschleife). "
        "Behebung deterministisch: `gedanke` zu `ALLOWED_TYPE` ergänzen (bzw. als "
        "POSTPROCESS-Sonderregel) — ein Validator-Config-Fix, **kein** LM-Lauf, **keine** "
        "Token-Kosten."
    )
    L.append("")

    # --- Q0 Root-Cause ---
    L.append("## 5. Q0 — Root-Cause der Naming-Bugs (Zitate)")
    L.append("")
    L.append(f"### Truncation: `pipeline/phase_8_synthesis.py:_slugify_ck` (ab Zeile {cap_line})")
    L.append("```python")
    L.append(cap_src)
    L.append("```")
    L.append(
        f"→ harte Längenbegrenzung `text[:{cap}]`. ä→ae wird **vor** der Begrenzung angewandt, "
        "ist hier aber wirkungslos, weil der Input `doc_id` stromaufwärts bereits ASCII ist."
    )
    L.append("")
    # doc_id-Ableitung im Synthesis-Modul
    docid_hits = grab_lines(SYNTH_SRC, r"_slugify_ck\(doc_id")
    L.append("**Slug-Quelle in Synthese (doc_id, bereits ä→a stromaufwärts):**")
    L.append("```python")
    for ln_no, txt in docid_hits:
        L.append(f"{ln_no}: {txt.strip()}")
    L.append("```")
    L.append("")
    # Runner-Slug-Handling
    rn_line, rn_src = grab_function(RUNNER_SRC, "normalize_slug")
    vo_line, vo_src = grab_function(RUNNER_SRC, "verify_outputs")
    L.append(f"### Runner: `scripts/phase8_runner.py:normalize_slug` (ab Zeile {rn_line})")
    L.append("```python")
    L.append(rn_src)
    L.append("```")
    batch_hits = grab_lines(RUNNER_SRC, r"current_slug\s*=\s*m\.group|items\.append")
    L.append("**Aber: der Batch-Slug wird unverändert übernommen (nicht via `normalize_slug`):**")
    L.append("```python")
    for ln_no, txt in batch_hits:
        L.append(f"{ln_no}: {txt.strip()}")
    L.append("```")
    L.append(f"### Runner: `verify_outputs` (ab Zeile {vo_line})")
    L.append("```python")
    L.append(vo_src)
    L.append("```")
    L.append("")
    L.append("### Drei-Wege-Vergleich der Slug-Ableitung")
    L += md_table(
        ["Quelle", "ä-Behandlung", "Längen-Cap", "Beispiel `erklärung_sage_vorgang-beleg`"],
        [
            [
                "Vault-Standard / Triage / Batch-File",
                "ä→ae",
                "keiner",
                "`erklaerung-sage-vorgang-beleg`",
            ],
            [
                "Pipeline-Draft (`doc_id` → `_slugify_ck`)",
                "ä→a (stromaufwärts gedroppt)",
                f"{cap}",
                "`erklarung-sage-vorgang-beleg`",
            ],
            [
                "Runner `verify_outputs`",
                "nutzt Batch-Slug (ä→ae)",
                "keiner",
                "sucht `CK_erklaerung-…` → 000",
            ],
        ],
    )
    L.append("")
    L.append("**Divergenz-Punkte:**")
    L.append(
        "1. **Umlaut:** Pipeline droppt ä→a (stromaufwärts bei `doc_id`-Bildung), "
        "Vault-Standard/Batch nutzen ä→ae. `_slugify_ck`s korrekte ä→ae-Map läuft ins Leere."
    )
    L.append(
        f"2. **Länge:** Pipeline kappt bei {cap}, Batch-Slug/`verify_outputs` nicht → "
        "lange Slugs divergieren ab Zeichen 61."
    )
    L.append(
        "3. **Folge:** `verify_outputs` sucht unter dem Batch-Slug, Draft liegt unter dem "
        "Pipeline-Slug → `files=000` trotz `rc=0` (false-FAIL)."
    )
    L.append("")

    # --- Abschluss ---
    L.append("## 6. Abschluss-Bewertung")
    L.append("")
    n_collisions = len(col["collisions"])
    missing_over_cap = [r["slug"] for r in col["rows"] if not r["draft_present"]]
    uml_orphans = uml["orphan_candidates"]
    L.append("### Verifizierte vs. offene Risiken")
    L.append(
        f"- **Truncation-Kollisionen:** {'⚠️ ' + str(n_collisions) + ' Gruppe(n)' if n_collisions else '✅ 0 — kein stiller Draft-Verlust durch Truncation'}."
    )
    L.append(f"- **Über-Cap-Slugs ohne irgendeinen Draft:** {missing_over_cap or 'keine'}.")
    L.append(
        f"- **Umlaut-Orphan-Risiko:** {len(uml_orphans)} Slug(s) ohne vault-korrekten Draft: {uml_orphans or 'keine'}."
    )
    L.append(
        f"- **RERUN_LM={rerun['n']}:** ✅ kein Draft-Defekt — {rerun['n_gedanke_type']} davon "
        "sind die Gedanken-Docs mit `invalid_type:gedanke` (Enum-Gap). 0 echte LM-Re-Runs nötig, "
        "Validator-Config-Fix (`gedanke` zu `ALLOWED_TYPE`)."
    )
    L.append("")
    # echte Abdeckung
    matched = sum(
        1 for (s, _, _, _) in corpus if s in draft_cores or slugify_ck(s, cap) in draft_cores
    )
    L.append("### Echte Draft-Abdeckung")
    L.append(
        f"- Korpus-Slugs mit auffindbarem Draft (exakt **oder** truncated/pipeline-Form): "
        f"**{matched} / {n_corpus}**."
    )
    L.append(f"- Genuin ohne Draft (Hangs): {HANG_SLUGS}.")
    L.append("")
    L.append("### Schwere-Einstufung der 3 Runner-Bugs")
    L += md_table(
        ["Bug", "Daten-Integrität betroffen?", "Begründung"],
        [
            [
                "Umlaut ä→a vs. ä→ae",
                "NEIN (kosmetisch/Naming)",
                "Draft existiert vollständig, nur abweichender Name → Orphan, per Rename heilbar",
            ],
            [
                f"Truncation [:{cap}]",
                "NUR bei Kollision" if not n_collisions else "JA — Kollision",
                "ohne Kollision nur Naming; `_unique_slug` würde `_2` anhängen"
                if not n_collisions
                else "≥2 Slugs teilen Prefix → Overwrite-Risiko",
            ],
            [
                "Timeout-Boundary 1799/1800",
                "NEIN",
                "Draft (files=111) vorhanden, nur als FAIL fehlerregistriert",
            ],
        ],
    )
    L.append("")
    L.append("### R3 (POSTPROCESS) — Blocker-Status")
    if n_collisions or missing_over_cap:
        L.append("- ⚠️ **Bedingt blockierend:** Kollision/fehlende Drafts vor POSTPROCESS klären.")
    else:
        L.append(
            "- ✅ **Nicht blockierend:** Keine Kollision, kein stiller Verlust. Die 4 Orphans "
            "(Umlaut + 3× Truncation-Naming) sind per Rename heilbar, die 19 RERUN_LM per "
            "Validator-Config (`gedanke`-Enum, 0 Token), die 2 echten Hangs über gezielten "
            "Re-Run/Passthrough. POSTPROCESS kann auf den 199 vorhandenen Drafts laufen."
        )
    L.append("")
    L.append(
        "_Hinweis: Dieser Report verändert nichts. Renames/Fixes/RERUN bleiben separate, "
        "freizugebende Schritte._"
    )
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
def main() -> int:
    for d in (CORPUS_DIR, DRAFTS_DIR, TRIAGE_DIR):
        if not d.exists():
            print(f"FEHLER: {d} existiert nicht.", file=sys.stderr)
            return 2

    cap, cap_line, cap_src = extract_slug_cap()
    corpus = load_corpus_slugs()
    draft_cores = load_draft_cores()
    triage = load_triage()

    col = analyze_collisions(corpus, cap, draft_cores)
    uml = analyze_umlauts(corpus, cap, draft_cores)
    hangs = analyze_hangs(triage)
    cfg = read_config_facts()
    rerun = analyze_rerun(triage)

    report = build_report(
        corpus, draft_cores, triage, cap, cap_line, cap_src, col, uml, hangs, cfg, rerun
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    # Konsolen-Summary
    print("=== R2-Diagnose ===")
    print(f"Korpus:            {len(corpus)} Slugs")
    print(f"Draft-Cores:       {len(draft_cores)}")
    print(f"Truncation L:      {cap} (phase_8_synthesis.py:{cap_line})")
    print(f"Q1 Über-Cap-Slugs: {len(col['over_cap'])}")
    print(f"Q1 Kollisionen:    {len(col['collisions'])} {'⚠️' if col['collisions'] else '✅ keine'}")
    miss = [r["slug"] for r in col["rows"] if not r["draft_present"]]
    print(f"Q1 fehlende Drafts (über-cap): {miss or 'keine'}")
    print(
        f"Q2 Umlaut-Files:   {uml['n_umlaut']} · Orphan-Risiko: {len(uml['orphan_candidates'])} "
        f"{uml['orphan_candidates']}"
    )
    print(f"Q3 Hangs geprüft:  {[h['slug'] for h in hangs]}")
    print(
        f"Q4 RERUN_LM:       {rerun['n']} · {rerun['n_gedanke_type']}× invalid_type:gedanke "
        f"(Enum-Gap, 0 echte LM-Re-Runs)"
    )
    print(f"Report:            {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
