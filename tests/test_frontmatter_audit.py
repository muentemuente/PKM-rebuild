"""Tests für WP3c-8 — Frontmatter-Lücken-Audit (read-only, deterministisch).

Alle Tests auf tmp-Vault; der Live-Brain-Vault wird nie berührt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pipeline.frontmatter_audit import (
    GAP_LLM,
    GAP_MECHANICAL,
    GAP_OWNER,
    REC_COMPLETE,
    REC_MECHANICAL,
    REC_OWNER,
    REC_RESTRUCTURE,
    audit_file,
    audit_vault,
    render_report,
)


def _complete_fm(**over: Any) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "title": "T",
        "slug": "ein-slug",
        "summary": "S",
        "type": "knowledge-article",
        "doc_role": ["explanation"],
        "category": "grundlagen",
        "tags": ["t"],
        "sources_docs": ["D_x"],
        "source_chunks": ["D_x-S0"],
        "status": "draft",
        "review_status": "ai_drafted",
        "confidence": "high",
        "doc_version": "0.1.0",
        "created": "2026-06-01",
        "updated": "2026-06-01",
        "last_synthesized": "2026-06-01",
        "prompt_version": "v2",
    }
    fm.update(over)
    return fm


def _write(vault: Path, folder: str, name: str, fm: dict[str, Any] | None) -> Path:
    p = vault / folder / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if fm is None:
        p.write_text("Kein Frontmatter.\n", encoding="utf-8")
    else:
        p.write_text(
            f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\n# T\n\nBody.\n", encoding="utf-8"
        )
    return p


def _gaps(audit: Any) -> dict[str, str]:
    return {g.label: g.gap_class for g in audit.gaps}


def test_complete_file_no_gaps(tmp_path: Path) -> None:
    p = _write(tmp_path, "01_Grundlagen", "voll", _complete_fm(slug="voll"))
    audit = audit_file(p, tmp_path)
    assert audit.complete is True
    assert audit.recommendation == REC_COMPLETE
    assert audit.cluster == "01_Grundlagen"


def test_missing_field_classes(tmp_path: Path) -> None:
    """Fehlende Felder werden korrekt klassifiziert (mechanical/llm/owner)."""
    fm = _complete_fm(slug="luecken")
    for f in ("updated", "summary", "category", "doc_version", "type", "sources_docs"):
        del fm[f]
    p = _write(tmp_path, "01_Grundlagen", "luecken", fm)
    g = _gaps(audit_file(p, tmp_path))
    assert g["missing:updated"] == GAP_MECHANICAL
    assert g["missing:doc_version"] == GAP_MECHANICAL
    assert g["missing:summary"] == GAP_LLM
    assert g["missing:type"] == GAP_LLM
    assert g["missing:category"] == GAP_OWNER
    assert g["missing:sources_docs"] == GAP_OWNER


def test_invalid_enum_and_slug_gaps(tmp_path: Path) -> None:
    """Ungültige Enums + Slug/Umlaut werden erkannt & klassifiziert."""
    fm = _complete_fm(slug="Ungültig_Slug", type="kein-typ", status="kaputt", category="fantasie")
    p = _write(tmp_path, "01_Grundlagen", "boese", fm)
    g = _gaps(audit_file(p, tmp_path))
    assert g["invalid:type"] == GAP_LLM
    assert g["invalid:status"] == GAP_MECHANICAL
    assert g["invalid:category"] == GAP_OWNER
    assert g["slug:umlaut"] == GAP_MECHANICAL
    assert g["slug:format"] == GAP_MECHANICAL


def test_recommendation_priority(tmp_path: Path) -> None:
    """Empfehlung: owner > restructure > mechanical-fix."""
    # nur mechanical
    fm_m = _complete_fm(slug="mech")
    del fm_m["updated"]
    am = audit_file(_write(tmp_path, "01_Grundlagen", "mech", fm_m), tmp_path)
    assert am.recommendation == REC_MECHANICAL

    # llm-Lücke + mechanical → restructure
    fm_l = _complete_fm(slug="llm")
    del fm_l["summary"]
    del fm_l["updated"]
    al = audit_file(_write(tmp_path, "01_Grundlagen", "llm", fm_l), tmp_path)
    assert al.recommendation == REC_RESTRUCTURE

    # owner-Lücke dominiert alles
    fm_o = _complete_fm(slug="own")
    del fm_o["category"]
    del fm_o["summary"]
    ao = audit_file(_write(tmp_path, "01_Grundlagen", "own", fm_o), tmp_path)
    assert ao.recommendation == REC_OWNER


def test_no_frontmatter_is_owner(tmp_path: Path) -> None:
    p = _write(tmp_path, "01_Grundlagen", "leer", None)
    audit = audit_file(p, tmp_path)
    assert audit.recommendation == REC_OWNER
    assert any(gp.label.startswith("frontmatter:") for gp in audit.gaps)


def test_audit_vault_excludes_index_and_meta(tmp_path: Path) -> None:
    """audit_vault zählt nur Content-Files (kein _index, kein 00_Meta)."""
    _write(tmp_path, "01_Grundlagen", "echt", _complete_fm(slug="echt"))
    _write(tmp_path, "01_Grundlagen", "_index", _complete_fm(slug="idx"))  # _index → exkludiert
    _write(tmp_path, "00_Meta", "tag-system", _complete_fm(slug="tags"))  # 00_Meta → exkludiert
    result = audit_vault(tmp_path)
    assert [f.slug for f in result.files] == ["echt"]


def test_render_report_and_verdict(tmp_path: Path) -> None:
    _write(tmp_path, "01_Grundlagen", "voll", _complete_fm(slug="voll"))
    fm = _complete_fm(slug="restr")
    del fm["summary"]
    _write(tmp_path, "01_Grundlagen", "restr", fm)
    result = audit_vault(tmp_path)
    report = render_report(result, tmp_path)
    assert "Frontmatter-Lücken-Audit" in report
    assert "restr" in report
    assert "## Fazit" in report
