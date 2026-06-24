"""Zentrale structlog-Konfiguration für den CLI-Bootstrap.

Genau EIN ``structlog.configure``-Aufruf, ausgelöst in ``pipeline.__main__.cli``.
Die in der Config definierte Log-Datei (``logging.file_path`` → ``work/pipeline.log``)
wird damit real geschrieben — vorher existierten zwar ``log.info(...)``-Events in den
Phasen-Modulen, aber ohne ``configure`` landeten sie nie im konfigurierten Sink (D19).

Der Konsolen-Output läuft weiterhin separat über ``rich`` (``console.print``); dieser
Sink hier ist ausschließlich die maschinenlesbare JSON-Log-Datei.

Idempotenz: ``configure_logging`` ist durch einen configure-once-Guard geschützt —
mehrfacher CLI-Aufruf (oder Test-Reentry) dupliziert weder Handler noch File-Streams.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TextIO

import structlog

from pipeline.config import LoggingConfig

# Modul-globaler Zustand für den configure-once-Guard. Der offene Stream wird
# gehalten, damit ein Re-Configure (force / Tests) ihn sauber schließen kann.
_configured: bool = False
_log_stream: TextIO | None = None


def configure_logging(cfg: LoggingConfig, *, force: bool = False) -> Path:
    """Konfiguriert structlog mit File-Sink laut Config (idempotent).

    Args:
        cfg: Die ``logging``-Sektion der PipelineConfig.
        force: Re-Konfiguration erzwingen — schließt einen offenen Stream und
            baut die Konfiguration neu auf (v.a. für Tests).

    Returns:
        Pfad der aktiven Log-Datei.
    """
    global _configured, _log_stream
    if _configured and not force:
        return cfg.file_path
    reset_logging()

    path = cfg.file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a", encoding="utf-8")
    _log_stream = stream

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if cfg.file_json
        else structlog.processors.KeyValueRenderer(key_order=["event", "level"])
    )
    level = logging.getLevelNamesMapping().get(cfg.level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )
    _configured = True
    return path


def reset_logging() -> None:
    """Setzt structlog auf Defaults zurück und schließt den File-Stream.

    Verhindert Stream-Leaks zwischen Test-Läufen und macht ``configure_logging``
    re-entrant. Nach dem Reset greift wieder der configure-once-Guard.
    """
    global _configured, _log_stream
    if _log_stream is not None:
        _log_stream.flush()
        _log_stream.close()
        _log_stream = None
    structlog.reset_defaults()
    _configured = False


def flush_logging() -> None:
    """Flusht den offenen File-Stream (ohne ihn zu schließen)."""
    if _log_stream is not None:
        _log_stream.flush()
