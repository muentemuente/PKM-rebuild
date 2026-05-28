"""Tests fuer pipeline/config.py — PipelineConfig und load_config."""

from pathlib import Path

from pipeline.config import load_config

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "pipeline" / "pipeline.config.yaml"


def test_config_loads_vault_section() -> None:
    """VaultConfig wird korrekt aus YAML geladen."""
    cfg = load_config(CONFIG_PATH)
    assert cfg.vault.use_cluster_number_prefix is True
    assert cfg.vault.generate_cluster_index is True
    assert cfg.vault.validate_wikilinks is True
    assert cfg.vault.attic_folder == "_attic"
    assert cfg.vault.unsorted_folder == "unsortiert"


def test_config_loads_tags_section() -> None:
    """TagsConfig wird korrekt aus YAML geladen."""
    cfg = load_config(CONFIG_PATH)
    assert cfg.tags.strict_vocabulary is False
    assert cfg.tags.max_tags_per_article == 10
    assert cfg.tags.min_tags_per_article == 2
    assert isinstance(cfg.tags.vocabulary_file, Path)


def test_config_loads_logging_section() -> None:
    """LoggingConfig wird korrekt aus YAML geladen."""
    cfg = load_config(CONFIG_PATH)
    assert cfg.logging.level == "INFO"
    assert cfg.logging.console_rich is True
    assert cfg.logging.file_json is True
    assert cfg.logging.log_meta_files is True
    assert isinstance(cfg.logging.file_path, Path)


def test_config_loads_memory_watch_section() -> None:
    """MemoryWatchConfig wird korrekt aus YAML geladen."""
    cfg = load_config(CONFIG_PATH)
    assert cfg.memory_watch.enabled is True
    assert cfg.memory_watch.warn_threshold_percent == 85
    assert cfg.memory_watch.pause_threshold_percent == 95
    assert cfg.memory_watch.check_interval_seconds == 30


def test_config_substitutes_data_root_in_tag_vocabulary_path() -> None:
    """${vault}-Platzhalter in tags.vocabulary_file wird aufgelöst."""
    cfg = load_config(CONFIG_PATH)
    # vocabulary_file muss absoluten Pfad enthalten, nicht den ${vault}-Platzhalter
    vocab_str = str(cfg.tags.vocabulary_file)
    assert "${vault}" not in vocab_str
    assert "tag-system.md" in vocab_str
    # Pfad muss unter dem vault-Verzeichnis liegen
    assert str(cfg.paths.vault) in vocab_str
