"""Tests für pipeline/redundancy_scan.py — WP2 Detection (kein Vault-Mutation).

Schnell: die ML-schwere Embedding-Berechnung wird NICHT geladen — semantische/
thematische Bänder werden über injizierte Ähnlichkeitsmatrizen getestet; die
Integration läuft mit ``use_embeddings=False`` (Hash + TF-IDF). Fixtures bilden die
§11-Archetypen nach: small_clear (klar verwandt), large_mixed (unverbunden),
contradictory (thematische Überschneidung).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import redundancy_scan as rs
from pipeline.redundancy_scan import Thresholds, VaultDoc
from pipeline.schemas import QwenPairVerdict

TH = Thresholds()


# === Band-Klassifikation (pure) ===============================================


@pytest.mark.parametrize(
    ("exact", "tfidf", "emb", "expected"),
    [
        (True, 0.0, 0.0, "exact"),
        (False, 0.80, 0.20, "near-dup"),  # lexikalisch nah
        (False, 0.30, 0.90, "semantic-dup"),  # semantisch hoch, lexikalisch niedrig
        (False, 0.10, 0.70, "thematic"),  # Mittelband
        (False, 0.10, 0.40, None),  # unter allen Schwellen
        (False, 0.72, 0.10, "near-dup"),  # exakt an der TF-IDF-Schwelle
        (False, 0.50, 0.85, "semantic-dup"),  # exakt an der emb-dup-Schwelle
        (False, 0.50, 0.60, "thematic"),  # exakt an der thematic-Untergrenze
    ],
)
def test_classify_band(exact: bool, tfidf: float, emb: float, expected: str | None) -> None:
    assert rs.classify_band(exact, tfidf, emb, TH) == expected


def test_near_dup_precedes_semantic() -> None:
    """Hohe Lexik UND hohe Semantik → near-dup (Lexik gewinnt, Präzedenz)."""
    assert rs.classify_band(False, 0.9, 0.9, TH) == "near-dup"


# === Synthese-Komponenten =====================================================


def test_synthesis_components_min_members() -> None:
    # Kette 0-1-2 (3 Knoten) erfüllt min=3; Paar 5-6 nicht.
    comps = rs.synthesis_components([(0, 1), (1, 2), (5, 6)], min_members=3)
    assert comps == [[0, 1, 2]]


def test_synthesis_components_two_groups() -> None:
    comps = rs.synthesis_components([(0, 1), (1, 2), (3, 4), (4, 5)], min_members=3)
    assert sorted(comps) == [[0, 1, 2], [3, 4, 5]]


# === scan_pairs über injizierte Matrizen ======================================


def _docs(*slugs: str) -> list[VaultDoc]:
    return [VaultDoc(slug=s, body=f"body {s}", sources_docs=[f"D_{s}"]) for s in slugs]


def test_scan_pairs_bands_and_candidate() -> None:
    docs = _docs("a", "b", "c", "z")
    hashes = ["h", "h", "x", "y"]  # a == b exakt
    tf = np.zeros((4, 4), dtype="float32")
    emb = np.array(
        [
            [1.0, 1.0, 0.70, 0.10],
            [1.0, 1.0, 0.70, 0.10],
            [0.70, 0.70, 1.0, 0.10],
            [0.10, 0.10, 0.10, 1.0],
        ],
        dtype="float32",
    )
    pairs, cands = rs.scan_pairs(docs, hashes, tf, emb, TH)
    bands = {(p.slug_a, p.slug_b): p.band for p in pairs}
    assert bands[("a", "b")] == "exact"
    assert bands[("a", "c")] == "thematic"
    assert bands[("b", "c")] == "thematic"
    assert ("a", "z") not in bands  # 0.10 < thematic_low
    # a,b,c über thematische Kanten (a-c,b-c) verbunden → 1 Kandidat mit 3 Docs
    assert len(cands) == 1
    assert cands[0].slugs == ["a", "b", "c"]
    assert cands[0].sources == ["D_a", "D_b", "D_c"]


def test_scan_pairs_slug_order_normalized() -> None:
    docs = _docs("zeta", "alpha")
    emb = np.array([[1.0, 0.70], [0.70, 1.0]], dtype="float32")
    pairs, _ = rs.scan_pairs(docs, ["1", "2"], np.zeros((2, 2), "float32"), emb, TH)
    assert (pairs[0].slug_a, pairs[0].slug_b) == ("alpha", "zeta")


# === Doc-Laden (read-only) ====================================================


def _write_doc(
    folder: Path, name: str, body: str, slug: str | None = None, sources: list[str] | None = None
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    fm = [f"slug: {slug or name}"]
    if sources:
        fm.append("sources_docs:")
        fm += [f"  - {s}" for s in sources]
    (folder / f"{name}.md").write_text("---\n" + "\n".join(fm) + f"\n---\n\n{body}\n", "utf-8")


def test_load_vault_docs_skips_index_and_reads_frontmatter(tmp_path: Path) -> None:
    _write_doc(tmp_path / "01_X", "alpha", "Inhalt A", sources=["D_a1", "D_a2"])
    (tmp_path / "01_X" / "_index.md").write_text("---\ntitle: idx\n---\n", "utf-8")
    (tmp_path / "01_X" / "beta.body.md").write_text("nur body", "utf-8")
    docs = rs.load_vault_docs(tmp_path)
    assert [d.slug for d in docs] == ["alpha"]
    assert docs[0].sources_docs == ["D_a1", "D_a2"]


# === Integration: run ohne Embeddings (Hash + TF-IDF) =========================

_NEAR_A = "Backups schützen Daten vor Verlust durch redundante Kopien auf mehreren Medien."
_NEAR_B = "Backups schützen Daten vor Verlust durch redundante Kopien auf mehreren Medien heute."
_OTHER = "Vektorgrafiken skalieren verlustfrei weil sie aus mathematischen Pfaden bestehen."


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    # exact: zwei identische Bodies
    _write_doc(v / "00_M", "dup-eins", _OTHER, slug="dup-eins")
    _write_doc(v / "00_M", "dup-zwei", _OTHER, slug="dup-zwei")
    # near-dup: stark überlappende Bodies
    _write_doc(v / "01_A", "near-eins", _NEAR_A, slug="near-eins")
    _write_doc(v / "01_A", "near-zwei", _NEAR_B, slug="near-zwei")
    return v


def test_run_scan_without_embeddings(vault: Path) -> None:
    result = rs.run_redundancy_scan(vault, thresholds=TH, use_embeddings=False)
    assert result.n_docs == 4
    assert result.used_embeddings is False
    bands = {(p.slug_a, p.slug_b): p.band for p in result.pairs}
    assert bands[("dup-eins", "dup-zwei")] == "exact"
    assert bands[("near-eins", "near-zwei")] == "near-dup"
    # ohne Embeddings keine semantischen/thematischen Bänder
    assert all(p.band in ("exact", "near-dup") for p in result.pairs)
    assert result.candidates == []


def test_run_scan_empty_vault_raises(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        rs.run_redundancy_scan(tmp_path / "empty", thresholds=TH, use_embeddings=False)


# === Reports: Idempotenz + Inhalt =============================================


def test_reports_idempotent(vault: Path) -> None:
    result = rs.run_redundancy_scan(vault, thresholds=TH, use_embeddings=False)
    assert rs.render_redundancy_report(result) == rs.render_redundancy_report(result)
    assert rs.render_synthesis_report(result) == rs.render_synthesis_report(result)


def test_write_reports_byte_identical_second_run(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    r1 = rs.run_redundancy_scan(vault, thresholds=TH, use_embeddings=False)
    red1, syn1 = rs.write_reports(r1, out)
    b_red, b_syn = red1.read_bytes(), syn1.read_bytes()
    r2 = rs.run_redundancy_scan(vault, thresholds=TH, use_embeddings=False)
    rs.write_reports(r2, out)
    assert red1.read_bytes() == b_red
    assert syn1.read_bytes() == b_syn


def test_redundancy_report_contains_bands_and_provenance(vault: Path) -> None:
    result = rs.run_redundancy_scan(vault, thresholds=TH, use_embeddings=False)
    text = rs.render_redundancy_report(result)
    assert "| exact |" in text
    assert "`near-eins`" in text
    assert "kein Wall-Clock" in text  # Idempotenz-Hinweis


# === Qwen (injiziert / Parser) ================================================


def test_extract_json_block_and_bare() -> None:
    assert rs._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert rs._extract_json('vorab {"b": 2} danach') == {"b": 2}
    assert rs._extract_json("kein json") is None


def test_apply_qwen_sets_fields() -> None:
    docs = _docs("a", "b", "c")
    emb = np.array([[1, 0.7, 0.7], [0.7, 1, 0.7], [0.7, 0.7, 1]], dtype="float32")
    pairs, cands = rs.scan_pairs(docs, ["1", "2", "3"], np.zeros((3, 3), "float32"), emb, TH)
    body = {d.slug: d.body for d in docs}

    def fake_eval(pair, ba, bb):  # type: ignore[no-untyped-def]
        return QwenPairVerdict(
            relation="overlap",
            recommendation="cross-link",
            confidence="medium",
            rationale="ähnlich",
        )

    rs._apply_qwen(pairs, cands, body, fake_eval)
    assert all(p.qwen_relation == "overlap" for p in pairs)
    assert all(p.qwen_recommendation == "cross-link" for p in pairs)
