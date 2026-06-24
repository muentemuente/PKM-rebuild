"""Tests für die zentrale structlog-Konfiguration (Phase A / D19)."""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
import structlog
from pipeline.config import LoggingConfig
from pipeline.logging_setup import configure_logging, reset_logging


@pytest.fixture
def _clean_logging() -> Generator[None, None, None]:
    """Setzt structlog vor und nach jedem Test zurück (kein Handler/Stream-Leak)."""
    reset_logging()
    yield
    reset_logging()


def _cfg(path: Path, *, file_json: bool = True, level: str = "INFO") -> LoggingConfig:
    return LoggingConfig(
        level=level,
        console_rich=True,
        file_json=file_json,
        file_path=path,
        log_meta_files=True,
    )


@pytest.mark.usefixtures("_clean_logging")
def test_configure_writes_structured_event_to_sink(tmp_path: Path) -> None:
    """configure_logging schreibt JSON-Events in den konfigurierten File-Sink."""
    log_path = tmp_path / "pipeline.log"
    returned = configure_logging(_cfg(log_path))
    assert returned == log_path

    structlog.get_logger().info("phase_done", phase="phase_4", count=42)
    reset_logging()  # flush + close

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "phase_done"
    assert event["phase"] == "phase_4"
    assert event["count"] == 42
    assert event["level"] == "info"
    assert "timestamp" in event


@pytest.mark.usefixtures("_clean_logging")
def test_configure_is_idempotent_no_stream_leak(tmp_path: Path) -> None:
    """Mehrfacher Aufruf ohne force dupliziert weder Stream noch Events."""
    log_path = tmp_path / "pipeline.log"
    configure_logging(_cfg(log_path))
    # Zweiter Aufruf mit anderem Pfad darf den aktiven Sink NICHT umstellen
    # (configure-once-Guard) und keinen zweiten Stream öffnen.
    other = tmp_path / "other.log"
    configure_logging(_cfg(other))

    structlog.get_logger().info("only_once")
    reset_logging()

    assert log_path.read_text(encoding="utf-8").strip()  # erster Sink aktiv
    assert not other.exists()  # zweiter Pfad nie geöffnet


@pytest.mark.usefixtures("_clean_logging")
def test_force_reconfigures_to_new_sink(tmp_path: Path) -> None:
    """force=True schließt den alten Stream und schaltet auf den neuen Sink um."""
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    configure_logging(_cfg(first))
    configure_logging(_cfg(second), force=True)

    structlog.get_logger().info("after_force")
    reset_logging()

    assert second.read_text(encoding="utf-8").strip()
    assert first.read_text(encoding="utf-8") == ""  # alter Sink leer geblieben


@pytest.mark.usefixtures("_clean_logging")
def test_level_filtering_drops_below_threshold(tmp_path: Path) -> None:
    """Level aus der Config wird respektiert (WARNING filtert INFO weg)."""
    log_path = tmp_path / "pipeline.log"
    configure_logging(_cfg(log_path, level="WARNING"))

    log = structlog.get_logger()
    log.info("dropped_info")
    log.warning("kept_warning")
    reset_logging()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "kept_warning"
