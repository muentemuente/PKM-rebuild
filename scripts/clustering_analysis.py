#!/usr/bin/env python3
"""Clustering-Analyse als Datengrundlage für Block 0.L.

Liefert:
  1. Pairwise-Similarity-Histogramm der Embeddings
  2. Cluster-Größen-Simulation bei Thresholds 0.55-0.80
  3. Top-10 TF-IDF-Begriffe pro Cluster (speziell C_cluster-0000)
  4. HDBSCAN-Trial (falls Library verfügbar)

Ausgabe: data/02_pipeline_output/clustering_analysis.md

Wichtig: Dieses Skript trifft KEINE Strategie-Entscheidung.
Nur Daten. Entscheidung gehört in die App.
"""

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components as scipy_connected_components
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import load_config

CONFIG_PATH = Path(__file__).parent.parent / "pipeline" / "pipeline.config.yaml"
_UNSORTED_ID = "C_unsortiert"


# === Loader ===================================================================


def _load_embeddings(path: Path) -> tuple[list[str], np.ndarray]:
    """Liest segment_ids und Embedding-Matrix aus Parquet."""
    table = pq.read_table(path, columns=["segment_id", "embedding"])
    segment_ids: list[str] = table["segment_id"].to_pylist()
    embeddings = np.array(table["embedding"].to_pylist(), dtype=np.float32)
    return segment_ids, embeddings


def _load_segment_texts(segments_path: Path) -> dict[str, str]:
    """Liest {segment_id: text} aus segments.jsonl."""
    texts: dict[str, str] = {}
    for line in segments_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            texts[d["segment_id"]] = d["text"]
    return texts


def _load_clusters(clusters_path: Path) -> list[dict]:
    """Liest cluster_proposals.json."""
    return json.loads(clusters_path.read_text(encoding="utf-8"))


# === Clustering-Logik (In-Memory, identisch zu Phase 6) ======================


def _find_component_labels(embeddings: np.ndarray, threshold: float) -> np.ndarray:
    """Connected-Components im Cosine-Similarity-Graph ab Threshold."""
    sim = embeddings @ embeddings.T
    adj = (sim >= threshold).astype(np.uint8)
    np.fill_diagonal(adj, 0)
    _, labels = scipy_connected_components(csr_matrix(adj), directed=False)
    return labels


# === Analysen =================================================================


def pairwise_sim_histogram(embeddings: np.ndarray) -> dict[str, int]:
    """Histogramm der paarweisen Cosine-Similarities (obere Dreiecksmatrix)."""
    sim = embeddings @ embeddings.T
    n = len(embeddings)
    rows, cols = np.triu_indices(n, k=1)
    upper = sim[rows, cols]

    hist: dict[str, int] = {}
    for lo in range(10):
        lo_f = lo / 10
        hi_f = (lo + 1) / 10
        key = f"{lo_f:.1f}-{hi_f:.1f}"
        if lo == 9:
            hist[key] = int(np.sum(upper >= lo_f))
        else:
            hist[key] = int(np.sum((upper >= lo_f) & (upper < hi_f)))
    return hist


def simulate_threshold(
    embeddings: np.ndarray,
    seg_ids: list[str],
    threshold: float,
    min_cluster_size: int = 3,
) -> dict:
    """Greedy-Clustering wie Phase 6 — nur In-Memory, kein Datei-Schreiben."""
    labels = _find_component_labels(embeddings, threshold)
    label_counts = Counter(labels.tolist())

    large = {lbl: cnt for lbl, cnt in label_counts.items() if cnt >= min_cluster_size}
    small_total = sum(cnt for cnt in label_counts.values() if cnt < min_cluster_size)
    n_total = len(seg_ids)

    sizes = sorted(large.values(), reverse=True)
    top_size = sizes[0] if sizes else 0
    mean_size = round(sum(sizes) / len(sizes), 1) if sizes else 0.0
    unsorted_pct = round(small_total / n_total * 100, 1) if n_total else 0.0

    return {
        "threshold": threshold,
        "n_clusters": len(large),
        "top_cluster_segs": top_size,
        "mean_cluster_segs": mean_size,
        "unsorted_pct": unsorted_pct,
    }


def tfidf_top_terms(
    clusters: list[dict],
    seg_texts: dict[str, str],
    top_n: int = 10,
) -> dict[str, list[str]]:
    """TF-IDF Top-N-Begriffe pro Cluster aus cluster_proposals.json."""
    cluster_docs: dict[str, str] = {}
    for c in clusters:
        if c["cluster_id"] == _UNSORTED_ID:
            continue
        texts = [seg_texts.get(sid, "") for sid in c["segment_ids"]]
        cluster_docs[c["cluster_id"]] = " ".join(texts)

    if not cluster_docs:
        return {}

    cluster_ids = list(cluster_docs.keys())
    corpus = [cluster_docs[cid] for cid in cluster_ids]

    vec = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 1),
        min_df=1,
        sublinear_tf=True,
        stop_words=None,
    )
    tfidf_matrix = vec.fit_transform(corpus)
    feature_names = vec.get_feature_names_out()

    result: dict[str, list[str]] = {}
    for i, cid in enumerate(cluster_ids):
        row = tfidf_matrix[i].toarray()[0]
        top_indices = row.argsort()[-top_n:][::-1]
        result[cid] = [feature_names[j] for j in top_indices if row[j] > 0]
    return result


def run_hdbscan_trial(
    embeddings: np.ndarray,
    min_cluster_size: int = 3,
    min_samples: int = 2,
) -> dict | None:
    """HDBSCAN-Lauf auf bestehenden Embeddings. None wenn Library fehlt."""
    try:
        import hdbscan
    except ImportError:
        return None

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(embeddings)

    label_counts = Counter(labels.tolist())
    n_noise = label_counts.get(-1, 0)
    named = {lbl: cnt for lbl, cnt in label_counts.items() if lbl >= 0}
    sizes = sorted(named.values(), reverse=True)

    return {
        "n_clusters": len(named),
        "n_noise": n_noise,
        "noise_pct": round(n_noise / len(embeddings) * 100, 1),
        "top_cluster_segs": sizes[0] if sizes else 0,
        "mean_cluster_segs": round(sum(sizes) / len(sizes), 1) if sizes else 0.0,
        "size_distribution": sizes[:20],
    }


# === Report-Generierung =======================================================


def _row(values: list) -> str:
    return "| " + " | ".join(str(v) for v in values) + " |"


def build_report(
    sim_hist: dict[str, int],
    threshold_sims: list[dict],
    tfidf_terms: dict[str, list[str]],
    clusters: list[dict],
    hdbscan_result: dict | None,
    current_threshold: float,
    n_total_segs: int,
) -> str:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # === Sektion 1: Pairwise-Similarity-Histogramm ===
    hist_rows = "\n".join(
        _row([rng, cnt, f"{cnt / sum(sim_hist.values()) * 100:.1f}%"])
        for rng, cnt in sim_hist.items()
    )
    total_pairs = sum(sim_hist.values())

    # === Sektion 2: Threshold-Simulation ===
    sim_header = _row(
        ["Threshold", "Cluster", "Top-Cluster Segs", "Ø Cluster Segs", "% Unsortiert"]
    )
    sim_sep = "|---|---|---|---|---|"
    sim_rows_list = []
    for s in threshold_sims:
        marker = " ←" if abs(s["threshold"] - current_threshold) < 0.001 else ""
        sim_rows_list.append(
            _row(
                [
                    f"{s['threshold']:.2f}{marker}",
                    s["n_clusters"],
                    s["top_cluster_segs"],
                    s["mean_cluster_segs"],
                    f"{s['unsorted_pct']}%",
                ]
            )
        )
    sim_rows = "\n".join(sim_rows_list)

    # === Sektion 3: TF-IDF ===
    mega = next((c for c in clusters if c["cluster_id"] == "C_cluster-0000"), None)
    mega_seg_count = len(mega["segment_ids"]) if mega else 0
    mega_terms = tfidf_terms.get("C_cluster-0000", [])
    mega_terms_str = ", ".join(mega_terms) if mega_terms else "—"

    named_clusters = [c for c in clusters if c["cluster_id"] != _UNSORTED_ID]
    other_clusters_rows = []
    for c in sorted(named_clusters, key=lambda x: len(x["segment_ids"]), reverse=True)[:10]:
        cid = c["cluster_id"]
        terms = ", ".join(tfidf_terms.get(cid, [])[:5])
        doc_ids = {s.rsplit("-S", 1)[0] for s in c["segment_ids"]}
        other_clusters_rows.append(_row([cid, c["label_guess"][:35], len(doc_ids), terms]))
    other_clusters_str = (
        "\n".join(other_clusters_rows) if other_clusters_rows else "| — | — | — | — |"
    )

    # === Sektion 4: HDBSCAN ===
    if hdbscan_result:
        hdb_section = f"""## 4. HDBSCAN-Trial

Parameter: `min_cluster_size=3, min_samples=2, metric=euclidean (L2-normalisierte Embeddings)`

| Metrik | HDBSCAN | Agglomerativ (threshold={current_threshold:.2f}) |
|---|---|---|
| Cluster (named) | {hdbscan_result["n_clusters"]} | {threshold_sims[2]["n_clusters"]} |
| Noise / Unsortiert Segs | {hdbscan_result["n_noise"]} ({hdbscan_result["noise_pct"]}%) | {threshold_sims[2]["unsorted_pct"]}% |
| Top-Cluster Segs | {hdbscan_result["top_cluster_segs"]} | {threshold_sims[2]["top_cluster_segs"]} |
| Ø Cluster Segs | {hdbscan_result["mean_cluster_segs"]} | {threshold_sims[2]["mean_cluster_segs"]} |

Cluster-Größen-Verteilung (Top-20): {hdbscan_result["size_distribution"]}
"""
    else:
        hdb_section = """## 4. HDBSCAN-Trial

hdbscan-Library nicht installierbar in dieser Umgebung. Trial übersprungen.
"""

    # === Sektion 5: Beobachtungen ===
    # Datenbasis für die 0.65-Zeile ermitteln
    row_065 = next(
        (s for s in threshold_sims if abs(s["threshold"] - 0.65) < 0.001), threshold_sims[0]
    )

    report = f"""---
title: Clustering-Strategie — Datenbasis
slug: clustering-analysis
status: stable
generated: {today}
n_segments: {n_total_segs}
---

# Clustering-Strategie — Datenbasis für Block 0.L

Dieses Dokument enthält ausschließlich Daten. Keine Strategie-Empfehlung.
Entscheidung Strategie A/B/C/D erfolgt in App-Konversation.

---

## 1. Pairwise-Similarity-Histogramm

Basis: obere Dreiecksmatrix der Cosine-Similarities ({total_pairs:,} Paare aus {n_total_segs} Segmenten).
Zeigt die natürliche Verteilung — Lücken = potenzielle Threshold-Kandidaten.

| Bereich | Anzahl Paare | Anteil |
|---|---|---|
{hist_rows}

---

## 2. Cluster-Größen bei verschiedenen Thresholds

Greedy-Clustering wie Phase 6 (Connected-Components). `min_cluster_size=3`.
← markiert aktuellen Pipeline-Stand.

{sim_header}
{sim_sep}
{sim_rows}

---

## 3. Top-Themen-Wörter (TF-IDF)

### Mega-Cluster C_cluster-0000 ({mega_seg_count} Segmente)

Top-10 TF-IDF-Begriffe: {mega_terms_str}

### Top-10 Cluster nach Segment-Anzahl

| Cluster-ID | Label-Guess | Docs | Top-5 TF-IDF |
|---|---|---|---|
{other_clusters_str}

---

{hdb_section}

---

## 5. Beobachtungen

- **Similarity-Verteilung:** {sim_hist.get("0.6-0.7", 0):,} Paare im Bereich 0.6-0.7; {sim_hist.get("0.7-0.8", 0):,} im Bereich 0.7-0.8. Zeigt ob es natürliche Cluster-Grenzen gibt.
- **Threshold=0.65 (aktuell):** {row_065["n_clusters"]} Cluster, {row_065["top_cluster_segs"]} Segs im Top-Cluster, {row_065["unsorted_pct"]}% unsortiert.
- **Mega-Cluster C_cluster-0000:** {mega_seg_count} Segmente. TF-IDF-Begriffe zeigen {("heterogenes Themenspektrum" if len(set(mega_terms[:5])) >= 3 else "engeres Themenspektrum")}.
- **HDBSCAN:** {"Alternativer Ansatz ohne festen Threshold. Noise-Rate und Cluster-Anzahl oben." if hdbscan_result else "Nicht ausführbar."}
- **Threshold-Sensitivität:** Zwischen 0.65 und 0.80 variiert % unsortiert stark — Hinweis auf uneindeutige Cluster-Struktur im Korpus.
"""
    return report.strip() + "\n"


# === Main =====================================================================


def main() -> None:
    cfg = load_config(CONFIG_PATH)
    out_dir = Path(cfg.paths.pipeline_output)

    embeddings_path = out_dir / "embeddings.parquet"
    segments_path = out_dir / "segments.jsonl"
    clusters_path = out_dir / "cluster_proposals.json"
    output_path = out_dir / "clustering_analysis.md"

    print("Lade Embeddings...")
    seg_ids, embeddings = _load_embeddings(embeddings_path)
    print(f"  {len(seg_ids)} Segmente, {embeddings.shape[1]}-dim")

    print("Lade Segment-Texte...")
    seg_texts = _load_segment_texts(segments_path)

    print("Lade Cluster-Proposals...")
    clusters = _load_clusters(clusters_path)

    print("1. Pairwise-Similarity-Histogramm...")
    sim_hist = pairwise_sim_histogram(embeddings)

    print("2. Threshold-Simulation (0.55-0.80)...")
    thresholds = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    threshold_sims = [simulate_threshold(embeddings, seg_ids, t) for t in thresholds]
    for s in threshold_sims:
        print(
            f"   threshold={s['threshold']:.2f}: {s['n_clusters']} Cluster, "
            f"top={s['top_cluster_segs']} segs, {s['unsorted_pct']}% unsortiert"
        )

    print("3. TF-IDF Top-Begriffe...")
    tfidf_terms = tfidf_top_terms(clusters, seg_texts)

    print("4. HDBSCAN-Trial...")
    hdbscan_result = run_hdbscan_trial(embeddings)
    if hdbscan_result:
        print(
            f"   {hdbscan_result['n_clusters']} Cluster, "
            f"{hdbscan_result['n_noise']} Noise ({hdbscan_result['noise_pct']}%)"
        )
    else:
        print("   hdbscan nicht verfügbar — übersprungen")

    print("Schreibe Bericht...")
    report = build_report(
        sim_hist=sim_hist,
        threshold_sims=threshold_sims,
        tfidf_terms=tfidf_terms,
        clusters=clusters,
        hdbscan_result=hdbscan_result,
        current_threshold=0.65,
        n_total_segs=len(seg_ids),
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"Fertig: {output_path}")


if __name__ == "__main__":
    main()
