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
    assert cfg.vault.unsorted_folder == "17_unsortiert"


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


def test_config_substitutes_config_in_tag_vocabulary_path() -> None:
    """${config}-Platzhalter in tags.vocabulary_file wird aus _paths aufgelöst."""
    cfg = load_config(CONFIG_PATH)
    vocab_str = str(cfg.tags.vocabulary_file)
    assert "${config}" not in vocab_str
    # YAML-Single-Source unter config/
    assert vocab_str.endswith("config/tag_vocabulary.yaml")
    assert str(cfg.paths.config) in vocab_str


def test_config_paths_come_from_paths_module() -> None:
    """Pfade werden zentral aus pipeline._paths injiziert (neues Layout)."""
    from pipeline import _paths

    cfg = load_config(CONFIG_PATH)
    assert cfg.paths.input == _paths.INPUT
    assert cfg.paths.work == _paths.WORK
    assert cfg.paths.output == _paths.OUTPUT
    assert cfg.paths.archive == _paths.ARCHIVE
    # Legacy-Aliasse gemappt
    assert cfg.paths.pipeline_output == _paths.WORK
    assert cfg.paths.vault == _paths.OUTPUT


# Erwartetes category→Ordner-Mapping VOR dem Single-Source-Refactor (eingefrorener
# Snapshot des früheren Code-Literals). Der Identitäts-Gate beweist: das aus
# categories.yaml geladene Mapping ist nach dem Refactor unverändert.
_EXPECTED_CATEGORY_TO_FOLDER = {
    "meta": "00_Meta",
    "grundlagen": "01_Grundlagen",
    "webentwicklung": "02_Webentwicklung",
    "betriebssysteme": "03_Betriebssysteme",
    "protokolle-und-standards": "04_Protokolle-und-Standards",
    "dateitypen-und-konfiguration": "05_Dateitypen-und-Konfiguration",
    "methoden-und-prozesse": "06_Methoden-und-Prozesse",
    "best-practices": "07_Best-Practices",
    "cheatsheets": "08_Cheatsheets",
    "ki-und-semantische-systeme": "09_KI-und-Semantische-Systeme",
    "datenarchitektur-und-datenbanken": "10_Datenarchitektur-und-Datenbanken",
    "dokumentenverarbeitung-und-extraktion": "11_Dokumentenverarbeitung-und-Extraktion",
    "wissensmodellierung-und-knowledge-graphs": "12_Wissensmodellierung-und-Knowledge-Graphs",
    "visualisierung-reporting-und-design-systeme": "13_Visualisierung-Reporting-und-Design-Systeme",
    "automatisierung-scripting-und-pipelines": "14_Automatisierung-Scripting-und-Pipelines",
    "gedanken": "15_Gedanken",
    "kunst-kultur": "16_Kunst-Kultur",
    "unsortiert": "17_unsortiert",
}


def test_category_mapping_identity_after_single_source_refactor() -> None:
    """Pflicht-Gate: alle 18 Kategorien mappen vor/nach dem Refactor identisch auf denselben Ordner."""
    from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER

    assert CATEGORY_TO_FOLDER == _EXPECTED_CATEGORY_TO_FOLDER
    assert len(CATEGORY_TO_FOLDER) == 18


def test_categories_yaml_is_single_source() -> None:
    """CATEGORY_TO_FOLDER wird aus config/categories.yaml geladen (keine Code-Literal-Drift mehr)."""
    import yaml
    from pipeline import _paths
    from pipeline.phase_9_vault_build import CATEGORY_TO_FOLDER

    data = yaml.safe_load(_paths.CATEGORIES_FILE.read_text(encoding="utf-8"))
    assert data["categories"] == CATEGORY_TO_FOLDER


def test_tag_vocabulary_yaml_loads_149() -> None:
    """config/tag_vocabulary.yaml ist die Single Source (149 Tags, Synonym-Map)."""
    from pipeline import _paths
    from pipeline.vocab import load_tag_vocabulary_yaml

    vocab, synonyms = load_tag_vocabulary_yaml(_paths.TAG_VOCABULARY_FILE)
    assert len(vocab) == 149
    # Synonym-Map: Alias → kanonisch (oder None = verworfen)
    assert synonyms.get("api-design") == "api"
    assert "ai-prompts" in synonyms
    assert synonyms["ai-prompts"] is None
