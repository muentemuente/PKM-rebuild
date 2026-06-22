"""Konfiguration: Pydantic-Modelle und Loader für pipeline.config.yaml.

Pfad-Variablen der Form ${key} werden beim Laden aufgelöst.
"""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from pipeline import _paths

_VAR_RE = re.compile(r"\$\{(\w+)\}")


class PathsConfig(BaseModel):
    # Pfade werden zentral aus pipeline._paths injiziert (nicht mehr aus der YAML).
    # Neues Layout (input/work/drafts/review/output/archive)
    data_root: Path
    input: Path
    work: Path
    drafts: Path
    review: Path
    output: Path
    archive: Path
    config: Path
    backups: Path
    # Legacy-Aliasse (auf neues Layout gemappt) — bestehende Phasen-Dispatcher
    # nutzen diese Namen weiter; WP3 migriert sie auf die neuen Felder.
    inbox: Path  # → input
    corpus_input: Path  # → input
    pipeline_output: Path  # → work
    vault: Path  # → output


class PipelineVersionConfig(BaseModel):
    version: str
    schema_version: str


class SampleConfig(BaseModel):
    enabled: bool
    count: int


class InventoryConfig(BaseModel):
    recursive: bool
    follow_symlinks: bool
    exclude_patterns: list[str]
    include_extensions: list[str]


class IdempotencyConfig(BaseModel):
    enabled: bool
    hash_algorithm: str
    meta_file_suffix: str


class SegmentationConfig(BaseModel):
    min_words_per_segment: int
    max_words_per_segment: int
    target_words_per_segment: int
    preserve_code_blocks: bool
    preserve_tables: bool
    preserve_lists: bool
    split_by_headings: bool
    book_max_words_per_segment: int
    book_split_levels: list[int]


class ExactMatchConfig(BaseModel):
    enabled: bool


class TfIdfRedundancyConfig(BaseModel):
    enabled: bool
    threshold: float
    ngram_range: list[int]
    max_features: int
    min_df: int


class RedundancyConfig(BaseModel):
    exact_match: ExactMatchConfig
    tfidf: TfIdfRedundancyConfig


class BatchingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_input_tokens: int
    split_oversized_clusters: bool


class QwenTemperatureConfig(BaseModel):
    # stage1/stage2 entfernt (Option B, DEPRECATED — kein Cross-Doc-Merge)
    stage3_synthesis: float
    stage4_frontmatter: float


class QwenMaxTokensConfig(BaseModel):
    # stage1/stage2 entfernt (Option B, DEPRECATED)
    stage3: int
    stage4: int


class QwenRestructureConfig(BaseModel):
    """Sampler + Reasoning-Toggle **nur** für den restructure-Pfad (WP3c).

    Isoliert von Phase 8: das Reasoning-Modell denkt für die deterministische
    Re-Strukturierung unnötig (93% Reasoning-Overhead, ~28min/File). ``reasoning_effort``
    steuert das Denken; auf diesem Stack (LM Studio + qwen3.6) ist **``"none"``** der
    einzige Wert, der Reasoning real abschaltet (``reasoning_tokens=0``) — das
    ``chat_template_kwargs.enable_thinking``-Toggle und ``/no_think`` werden ignoriert
    (WP3c-3 empirisch verifiziert). ``max_tokens_*`` brauchen dann nur den Content-Bedarf.
    """

    model_config = ConfigDict(extra="ignore")

    prompt_version: str
    reasoning_effort: str
    temperature: float
    top_p: float
    presence_penalty: float
    max_tokens_stage3: int
    max_tokens_stage4: int


class QwenConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str
    model: str
    context_window: int
    prompt_version: str
    json_mode: bool
    max_retries: int
    retry_backoff_seconds: int
    timeout_seconds: int
    temperature: QwenTemperatureConfig
    max_tokens: QwenMaxTokensConfig
    restructure: QwenRestructureConfig


class EmbeddingsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool
    model: str
    batch_size: int
    device: str
    similarity_threshold: float


class ClusteringConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_cluster_size: int
    # initial_strategy + umap_hdbscan entfernt (Embedding-Clustering verworfen, R9)


class RedundancyScanConfig(BaseModel):
    """WP2: Schwellen + Toggles der Doc-Redundanz-/Synthese-Erkennung (Detection only)."""

    model_config = ConfigDict(extra="ignore")

    tfidf_threshold: float  # near-dup (lexikalisch)
    embedding_dup_threshold: float  # semantische Dublette (Embedding hoch, TF-IDF niedrig)
    embedding_thematic_low: float  # Untergrenze thematisches Mittelband
    synthesis_min_members: int  # Synthese-Kandidat: Komponente >= N Docs
    use_embeddings: bool  # False = nur Hash + TF-IDF (Fallback ohne mpnet)
    qwen_evaluate: bool  # optionale Qwen-Paar-Bewertung (Default aus)


class StructureConfig(BaseModel):
    extract_headings: bool
    extract_code_blocks: bool
    extract_tables: bool
    extract_links: bool
    extract_images: bool
    guess_doc_type: bool
    book_word_threshold: int


class NormalizationConfig(BaseModel):
    target_encoding: str
    line_endings: str
    tab_replacement: str
    max_blank_lines: int
    strip_trailing_whitespace: bool
    parse_frontmatter: bool


class VaultConfig(BaseModel):
    use_cluster_number_prefix: bool
    generate_cluster_index: bool
    validate_wikilinks: bool
    attic_folder: str
    unsorted_folder: str
    unsorted_warn_threshold: int = 10  # build-vault warnt, wenn 17_unsortiert > diesem Wert
    repair_on_build: bool = True  # S1/G1: Safe-Tier-repair_text am Body-Chokepoint (Phase 9)
    format_on_build: bool = True  # S2/G2: safe-tier-mdformat NACH repair am Body-Chokepoint
    audit_on_build: bool = True  # S3/G4: read-only Audit-Pass über output/ nach dem Build


class TagsConfig(BaseModel):
    vocabulary_file: Path
    strict_vocabulary: bool
    max_tags_per_article: int
    min_tags_per_article: int


class LoggingConfig(BaseModel):
    level: str
    console_rich: bool
    file_json: bool
    file_path: Path
    log_meta_files: bool


class MemoryWatchConfig(BaseModel):
    enabled: bool
    warn_threshold_percent: int
    pause_threshold_percent: int
    check_interval_seconds: int


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: PathsConfig
    pipeline: PipelineVersionConfig
    sample: SampleConfig
    inventory: InventoryConfig
    idempotency: IdempotencyConfig
    normalization: NormalizationConfig
    structure: StructureConfig
    segmentation: SegmentationConfig
    redundancy: RedundancyConfig
    redundancy_scan: RedundancyScanConfig
    embeddings: EmbeddingsConfig
    clustering: ClusteringConfig
    batching: BatchingConfig
    qwen: QwenConfig
    vault: VaultConfig
    tags: TagsConfig
    logging: LoggingConfig
    memory_watch: MemoryWatchConfig


def _substitute_vars(text: str, context: dict[str, str]) -> str:
    """Ersetzt ${key}-Platzhalter durch Werte aus context."""

    def replacer(m: re.Match[str]) -> str:
        return context.get(m.group(1), m.group(0))

    return _VAR_RE.sub(replacer, text)


def _paths_context() -> dict[str, str]:
    """Baut den Pfad-Kontext zentral aus ``pipeline._paths`` (Single Source of Truth).

    Enthält neue Layout-Namen + Legacy-Aliasse (gemappt), damit sowohl
    ``${work}`` als auch ``${pipeline_output}`` in der YAML auflösbar bleiben.
    """
    return {
        "data_root": str(_paths.PIPELINE_ROOT),
        "input": str(_paths.INPUT),
        "work": str(_paths.WORK),
        "drafts": str(_paths.DRAFTS),
        "review": str(_paths.REVIEW),
        "output": str(_paths.OUTPUT),
        "archive": str(_paths.ARCHIVE),
        "config": str(_paths.CONFIG),
        "backups": str(_paths.BACKUPS),
        # Legacy-Aliasse
        "inbox": str(_paths.INPUT),
        "corpus_input": str(_paths.INPUT),
        "pipeline_output": str(_paths.WORK),
        "vault": str(_paths.OUTPUT),
    }


def _substitute_str_values(raw: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    """Ersetzt ${key}-Platzhalter in allen String-Werten einer Sektion (nicht rekursiv)."""
    return {k: _substitute_vars(v, context) if isinstance(v, str) else v for k, v in raw.items()}


def load_config(config_path: Path) -> PipelineConfig:
    """Lädt pipeline.config.yaml, löst Pfad-Variablen auf und gibt PipelineConfig zurück.

    Args:
        config_path: Pfad zur pipeline.config.yaml (absolut oder relativ zu CWD).

    Returns:
        Validierte PipelineConfig-Instanz.

    Raises:
        FileNotFoundError: Wenn die Config-Datei nicht existiert.
        pydantic.ValidationError: Bei ungültiger Konfiguration.
    """
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # Pfade kommen zentral aus pipeline._paths (nicht aus der YAML — diese hat keinen
    # paths-Block mehr). Das gilt auch für die ${var}-Substitution in tags/logging.
    paths_context = _paths_context()
    raw["paths"] = paths_context
    # ${var}-Substitution für Sektionen mit Pfad-Referenzen
    for section in ("tags", "logging"):
        if section in raw and isinstance(raw[section], dict):
            raw[section] = _substitute_str_values(raw[section], paths_context)
    return PipelineConfig.model_validate(raw)
