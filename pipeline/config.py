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


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: PathsConfig
    pipeline: PipelineVersionConfig
    sample: SampleConfig
    inventory: InventoryConfig
    idempotency: IdempotencyConfig


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
