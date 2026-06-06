"""Tests für scripts/clustering_analysis.py.

Verifiziert: Skript läuft auf echten Daten, Output-Datei hat gültiges
Frontmatter, Hauptsektionen vorhanden.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import _paths
from scripts.clustering_analysis import (
    pairwise_sim_histogram,
    simulate_threshold,
    tfidf_top_terms,
)

# Alt-Build-Artefakte (Clustering verworfen, R9) liegen archiviert.
_DATA_DIR = _paths.ARCHIVE / "02_pipeline_output"
_EMBEDDINGS_PATH = _DATA_DIR / "embeddings.parquet"
_OUTPUT_PATH = _DATA_DIR / "clustering_analysis.md"


# === Unit Tests ===============================================================


def _tiny_embeddings() -> tuple[list[str], np.ndarray]:
    """5 L2-normalisierte Mock-Embeddings (4-dim, nicht-negativ → Similarities in [0,1])."""
    rng = np.random.default_rng(42)
    raw = np.abs(rng.standard_normal((5, 4))).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return [f"D_doc{i}-S0000" for i in range(5)], raw / norms


def test_pairwise_sim_histogram_bins_cover_all_pairs() -> None:
    """Histogramm-Bins decken alle Paare ab (10 Bins, Summe = n*(n-1)/2)."""
    _, embs = _tiny_embeddings()
    hist = pairwise_sim_histogram(embs)
    n = len(embs)
    expected_pairs = n * (n - 1) // 2
    assert sum(hist.values()) == expected_pairs
    assert len(hist) == 10


def test_simulate_threshold_returns_expected_keys() -> None:
    """simulate_threshold liefert alle erwarteten Schlüssel."""
    seg_ids, embs = _tiny_embeddings()
    result = simulate_threshold(embs, seg_ids, threshold=0.7)
    for key in ("threshold", "n_clusters", "top_cluster_segs", "mean_cluster_segs", "unsorted_pct"):
        assert key in result


def test_tfidf_top_terms_skips_unsortiert() -> None:
    """C_unsortiert wird nicht in TF-IDF-Analyse einbezogen."""
    clusters = [
        {"cluster_id": "C_cluster-0001", "segment_ids": ["D_a-S0000", "D_b-S0000"]},
        {"cluster_id": "C_unsortiert", "segment_ids": ["D_c-S0000"]},
    ]
    texts = {"D_a-S0000": "hello world", "D_b-S0000": "foo bar", "D_c-S0000": "unsorted content"}
    result = tfidf_top_terms(clusters, texts)
    assert "C_cluster-0001" in result
    assert "C_unsortiert" not in result


# === Integrations-Test (echte Daten) ==========================================


@pytest.mark.skipif(
    not _EMBEDDINGS_PATH.exists(),
    reason="embeddings.parquet nicht vorhanden (Pipeline noch nicht gelaufen)",
)
def test_output_file_has_valid_frontmatter() -> None:
    """clustering_analysis.md hat gültiges YAML-Frontmatter."""
    assert _OUTPUT_PATH.exists(), "clustering_analysis.md fehlt — Skript noch nicht gelaufen"
    content = _OUTPUT_PATH.read_text(encoding="utf-8")
    assert content.startswith("---"), "Kein YAML-Frontmatter-Start"
    fm_end = content.find("---", 3)
    assert fm_end > 3, "Frontmatter-Ende fehlt"
    fm = yaml.safe_load(content[3:fm_end])
    assert fm.get("slug") == "clustering-analysis"
    assert fm.get("status") == "stable"
    assert "n_segments" in fm


@pytest.mark.skipif(
    not _OUTPUT_PATH.exists(),
    reason="clustering_analysis.md noch nicht generiert",
)
def test_output_file_has_main_sections() -> None:
    """clustering_analysis.md enthält alle 5 Hauptsektionen."""
    content = _OUTPUT_PATH.read_text(encoding="utf-8")
    for section in [
        "## 1. Pairwise-Similarity-Histogramm",
        "## 2. Cluster-Größen bei verschiedenen Thresholds",
        "## 3. Top-Themen-Wörter",
        "## 4. HDBSCAN-Trial",
        "## 5. Beobachtungen",
    ]:
        assert section in content, f"Sektion fehlt: {section}"
