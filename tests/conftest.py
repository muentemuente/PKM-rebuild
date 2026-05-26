"""Pytest-Konfiguration und gemeinsame Fixtures."""

from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Liefert ein temporäres Verzeichnis, das nach dem Test gelöscht wird."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def fixtures_dir() -> Path:
    """Pfad zum Test-Fixtures-Verzeichnis."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_corpus_dir(fixtures_dir: Path) -> Path:
    """Pfad zum synthetischen Sample-Korpus für Pipeline-Tests."""
    return fixtures_dir / "sample_corpus"
