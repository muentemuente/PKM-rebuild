"""G6 — Doc-Count-Baseline-Reconcile.

Verankert die genehmigte Baseline (165 Audit-Content-Files / 6 ``_attic``) als prüfbaren
Reconcile. Die Baseline lebt an EINER Stelle (:data:`pipeline.vault_audit.DOC_COUNT_BASELINE`);
diese Tests laufen auf ``tmp_path``-Fixture-Vaults — der Live-Vault wird nicht berührt.
"""

from __future__ import annotations

from pathlib import Path

from pipeline import vault_audit as va

_FM = "---\ntitle: {t}\nslug: {t}\ntype: knowledge-article\nstatus: draft\ncategory: grundlagen\n---\n\n# {t}\n\nText.\n"


def _make_vault(root: Path, n_content: int, n_attic: int) -> Path:
    """Fixture-Vault mit ``n_content`` Audit-Content-Files + ``n_attic`` ``_attic``-Artikeln."""
    vault = root / "vault"
    (vault / "01_Grundlagen").mkdir(parents=True)
    for i in range(n_content):
        (vault / "01_Grundlagen" / f"art{i}.md").write_text(
            _FM.format(t=f"art{i}"), encoding="utf-8"
        )
    if n_attic:
        (vault / "_attic").mkdir()
        for i in range(n_attic):
            (vault / "_attic" / f"old{i}.md").write_text(_FM.format(t=f"old{i}"), encoding="utf-8")
    return vault


def test_baseline_constant_is_165_6() -> None:
    """Genehmigte Baseline: 165 Audit-Content-Files / 6 _attic — einzige Quelle."""
    assert va.DOC_COUNT_BASELINE == (165, 6)


def test_audit_vault_default_uses_baseline_constant() -> None:
    """audit_vault zieht seinen Baseline-Default aus der Konstante (kein Streu-Literal)."""
    import inspect

    default = inspect.signature(va.audit_vault).parameters["baseline"].default
    assert default == va.DOC_COUNT_BASELINE


def test_reconcile_pass_on_matching_count(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, n_content=3, n_attic=2)
    counts = va.doc_count(va.build_index(vault), vault)
    findings = va.reconcile_doc_count(counts, baseline=(3, 2))
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].message.startswith("PASS")


def test_reconcile_fail_on_content_deviation(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, n_content=4, n_attic=2)
    index = va.build_index(vault)
    counts = va.doc_count(index, vault)
    findings = va.reconcile_doc_count(
        counts, baseline=(3, 2), by_cluster=va.content_by_cluster(index)
    )
    assert any(
        f.severity == "warning" and "content" in f.message and "Δ+1" in f.message for f in findings
    )
    # Cluster-Lokalisierung mit angehängt:
    assert any("01_Grundlagen" in f.message for f in findings)


def test_reconcile_fail_on_attic_deviation(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, n_content=3, n_attic=5)
    counts = va.doc_count(va.build_index(vault), vault)
    findings = va.reconcile_doc_count(counts, baseline=(3, 2))
    assert any(
        f.severity == "warning" and "_attic" in f.message and "Δ+3" in f.message for f in findings
    )


def test_content_by_cluster_localizes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, n_content=3, n_attic=0)
    dist = va.content_by_cluster(va.build_index(vault))
    assert dist == {"01_Grundlagen": 3}
