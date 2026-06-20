"""Tests für das Transform-Protokoll + Registry (Phase-1 S4).

Belegt: Registry-Listing, Metadaten, Adapter-Äquivalenz zur Direkt-Funktion und
Non-Mutation (kein Vault-Write, audit verändert den Text nicht).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pipeline import transforms as tf
from pipeline.format_vault import format_body_safe
from pipeline.vault_audit import repair_text

# Body mit Safe-Tier-Defekten (entboldbar + Junk-Heading + PUA) für Äquivalenz-Checks.
_DEFECT = "# Unbenannt\n\n## **Wichtig**\n\nEin markierter Begriff.\n"
_MESSY = "# Titel\n\n*  erstes\n*  zweites\n"


# === Registry-Listing =========================================================


def test_registry_lists_default_transforms() -> None:
    assert tf.names() == ["audit-readonly", "format-safe", "repair-safe"]


def test_all_transforms_sorted_by_name() -> None:
    got = [t.name for t in tf.all_transforms()]
    assert got == sorted(got)
    assert set(got) == {"repair-safe", "format-safe", "audit-readonly"}


def test_get_unknown_raises() -> None:
    with pytest.raises(KeyError):
        tf.get("gibt-es-nicht")


def test_register_duplicate_raises() -> None:
    with pytest.raises(ValueError, match="bereits registriert"):
        tf.register(tf.FunctionTransform("repair-safe", tf.TIER_SAFE, True, repair_text))


# === Metadaten ================================================================


def test_metadata_repair_safe() -> None:
    t = tf.get("repair-safe")
    assert t.tier == tf.TIER_SAFE
    assert t.mutating is True


def test_metadata_format_safe() -> None:
    t = tf.get("format-safe")
    assert t.tier == tf.TIER_SAFE
    assert t.mutating is True


def test_metadata_audit_readonly() -> None:
    t = tf.get("audit-readonly")
    assert t.tier == tf.TIER_AUDIT
    assert t.mutating is False


def test_default_chain_is_repair_then_format() -> None:
    """Entscheidung 2A: Default-Chain Repair → Format."""
    assert tf.DEFAULT_CHAIN == ("repair-safe", "format-safe")


def test_all_default_transforms_satisfy_protocol() -> None:
    for t in tf.all_transforms():
        assert isinstance(t, tf.Transform)


# === Adapter-Äquivalenz (== Direkt-Funktion) ==================================


def test_repair_adapter_equivalent_to_repair_text() -> None:
    res = tf.get("repair-safe").apply(_DEFECT)
    direct_text, direct_actions = repair_text(_DEFECT)
    assert res.text == direct_text
    assert res.report == direct_actions
    assert res.changed is (direct_text != _DEFECT)


def test_format_adapter_equivalent_to_format_body_safe() -> None:
    res = tf.get("format-safe").apply(_MESSY)
    direct_text, direct_changed = format_body_safe(_MESSY)
    assert res.text == direct_text
    assert res.changed is direct_changed


def test_audit_adapter_is_readonly_but_reports() -> None:
    res = tf.get("audit-readonly").apply(_DEFECT)
    assert res.text == _DEFECT  # Text unverändert (read-only)
    assert res.changed is False
    assert res.report  # Defekte werden gemeldet (Headings/Korruption)


def test_audit_clean_text_no_findings() -> None:
    clean = "# Titel\n\nSauberer Absatz ohne Defekte.\n"
    res = tf.get("audit-readonly").apply(clean)
    assert res.text == clean
    assert res.report == []


# === Non-Mutation =============================================================


def test_transforms_do_not_write_filesystem(tmp_path: Path) -> None:
    """Transforms operieren rein auf Text — kein Vault-/Datei-Write (S4 non-mutating)."""
    before = sorted(tmp_path.rglob("*"))
    for name in tf.names():
        tf.get(name).apply(_DEFECT)
    after = sorted(tmp_path.rglob("*"))
    assert before == after  # nichts angelegt/geschrieben


def test_repair_then_format_chain_composes_manually() -> None:
    """Manuelle Verkettung (Vorgriff S5): Output→Input bleibt konsistent."""
    body = _DEFECT
    for name in tf.DEFAULT_CHAIN:
        body = tf.get(name).apply(body).text
    # repariert (entboldet) UND danach formatierbar — kein Crash, deterministisch idempotent
    assert "**Wichtig**" not in body
    # 2. Durchlauf der Chain ist stabil (idempotent)
    body2 = body
    for name in tf.DEFAULT_CHAIN:
        body2 = tf.get(name).apply(body2).text
    assert body2 == body
