"""WP3c-8 — Frontmatter-Lücken-Audit (read-only, deterministisch, kein LLM).

Misst über den Live-Vault, welche Frontmatter-Lücken existieren und ob ein
restructure-Lauf sie **real** schließen würde. Liefert die kuratierte Teilmenge für
einen gezielten Lauf statt eines pauschalen 166-File-Großlaufs.

**Reuse statt Parallel-Validierung:** die Schema-Konstanten stammen aus der
Single Source of Truth — Pflichtfelder/Slug/Umlaut aus `scripts._pkm_common`
(re-exportiert aus `pipeline.taxonomy`), Enums direkt aus `pipeline.taxonomy`.
Neu ist allein die **Schließbarkeits-Klassifikation** jeder Lücke.

Lücken-Klassen:

* ``mechanical`` — deterministisch füllbar ohne LLM (Timestamps, `doc_version`,
  `prompt_version`, `status`/`review_status`-Normalisierung, Slug/Umlaut-Fix).
* ``llm`` — ein restructure-Lauf könnte füllen (`summary`, `type`, `doc_role`,
  `confidence`, `title`).
* ``owner`` — nicht automatisch ableitbar (`category` bei Ambiguität,
  `sources_docs`/`source_chunks`, unparsebares Frontmatter).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scripts._pkm_common import REQUIRED_FIELDS, SLUG_RE, UMLAUT_MAP

from pipeline.taxonomy import (
    ALLOWED_CATEGORIES,
    ALLOWED_CONFIDENCE,
    ALLOWED_DOC_ROLE,
    ALLOWED_REVIEW,
    ALLOWED_STATUS,
    ALLOWED_TYPE,
)
from pipeline.vault_audit import is_content_md, parse_frontmatter, split_frontmatter

GAP_MECHANICAL = "mechanical"
GAP_LLM = "llm"
GAP_OWNER = "owner"

#: Empfehlungs-Buckets (eine Empfehlung pro File).
REC_COMPLETE = "complete"
REC_MECHANICAL = "mechanical-fix"
REC_RESTRUCTURE = "restructure"
REC_OWNER = "owner"

#: Klassifikation **fehlender** Pflichtfelder.
_MISSING_CLASS: dict[str, str] = {
    "title": GAP_LLM,
    "slug": GAP_MECHANICAL,
    "summary": GAP_LLM,
    "type": GAP_LLM,
    "doc_role": GAP_LLM,
    "category": GAP_OWNER,
    "sources_docs": GAP_OWNER,
    "source_chunks": GAP_OWNER,
    "status": GAP_MECHANICAL,
    "review_status": GAP_MECHANICAL,
    "confidence": GAP_LLM,
    "doc_version": GAP_MECHANICAL,
    "created": GAP_MECHANICAL,
    "updated": GAP_MECHANICAL,
    "last_synthesized": GAP_MECHANICAL,
    "prompt_version": GAP_MECHANICAL,
}

#: Klassifikation **ungültiger** Enum-Werte (Wert vorhanden, aber außerhalb SSoT).
_INVALID_CLASS: dict[str, str] = {
    "type": GAP_LLM,
    "status": GAP_MECHANICAL,
    "review_status": GAP_MECHANICAL,
    "confidence": GAP_LLM,
    "doc_role": GAP_LLM,
    "category": GAP_OWNER,
}

_ENUM_FIELDS: dict[str, set[str]] = {
    "type": ALLOWED_TYPE,
    "status": ALLOWED_STATUS,
    "review_status": ALLOWED_REVIEW,
    "confidence": ALLOWED_CONFIDENCE,
}


@dataclass(frozen=True)
class Gap:
    """Eine Frontmatter-Lücke mit Schließbarkeits-Klasse."""

    label: str  # z.B. "missing:summary", "invalid:type", "slug:umlaut"
    gap_class: str  # GAP_MECHANICAL | GAP_LLM | GAP_OWNER


@dataclass(frozen=True)
class FileAudit:
    """Audit-Ergebnis eines einzelnen Vault-Files."""

    slug: str
    cluster: str
    relpath: str
    gaps: tuple[Gap, ...]

    @property
    def complete(self) -> bool:
        return not self.gaps

    @property
    def recommendation(self) -> str:
        if not self.gaps:
            return REC_COMPLETE
        classes = {g.gap_class for g in self.gaps}
        if GAP_OWNER in classes:
            return REC_OWNER
        if GAP_LLM in classes:
            return REC_RESTRUCTURE
        return REC_MECHANICAL


@dataclass
class AuditResult:
    """Aggregiertes Audit über den Vault."""

    files: list[FileAudit] = field(default_factory=list)

    def by_recommendation(self, rec: str) -> list[FileAudit]:
        return [f for f in self.files if f.recommendation == rec]

    def gap_class_totals(self) -> dict[str, int]:
        totals = {GAP_MECHANICAL: 0, GAP_LLM: 0, GAP_OWNER: 0}
        for fa in self.files:
            for g in fa.gaps:
                totals[g.gap_class] += 1
        return totals


# === Audit-Logik ==============================================================


def _enum_gaps(fm: dict[str, object]) -> list[Gap]:
    """Ungültige Enum-/Slug-Werte (Wert vorhanden, aber außerhalb SSoT)."""
    gaps: list[Gap] = []
    for fieldname, allowed in _ENUM_FIELDS.items():
        val = fm.get(fieldname)
        if val is not None and val not in allowed:
            gaps.append(Gap(f"invalid:{fieldname}", _INVALID_CLASS[fieldname]))

    roles = fm.get("doc_role")
    if isinstance(roles, list):
        if set(roles) - ALLOWED_DOC_ROLE:
            gaps.append(Gap("invalid:doc_role", _INVALID_CLASS["doc_role"]))
    elif roles is not None:
        gaps.append(Gap("invalid:doc_role", _INVALID_CLASS["doc_role"]))

    cat = fm.get("category")
    if cat is not None and cat not in ALLOWED_CATEGORIES:
        gaps.append(Gap("invalid:category", _INVALID_CLASS["category"]))

    slug = fm.get("slug")
    if isinstance(slug, str):
        if any(u in slug for u in UMLAUT_MAP):
            gaps.append(Gap("slug:umlaut", GAP_MECHANICAL))
        if not SLUG_RE.match(slug):
            gaps.append(Gap("slug:format", GAP_MECHANICAL))
    return gaps


def audit_file(path: Path, vault_dir: Path) -> FileAudit:
    """Auditiert ein einzelnes File (read-only) und klassifiziert seine Lücken."""
    rel = path.relative_to(vault_dir)
    cluster = rel.parts[0] if len(rel.parts) > 1 else ""
    fm_text, _, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    if not fm_text:
        return FileAudit(path.stem, cluster, str(rel), (Gap("frontmatter:fehlt", GAP_OWNER),))
    data, err = parse_frontmatter(fm_text)
    if data is None:
        return FileAudit(
            path.stem, cluster, str(rel), (Gap(f"frontmatter:unparsebar({err})", GAP_OWNER),)
        )

    slug = str(data.get("slug") or path.stem)
    gaps: list[Gap] = []
    for missing in sorted(REQUIRED_FIELDS - set(data)):
        gaps.append(Gap(f"missing:{missing}", _MISSING_CLASS.get(missing, GAP_LLM)))
    gaps.extend(_enum_gaps(data))
    return FileAudit(slug, cluster, str(rel), tuple(gaps))


def audit_vault(vault_dir: Path) -> AuditResult:
    """Auditiert alle Content-Files des Vaults (read-only, deterministisch)."""
    result = AuditResult()
    for path in sorted(vault_dir.rglob("*.md")):
        if not is_content_md(path, vault_dir):
            continue
        result.files.append(audit_file(path, vault_dir))
    return result


# === Report ===================================================================


def render_report(result: AuditResult, vault_dir: Path) -> str:
    """Markdown-Report: Aggregat + Pro-File-Tabelle + kuratierte Teilmenge."""
    total = len(result.files)
    complete = result.by_recommendation(REC_COMPLETE)
    restructure = result.by_recommendation(REC_RESTRUCTURE)
    mechanical = result.by_recommendation(REC_MECHANICAL)
    owner = result.by_recommendation(REC_OWNER)
    totals = result.gap_class_totals()

    lines = [
        "# Frontmatter-Lücken-Audit (read-only)",
        "",
        f"Vault: `{vault_dir}` · Files: **{total}**",
        "",
        "## Aggregat",
        "",
        "| Bucket | Files | Bedeutung |",
        "|---|---|---|",
        f"| complete | {len(complete)} | vollständig & valide |",
        f"| restructure | {len(restructure)} | überwiegend llm-schließbare Lücken → echter Nutzen |",
        f"| mechanical-fix | {len(mechanical)} | nur deterministisch füllbar → kein LLM nötig |",
        f"| owner | {len(owner)} | mind. eine nur-owner-Lücke → Owner-Liste |",
        "",
        "**Lücken nach Klasse (gesamt):** "
        f"mechanical={totals[GAP_MECHANICAL]} · llm={totals[GAP_LLM]} · owner={totals[GAP_OWNER]}",
        "",
        "## Kuratierte Teilmenge — restructure-Nutzen",
        "",
    ]
    if restructure:
        lines += ["| slug | cluster | Lücken |", "|---|---|---|"]
        for fa in restructure:
            lines.append(f"| `{fa.slug}` | {fa.cluster} | {', '.join(g.label for g in fa.gaps)} |")
    else:
        lines.append("_keine_ — kein File hat überwiegend llm-schließbare Lücken.")
    lines += ["", "## Owner-Liste (nur-owner-Lücken)", ""]
    if owner:
        lines += ["| slug | cluster | Lücken |", "|---|---|---|"]
        for fa in owner:
            lines.append(f"| `{fa.slug}` | {fa.cluster} | {', '.join(g.label for g in fa.gaps)} |")
    else:
        lines.append("_keine_")

    lines += [
        "",
        "## Alle Files mit Lücken",
        "",
        "| slug | cluster | Empfehlung | Lücken |",
        "|---|---|---|---|",
    ]
    for fa in result.files:
        if fa.complete:
            continue
        lines.append(
            f"| `{fa.slug}` | {fa.cluster} | {fa.recommendation} | "
            f"{', '.join(g.label for g in fa.gaps)} |"
        )

    lines += [
        "",
        "## Fazit",
        "",
        _verdict(len(restructure), len(mechanical), len(owner), len(complete)),
    ]
    return "\n".join(lines) + "\n"


def _verdict(n_restructure: int, n_mechanical: int, n_owner: int, n_complete: int) -> str:
    if n_restructure == 0 and n_mechanical == 0 and n_owner == 0:
        return (
            f"Alle {n_complete} Files sind vollständig & valide — **kein restructure-Großlauf** "
            "und kein Frontmatter-Fix nötig."
        )
    parts = []
    if n_restructure:
        parts.append(
            f"Gezielter restructure-Lauf lohnt auf **{n_restructure}** File(s) "
            "(llm-schließbare Lücken)."
        )
    if n_mechanical:
        parts.append(
            f"**{n_mechanical}** File(s) brauchen nur einen **deterministischen** "
            "Frontmatter-Fix (kein LLM, keine Promotion) — eigener Task."
        )
    if n_owner:
        parts.append(f"**{n_owner}** File(s) haben nur-owner-Lücken → separate Owner-Klärung.")
    parts.append("Ein pauschaler 166-File-Großlauf ist nicht indiziert.")
    return " ".join(parts)


def write_audit_xlsx(result: AuditResult, path: Path) -> Path:
    """Optionales `.xlsx` (eine Zeile/File: slug, cluster, Empfehlung, Lücken)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "frontmatter-audit"
    ws.append(["slug", "cluster", "recommendation", "gap_count", "gaps"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for fa in result.files:
        ws.append(
            [
                fa.slug,
                fa.cluster,
                fa.recommendation,
                len(fa.gaps),
                ", ".join(g.label for g in fa.gaps),
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
