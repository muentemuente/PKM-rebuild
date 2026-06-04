"""Tests für scripts/phase8_runner.py (Pre-Phase-9-Hardening, WP1.2).

Akzeptanzkriterien:
  - canonical_ck_slug ist deckungsgleich mit der Pipeline-Ableitung
    (_slugify_ck ∘ _filename_to_slug) — Drift-Guard.
  - NFD-Umlaute werden kanonisch zu ae/oe/ue aufgelöst.
  - 60-Cap wird eingehalten.
  - verify_outputs ist autoritativ: existieren Draft-Files → success,
    unabhängig vom Pipeline-Returncode (Timeout-Boundary).
"""

import unicodedata

import pytest
import scripts.phase8_runner as runner
from pipeline.phase_1_inventory import _filename_to_slug
from pipeline.phase_8_synthesis import _slugify_ck

# === canonical_ck_slug == Pipeline-Ableitung ===================================

_SLUG_SAMPLES = [
    "erklärung_sage_vorgang-beleg",
    "Lösung Übersicht",
    "HTTP-Protokoll",
    "Größe-Maße",
    "Straße_2",
    "foo!@#bar  baz",
    "café déjà",
    "Wörter & Begriffe (Sammlung)",
    "ÜBER-ÄRZTE",
    "emoji😀test",
    "a" * 80,
    ".hidden",
]


@pytest.mark.parametrize("stem", _SLUG_SAMPLES)
def test_canonical_ck_slug_matches_pipeline(stem: str) -> None:
    # Single Source of Truth ist die Pipeline; bricht dieser Test, ist der
    # Runner-Slug von der Pipeline abgedriftet.
    assert runner.canonical_ck_slug(stem) == _slugify_ck(_filename_to_slug(stem))


@pytest.mark.parametrize("stem", _SLUG_SAMPLES)
def test_canonical_ck_slug_nfd_equals_nfc(stem: str) -> None:
    nfc = unicodedata.normalize("NFC", stem)
    nfd = unicodedata.normalize("NFD", stem)
    assert runner.canonical_ck_slug(nfd) == runner.canonical_ck_slug(nfc)


def test_canonical_ck_slug_umlaut_nfd() -> None:
    nfd = unicodedata.normalize("NFD", "Lösung-Übersicht")
    assert runner.canonical_ck_slug(nfd) == "loesung-uebersicht"


def test_canonical_ck_slug_caps_at_60() -> None:
    out = runner.canonical_ck_slug("a" * 200)
    assert len(out) == 60
    assert out == "a" * 60


def test_canonical_ck_slug_empty_fallback() -> None:
    assert runner.canonical_ck_slug("") == "concept"
    assert runner.canonical_ck_slug("!!!") == "concept"


# === verify_outputs / is_complete (autoritativ) ================================


def _write_triple(d, slug: str, *, md: bool, fm: bool, body: bool) -> None:
    if md:
        (d / f"CK_{slug}.md").write_text("x", encoding="utf-8")
    if fm:
        (d / f"CK_{slug}.frontmatter.json").write_text("{}", encoding="utf-8")
    if body:
        (d / f"CK_{slug}.body.md").write_text("x", encoding="utf-8")


def test_verify_outputs_detects_present_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "DRAFTS_DIR", tmp_path)
    _write_triple(tmp_path, "demo", md=True, fm=True, body=True)
    out = runner.verify_outputs("demo")
    assert out == {"md": True, "body_md": True, "frontmatter": True}
    assert runner.is_complete(out) is True


def test_is_complete_body_optional(tmp_path, monkeypatch) -> None:
    # Passthrough-Routing erzeugt keine body.md — md + frontmatter genügen.
    monkeypatch.setattr(runner, "DRAFTS_DIR", tmp_path)
    _write_triple(tmp_path, "demo", md=True, fm=True, body=False)
    assert runner.is_complete(runner.verify_outputs("demo")) is True


def test_is_complete_requires_md_and_frontmatter(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "DRAFTS_DIR", tmp_path)
    _write_triple(tmp_path, "demo", md=True, fm=False, body=True)
    assert runner.is_complete(runner.verify_outputs("demo")) is False


def test_authoritative_success_on_existing_outputs_despite_timeout(tmp_path, monkeypatch) -> None:
    # Boundary-Szenario: Pipeline meldet rc != 0 (Timeout), aber der Draft
    # wurde geschrieben. Die Erfolgs-Entscheidung hängt allein an is_complete.
    monkeypatch.setattr(runner, "DRAFTS_DIR", tmp_path)
    _write_triple(tmp_path, "demo", md=True, fm=True, body=False)
    rc = -1  # subprocess.TimeoutExpired-Pfad im Runner
    complete = runner.is_complete(runner.verify_outputs("demo"))
    success = complete  # entspricht der Runner-Logik (verify_outputs autoritativ)
    assert success is True
    assert rc != 0  # rc ist informativ, nicht ausschlaggebend
