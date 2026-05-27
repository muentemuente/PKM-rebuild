"""Phase 1 — Inventar: Einsammeln aller Markdown-Dateien aus corpus_input.

Input:  data/01_corpus_input/**/*.md  (read-only, niemals schreiben)
Output: data/02_pipeline_output/files_manifest.jsonl
        data/02_pipeline_output/files_manifest.jsonl.meta.json

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 1):
  - Alle .md aus corpus_input erfasst (Count-Check im Log)
  - Keine doppelten doc_ids (Slug-Kollisionen → Suffix _2, _3, ...)
  - SHA-256 für jedes File berechnet
  - Idempotenz: zweimaliger Lauf mit gleichem Input → identische Outputs
"""

from pathlib import Path

import structlog

from pipeline.schemas import DocumentRecord

log = structlog.get_logger()


def run_phase_1(
    corpus_input: Path,
    output_path: Path,
    *,
    force: bool = False,
    sample: int | None = None,
) -> list[DocumentRecord]:
    """Phase 1 ausführen: Korpus inventarisieren.

    Args:
        corpus_input: Pfad zu data/01_corpus_input/ (read-only).
        output_path: Ziel-JSONL data/02_pipeline_output/files_manifest.jsonl.
        force: Wenn True, wird existierender Output ignoriert und neu berechnet.
        sample: Wenn gesetzt, werden nur N Dateien verarbeitet (Test-Modus).

    Returns:
        Liste aller DocumentRecord-Einträge.

    Raises:
        NotImplementedError: Stub — Implementierung folgt in Phase 1.
    """
    # Placeholder — Implementierung folgt
    log.warning(
        "phase_1_stub",
        phase="phase_1_inventory",
        msg="Phase 1 ist noch nicht implementiert.",
    )
    raise NotImplementedError("Phase 1 (Inventar) ist noch ein Stub. Implementierung folgt.")
