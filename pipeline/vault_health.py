"""R1 — Vault-Health-Report (MVP): aggregiert die ``quality-score``-Historie.

Reine **Aggregation/Veredelung** vorhandener ``quality_scores_<ts>.jsonl``-Läufe
(Output von :mod:`pipeline.quality_score`) zu einem kompakten, on-demand
aufrufbaren Health-Report. **Kein** neues Scoring, **kein** LLM, **kein** Vault-Read,
**kein** State-Store/Scheduler — es werden ausschließlich die JSONL-Stände gelesen
und, falls ein Vorlauf existiert, ein Delta gebildet.

Zwei Achsen (identisch zu :mod:`pipeline.quality_score`):

* **Readiness-Band** — ``produktiv`` / ``nutzbar`` / ``nacharbeit``
* **Integrations-Tertil** — ``hub-kandidat`` / ``verknüpfbar`` / ``insel``

``High-Value-Target`` = Band ``produktiv``/``nutzbar`` **und** Tertil ``hub-kandidat``
(deckungsgleich mit ``VaultQuality.high_value_targets``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()

#: Achsen-Vokabular (Reihenfolge = Report-Reihenfolge, best → worst).
READINESS_BANDS = ("produktiv", "nutzbar", "nacharbeit")
INTEGRATION_TIERS = ("hub-kandidat", "verknüpfbar", "insel")
_HIGH_VALUE_BANDS = frozenset({"produktiv", "nutzbar"})

#: ``quality_scores_YYYYMMDD_HHMMSS.jsonl`` — der Zeitstempel ist fixed-width,
#: lexikografisch = chronologisch.
_SCORE_GLOB = "quality_scores_*.jsonl"
_TS_RE = re.compile(r"quality_scores_(\d{8}_\d{6})\.jsonl$")


@dataclass(frozen=True)
class HealthSnapshot:
    """Aggregat eines einzelnen JSONL-Stands."""

    path: Path
    timestamp: str  # aus Dateiname geparst (oder "" wenn unparsbar)
    total: int
    band_counts: dict[str, int]
    tier_counts: dict[str, int]
    hub_relpaths: frozenset[str]  # relpath aller Files mit Tertil hub-kandidat
    high_value: frozenset[str]  # relpath aller High-Value-Targets
    has_two_axis: bool  # False = altes Single-Axis-Schema (kein readiness_band/tier)


@dataclass(frozen=True)
class HealthDelta:
    """Differenz zweier Snapshots (curr - prev)."""

    band_delta: dict[str, int]
    tier_delta: dict[str, int]
    total_delta: int
    new_hubs: tuple[str, ...]
    vanished_hubs: tuple[str, ...]
    new_high_value: tuple[str, ...]


@dataclass(frozen=True)
class HealthReport:
    """Vollständiges Report-Ergebnis (Snapshot + optionales Delta)."""

    current: HealthSnapshot
    previous: HealthSnapshot | None
    delta: HealthDelta | None
    markdown: str = field(default="")


def find_score_jsonls(quality_dir: Path) -> list[Path]:
    """Alle ``quality_scores_*.jsonl`` in ``quality_dir``, chronologisch (alt → neu)."""
    if not quality_dir.is_dir():
        return []
    return sorted(quality_dir.glob(_SCORE_GLOB), key=lambda p: p.name)


def _parse_ts(path: Path) -> str:
    m = _TS_RE.search(path.name)
    return m.group(1) if m else ""


def load_snapshot(path: Path) -> HealthSnapshot:
    """Liest einen JSONL-Stand und aggregiert Band-/Tertil-Zählungen + Hub-Set.

    Robust gegen unbekannte Band-/Tertil-Werte (werden gezählt, aber nicht als
    ``0`` erfunden) und gegen leere Zeilen.
    """
    band_counts: dict[str, int] = dict.fromkeys(READINESS_BANDS, 0)
    tier_counts: dict[str, int] = dict.fromkeys(INTEGRATION_TIERS, 0)
    hubs: set[str] = set()
    high_value: set[str] = set()
    total = 0
    has_two_axis = False

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            total += 1
            band = rec.get("readiness_band", "")
            tier = rec.get("integration_tier", "")
            if band or tier:
                has_two_axis = True
            relpath = rec.get("relpath", rec.get("slug", ""))
            band_counts[band] = band_counts.get(band, 0) + 1
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            if tier == "hub-kandidat":
                hubs.add(relpath)
                if band in _HIGH_VALUE_BANDS:
                    high_value.add(relpath)

    return HealthSnapshot(
        path=path,
        timestamp=_parse_ts(path),
        total=total,
        band_counts=band_counts,
        tier_counts=tier_counts,
        hub_relpaths=frozenset(hubs),
        high_value=frozenset(high_value),
        has_two_axis=has_two_axis,
    )


def compute_delta(current: HealthSnapshot, previous: HealthSnapshot) -> HealthDelta:
    """Delta ``current - previous`` über beide Achsen + Hub-/High-Value-Fluktuation."""
    band_delta = {
        b: current.band_counts.get(b, 0) - previous.band_counts.get(b, 0) for b in READINESS_BANDS
    }
    tier_delta = {
        t: current.tier_counts.get(t, 0) - previous.tier_counts.get(t, 0) for t in INTEGRATION_TIERS
    }
    return HealthDelta(
        band_delta=band_delta,
        tier_delta=tier_delta,
        total_delta=current.total - previous.total,
        new_hubs=tuple(sorted(current.hub_relpaths - previous.hub_relpaths)),
        vanished_hubs=tuple(sorted(previous.hub_relpaths - current.hub_relpaths)),
        new_high_value=tuple(sorted(current.high_value - previous.high_value)),
    )


def _fmt_signed(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def render_report(
    current: HealthSnapshot,
    previous: HealthSnapshot | None,
    delta: HealthDelta | None,
) -> str:
    """Rendert den Health-Report als Markdown (kompakt, Tabellen statt Fließtext)."""
    lines: list[str] = [
        "# Vault-Health-Report",
        "",
        f"- Stand: `{current.path.name}` ({current.timestamp or 'n/a'})",
        f"- Dateien bewertet: **{current.total}**",
        f"- High-Value-Targets (produktiv/nutzbar x hub-kandidat): **{len(current.high_value)}**",
    ]

    if previous is None:
        lines.append("- Vergleich: **erster Lauf — kein Vergleich möglich**")
    elif delta is None:
        # Vorlauf existiert, ist aber nicht vergleichbar (altes Single-Axis-Schema).
        lines.append(
            f"- Vergleich gegen `{previous.path.name}` **nicht möglich**: "
            "vorheriger Lauf nutzt inkompatibles Schema (pre-zwei-Achsen, ohne "
            "`readiness_band`/`integration_tier`) — nur Snapshot."
        )
    else:
        lines.append(
            f"- Vergleich gegen: `{previous.path.name}` "
            f"({previous.timestamp or 'n/a'}), Δ Dateien {_fmt_signed(delta.total_delta)}"
        )
    lines.append("")

    # Achse A — Readiness-Band
    lines += ["## Achse A — Readiness-Band", "", "| Band | Files | Δ |", "|---|---:|---:|"]
    for b in READINESS_BANDS:
        d = _fmt_signed(delta.band_delta[b]) if delta else "—"
        lines.append(f"| {b} | {current.band_counts.get(b, 0)} | {d} |")
    lines.append("")

    # Achse B — Integrations-Tertil
    lines += ["## Achse B — Integrations-Tertil", "", "| Tertil | Files | Δ |", "|---|---:|---:|"]
    for t in INTEGRATION_TIERS:
        d = _fmt_signed(delta.tier_delta[t]) if delta else "—"
        lines.append(f"| {t} | {current.tier_counts.get(t, 0)} | {d} |")
    lines.append("")

    # Hub-Fluktuation (nur bei Delta)
    if delta is not None:
        lines += ["## Hub-Kandidaten — Veränderung", ""]
        if not delta.new_hubs and not delta.vanished_hubs:
            lines.append("- keine Veränderung gegenüber Vorlauf")
        else:
            if delta.new_hubs:
                lines.append(f"- **neu** ({len(delta.new_hubs)}):")
                lines += [f"  - `{r}`" for r in delta.new_hubs]
            if delta.vanished_hubs:
                lines.append(f"- **verschwunden** ({len(delta.vanished_hubs)}):")
                lines += [f"  - `{r}`" for r in delta.vanished_hubs]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_report(quality_dir: Path) -> HealthReport:
    """Baut den Health-Report aus den JSONL-Ständen in ``quality_dir``.

    Raises:
        FileNotFoundError: wenn kein ``quality_scores_*.jsonl`` existiert.
    """
    jsonls = find_score_jsonls(quality_dir)
    if not jsonls:
        raise FileNotFoundError(
            f"Kein quality_scores_*.jsonl in {quality_dir} — erst `pkm quality-score` laufen lassen."
        )
    current = load_snapshot(jsonls[-1])
    previous = load_snapshot(jsonls[-2]) if len(jsonls) >= 2 else None
    # Delta nur bei schema-kompatiblem Vorlauf (beide Zwei-Achsen). Ein alter
    # Single-Axis-Lauf würde sonst ein irreführendes Voll-Delta erzeugen.
    delta = (
        compute_delta(current, previous)
        if (previous is not None and previous.has_two_axis and current.has_two_axis)
        else None
    )
    md = render_report(current, previous, delta)
    log.info(
        "vault_health_built",
        current=current.path.name,
        previous=previous.path.name if previous else None,
        total=current.total,
        high_value=len(current.high_value),
    )
    return HealthReport(current=current, previous=previous, delta=delta, markdown=md)
