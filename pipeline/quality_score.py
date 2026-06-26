"""Q1b — Zwei-Achsen-Quality-Scoring (read-only, kein LLM, kein Vault-Write).

Gibt **jeder** Vault-Content-Datei einen nachvollziehbaren Qualitätsstatus über sechs
Dimensionen (je 0-100, höher = besser), getrennt in **zwei orthogonale Achsen**:

* **Achse A — Readiness-Composite** (D1-D4) bestimmt das **Band**
  (``produktiv``/``nutzbar``/``nacharbeit``): „Ist die Datei für sich in gutem Zustand?"
* **Achse B — Integrations-Index** (D5/D6) ist ein **separates** Backlog-Signal mit
  Tertil-Label (``insel``/``verknüpfbar``/``hub-kandidat``) und fließt bewusst **nicht**
  ins Band: „Welchen Hebel hat Arbeit an Verlinkung/Synthese?"

Der Leverage-Quadrant (Band x Tertil) ist der Report-Kern. Alle Signale stammen
**deterministisch aus vorhandenen Rohdaten** — es wird nichts neu detektiert, sondern
bestehende Engines wiederverwendet (Reuse statt Parallel-Implementierung):

* **D1 Formale MD-Qualität** — :mod:`pipeline.vault_audit`-Findings (Heading-/Fence-/
  Korruptions-Defekte) + :func:`pipeline.format_vault.format_file`-Diff-Größe als Proxy.
* **D2 Strukturqualität** — Heading-Hierarchie (via :func:`vault_audit.iter_body`),
  Sektionsanzahl + Längen-Band.
* **D3 Metadaten-Vollständigkeit** — :func:`pipeline.frontmatter_audit.audit_file`
  (Pflichtfeld-Coverage + Enum-Validität) + Reichtum optionaler Felder.
* **D4 Redundanzgrad** (invers) — geparste ``redundancy_report.md``/
  ``synthesis_candidates.md``-Bänder. ``n/a`` ohne Report (nie geschätzt).
* **D5 Verknüpfbarkeit** — aufgelöster Out-/In-Grad der Wikilinks (Reuse der
  ``vault_audit``-Auflösungslogik) + ``related:``-Grad, Penalty für Dangling.
* **D6 Synthesepotenzial** — ``synthesis_candidates``-Membership + Keyphrase-Overlap
  (``keyphrases``-Feld) + thematische Ø-Similarity. ``n/a`` ohne Report.

Das Modul ist **non-mutating**: es liest den Vault und liefert Datenstrukturen +
Report-Text zurück. ``n/a``-Dimensionen reduzieren das Composite-Gewicht
**proportional** (Renormalisierung), senken den Score nicht künstlich.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts._pkm_common import REQUIRED_FIELDS as REQUIRED_FRONTMATTER_FIELDS

from pipeline.format_vault import format_file
from pipeline.frontmatter_audit import audit_file
from pipeline.vault_audit import (
    _INLINE_CODE_RE,
    _WIKILINK_RE,
    VaultIndex,
    _link_target_base,
    _resolves,
    build_index,
    check_corruption,
    check_fences,
    check_headings,
    check_wikilinks,
    iter_body,
    split_frontmatter,
)

# === Konstanten ===============================================================

#: Dimensions-Kennungen (stabile Reihenfolge für Report/JSONL).
DIMENSIONS: tuple[str, ...] = ("d1", "d2", "d3", "d4", "d5", "d6")

#: Achse A — Readiness (intrinsische Datei-Qualität → bestimmt das Band).
READINESS_DIMS: tuple[str, ...] = ("d1", "d2", "d3", "d4")
#: Achse B — Integration (Graph-/Synthese-Hebel → separater Index, NICHT im Band).
INTEGRATION_DIMS: tuple[str, ...] = ("d5", "d6")

#: Integrations-Tertil-Labels (Achse B).
TIER_INSEL = "insel"
TIER_VERKNUEPFBAR = "verknüpfbar"
TIER_HUB = "hub-kandidat"

#: Menschliche Dimensions-Labels (Report-Header).
DIMENSION_LABELS: dict[str, str] = {
    "d1": "Formale MD-Qualität",
    "d2": "Strukturqualität",
    "d3": "Metadaten-Vollständigkeit",
    "d4": "Redundanzgrad (invers)",
    "d5": "Verknüpfbarkeit",
    "d6": "Synthesepotenzial",
}

#: Band-Kennungen.
BAND_PRODUKTIV = "produktiv"
BAND_NUTZBAR = "nutzbar"
BAND_NACHARBEIT = "nacharbeit"

#: Dup-Band-Präzedenz (Index = Stärke; höher = schlechtere Qualität).
_DUP_BAND_RANK: dict[str, int] = {"thematic": 0, "semantic-dup": 1, "near-dup": 2, "exact": 3}

_ATX_RE = re.compile(r"^(#{1,6})\s+\S")
_SC_HEADER_RE = re.compile(r"^##\s+(SC_\d+).*?Ø-Sim\s+([0-9.]+)")
_MEMBERS_RE = re.compile(r"^\*\*Mitglieder:\*\*\s*(.+)$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


# === Konfiguration (Tunables; CLI füllt aus pipeline.config.yaml) =============


@dataclass(frozen=True)
class QualityConfig:
    """Gewichte + Schwellen des Scorings. Defaults = Spec; YAML ist autoritativ.

    Die Defaults erlauben Tests ohne Config-File; die CLI überschreibt sie aus
    ``pipeline.config.yaml → quality_score`` (Hard Rule: Tunables nicht im Code).
    """

    # Achse A — Readiness-Composite (bestimmt das Band): D1-D4, Default je 1/4.
    readiness_weights: dict[str, float] = field(
        default_factory=lambda: {d: 1.0 for d in READINESS_DIMS}
    )
    # Achse B — Integrations-Index (separat, NICHT im Band): D5/D6, Default je 1/2.
    integration_weights: dict[str, float] = field(
        default_factory=lambda: {d: 1.0 for d in INTEGRATION_DIMS}
    )
    # Readiness-Band-Schwellen (Achse A).
    produktiv_min: float = 80.0
    nutzbar_min: float = 60.0
    # Integrations-Tertil-Schwellen (Achse B, absolut): insel < low; hub >= high.
    integration_insel_max: float = 20.0  # < → insel
    integration_hub_min: float = 50.0  # >= → hub-kandidat (dazwischen → verknüpfbar)
    # D1.
    d1_severity_weights: dict[str, float] = field(
        default_factory=lambda: {"error": 3.0, "warning": 1.5, "info": 0.5}
    )
    d1_density_factor: float = 6.0  # Punkt-Abzug je gewichtetem Defekt pro 1k Zeichen
    d1_format_factor: float = 35.0  # Punkt-Abzug je Anteil format-geänderter Zeilen
    # D2 — typ-bewusst (Sektions-Cap je type) + Längen-Softening.
    d2_target_sections_min: int = 2
    d2_sections_max_by_type: dict[str, int] = field(
        default_factory=lambda: {
            "gedanke": 8,
            "knowledge-article": 14,
            "process-document": 28,
            "compact-reference": 45,
        }
    )
    d2_sections_max_default: int = 14  # Fallback (type fehlt/unbekannt)
    d2_length_softening_w: int = 120  # effektiver Cap >= round(word_count / W)
    d2_section_penalty_cap: float = 40.0  # Sektionszahl allein zieht d2 nie auf 0
    d2_target_words_min: int = 80
    d2_target_words_max: int = 3000
    d2_jump_penalty: float = 15.0
    d2_section_penalty: float = 8.0
    d2_length_penalty: float = 12.0
    # D3.
    d3_required_weight: float = 0.7
    d3_optional_weight: float = 0.3
    d3_invalid_penalty: float = 8.0
    d3_optional_fields: tuple[str, ...] = (
        "keyphrases",
        "related",
        "aliases",
        "tags",
        "subcategory",
        "parent_concept",
        "child_concepts",
        "used_in",
    )
    # D4 — Restqualität je stärkstem Band (höher = besser).
    d4_band_scores: dict[str, float] = field(
        default_factory=lambda: {
            "exact": 0.0,
            "near-dup": 25.0,
            "semantic-dup": 50.0,
            "thematic": 80.0,
        }
    )
    # D5.
    d5_target_out_degree: int = 3
    d5_target_in_degree: int = 2
    d5_dangling_penalty: float = 20.0
    # D6.
    d6_weight_membership: float = 40.0
    d6_weight_keyphrase: float = 30.0
    d6_weight_thematic: float = 30.0
    d6_keyphrase_min_shared: int = 2
    d6_keyphrase_target_docs: int = 3
    d6_thematic_low: float = 0.70  # Untergrenze thematisches Band (= redundancy_scan)
    d6_thematic_high: float = 0.85  # Obergrenze (emb-dup)


# === Datenmodell ==============================================================


@dataclass(frozen=True)
class DimensionScore:
    """Ein Dimensions-Score mit Nachvollziehbarkeit.

    ``score is None`` markiert ``n/a`` (z. B. fehlende Redundanz-Daten) — die
    Dimension wird im Composite proportional ausgewichtet, **nicht** als 0 gewertet.
    """

    name: str
    score: float | None
    evidence: list[str]

    @property
    def na(self) -> bool:
        return self.score is None


@dataclass(frozen=True)
class FileQuality:
    """Qualitätsbefund einer einzelnen Vault-Datei (zwei Achsen).

    ``readiness_band`` (aus D1-D4) ist die Qualitäts-Einordnung; der
    ``integration_index`` (aus D5/D6) ist ein **separates** Backlog-Signal und
    fließt bewusst **nicht** ins Band ein.
    """

    relpath: str
    slug: str
    dimensions: dict[str, DimensionScore]
    readiness_composite: float
    readiness_band: str
    integration_index: float
    integration_tier: str

    def weakest_readiness(self) -> DimensionScore | None:
        """Schwächste bewertete **Readiness**-Dimension (D1-D4); ``None`` wenn alle n/a."""
        scored = [
            self.dimensions[d] for d in READINESS_DIMS if self.dimensions[d].score is not None
        ]
        return min(scored, key=lambda d: d.score) if scored else None  # type: ignore[arg-type,return-value]


@dataclass
class VaultQuality:
    """Aggregat über den Vault."""

    vault_dir: Path
    files: list[FileQuality]
    sources_active: dict[str, bool]  # welche Reuse-Quellen aktiv (z. B. redundancy)

    def readiness_band_counts(self) -> dict[str, int]:
        out = {BAND_PRODUKTIV: 0, BAND_NUTZBAR: 0, BAND_NACHARBEIT: 0}
        for f in self.files:
            out[f.readiness_band] += 1
        return out

    def integration_tier_counts(self) -> dict[str, int]:
        out = {TIER_INSEL: 0, TIER_VERKNUEPFBAR: 0, TIER_HUB: 0}
        for f in self.files:
            out[f.integration_tier] += 1
        return out

    def leverage_quadrant(self) -> dict[tuple[str, str], int]:
        """Kreuztabelle (Readiness-Band x Integrations-Tertil)."""
        out: dict[tuple[str, str], int] = {}
        for f in self.files:
            key = (f.readiness_band, f.integration_tier)
            out[key] = out.get(key, 0) + 1
        return out

    def high_value_targets(self) -> list[FileQuality]:
        """produktiv/nutzbar x hub-kandidat — direkt nutzbar **und** hoher Verlinkungs-Hebel."""
        return sorted(
            (
                f
                for f in self.files
                if f.readiness_band in (BAND_PRODUKTIV, BAND_NUTZBAR)
                and f.integration_tier == TIER_HUB
            ),
            key=lambda f: (-f.integration_index, -f.readiness_composite),
        )

    def score_map(self) -> dict[str, tuple[float, float]]:
        """relpath → (Readiness, Integration) für den Idempotenz-Hash."""
        return {f.relpath: (f.readiness_composite, f.integration_index) for f in self.files}

    def score_hash(self) -> str:
        """Stabiler Hash der Score-Map (kein Wall-Clock) — Idempotenz-Beleg."""
        payload = json.dumps(
            {k: [round(v[0], 4), round(v[1], 4)] for k, v in sorted(self.score_map().items())},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# === Redundanz-Report-Reuse (Markdown-Parse, kein Embedding-Lauf) =============


@dataclass
class RedundancyData:
    """Aus ``redundancy_report.md`` + ``synthesis_candidates.md`` geparste Signale."""

    dup_band_by_slug: dict[str, str] = field(default_factory=dict)  # stärkstes Dup-Band
    synthesis_members: set[str] = field(default_factory=set)
    mean_sim_by_slug: dict[str, float] = field(default_factory=dict)  # Ø-Sim des SC

    def worst_band(self, slug: str) -> str | None:
        """Stärkstes Band des Slugs (Dup-Bänder > thematic) oder ``None`` (keine Überlappung)."""
        if slug in self.dup_band_by_slug:
            return self.dup_band_by_slug[slug]
        if slug in self.synthesis_members:
            return "thematic"
        return None


def _parse_redundancy_report(text: str) -> dict[str, str]:
    """Dup-Tabelle → ``{slug: stärkstes Band}`` (exact/near-dup/semantic-dup)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        band = cells[0]
        if band not in _DUP_BAND_RANK or band == "thematic":
            continue
        for raw in (cells[1], cells[2]):
            slug = raw.strip().strip("`").strip()
            if not slug:
                continue
            prev = out.get(slug)
            if prev is None or _DUP_BAND_RANK[band] > _DUP_BAND_RANK[prev]:
                out[slug] = band
    return out


def _parse_synthesis_report(text: str) -> tuple[set[str], dict[str, float]]:
    """SC-Komponenten → (Mitglieder-Slugs, ``{slug: Ø-Sim seines SC}``)."""
    members: set[str] = set()
    mean_sim: dict[str, float] = {}
    current_sim = 0.0
    for line in text.splitlines():
        header = _SC_HEADER_RE.match(line)
        if header:
            current_sim = float(header.group(2))
            continue
        m = _MEMBERS_RE.match(line)
        if m:
            for slug in _BACKTICK_RE.findall(m.group(1)):
                members.add(slug)
                mean_sim[slug] = current_sim
    return members, mean_sim


def load_redundancy_data(
    redundancy_md: Path | None, synthesis_md: Path | None
) -> RedundancyData | None:
    """Lädt Redundanz-Signale aus den Reports. ``None`` wenn beide fehlen (→ D4/D6 n/a)."""
    if (redundancy_md is None or not redundancy_md.is_file()) and (
        synthesis_md is None or not synthesis_md.is_file()
    ):
        return None
    data = RedundancyData()
    if redundancy_md is not None and redundancy_md.is_file():
        data.dup_band_by_slug = _parse_redundancy_report(redundancy_md.read_text(encoding="utf-8"))
    if synthesis_md is not None and synthesis_md.is_file():
        data.synthesis_members, data.mean_sim_by_slug = _parse_synthesis_report(
            synthesis_md.read_text(encoding="utf-8")
        )
    return data


def resolve_redundancy_paths(reuse: Path | None, work_dir: Path) -> tuple[Path | None, Path | None]:
    """Bestimmt die beiden Report-Pfade aus ``--reuse-redundancy`` oder ``work/`` (Default).

    ``reuse`` darf ein Verzeichnis, ein ``redundancy_report.md`` oder ein
    ``synthesis_candidates.md`` sein; die jeweils andere Datei wird im selben Ordner
    gesucht. Ohne ``reuse`` werden die kanonischen ``work/``-Reports genutzt (kein
    Embedding-Lauf — nur Reuse vorhandener Reports, §3).
    """
    base = reuse if reuse is not None else work_dir
    folder = base if base.is_dir() else base.parent
    red = folder / "redundancy_report.md"
    syn = folder / "synthesis_candidates.md"
    return (red if red.is_file() else None, syn if syn.is_file() else None)


# === Hilfen: Body-Parsing (Reuse von vault_audit.iter_body) ===================


def _headings(text: str) -> list[tuple[int, str]]:
    """Heading-Liste ``[(level, text)]`` (fence-aware via ``iter_body``)."""
    out: list[tuple[int, str]] = []
    for bl in iter_body(text):
        if bl.in_fence:
            continue
        m = _ATX_RE.match(bl.text)
        if m:
            out.append((len(m.group(1)), bl.text.lstrip("#").strip()))
    return out


def _resolved_out_links(text: str, index: VaultIndex) -> int:
    """Anzahl **eindeutiger** auflösbarer Wikilink-Ziele im Body (Reuse der Auflösung)."""
    targets: set[str] = set()
    for bl in iter_body(text):
        if bl.in_fence:
            continue
        scan = _INLINE_CODE_RE.sub("", bl.text)
        for m in _WIKILINK_RE.finditer(scan):
            if scan[m.end() : m.end() + 1] == "(":
                continue
            base = _link_target_base(m.group(2))
            if base and _resolves(base, index):
                targets.add(base.lower())
    return len(targets)


def _str_list_len(value: Any) -> int:
    """Länge eines Frontmatter-Listenfeldes (0 wenn kein nicht-leerer Listentyp)."""
    if isinstance(value, list):
        return len([v for v in value if str(v).strip()])
    return 0


def _is_present(value: Any) -> bool:
    """``True`` wenn ein Frontmatter-Feld nicht-leer ist (Liste **oder** Skalar)."""
    if value is None:
        return False
    if isinstance(value, list):
        return any(str(v).strip() for v in value)
    return bool(str(value).strip())


# === Vault-weite Vorab-Indizes (In-Grad, Keyphrase-Overlap) ===================


def _build_in_degree(index: VaultIndex) -> dict[str, int]:
    """Vault-weiter In-Grad je Stem (wie oft verlinkt ein **anderes** Doc darauf)."""
    in_deg: dict[str, int] = {}
    for rel, text in index.audit_files.items():
        src_stem = Path(rel).stem
        seen: set[str] = set()
        for bl in iter_body(text):
            if bl.in_fence:
                continue
            scan = _INLINE_CODE_RE.sub("", bl.text)
            for m in _WIKILINK_RE.finditer(scan):
                if scan[m.end() : m.end() + 1] == "(":
                    continue
                base = _link_target_base(m.group(2))
                if base and _resolves(base, index):
                    seen.add(base.lower())
        for tgt in seen:
            if tgt != src_stem.lower():
                in_deg[tgt] = in_deg.get(tgt, 0) + 1
    return in_deg


def _build_keyphrase_overlap(index: VaultIndex, min_shared: int) -> dict[str, int]:
    """Je relpath: Anzahl **anderer** Docs, die ≥ ``min_shared`` Keyphrases teilen."""
    kp_by_rel: dict[str, set[str]] = {}
    for rel, fm in index.frontmatter.items():
        if not isinstance(fm, dict):
            kp_by_rel[rel] = set()
            continue
        raw = fm.get("keyphrases")
        kp_by_rel[rel] = (
            {str(p).strip().lower() for p in raw if str(p).strip()}
            if isinstance(raw, list)
            else set()
        )
    out: dict[str, int] = {}
    rels = list(kp_by_rel)
    for i, rel in enumerate(rels):
        kp = kp_by_rel[rel]
        if not kp:
            out[rel] = 0
            continue
        count = 0
        for j, other in enumerate(rels):
            if i == j:
                continue
            if len(kp & kp_by_rel[other]) >= min_shared:
                count += 1
        out[rel] = count
    return out


# === Dimensions-Scoring (pure) ================================================


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def score_d1(relpath: str, text: str, cfg: QualityConfig) -> DimensionScore:
    """D1 — formale MD-Qualität: gewichtete Defektdichte + Format-Diff-Proxy."""
    findings = (
        check_headings(relpath, text)
        + check_fences(relpath, text)
        + check_corruption(relpath, text)
    )
    weighted = sum(cfg.d1_severity_weights.get(f.severity, 1.0) for f in findings)
    chars = max(len(text), 1)
    density = weighted / max(chars / 1000.0, 1.0)
    fr = format_file(text, relpath)
    n_lines = max(text.count("\n"), 1)
    format_ratio = (fr.added + fr.removed) / n_lines
    penalty = cfg.d1_density_factor * density + cfg.d1_format_factor * format_ratio
    score = _clamp(100.0 - penalty)
    ev: list[str] = []
    if findings:
        from collections import Counter

        counts = Counter(f.rule for f in findings)
        ev.append("Findings: " + ", ".join(f"{r}:{n}" for r, n in sorted(counts.items())))
    if fr.added or fr.removed:
        ev.append(f"Format-Diff: +{fr.added}/-{fr.removed} Zeilen")
    if not ev:
        ev.append("keine formalen Defekte")
    return DimensionScore("d1", score, ev)


def _d2_sections_cap(type_: str | None, words: int, cfg: QualityConfig) -> int:
    """Effektiver Sektions-Cap: typ-bewusst, durch Wortzahl gelockert (mildere Regel).

    Es greift die **mildere** der beiden Regeln: der typ-spezifische Cap oder ein
    proportional zur Länge gelockerter Cap — verhindert, dass lange legitime
    Referenz-Docs am reinen Sektions-Cap scheitern.
    """
    type_max = cfg.d2_sections_max_by_type.get(type_ or "", cfg.d2_sections_max_default)
    length_cap = round(words / cfg.d2_length_softening_w) if cfg.d2_length_softening_w else 0
    return max(type_max, length_cap)


def score_d2(text: str, fm: dict[str, Any] | None, cfg: QualityConfig) -> DimensionScore:
    """D2 — Strukturqualität: Heading-Hierarchie, typ-bewusste Sektionsanzahl, Längen-Band."""
    headings = _headings(text)
    _, body, _ = split_frontmatter(text)
    words = len(body.split())
    type_ = fm.get("type") if isinstance(fm, dict) else None
    is_gedanke = type_ == "gedanke"

    jumps = 0
    prev = 0
    for level, _t in headings:
        if prev and level - prev > 1:
            jumps += 1
        prev = level
    penalty = cfg.d2_jump_penalty * jumps
    ev: list[str] = []
    if jumps:
        ev.append(f"{jumps} Hierarchie-Sprung(e)")

    n = len(headings)
    sections_cap = _d2_sections_cap(type_, words, cfg)
    # Untergrenze (gedanke darf headinglos sein → ausgenommen).
    if not is_gedanke and n < cfg.d2_target_sections_min:
        penalty += cfg.d2_section_penalty * (cfg.d2_target_sections_min - n)
        ev.append(f"nur {n} Sektion(en) (<{cfg.d2_target_sections_min})")
    # Obergrenze typ-bewusst + gedeckelt: Sektionszahl allein zieht d2 nie auf 0.
    elif n > sections_cap:
        sec_pen = min(cfg.d2_section_penalty * (n - sections_cap), cfg.d2_section_penalty_cap)
        penalty += sec_pen
        ev.append(f"{n} Sektionen (>{sections_cap}, Cap {type_ or '?'})")

    if not is_gedanke and (words < cfg.d2_target_words_min or words > cfg.d2_target_words_max):
        penalty += cfg.d2_length_penalty
        ev.append(
            f"Länge {words} W außerhalb [{cfg.d2_target_words_min},{cfg.d2_target_words_max}]"
        )

    if not ev:
        ev.append(f"{n} Sektionen, {words} W, saubere Hierarchie")
    return DimensionScore("d2", _clamp(100.0 - penalty), ev)


def score_d3(
    path: Path, vault_dir: Path, fm: dict[str, Any] | None, cfg: QualityConfig
) -> DimensionScore:
    """D3 — Metadaten: Pflichtfeld-Coverage (frontmatter_audit) + optionaler Reichtum."""
    fa = audit_file(path, vault_dir)
    missing = [g for g in fa.gaps if g.label.startswith("missing:")]
    invalid = [g for g in fa.gaps if g.label.startswith(("invalid:", "slug:", "frontmatter:"))]
    req_total = len(REQUIRED_FRONTMATTER_FIELDS)
    if fm is None:
        coverage = 0.0
        opt_ratio = 0.0
    else:
        coverage = max(0.0, (req_total - len(missing)) / req_total)
        present = sum(1 for fld in cfg.d3_optional_fields if _is_present(fm.get(fld)))
        opt_ratio = present / len(cfg.d3_optional_fields)
    base = cfg.d3_required_weight * coverage + cfg.d3_optional_weight * opt_ratio
    score = _clamp(100.0 * base - cfg.d3_invalid_penalty * len(invalid))
    ev = [f"Pflichtfeld-Coverage {coverage * 100:.0f}%", f"optional {opt_ratio * 100:.0f}%"]
    if missing:
        ev.append("fehlt: " + ", ".join(g.label.split(":", 1)[1] for g in missing))
    if invalid:
        ev.append("invalid: " + ", ".join(g.label for g in invalid))
    return DimensionScore("d3", score, ev)


def score_d4(slug: str, redundancy: RedundancyData | None, cfg: QualityConfig) -> DimensionScore:
    """D4 — Redundanzgrad (invers): 100 ohne Überlappung, abgestuft nach stärkstem Band."""
    if redundancy is None:
        return DimensionScore("d4", None, ["n/a — kein Redundanz-Report"])
    band = redundancy.worst_band(slug)
    if band is None:
        return DimensionScore("d4", 100.0, ["keine Redundanz-Überlappung"])
    score = cfg.d4_band_scores.get(band, 50.0)
    return DimensionScore("d4", _clamp(score), [f"stärkstes Band: {band}"])


def score_d5(
    relpath: str,
    text: str,
    fm: dict[str, Any] | None,
    index: VaultIndex,
    in_degree: dict[str, int],
    cfg: QualityConfig,
) -> DimensionScore:
    """D5 — Verknüpfbarkeit: aufgelöster Out-/In-Grad + ``related:``, Penalty für Dangling."""
    resolved_out = _resolved_out_links(text, index)
    dangling = sum(1 for f in check_wikilinks(relpath, text, index) if f.rule == "wikilink")
    related = _str_list_len(fm.get("related")) if isinstance(fm, dict) else 0
    in_deg = in_degree.get(Path(relpath).stem.lower(), 0)
    out_total = resolved_out + related
    out_score = min(1.0, out_total / cfg.d5_target_out_degree)
    in_score = min(1.0, in_deg / cfg.d5_target_in_degree)
    score = _clamp(100.0 * (0.5 * out_score + 0.5 * in_score) - cfg.d5_dangling_penalty * dangling)
    ev = [f"Out-Grad {out_total} (Links {resolved_out}+related {related})", f"In-Grad {in_deg}"]
    if dangling:
        ev.append(f"{dangling} Dangling-Link(s)")
    return DimensionScore("d5", score, ev)


def score_d6(
    slug: str,
    relpath: str,
    redundancy: RedundancyData | None,
    keyphrase_overlap: dict[str, int],
    cfg: QualityConfig,
) -> DimensionScore:
    """D6 — Synthesepotenzial: SC-Membership + Keyphrase-Overlap + thematische Ø-Sim."""
    if redundancy is None:
        return DimensionScore("d6", None, ["n/a — kein Synthese-Report"])
    is_member = slug in redundancy.synthesis_members
    membership = 1.0 if is_member else 0.0
    shared = keyphrase_overlap.get(relpath, 0)
    kp_score = min(1.0, shared / cfg.d6_keyphrase_target_docs)
    span = max(cfg.d6_thematic_high - cfg.d6_thematic_low, 1e-6)
    if is_member:
        sim = redundancy.mean_sim_by_slug.get(slug, cfg.d6_thematic_low)
        thematic = max(0.0, min(1.0, (sim - cfg.d6_thematic_low) / span))
    else:
        thematic = 0.0
    score = _clamp(
        cfg.d6_weight_membership * membership
        + cfg.d6_weight_keyphrase * kp_score
        + cfg.d6_weight_thematic * thematic
    )
    ev = [
        f"SC-Member: {'ja' if is_member else 'nein'}",
        f"Keyphrase-Overlap: {shared} Doc(s)",
    ]
    if is_member:
        ev.append(f"thematische Ø-Sim {redundancy.mean_sim_by_slug.get(slug, 0.0):.3f}")
    return DimensionScore("d6", score, ev)


# === Achsen-Aggregation =======================================================


def _weighted(
    dims: dict[str, DimensionScore], names: tuple[str, ...], weights: dict[str, float]
) -> float:
    """Gewichtetes Mittel über ``names``; ``n/a``-Dimensionen proportional ausgewichtet."""
    num = 0.0
    den = 0.0
    for name in names:
        d = dims[name]
        if d.score is None:
            continue
        w = weights.get(name, 1.0)
        num += w * d.score
        den += w
    return round(num / den, 2) if den else 0.0


def readiness_composite(dims: dict[str, DimensionScore], cfg: QualityConfig) -> float:
    """Achse A — intrinsische Datei-Qualität aus D1-D4 (bestimmt das Band)."""
    return _weighted(dims, READINESS_DIMS, cfg.readiness_weights)


def integration_index(dims: dict[str, DimensionScore], cfg: QualityConfig) -> float:
    """Achse B — Graph-/Synthese-Hebel aus D5/D6 (separates Backlog-Signal)."""
    return _weighted(dims, INTEGRATION_DIMS, cfg.integration_weights)


def readiness_band_of(composite: float, cfg: QualityConfig) -> str:
    if composite >= cfg.produktiv_min:
        return BAND_PRODUKTIV
    if composite >= cfg.nutzbar_min:
        return BAND_NUTZBAR
    return BAND_NACHARBEIT


def integration_tier_of(index_val: float, cfg: QualityConfig) -> str:
    if index_val >= cfg.integration_hub_min:
        return TIER_HUB
    if index_val < cfg.integration_insel_max:
        return TIER_INSEL
    return TIER_VERKNUEPFBAR


# === Orchestrierung ===========================================================


def score_file(
    relpath: str,
    text: str,
    fm: dict[str, Any] | None,
    *,
    vault_dir: Path,
    index: VaultIndex,
    in_degree: dict[str, int],
    keyphrase_overlap: dict[str, int],
    redundancy: RedundancyData | None,
    cfg: QualityConfig,
) -> FileQuality:
    """Bewertet eine einzelne Datei über die sechs Dimensionen + beide Achsen."""
    slug = str(fm.get("slug")) if isinstance(fm, dict) and fm.get("slug") else Path(relpath).stem
    path = vault_dir / relpath
    dims = {
        "d1": score_d1(relpath, text, cfg),
        "d2": score_d2(text, fm, cfg),
        "d3": score_d3(path, vault_dir, fm, cfg),
        "d4": score_d4(slug, redundancy, cfg),
        "d5": score_d5(relpath, text, fm, index, in_degree, cfg),
        "d6": score_d6(slug, relpath, redundancy, keyphrase_overlap, cfg),
    }
    readiness = readiness_composite(dims, cfg)
    integration = integration_index(dims, cfg)
    return FileQuality(
        relpath,
        slug,
        dims,
        readiness,
        readiness_band_of(readiness, cfg),
        integration,
        integration_tier_of(integration, cfg),
    )


def score_vault(
    vault_dir: Path,
    *,
    redundancy: RedundancyData | None,
    cfg: QualityConfig | None = None,
) -> VaultQuality:
    """Scort den gesamten Vault (read-only, deterministisch, kein LLM/Vault-Write)."""
    cfg = cfg or QualityConfig()
    index = build_index(vault_dir)
    in_degree = _build_in_degree(index)
    keyphrase_overlap = _build_keyphrase_overlap(index, cfg.d6_keyphrase_min_shared)
    files: list[FileQuality] = []
    for rel, text in sorted(index.audit_files.items()):
        fm = index.frontmatter.get(rel)
        files.append(
            score_file(
                rel,
                text,
                fm,
                vault_dir=vault_dir,
                index=index,
                in_degree=in_degree,
                keyphrase_overlap=keyphrase_overlap,
                redundancy=redundancy,
                cfg=cfg,
            )
        )
    files.sort(key=lambda f: f.relpath)
    return VaultQuality(
        vault_dir=vault_dir,
        files=files,
        sources_active={"redundancy": redundancy is not None},
    )


# === Report / Export ==========================================================


def _dim_distribution(files: list[FileQuality], name: str) -> tuple[float, float, float] | None:
    """(Min, Median, Max) der bewerteten Scores einer Dimension; ``None`` wenn alle n/a."""
    vals: list[float] = sorted(s for f in files if (s := f.dimensions[name].score) is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return vals[0], median, vals[-1]


def render_report(vq: VaultQuality, cfg: QualityConfig, *, top_n: int = 15) -> str:
    """Markdown-Report: zwei Achsen + Leverage-Quadrant + High-Value-Liste + Fazit."""
    files = vq.files
    total = len(files)
    bands = vq.readiness_band_counts()
    tiers = vq.integration_tier_counts()
    lines = [
        "# Quality-Score-Report (Q1b — zwei Achsen, deterministisch, read-only)",
        "",
        f"<!-- score_hash: {vq.score_hash()} · reproduzierbar, kein Wall-Clock im Body -->",
        "",
        f"- Vault: `{vq.vault_dir}` · Files: **{total}**",
        "- Datenquellen: "
        + ", ".join(f"{k}={'aktiv' if v else 'n/a'}" for k, v in sorted(vq.sources_active.items())),
        "- **Achse A (Readiness, D1-D4)** → Band · **Achse B (Integration, D5/D6)** → Backlog-Hebel",
        "",
        "## Readiness-Band-Verteilung (Achse A)",
        "",
        "| Band | Files | Anteil |",
        "|---|---:|---:|",
    ]
    for b in (BAND_PRODUKTIV, BAND_NUTZBAR, BAND_NACHARBEIT):
        pct = (bands[b] / total * 100) if total else 0.0
        lines.append(f"| {b} | {bands[b]} | {pct:.0f}% |")

    lines += [
        "",
        "## Integrations-Tertil-Verteilung (Achse B)",
        "",
        "| Tertil | Files | Anteil |",
        "|---|---:|---:|",
    ]
    for t in (TIER_HUB, TIER_VERKNUEPFBAR, TIER_INSEL):
        pct = (tiers[t] / total * 100) if total else 0.0
        lines.append(f"| {t} | {tiers[t]} | {pct:.0f}% |")

    # Leverage-Quadrant (A x B).
    quad = vq.leverage_quadrant()
    lines += [
        "",
        "## Leverage-Quadrant (Readiness x Integration)",
        "",
        "| Readiness ↓ / Integration → | hub-kandidat | verknüpfbar | insel |",
        "|---|---:|---:|---:|",
    ]
    for b in (BAND_PRODUKTIV, BAND_NUTZBAR, BAND_NACHARBEIT):
        row = " | ".join(
            str(quad.get((b, t), 0)) for t in (TIER_HUB, TIER_VERKNUEPFBAR, TIER_INSEL)
        )
        lines.append(f"| {b} | {row} |")
    lines += [
        "",
        "> `produktiv x hub-kandidat` = **High-Value, jetzt verknüpfen/synthetisieren**. "
        "`nacharbeit x insel` = erst Basis fixen.",
    ]

    lines += [
        "",
        "## Dimensions-Verteilung (Min / Median / Max)",
        "",
        "| Dim | Label | Achse | Min | Median | Max |",
        "|---|---|---|---:|---:|---:|",
    ]
    for d in DIMENSIONS:
        axis = "A" if d in READINESS_DIMS else "B"
        dist = _dim_distribution(files, d)
        if dist is None:
            lines.append(f"| {d} | {DIMENSION_LABELS[d]} | {axis} | n/a | n/a | n/a |")
        else:
            lines.append(
                f"| {d} | {DIMENSION_LABELS[d]} | {axis} | "
                f"{dist[0]:.0f} | {dist[1]:.0f} | {dist[2]:.0f} |"
            )

    lines += ["", f"## Worst-Readiness-Offenders (Top {top_n})", ""]
    worst = sorted(files, key=lambda f: f.readiness_composite)[:top_n]
    lines += ["| Slug | Readiness | treibende Dimension |", "|---|---:|---|"]
    for f in worst:
        w = f.weakest_readiness()
        wd = f"{w.name} ({w.score:.0f}): {'; '.join(w.evidence)}" if w else "—"
        lines.append(f"| `{f.slug}` | {f.readiness_composite:.0f} | {wd} |")

    # High-Value-Liste (Hub-Kandidaten in produktiv/nutzbar).
    hv = vq.high_value_targets()
    lines += ["", "## Hub-Kandidaten in produktiv/nutzbar (High-Value-Targets)", ""]
    if not hv:
        lines += ["_keine_ — kein direkt nutzbares Doc erreicht das hub-Tertil.", ""]
    else:
        lines += ["| Slug | Readiness-Band | Integration | treibend |", "|---|---|---:|---|"]
        for f in hv:
            d5 = f.dimensions["d5"].score or 0.0
            d6 = f.dimensions["d6"].score
            d6s = f"{d6:.0f}" if d6 is not None else "n/a"
            lines.append(
                f"| `{f.slug}` | {f.readiness_band} | {f.integration_index:.0f} | "
                f"D5 {d5:.0f}/D6 {d6s} |"
            )
        lines.append("")

    prod_pct = (bands[BAND_PRODUKTIV] / total * 100) if total else 0.0
    lever = _biggest_lever(files)
    lines += [
        "## Fazit",
        "",
        f"Produktiv-Quote **{prod_pct:.0f}%** ({bands[BAND_PRODUKTIV]}/{total}). "
        f"Größter Readiness-Hebel: {lever}. "
        f"High-Value-Targets (produktiv/nutzbar x hub-kandidat): **{len(hv)}**.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _biggest_lever(files: list[FileQuality]) -> str:
    """Readiness-Dimension mit dem niedrigsten Median (größter Verbesserungshebel)."""
    best: tuple[str, float] | None = None
    for d in READINESS_DIMS:
        dist = _dim_distribution(files, d)
        if dist is None:
            continue
        if best is None or dist[1] < best[1]:
            best = (d, dist[1])
    if best is None:
        return "—"
    return f"{best[0]} ({DIMENSION_LABELS[best[0]]}, Median {best[1]:.0f})"


def to_jsonl_records(vq: VaultQuality) -> list[dict[str, Any]]:
    """Pro Datei ein JSONL-Record (zwei Achsen + alle Sub-Scores + Evidence)."""
    out: list[dict[str, Any]] = []
    for f in vq.files:
        rec: dict[str, Any] = {
            "relpath": f.relpath,
            "slug": f.slug,
            "readiness_composite": f.readiness_composite,
            "readiness_band": f.readiness_band,
            "integration_index": f.integration_index,
            "integration_tier": f.integration_tier,
        }
        for d in DIMENSIONS:
            ds = f.dimensions[d]
            rec[d] = {"score": ds.score, "evidence": ds.evidence}
        out.append(rec)
    return out


def write_jsonl(vq: VaultQuality, path: Path) -> Path:
    """Schreibt die JSONL-Records (1 Zeile/File)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in to_jsonl_records(vq):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def write_xlsx(vq: VaultQuality, path: Path) -> Path:
    """Optionales ``.xlsx`` (eine Zeile/File: Slug, beide Achsen, D1-D6)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "quality-score"
    ws.append(
        [
            "slug",
            "readiness_band",
            "readiness_composite",
            "integration_tier",
            "integration_index",
            *DIMENSIONS,
        ]
    )
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for f in vq.files:
        ws.append(
            [
                f.slug,
                f.readiness_band,
                f.readiness_composite,
                f.integration_tier,
                f.integration_index,
                *(f.dimensions[d].score for d in DIMENSIONS),
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
