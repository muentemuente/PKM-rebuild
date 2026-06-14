"""Tests für scripts/publish_assets.py (WP3, add-only Asset-Merge).

Akzeptanzkriterien:
  - Neue Assets werden kopiert (nur mit apply)
  - Byte-identische Assets werden übersprungen (idempotent)
  - Vorhandene Assets mit anderem Inhalt → Konflikt, NICHT überschrieben
  - dry-run schreibt nichts
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.publish_assets import plan_publish, publish_assets


@pytest.fixture
def env(tmp_path: Path) -> tuple[Path, Path]:
    """Legt src (output/_assets) + dst (vault/_assets) an."""
    src = tmp_path / "output" / "_assets"
    dst = tmp_path / "vault" / "_assets"
    src.mkdir(parents=True)
    return src, dst


def test_new_asset_planned_but_not_copied_in_dry_run(env) -> None:
    src, dst = env
    (src / "slug__bild.png").write_bytes(b"PNG")
    plan = publish_assets(src, dst, apply=False)
    assert plan["to_copy"] == ["slug__bild.png"]
    assert not (dst / "slug__bild.png").exists()  # dry-run schreibt nichts


def test_new_asset_copied_on_apply(env) -> None:
    src, dst = env
    (src / "slug__bild.png").write_bytes(b"PNG")
    plan = publish_assets(src, dst, apply=True)
    assert plan["to_copy"] == ["slug__bild.png"]
    assert (dst / "slug__bild.png").read_bytes() == b"PNG"


def test_identical_asset_skipped(env) -> None:
    src, dst = env
    (src / "a.png").write_bytes(b"X")
    dst.mkdir(parents=True)
    (dst / "a.png").write_bytes(b"X")
    plan = publish_assets(src, dst, apply=True)
    assert plan["to_copy"] == []
    assert plan["unchanged"] == ["a.png"]


def test_conflicting_asset_not_overwritten(env) -> None:
    src, dst = env
    (src / "a.png").write_bytes(b"NEU")
    dst.mkdir(parents=True)
    (dst / "a.png").write_bytes(b"ALT")
    plan = publish_assets(src, dst, apply=True)
    assert plan["conflicts"] == ["a.png"]
    assert plan["to_copy"] == []
    # add-only: Ziel bleibt unverändert
    assert (dst / "a.png").read_bytes() == b"ALT"


def test_apply_is_idempotent(env) -> None:
    src, dst = env
    (src / "a.png").write_bytes(b"X")
    publish_assets(src, dst, apply=True)
    plan2 = publish_assets(src, dst, apply=True)
    assert plan2["to_copy"] == []
    assert plan2["unchanged"] == ["a.png"]


def test_plan_publish_does_not_write(env) -> None:
    src, dst = env
    (src / "a.png").write_bytes(b"X")
    plan_publish(src, dst)
    assert not dst.exists()
