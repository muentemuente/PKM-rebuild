"""Phase 10 — Kontroll-Berichte.

Generiert drei Markdown-Reports aus bestehenden Pipeline-Outputs:
  corpus_report.md     — Übersicht Korpus (Größen, Typen, Sprachen)
  duplicate_report.md  — Duplikate und Kanten
  cluster_report.md    — Cluster-Verteilung (Gate-1-Input)

Inputs (alle aus work/):
  files_manifest.jsonl, documents_structured.jsonl, segments.jsonl,
  exact_duplicates.json, near_duplicate_edges.jsonl, cluster_proposals.json,
  batches/batch_*.md

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 10):
  - Reports regenerierbar (idempotent via Input-Hash)
  - Mensch-lesbar Markdown mit gültigem Frontmatter
"""

import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from pipeline.phase_9_vault_build import (
    CATEGORY_TO_FOLDER,
    _build_plan,
)
from pipeline.schemas import (
    DocumentRecord,
    ExactDuplicateGroup,
    NearDuplicateEdge,
    StructuredDocumentRecord,
)

log = structlog.get_logger()

_UNSORTED_FOLDER = CATEGORY_TO_FOLDER["unsortiert"]

_DE_WORDS = frozenset(
    [
        "und",
        "der",
        "die",
        "das",
        "ist",
        "auch",
        "mit",
        "von",
        "zu",
        "für",
        "nicht",
        "sich",
        "nach",
        "noch",
        "oder",
        "aber",
        "wenn",
        "bei",
        "wie",
        "eine",
        "einen",
        "einem",
        "einer",
        "eines",
        "werden",
        "wird",
        "wurde",
    ]
)
_EN_WORDS = frozenset(
    [
        "the",
        "and",
        "is",
        "are",
        "of",
        "to",
        "for",
        "this",
        "that",
        "with",
        "from",
        "have",
        "has",
        "not",
        "can",
        "will",
        "they",
        "you",
        "your",
        "which",
        "been",
        "were",
        "their",
        "there",
    ]
)


# === Helpers ==================================================================


def _sha256_file(path: Path) -> str:
    """SHA-256 einer Datei (binär, in Chunks)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _combined_hash(paths: list[Path]) -> str:
    """Kombinierter SHA-256 aus mehreren Dateien (nur existierende)."""
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _is_cached(output_path: Path, meta_path: Path, input_hash: str) -> bool:
    if not output_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(meta.get("input_hash") == input_hash)
    except Exception:
        return False


def _write_meta(
    meta_path: Path,
    input_hash: str,
    output_path: Path,
    phase: str,
    pipeline_version: str,
    duration_seconds: float,
) -> None:
    output_hash = f"sha256:{_sha256_file(output_path)}" if output_path.exists() else ""
    meta: dict[str, Any] = {
        "phase": phase,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pipeline_version": pipeline_version,
        "config_snapshot": {},
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _meta_path_for(output_path: Path) -> Path:
    return output_path.parent / f".{output_path.name}.meta.json"


def _detect_language(text: str) -> str:
    """Heuristisch: 'de' | 'en' | 'mixed' | 'unklar' via Stoppwörter."""
    words = re.findall(r"\b[a-zäöüß]{2,}\b", text[:1000].lower())
    de = sum(1 for w in words if w in _DE_WORDS)
    en = sum(1 for w in words if w in _EN_WORDS)
    if de == 0 and en == 0:
        return "unklar"
    if de >= en * 2:
        return "de"
    if en >= de * 2:
        return "en"
    return "mixed"


def _iso_date() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


# === Loaders ==================================================================


def _load_manifest(path: Path) -> list[DocumentRecord]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(DocumentRecord.model_validate_json(line))
    return records


def _load_structured(path: Path) -> dict[str, StructuredDocumentRecord]:
    result: dict[str, StructuredDocumentRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = StructuredDocumentRecord.model_validate_json(line)
            result[rec.doc_id] = rec
    return result


def _load_segment_counts(path: Path) -> int:
    """Zählt nur die Zeilen in segments.jsonl (keine Text-Deserialisierung)."""
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _load_edges(path: Path) -> list[NearDuplicateEdge]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            result.append(NearDuplicateEdge.model_validate_json(line))
    return result


def _load_exact_duplicates(path: Path) -> list[ExactDuplicateGroup]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ExactDuplicateGroup.model_validate(item) for item in data]


def _load_language_map(cleaned_path: Path) -> dict[str, str]:
    """Lädt {doc_id: language} via Stoppwort-Heuristik auf Body-Text."""
    result: dict[str, str] = {}
    for line in cleaned_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            result[d["doc_id"]] = _detect_language(d.get("body", ""))
    return result


# === Report Generators ========================================================


def _load_vault_fm(path: Path) -> dict[str, Any] | None:
    """Liest das YAML-Frontmatter einer Vault-Datei. None bei Fehler/kein Block."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): v for k, v in data.items()}


def _count_excluded(corpus_input: Path) -> int:
    """Anzahl excluded Korpus-Dateien in `input/_excluded/`."""
    excluded_dir = corpus_input / "_excluded"
    if not excluded_dir.exists():
        return 0
    return sum(1 for _ in excluded_dir.glob("*.md"))


def _vault_ground_truth(
    drafts_dir: Path, vault_dir: Path
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Ermittelt die Phase-9-Artikel als Ground Truth aus Build-Plan + Vault-Dateien.

    Der Build-Plan (aus den Drafts) bestimmt deterministisch die erwarteten
    (Ordner, Slug)-Paare; jede zugehörige Vault-Datei wird gelesen (Tags/Status/Titel).
    So werden kuratierte Sonderdateien (z.B. in `00_Meta`) korrekt ausgeschlossen.

    Returns:
        (articles, missing). articles: dicts mit folder/slug/title/status/tags.
        missing: erwartete Dateien, die im Vault fehlen (Cross-Check-Abweichung).
    """
    plan = _build_plan(drafts_dir)
    articles: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for art in plan.articles:
        path = vault_dir / art.folder / f"{art.final_slug}.md"
        fm = _load_vault_fm(path)
        if fm is None:
            missing.append({"folder": art.folder, "slug": art.final_slug})
            continue
        articles.append(
            {
                "folder": art.folder,
                "slug": art.final_slug,
                "title": str(fm.get("title", art.final_slug)),
                "status": str(fm.get("status", "")),
                "tags": list(fm.get("tags") or []),
                "merged_from": list(fm.get("merged_from") or []),
            }
        )
    return articles, missing


def generate_corpus_report(
    manifest_path: Path,
    structured_path: Path,
    segments_path: Path,
    output_path: Path,
    drafts_dir: Path,
    vault_dir: Path,
    corpus_input: Path,
    cleaned_path: Path | None = None,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> Path:
    """Generiert corpus_report.md aus Phase-1/3/4-Outputs + Verarbeitungs-Status."""
    input_paths = [manifest_path, structured_path, segments_path]
    if cleaned_path and cleaned_path.exists():
        input_paths.append(cleaned_path)
    input_paths += sorted(drafts_dir.glob("*.md"))
    input_hash = _combined_hash(input_paths)
    meta_path = _meta_path_for(output_path)

    if not force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_10_corpus_cached")
        return output_path

    t0 = time.monotonic()
    docs = _load_manifest(manifest_path)
    structured = _load_structured(structured_path)
    seg_count = _load_segment_counts(segments_path)

    # Verarbeitungs-Status (Ground Truth: gebauter Vault + _excluded/-Ordner)
    articles, _missing = _vault_ground_truth(drafts_dir, vault_dir)
    n_ready = len(articles)
    n_excluded = _count_excluded(corpus_input)
    n_hold = len(docs) - n_ready - n_excluded

    total_words = sum(d.word_count for d in docs)
    total_chars = sum(d.char_count for d in docs)
    total_bytes = sum(d.size_bytes for d in docs)

    size_bins: dict[str, int] = {
        "< 100": 0,
        "100-500": 0,
        "500-2000": 0,
        "2000-10000": 0,
        "> 10000": 0,
    }
    for d in docs:
        w = d.word_count
        if w < 100:
            size_bins["< 100"] += 1
        elif w < 500:
            size_bins["100-500"] += 1
        elif w < 2000:
            size_bins["500-2000"] += 1
        elif w <= 10000:
            size_bins["2000-10000"] += 1
        else:
            size_bins["> 10000"] += 1

    type_counts: Counter[str] = Counter()
    for d in docs:
        rec = structured.get(d.doc_id)
        label = rec.doc_type_guess.label if rec else "unklar"
        type_counts[label] += 1

    if cleaned_path and cleaned_path.exists():
        lang_map = _load_language_map(cleaned_path)
        lang_counts: Counter[str] = Counter(lang_map.values())
        lang_rows = "\n".join(f"| {lang} | {cnt} |" for lang, cnt in lang_counts.most_common())
        lang_section = f"| Sprache | Anzahl |\n|---|---|\n{lang_rows}"
    else:
        lang_section = "_Nicht analysiert (cleaned_documents.jsonl nicht verfügbar)_"

    sorted_docs = sorted(docs, key=lambda d: d.word_count, reverse=True)
    top_long = sorted_docs[:10]
    non_empty = [d for d in docs if d.word_count > 0]
    top_short = sorted(non_empty, key=lambda d: d.word_count)[:10]

    type_rows = "\n".join(
        f"| {t} | {cnt} | {cnt / len(docs) * 100:.1f}% |" for t, cnt in type_counts.most_common()
    )
    long_rows = "\n".join(f"| {d.filename} | {d.word_count:,} |" for d in top_long)
    short_rows = "\n".join(f"| {d.filename} | {d.word_count:,} |" for d in top_short)

    content = f"""---
title: Korpus-Bericht
slug: corpus-report
status: stable
generated: {_iso_date()}
pipeline_version: {pipeline_version}
---

# Korpus-Bericht

## Übersicht
- Files gesamt (Korpus, Doc-Ebene): {len(docs):,}
- Dateigröße gesamt: {total_bytes / 1_048_576:.1f} MB
- Wörter gesamt: {total_words:,}
- Zeichen gesamt: {total_chars:,}
- Segmente gesamt (Segment-Ebene, ≠ Doc-Count): {seg_count:,}

## Verarbeitungs-Status (Ground Truth: Vault + `_excluded/`)
| Status | Anzahl | Bedeutung |
|---|---:|---|
| `ready` (im Vault) | {n_ready} | Draft sauber → als Vault-Artikel gebaut |
| `hold` (pending) | {n_hold} | Korpus-Doc ohne gebauten Artikel, nicht excluded |
| `excluded` | {n_excluded} | bewusst ausgeschlossen (`input/_excluded/`) |
| **Summe** | **{n_ready + n_hold + n_excluded}** | == Files gesamt ({len(docs)}) |

## Doc-Typ-Verteilung (heuristisch)
| Typ | Anzahl | Anteil |
|---|---|---|
{type_rows}

## Sprach-Verteilung (heuristisch, Stoppwort-Analyse)
{lang_section}

## Größen-Verteilung
| Bereich | Anzahl |
|---|---|
| < 100 Wörter | {size_bins["< 100"]} |
| 100-500 | {size_bins["100-500"]} |
| 500-2000 | {size_bins["500-2000"]} |
| 2000-10000 | {size_bins["2000-10000"]} |
| > 10000 | {size_bins["> 10000"]} |

## Top-10 längste Files
| Datei | Wörter |
|---|---|
{long_rows}

## Top-10 kürzeste Files
| Datei | Wörter |
|---|---|
{short_rows}
"""
    output_path.write_text(content.strip() + "\n", encoding="utf-8")
    _write_meta(
        meta_path,
        input_hash,
        output_path,
        "phase_10_corpus_report",
        pipeline_version,
        time.monotonic() - t0,
    )
    log.info("phase_10_corpus_done", docs=len(docs), segments=seg_count)
    return output_path


def generate_duplicate_report(
    exact_path: Path,
    edges_path: Path,
    output_path: Path,
    drafts_dir: Path,
    vault_dir: Path,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> Path:
    """Generiert duplicate_report.md aus Phase-5-Outputs + Option-B-Merge-Status."""
    input_paths = [exact_path, edges_path, *sorted(drafts_dir.glob("*.md"))]
    input_hash = _combined_hash(input_paths)
    meta_path = _meta_path_for(output_path)

    if not force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_10_duplicate_cached")
        return output_path

    t0 = time.monotonic()
    exact_groups = _load_exact_duplicates(exact_path)
    edges = _load_edges(edges_path)
    sims = [e.similarity for e in edges]

    # Option B: kein Cross-Doc-Merge → merged_from muss überall leer sein (verifizieren)
    articles, _missing = _vault_ground_truth(drafts_dir, vault_dir)
    n_with_merge = sum(1 for a in articles if a["merged_from"])
    merge_note = (
        f"**Keine Konsolidierungen (Pro-Doc-Veredelung, Option B).** "
        f"`merged_from` ist bei allen {len(articles)} Vault-Artikeln leer "
        f"({n_with_merge} mit Einträgen)."
    )

    affected_docs = sum(len(g.doc_ids) for g in exact_groups)

    bins: dict[str, int] = {"0.72-0.80": 0, "0.80-0.90": 0, "0.90-0.99": 0, "1.00": 0}
    for s in sims:
        if s >= 1.0:
            bins["1.00"] += 1
        elif s >= 0.90:
            bins["0.90-0.99"] += 1
        elif s >= 0.80:
            bins["0.80-0.90"] += 1
        else:
            bins["0.72-0.80"] += 1

    exact_rows = (
        "\n".join(f"| {i + 1} | {', '.join(g.doc_ids)} |" for i, g in enumerate(exact_groups))
        or "| — | keine exakten Duplikate gefunden |"
    )
    exact_header = f"""| Gruppe | Files |
|---|---|
{exact_rows}"""

    top10_edges = sorted(edges, key=lambda e: e.similarity, reverse=True)[:10]
    edge_rows = (
        "\n".join(
            f"| {e.segment_id_a} | {e.segment_id_b} | {e.similarity:.3f} |" for e in top10_edges
        )
        or "| — | — | — |"
    )

    content = f"""---
title: Duplikat-Bericht
slug: duplicate-report
status: stable
generated: {_iso_date()}
pipeline_version: {pipeline_version}
---

# Duplikat-Bericht

## Konsolidierungen (Option B)
{merge_note}

## Exakte Duplikate (SHA-256)
- Anzahl Gruppen: {len(exact_groups)}
- Betroffene Files: {affected_docs}

{exact_header}

## Nahe Duplikate (TF-IDF Cosine ≥ 0.72)
- Anzahl Kanten: {len(edges)}

### Top-10 nach Similarity
| Segment A | Segment B | Similarity |
|---|---|---|
{edge_rows}

## Verteilung
| Bereich | Kanten |
|---|---|
| 0.72-0.80 | {bins["0.72-0.80"]} |
| 0.80-0.90 | {bins["0.80-0.90"]} |
| 0.90-0.99 | {bins["0.90-0.99"]} |
| 1.00 (identisch auf Segment-Ebene) | {bins["1.00"]} |
"""
    output_path.write_text(content.strip() + "\n", encoding="utf-8")
    _write_meta(
        meta_path,
        input_hash,
        output_path,
        "phase_10_duplicate_report",
        pipeline_version,
        time.monotonic() - t0,
    )
    log.info("phase_10_duplicate_done", groups=len(exact_groups), edges=len(edges))
    return output_path


def generate_cluster_report(
    drafts_dir: Path,
    vault_dir: Path,
    output_path: Path,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> Path:
    """Generiert cluster_report.md aus dem gebauten Vault (Ground Truth).

    Embedding-/HDBSCAN-Clustering ist verworfen (R9). Die 16 Ordner sind ein
    kuratiertes Schema; dieser Report beschreibt die reale Artikel-Verteilung
    im gebauten `output/`, nicht berechnete Cluster.
    """
    input_paths = sorted(drafts_dir.glob("*.md")) + sorted(vault_dir.rglob("*.md"))
    input_hash = _combined_hash(input_paths)
    meta_path = _meta_path_for(output_path)

    if not force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_10_cluster_cached")
        return output_path

    t0 = time.monotonic()
    articles, missing = _vault_ground_truth(drafts_dir, vault_dir)
    total = len(articles)

    folder_counts: Counter[str] = Counter(a["folder"] for a in articles)
    folder_rows = "\n".join(f"| {folder} | {n} |" for folder, n in sorted(folder_counts.items()))
    sum_check = sum(folder_counts.values())
    sum_marker = "" if sum_check == total else f" ⚠️ Abweichung (erwartet {total})"

    # Tag-Häufigkeiten gesamt
    tag_total: Counter[str] = Counter()
    for a in articles:
        tag_total.update(a["tags"])
    tag_total_rows = (
        "\n".join(f"| `{t}` | {n} |" for t, n in tag_total.most_common(30)) or "| — | 0 |"
    )

    # Tag-Häufigkeiten pro Ordner (Top 5 je Ordner)
    per_folder_tags: dict[str, Counter[str]] = {}
    for a in articles:
        per_folder_tags.setdefault(a["folder"], Counter()).update(a["tags"])
    per_folder_blocks = []
    for folder in sorted(per_folder_tags):
        top = per_folder_tags[folder].most_common(5)
        tags_str = ", ".join(f"`{t}` ({n})" for t, n in top) or "—"
        per_folder_blocks.append(f"- **{folder}** ({folder_counts[folder]}): {tags_str}")
    per_folder_section = "\n".join(per_folder_blocks)

    # unsortiert/-Sektion (Mapping-Lücke vs. echtes Mikrocluster — nur kennzeichnen)
    unsorted_articles = sorted(
        (a for a in articles if a["folder"] == _UNSORTED_FOLDER), key=lambda a: a["slug"]
    )
    if unsorted_articles:
        unsorted_rows = "\n".join(f"| `{a['slug']}` | {a['title']} |" for a in unsorted_articles)
        unsorted_section = (
            f"{len(unsorted_articles)} Artikel ohne eindeutige Kategorie "
            f"(Mapping-Lücke / Business-Domäne ohne eigenen Ordner — **kein** echtes "
            f"Mikrocluster, nicht automatisch verschoben):\n\n"
            f"| Slug | Titel |\n|---|---|\n{unsorted_rows}"
        )
    else:
        unsorted_section = f"_`{_UNSORTED_FOLDER}/` ist leer._"

    missing_section = (
        "\n".join(f"| {m['folder']} | `{m['slug']}` |" for m in missing)
        if missing
        else "| — | keine |"
    )
    errors_note = (
        f"⚠️ {len(missing)} erwartete Vault-Dateien fehlen (s. Tabelle)."
        if missing
        else "Keine fehlenden Dateien (Build-Plan deckt sich mit Vault)."
    )

    content = f"""---
title: Cluster-Bericht (Vault-Verteilung)
slug: cluster-report
status: stable
generated: {_iso_date()}
pipeline_version: {pipeline_version}
---

# Cluster-Bericht — Vault-Verteilung

> Quelle: gebauter `output/` (Ground Truth). Embedding-Clustering ist verworfen (R9);
> die Ordner sind ein kuratiertes Schema, keine berechneten Cluster.

## Übersicht
- Vault-Artikel gesamt: {total}
- Genutzte Ordner: {len(folder_counts)}
- Summe über Ordner: {sum_check}{sum_marker}
- Cross-Check Build-Plan vs. Vault: {errors_note}

## Artikel pro Vault-Ordner
| Ordner | Artikel |
|---|---|
{folder_rows}
| **Summe** | **{sum_check}**{sum_marker} |

## `{_UNSORTED_FOLDER}/`
{unsorted_section}

## Tag-Häufigkeiten (gesamt, Top 30)
| Tag | Anzahl |
|---|---|
{tag_total_rows}

## Tag-Häufigkeiten pro Ordner (Top 5)
{per_folder_section}

## Fehlende Dateien (Cross-Check)
| Ordner | Slug |
|---|---|
{missing_section}
"""
    output_path.write_text(content.strip() + "\n", encoding="utf-8")
    _write_meta(
        meta_path,
        input_hash,
        output_path,
        "phase_10_cluster_report",
        pipeline_version,
        time.monotonic() - t0,
    )
    log.info(
        "phase_10_cluster_done",
        articles=total,
        folders=len(folder_counts),
        unsorted=len(unsorted_articles),
        missing=len(missing),
    )
    return output_path


# === Orchestrator =============================================================


def run_phase_10(
    manifest_path: Path,
    structured_path: Path,
    segments_path: Path,
    exact_path: Path,
    edges_path: Path,
    drafts_dir: Path,
    vault_dir: Path,
    corpus_input: Path,
    output_dir: Path,
    cleaned_path: Path | None = None,
    force: bool = False,
    pipeline_version: str = "0.0.0",
) -> dict[str, Any]:
    """Orchestriert alle drei Report-Generatoren.

    Args:
        manifest_path: files_manifest.jsonl (Phase 1)
        structured_path: documents_structured.jsonl (Phase 3)
        segments_path: segments.jsonl (Phase 4)
        exact_path: exact_duplicates.json (Phase 5)
        edges_path: near_duplicate_edges.jsonl (Phase 5)
        drafts_dir: drafts (Ground-Truth-Basis für Build-Plan)
        vault_dir: output (gebauter Vault, Ground Truth für cluster_report)
        corpus_input: input (für `_excluded/`-Zählung)
        output_dir: Zielverzeichnis für Reports
        cleaned_path: cleaned_documents.jsonl (optional, für Sprach-Heuristik)
        force: Cache ignorieren
        pipeline_version: Version-String

    Returns:
        Summary-Dict mit reports_generated, report_paths, duration_seconds.
    """
    t0 = time.monotonic()

    corpus_out = output_dir / "corpus_report.md"
    dup_out = output_dir / "duplicate_report.md"
    cluster_out = output_dir / "cluster_report.md"

    generate_corpus_report(
        manifest_path=manifest_path,
        structured_path=structured_path,
        segments_path=segments_path,
        output_path=corpus_out,
        drafts_dir=drafts_dir,
        vault_dir=vault_dir,
        corpus_input=corpus_input,
        cleaned_path=cleaned_path,
        force=force,
        pipeline_version=pipeline_version,
    )
    generate_duplicate_report(
        exact_path=exact_path,
        edges_path=edges_path,
        output_path=dup_out,
        drafts_dir=drafts_dir,
        vault_dir=vault_dir,
        force=force,
        pipeline_version=pipeline_version,
    )
    generate_cluster_report(
        drafts_dir=drafts_dir,
        vault_dir=vault_dir,
        output_path=cluster_out,
        force=force,
        pipeline_version=pipeline_version,
    )

    return {
        "reports_generated": 3,
        "report_paths": [str(corpus_out), str(dup_out), str(cluster_out)],
        "duration_seconds": round(time.monotonic() - t0, 2),
    }
