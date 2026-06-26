"""Tests für die deterministische NB-Report-Suite (WP-N1) in pipeline/vault_audit.py.

Pro Detektor mind. 1 Positiv- + 1 Negativ-Fixture. Die Negativ-Fälle für Dup
(Code-Block) und Boilerplate (legitime Link-Liste) sowie die ``gedanke``-Exemption
sind FP-kritisch und hier explizit abgesichert.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import vault_audit as va

_CFG = va.NBReportConfig(now=date(2026, 6, 26))


def _rules(findings: list[va.Finding]) -> set[str]:
    return {f.rule for f in findings}


# === 2.1 NB-14 Fragment =======================================================


def test_fragment_flags_short_note_without_heading_and_summary() -> None:
    fm = {"title": "X", "summary": "", "type": "knowledge-article"}
    text = "---\n...\n---\nNur ein paar Wörter ohne Struktur."
    findings = va.check_fragment("a.md", text, fm, _CFG)
    assert _rules(findings) == {"nb14-fragment"}


def test_fragment_exempts_gedanke() -> None:
    fm = {"title": "", "summary": "", "type": "gedanke"}
    text = "---\n...\n---\nKurzer Gedanke."
    assert va.check_fragment("g.md", text, fm, _CFG) == []


def test_fragment_skips_complete_short_reference() -> None:
    fm = {"title": "Ref", "summary": "Eine knappe, aber vollständige Referenz.", "type": "compact-reference"}
    text = "---\n...\n---\nKurz, aber Titel und Summary gesetzt."
    assert va.check_fragment("r.md", text, fm, _CFG) == []


# === 2.2 NB-1 Dup-Paragraph ===================================================

_DUP_PARA = "Dieser Absatz ist lang genug um als Dublette erkannt zu werden im Vault."


def test_dup_flags_repeated_paragraph() -> None:
    text = f"---\n...\n---\n{_DUP_PARA}\n\nZwischentext der anders ist und genug Wörter hat hier.\n\n{_DUP_PARA}\n"
    findings = va.check_dup_paragraph("d.md", text, _CFG)
    assert _rules(findings) == {"nb1-dup-paragraph"}


def test_dup_ignores_repeated_code_block() -> None:
    block = "```python\nprint('exakt dieselbe lange Zeile mit genug Woertern hier drin')\n```"
    text = f"---\n...\n---\n{block}\n\n{block}\n"
    assert va.check_dup_paragraph("c.md", text, _CFG) == []


def test_dup_ignores_repeated_short_list_line() -> None:
    text = "---\n...\n---\n- kurz\n\n- kurz\n"
    assert va.check_dup_paragraph("l.md", text, _CFG) == []


# === 2.3 NB-6/7 Gap-Marker ====================================================


def test_gap_flags_todo_marker() -> None:
    text = "---\n...\n---\nHier fehlt noch Inhalt. TODO ergänzen.\n"
    findings = va.check_gap_markers("t.md", text, _CFG)
    assert "nb67-gap-marker" in _rules(findings)


def test_gap_flags_empty_section() -> None:
    text = "---\n...\n---\n# Erste\n\n## Leer\n## Naechste\nInhalt hier.\n"
    findings = va.check_gap_markers("e.md", text, _CFG)
    assert any("leere Sektion" in f.message for f in findings)


def test_gap_ignores_todo_in_code_fence() -> None:
    text = "---\n...\n---\n```python\n# TODO im Code ist kein Lückenmarker\nx = 1\n```\n"
    assert va.check_gap_markers("cf.md", text, _CFG) == []


# === 2.4 NB-12 Staleness ======================================================


def test_stale_flags_old_updated() -> None:
    fm = {"updated": "2024-01-01"}
    findings = va.check_staleness("s.md", "---\n...\n---\nText.\n", fm, _CFG)
    assert any(f.rule == "nb12-stale-age" for f in findings)


def test_stale_flags_text_marker() -> None:
    fm = {"updated": "2026-06-01"}
    text = "---\n...\n---\nStand 2021 war das so dokumentiert.\n"
    findings = va.check_staleness("m.md", text, fm, _CFG)
    assert any(f.rule == "nb12-stale-marker" for f in findings)


def test_stale_skips_fresh_note_and_year_in_code() -> None:
    fm = {"updated": "2026-06-01"}
    text = "---\n...\n---\n```\nyear = 2010\n```\nFrischer Fließtext.\n"
    assert va.check_staleness("f.md", text, fm, _CFG) == []


# === 2.5 NB-2 Boilerplate =====================================================


def test_boilerplate_flags_consent_phrase() -> None:
    text = "---\n...\n---\nDiese Website verwendet Cookies, um Dienste anzubieten.\n"
    findings = va.check_boilerplate("b.md", text, _CFG)
    assert _rules(findings) == {"nb2-boilerplate"}


def test_boilerplate_flags_two_signals() -> None:
    text = "---\n...\n---\nStart | Über | Kontakt | Impressum\nWeiterlesen\n"
    findings = va.check_boilerplate("n.md", text, _CFG)
    assert _rules(findings) == {"nb2-boilerplate"}


def test_boilerplate_suppresses_legit_link_list() -> None:
    # Reine Quellen-Linkliste = nur ein Signal (link-run) → FP-Guard unterdrückt.
    text = (
        "---\n...\n---\nQuellen:\n"
        "- [[Quelle A]]\n- [[Quelle B]]\n- [[Quelle C]]\n- [[Quelle D]]\n"
    )
    assert va.check_boilerplate("q.md", text, _CFG) == []


def test_boilerplate_ignores_prose_siehe_startseite() -> None:
    text = "---\n...\n---\nSiehe Startseite für den Gesamtüberblick und weitere Details.\n"
    assert va.check_boilerplate("p.md", text, _CFG) == []


# === Toggles + Near-Dup-Verdrahtung ===========================================


def test_near_dup_off_by_default() -> None:
    assert _CFG.near_dup is False
    assert _CFG.acronyms is False


def test_near_dup_uses_embedder_when_enabled(monkeypatch) -> None:
    from pipeline import redundancy_scan

    p1 = "Ein ausreichend langer Absatz über Wissensmanagement und Vaults hier im Test mit vielen weiteren Woertern."
    p2 = "Ein voellig anderer aber ebenso langer Absatz mit ganz anderem Inhalt hier drin und noch mehr Text."

    def _fake_sim(texts: list[str], **_kw: object) -> list[list[float]]:
        n = len(texts)
        return [[0.99] * n for _ in range(n)]

    monkeypatch.setattr(redundancy_scan, "embed_similarity", _fake_sim)
    cfg = va.NBReportConfig(now=date(2026, 6, 26), near_dup=True)
    text = f"---\n...\n---\n{p1}\n\n{p2}\n"
    findings = va.check_dup_paragraph("nd.md", text, cfg)
    assert any(f.rule == "nb1-near-dup" for f in findings)


def test_disabled_groups_emit_nothing() -> None:
    cfg = va.NBReportConfig(
        fragment=False, dup=False, gap=False, stale=False, boilerplate=False
    )
    text = "---\n...\n---\nTODO. Stand 2019. verwendet Cookies.\n"
    fm = {"updated": "2020-01-01", "title": "", "summary": "", "type": "knowledge-article"}
    assert va.check_nb_report_suite("x.md", text, fm, cfg) == []
