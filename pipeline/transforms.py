"""Transform-Protokoll + Registry (Phase-1 S4, Composability-Kern Option 2).

Vereinheitlicht die bestehenden Vault-Werkzeuge hinter **einer** Schnittstelle, damit
sie verkettbar (S5) und über einen gemeinsamen ``--apply``-Driver (S6, D4) ausführbar
werden. **Dieses Modul ist rein additiv und non-mutating** — es adaptiert vorhandene
Funktionen, schreibt nichts in den Vault und implementiert KEIN ``--apply`` (das ist S6).

Ein **Transform** bildet einen Dokument-Body deterministisch auf ein
:class:`TransformResult` ab (Body → (Body, Report)). Damit gilt:

* **chain-ready** (S5): Der Output-Body eines Transforms ist der Input des nächsten;
  :data:`DEFAULT_CHAIN` hält die kanonische Default-Reihenfolge (Entscheidung 2A:
  Repair → Format). Den Chain-Runner baut S5.
* **apply-ready** (S6): Die Metadaten ``tier`` (safe/review/audit) und ``mutating``
  erlauben dem späteren Driver zu entscheiden, was auto-anwendbar ist (safe),
  was ein Owner-Gate braucht (review) und was rein lesend ist (audit). Den Driver +
  D4-Mechanik (Snapshot/Canary/Verify/Promote) baut S6.

Registrierte Transforms (S4):

==================  =======  ========  ==================================================
name                tier     mutating  Adapter
==================  =======  ========  ==================================================
``repair-safe``     safe     True      :func:`pipeline.vault_audit.repair_text`
``format-safe``     safe     True      :func:`pipeline.format_vault.format_body_safe`
``audit-readonly``  audit    False     read-only Text-Checks aus ``pipeline.vault_audit``
==================  =======  ========  ==================================================
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pipeline.format_vault import format_body_safe
from pipeline.vault_audit import (
    check_corruption,
    check_fences,
    check_headings,
    repair_text,
)

# === Tier-Konstanten ==========================================================
#: Deterministisch/verlustfrei/idempotent → vom Driver (S6) auto-anwendbar.
TIER_SAFE = "safe"
#: Verlustbehaftet/nicht-deterministisch → nur per Owner-Gate (Patch-Vorschlag, S6).
TIER_REVIEW = "review"
#: Rein lesend (Detektion) → nie ein Write, ``mutating=False``.
TIER_AUDIT = "audit"


# === Ergebnis-Typ =============================================================


@dataclass(frozen=True)
class TransformResult:
    """Ergebnis eines Transforms auf einem Body.

    Args:
        text: Resultierender Body (bei ``audit``/No-op identisch mit dem Input).
        changed: ``True`` wenn ``text`` vom Input abweicht.
        report: Menschenlesbare Aktions-/Befund-Zeilen (leer = nichts zu melden).
    """

    text: str
    changed: bool
    report: list[str]


# === Protokoll ================================================================


@runtime_checkable
class Transform(Protocol):
    """Einheitliche Schnittstelle aller Vault-Werkzeuge (Body → :class:`TransformResult`).

    Attribute (read-only — kompatibel mit ``frozen``-Implementierungen):
        name: Eindeutiger Registry-Schlüssel (kebab-case).
        tier: :data:`TIER_SAFE` | :data:`TIER_REVIEW` | :data:`TIER_AUDIT`.
        mutating: Ob der Transform den Body verändern kann (``audit`` = False).
    """

    @property
    def name(self) -> str: ...

    @property
    def tier(self) -> str: ...

    @property
    def mutating(self) -> bool: ...

    def apply(self, text: str) -> TransformResult:
        """Wendet den Transform auf ``text`` an und liefert das Ergebnis."""
        ...


@dataclass(frozen=True)
class FunctionTransform:
    """Adapter, der eine bestehende ``str -> (str, list[str])``-Funktion als Transform kapselt.

    Adaptiert vorhandene Engine-Funktionen (kein Re-Implement) auf das einheitliche
    :class:`Transform`-Protokoll. ``changed`` wird aus dem Text-Vergleich abgeleitet,
    sodass auch Funktionen, die nur einen bool/leere Liste liefern, konsistent sind.
    """

    name: str
    tier: str
    mutating: bool
    func: Callable[[str], tuple[str, list[str]]]

    def apply(self, text: str) -> TransformResult:
        new_text, report = self.func(text)
        return TransformResult(text=new_text, changed=new_text != text, report=list(report))


# === Adapter-Funktionen =======================================================


def _format_safe_adapter(text: str) -> tuple[str, list[str]]:
    """``format_body_safe`` (text, bool) → (text, report)."""
    new_text, changed = format_body_safe(text)
    return new_text, (["mdformat safe-tier formatiert"] if changed else [])


def _audit_readonly_adapter(text: str) -> tuple[str, list[str]]:
    """Read-only Text-Audit: index-freie Detektionsregeln, Text bleibt unverändert.

    Reuse der bestehenden ``vault_audit``-Checks, die ohne Vault-Index auskommen
    (Headings, Fences, Korruption). Index-abhängige Regeln (Wikilink-Auflösung,
    Frontmatter↔SSoT, Alias/Doc-Count) bleiben dem Verzeichnis-Audit
    (``vault_audit.audit_build_output`` / ``audit_vault``) vorbehalten.
    """
    findings = [
        *check_headings("", text),
        *check_fences("", text),
        *check_corruption("", text),
    ]
    return text, [f"{f.rule}: {f.message}" for f in findings]


# === Registry =================================================================

_REGISTRY: dict[str, Transform] = {}

#: Kanonische Default-Chain (Entscheidung 2A). Vom Chain-Runner (S5) konsumiert.
DEFAULT_CHAIN: tuple[str, ...] = ("repair-safe", "format-safe")


def register(transform: Transform, *, replace: bool = False) -> None:
    """Registriert einen Transform unter seinem ``name``.

    Raises:
        ValueError: Wenn der Name bereits belegt ist und ``replace`` False ist.
    """
    if not replace and transform.name in _REGISTRY:
        raise ValueError(f"Transform '{transform.name}' ist bereits registriert")
    _REGISTRY[transform.name] = transform


def get(name: str) -> Transform:
    """Liefert den registrierten Transform ``name``.

    Raises:
        KeyError: Wenn kein Transform unter ``name`` registriert ist.
    """
    if name not in _REGISTRY:
        raise KeyError(f"unbekannter Transform: '{name}' (verfügbar: {', '.join(names())})")
    return _REGISTRY[name]


def names() -> list[str]:
    """Sortierte Liste aller registrierten Transform-Namen."""
    return sorted(_REGISTRY)


def all_transforms() -> list[Transform]:
    """Alle registrierten Transforms (nach Name sortiert)."""
    return [_REGISTRY[n] for n in names()]


def _register_defaults() -> None:
    """Registriert die S4-Default-Transforms (idempotent über ``replace``)."""
    register(
        FunctionTransform("repair-safe", TIER_SAFE, True, repair_text),
        replace=True,
    )
    register(
        FunctionTransform("format-safe", TIER_SAFE, True, _format_safe_adapter),
        replace=True,
    )
    register(
        FunctionTransform("audit-readonly", TIER_AUDIT, False, _audit_readonly_adapter),
        replace=True,
    )


_register_defaults()
