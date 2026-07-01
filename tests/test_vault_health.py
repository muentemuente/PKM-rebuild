"""Tests für R1 — Vault-Health-Report (Aggregation über quality-score-JSONL).

Alle Tests laufen auf ``tmp_path``-JSONL-Ständen; kein Vault, kein Scoring, kein
Netz. Deckt die drei vom Task geforderten Fälle: Snapshot-only (1 Lauf),
Delta (2 Läufe), leeres Verzeichnis.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pipeline.vault_health import (
    build_report,
    compute_delta,
    find_score_jsonls,
    load_snapshot,
)


def _rec(relpath: str, band: str, tier: str) -> dict[str, object]:
    """Minimaler quality_scores-Record (nur die vom Health-Report gelesenen Keys)."""
    return {
        "relpath": relpath,
        "slug": relpath.removesuffix(".md"),
        "readiness_band": band,
        "integration_tier": tier,
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


def test_snapshot_only_no_previous(tmp_path: Path) -> None:
    """Nur ein JSONL-Stand → Snapshot ohne Delta, klar gekennzeichnet."""
    qdir = tmp_path / "quality"
    _write_jsonl(
        qdir / "quality_scores_20260101_120000.jsonl",
        [
            _rec("a.md", "produktiv", "hub-kandidat"),
            _rec("b.md", "nutzbar", "verknüpfbar"),
            _rec("c.md", "nacharbeit", "insel"),
        ],
    )

    report = build_report(qdir)

    assert report.previous is None
    assert report.delta is None
    assert report.current.total == 3
    assert report.current.band_counts == {"produktiv": 1, "nutzbar": 1, "nacharbeit": 1}
    assert report.current.tier_counts == {"hub-kandidat": 1, "verknüpfbar": 1, "insel": 1}
    # High-Value = produktiv/nutzbar x hub-kandidat -> nur a.md
    assert report.current.high_value == frozenset({"a.md"})
    assert "erster Lauf — kein Vergleich möglich" in report.markdown


def test_delta_two_stands(tmp_path: Path) -> None:
    """Zwei Stände → Delta über Bänder/Tertile + neue/verschwundene Hubs."""
    qdir = tmp_path / "quality"
    # Vorlauf: a=hub, b=hub, c=insel
    _write_jsonl(
        qdir / "quality_scores_20260101_120000.jsonl",
        [
            _rec("a.md", "produktiv", "hub-kandidat"),
            _rec("b.md", "nutzbar", "hub-kandidat"),
            _rec("c.md", "nacharbeit", "insel"),
        ],
    )
    # Neuer Lauf: a bleibt hub, b fällt zu verknüpfbar, c steigt zu hub, d neu insel
    _write_jsonl(
        qdir / "quality_scores_20260102_120000.jsonl",
        [
            _rec("a.md", "produktiv", "hub-kandidat"),
            _rec("b.md", "nutzbar", "verknüpfbar"),
            _rec("c.md", "produktiv", "hub-kandidat"),
            _rec("d.md", "nacharbeit", "insel"),
        ],
    )

    report = build_report(qdir)

    assert report.previous is not None
    assert report.delta is not None
    d = report.delta
    assert report.current.total == 4
    assert d.total_delta == 1
    # produktiv: 1→2 (+1), nutzbar: 1→1 (0), nacharbeit: 1→1 (0)
    assert d.band_delta == {"produktiv": 1, "nutzbar": 0, "nacharbeit": 0}
    # hub: 2→2 (0), verknüpfbar: 0→1 (+1), insel: 1→1 (0)
    assert d.tier_delta == {"hub-kandidat": 0, "verknüpfbar": 1, "insel": 0}
    assert d.new_hubs == ("c.md",)
    assert d.vanished_hubs == ("b.md",)
    # neu High-Value: c.md (produktiv x hub), a war schon vorher hoch
    assert d.new_high_value == ("c.md",)
    assert "verschwunden" in report.markdown
    assert "`c.md`" in report.markdown


def test_incompatible_previous_schema_suppresses_delta(tmp_path: Path) -> None:
    """Alter Single-Axis-Lauf (band/composite, ohne readiness_band/tier) als Vorlauf
    → kein irreführendes Voll-Delta, sondern Snapshot mit klarem Hinweis."""
    qdir = tmp_path / "quality"
    # Vorlauf: altes Schema — nur band/composite, KEIN readiness_band/integration_tier.
    _write_jsonl(
        qdir / "quality_scores_20260101_120000.jsonl",
        [{"relpath": "a.md", "slug": "a", "band": "review", "composite": 70.0}],
    )
    # Neuer Lauf: Zwei-Achsen-Schema.
    _write_jsonl(
        qdir / "quality_scores_20260102_120000.jsonl",
        [_rec("a.md", "produktiv", "hub-kandidat")],
    )

    report = build_report(qdir)

    assert report.previous is not None  # Vorlauf existiert
    assert report.previous.has_two_axis is False
    assert report.delta is None  # aber nicht vergleichbar
    assert "inkompatibles Schema" in report.markdown


def test_empty_quality_dir_raises(tmp_path: Path) -> None:
    """Leeres (oder fehlendes) work/quality/ → klarer FileNotFoundError."""
    empty = tmp_path / "quality"
    empty.mkdir()
    assert find_score_jsonls(empty) == []
    with pytest.raises(FileNotFoundError, match="Kein quality_scores"):
        build_report(empty)
    # auch ein gar nicht existierendes Verzeichnis darf nicht crashen
    with pytest.raises(FileNotFoundError):
        build_report(tmp_path / "does-not-exist")


def test_newest_two_are_picked(tmp_path: Path) -> None:
    """Bei >2 Ständen werden die zwei jüngsten (lexikografisch = chronologisch) genutzt."""
    qdir = tmp_path / "quality"
    for ts in ("20260101_120000", "20260102_120000", "20260103_120000"):
        _write_jsonl(qdir / f"quality_scores_{ts}.jsonl", [_rec("a.md", "produktiv", "insel")])
    jsonls = find_score_jsonls(qdir)
    assert [p.name for p in jsonls] == [
        "quality_scores_20260101_120000.jsonl",
        "quality_scores_20260102_120000.jsonl",
        "quality_scores_20260103_120000.jsonl",
    ]
    report = build_report(qdir)
    assert report.current.timestamp == "20260103_120000"
    assert report.previous is not None
    assert report.previous.timestamp == "20260102_120000"


def test_unknown_band_counted_not_invented(tmp_path: Path) -> None:
    """Unbekannte Band-/Tertil-Werte werden gezählt, ohne Standard-Keys zu verfälschen."""
    qdir = tmp_path / "quality"
    path = _write_jsonl(
        qdir / "quality_scores_20260101_120000.jsonl",
        [_rec("a.md", "mystery", "insel")],
    )
    snap = load_snapshot(path)
    assert snap.band_counts["produktiv"] == 0
    assert snap.band_counts["mystery"] == 1
    # Delta gegen sich selbst ist überall 0
    d = compute_delta(snap, snap)
    assert all(v == 0 for v in d.band_delta.values())
