"""Konfiguration: Pydantic-Modelle und Loader für pipeline.config.yaml.

Pfad-Variablen der Form ${key} werden beim Laden aufgelöst.
"""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

_VAR_RE = re.compile(r"\$\{(\w+)\}")


class PathsConfig(BaseModel):
    data_root: Path
    corpus_input: Path
    pipeline_output: Path
    drafts: Path
    vault: Path
    backups: Path


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
    stage1_cluster_analysis: float
    stage2_merge_proposal: float
    stage3_synthesis: float
    stage4_frontmatter: float


class QwenMaxTokensConfig(BaseModel):
    stage1: int
    stage2: int
    stage3: int
    stage4: int


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
    initial_strategy: str


class StructureConfig(BaseModel):
    extract_headings: bool
    extract_code_blocks: bool
    extract_tables: bool
    extract_links: bool
    extract_images: bool
    guess_doc_type: bool


class NormalizationConfig(BaseModel):
    target_encoding: str
    line_endings: str
    tab_replacement: str
    max_blank_lines: int
    strip_trailing_whitespace: bool
    parse_frontmatter: bool


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: PathsConfig
    pipeline: PipelineVersionConfig
    sample: SampleConfig
    inventory: InventoryConfig
    idempotency: IdempotencyConfig
    normalization: NormalizationConfig
    structure: StructureConfig
    segmentation: SegmentationConfig
    redundancy: RedundancyConfig
    embeddings: EmbeddingsConfig
    clustering: ClusteringConfig
    batching: BatchingConfig
    qwen: QwenConfig


def _substitute_vars(text: str, context: dict[str, str]) -> str:
    """Ersetzt ${key}-Platzhalter durch Werte aus context."""

    def replacer(m: re.Match[str]) -> str:
        return context.get(m.group(1), m.group(0))

    return _VAR_RE.sub(replacer, text)


def _resolve_paths(raw: dict[str, Any]) -> dict[str, str]:
    """Löst ${variable}-Referenzen in der paths-Sektion auf.

    Verarbeitet data_root zuerst, damit nachfolgende Pfade darauf verweisen können.
    """
    context: dict[str, str] = {}
    ordered_keys = ["data_root"] + [k for k in raw if k != "data_root"]
    for key in ordered_keys:
        val = _substitute_vars(str(raw[key]), context)
        context[key] = str(Path(val).expanduser())
    return context


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
    raw["paths"] = _resolve_paths(raw["paths"])
    return PipelineConfig.model_validate(raw)
