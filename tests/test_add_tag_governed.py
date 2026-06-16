"""Tests für E1=A — `add_tag` schreibt direkt ins YAML-SSoT + hält md-Doc synchron.

Alle Tests laufen gegen tmp-Fixtures (Pfad-Parameter); der echte Repo-Zustand wird
nicht angefasst.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import manage_vocab as mv

_VOCAB_YAML = """# header-Kommentar (bleibt erhalten)
sections:
  "Web & APIs":
    - api
    - http
  Datenbanken:
    - sql

# Synonym-Map: Alias → kanonischer Tag (null = verworfen).
synonyms:
  api-design: api
  veraltet: null
"""

_TAGSYS_MD = """---
title: Tag-System
updated: 2026-01-01
---

# Tag-System

## Kern-Vokabular (3)

### Web
`api` · `http`

---

## Synonym-Map

| Qwen-Vorschlag | Canonical |
|---|---|
| `api-design` | `api` |

---

## Änderungs-Log

- 2026-01-01 — Initial
"""


@pytest.fixture
def env(tmp_path: Path) -> tuple[Path, Path]:
    yml = tmp_path / "tag_vocabulary.yaml"
    yml.write_text(_VOCAB_YAML, encoding="utf-8")
    md = tmp_path / "tag-system.md"
    md.write_text(_TAGSYS_MD, encoding="utf-8")
    return yml, md


def _sections(yml: Path) -> dict[str, list[str]]:
    return yaml.safe_load(yml.read_text(encoding="utf-8"))["sections"]


# === YAML-Schreiben ===========================================================


def test_add_tag_writes_into_yaml_ssot(env: tuple[Path, Path]) -> None:
    yml, md = env
    res = mv.add_tag(
        "observability", "Monitoring/Tracing-Thema", tag_system_path=yml, md_doc_path=md
    )
    assert res["already"] is False
    secs = _sections(yml)
    flat = {t for tags in secs.values() for t in tags}
    assert "observability" in flat
    # governed-growth-Sektion wurde angelegt
    assert "observability" in secs["Erweiterungen"]
    # Bestand unangetastet
    assert "api" in secs["Web & APIs"]


def test_add_tag_persists_reason_in_changelog(env: tuple[Path, Path]) -> None:
    yml, md = env
    mv.add_tag("observability", "Monitoring/Tracing-Thema", tag_system_path=yml, md_doc_path=md)
    data = yaml.safe_load(yml.read_text(encoding="utf-8"))
    assert "changelog" in data
    entry = next(e for e in data["changelog"] if e["tag"] == "observability")
    assert entry["reason"] == "Monitoring/Tracing-Thema"
    assert entry["date"]  # Datum gesetzt


def test_add_tag_preserves_yaml_header(env: tuple[Path, Path]) -> None:
    yml, md = env
    mv.add_tag("observability", "Grund", tag_system_path=yml, md_doc_path=md)
    assert yml.read_text(encoding="utf-8").startswith("# header-Kommentar")


def test_add_tag_syncs_md_doc(env: tuple[Path, Path]) -> None:
    yml, md = env
    res = mv.add_tag("observability", "Monitoring-Thema", tag_system_path=yml, md_doc_path=md)
    assert res["md_synced"] is True
    md_text = md.read_text(encoding="utf-8")
    assert "### Erweiterungen" in md_text
    assert "`observability`" in md_text
    assert "Monitoring-Thema" in md_text


def test_add_tag_without_md_doc_still_writes_yaml(env: tuple[Path, Path]) -> None:
    yml, _ = env
    missing_md = yml.parent / "does-not-exist.md"
    res = mv.add_tag("observability", "Grund", tag_system_path=yml, md_doc_path=missing_md)
    assert res["md_synced"] is False
    assert "observability" in {t for s in _sections(yml).values() for t in s}


# === Idempotenz / Validierung =================================================


def test_add_tag_idempotent_no_dup(env: tuple[Path, Path]) -> None:
    yml, md = env
    mv.add_tag("observability", "Grund", tag_system_path=yml, md_doc_path=md)
    res2 = mv.add_tag("observability", "Grund", tag_system_path=yml, md_doc_path=md)
    assert res2["already"] is True
    # genau einmal im YAML
    assert yml.read_text(encoding="utf-8").count("- observability") == 1


def test_add_existing_canonical_is_noop(env: tuple[Path, Path]) -> None:
    yml, md = env
    res = mv.add_tag("api", "schon da", tag_system_path=yml, md_doc_path=md)
    assert res["already"] is True


def test_add_tag_that_is_synonym_alias_raises(env: tuple[Path, Path]) -> None:
    yml, md = env
    with pytest.raises(ValueError, match="Synonym/Alias"):
        mv.add_tag("api-design", "Grund", tag_system_path=yml, md_doc_path=md)


def test_add_tag_reason_required_on_yaml(env: tuple[Path, Path]) -> None:
    yml, md = env
    with pytest.raises(ValueError, match="Begründung"):
        mv.add_tag("observability", "   ", tag_system_path=yml, md_doc_path=md)


def test_add_tag_dry_run_writes_nothing(env: tuple[Path, Path]) -> None:
    yml, md = env
    before_yml = yml.read_text(encoding="utf-8")
    before_md = md.read_text(encoding="utf-8")
    res = mv.add_tag("observability", "Grund", tag_system_path=yml, md_doc_path=md, dry_run=True)
    assert res["dry_run"] is True
    assert res["md_synced"] is True  # md existiert → würde syncen
    assert yml.read_text(encoding="utf-8") == before_yml
    assert md.read_text(encoding="utf-8") == before_md


def test_second_distinct_tag_appends_to_changelog(env: tuple[Path, Path]) -> None:
    yml, md = env
    mv.add_tag("observability", "Grund A", tag_system_path=yml, md_doc_path=md)
    mv.add_tag("tracing", "Grund B", tag_system_path=yml, md_doc_path=md)
    data = yaml.safe_load(yml.read_text(encoding="utf-8"))
    tags_logged = {e["tag"] for e in data["changelog"]}
    assert {"observability", "tracing"} <= tags_logged
    # beide in Erweiterungen-Sektion, sortiert + dedup
    assert _sections(yml)["Erweiterungen"] == ["observability", "tracing"]
