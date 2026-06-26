"""WP-A1b — D4-Mass-Write der deterministischen ``keyphrases`` (additiv, reversibel).

Schreibt **ausschließlich** den ``keyphrases``-Key additiv ins Frontmatter einer
Bestands-Note — **byte-stabil** für alles andere (kein Body, keine Reformatierung,
kein anderes Feld). Frontmatter-chirurgisch (Text-Insert vor dem schließenden
``---``), **nicht** über einen YAML-Roundtrip (der würde bestehende Keys umformatieren).

Reversibilität: der Aufrufer (CLI) snapshottet den Vault **vor** dem Write
(:func:`snapshot_vault`) — Rollback = Snapshot zurückkopieren.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

#: Frontmatter-Block am Datei-Anfang: (öffnendes ---, FM-Body inkl. \n, schließendes ---).
_FM_BLOCK_RE = re.compile(r"\A(---\r?\n)(.*?\n)(---[ \t]*\r?\n)", re.DOTALL)


class BackfillError(RuntimeError):
    """Sauberer Fehler bei nicht-additiv-schreibbarer Note (kein Write erfolgt)."""


def _render_keyphrases_block(phrases: list[str]) -> str:
    """Rendert den ``keyphrases``-YAML-Block (2-Space-Listen-Stil wie der Vault).

    Jede Phrase wird über ``yaml.safe_dump`` einzeln scalar-escaped (robust gegen
    ``:``/Anführungszeichen/Umlaute), danach als ``  - <scalar>`` eingerückt.
    """
    lines = ["keyphrases:"]
    for phrase in phrases:
        scalar = yaml.safe_dump(phrase, allow_unicode=True, default_flow_style=False)
        scalar = scalar.strip().splitlines()[0]  # erste Zeile = der escapte Scalar
        lines.append(f"  - {scalar}")
    return "\n".join(lines) + "\n"


def add_keyphrases_to_frontmatter(text: str, phrases: list[str]) -> str:
    """Fügt den ``keyphrases``-Block additiv ins Frontmatter ein (byte-stabil sonst).

    Raises:
        BackfillError: wenn kein Frontmatter existiert oder ``keyphrases`` bereits
            gesetzt ist (additiv-only — kein Overwrite, das wäre Owner-Territorium).
    """
    match = _FM_BLOCK_RE.match(text)
    if not match:
        raise BackfillError("kein parsebares Frontmatter am Datei-Anfang")
    open_d, fm_body, close_d = match.groups()
    if re.search(r"(?m)^keyphrases:", fm_body):
        raise BackfillError("keyphrases bereits vorhanden — additiv-only, kein Overwrite")
    block = _render_keyphrases_block(phrases)
    return open_d + fm_body + block + close_d + text[match.end() :]


def verify_additive(original: str, written: str, phrases: list[str]) -> None:
    """Verifiziert: Diff **ausschließlich** ``keyphrases``, Rest byte-stabil, Roundtrip ok.

    Raises:
        BackfillError: bei jeder Abweichung (kein-additiv / Body geändert / Parse-Fail).
    """
    # 1) Entfernt man den keyphrases-Block aus ``written``, muss exakt ``original`` bleiben.
    stripped = _strip_keyphrases_block(written)
    if stripped != original:
        raise BackfillError("Diff nicht ausschließlich keyphrases (Rest nicht byte-stabil)")
    # 2) Semantischer Roundtrip: Frontmatter parst, keyphrases == erwartete Liste.
    fm_match = _FM_BLOCK_RE.match(written)
    if not fm_match:
        raise BackfillError("geschriebenes Frontmatter nicht mehr parsebar")
    data = yaml.safe_load(fm_match.group(2))
    if not isinstance(data, dict) or data.get("keyphrases") != phrases:
        raise BackfillError("keyphrases-Roundtrip stimmt nicht mit erwarteten Phrasen überein")


def _strip_keyphrases_block(text: str) -> str:
    """Entfernt den additiv eingefügten ``keyphrases``-Block wieder (für die Diff-Probe)."""
    match = _FM_BLOCK_RE.match(text)
    if not match:
        return text
    open_d, fm_body, close_d = match.groups()
    # Block = 'keyphrases:\n' + Folge von '  - ...'-Zeilen bis zur nächsten Nicht-Item-Zeile.
    new_body = re.sub(r"(?m)^keyphrases:\n(?:  - .*\n)*", "", fm_body)
    return open_d + new_body + close_d + text[match.end() :]


def write_keyphrases(note_path: Path, phrases: list[str]) -> str:
    """Schreibt ``keyphrases`` additiv in eine Note. Returns den Original-Text (für Verify)."""
    original = note_path.read_text(encoding="utf-8")
    written = add_keyphrases_to_frontmatter(original, phrases)
    verify_additive(original, written, phrases)
    note_path.write_text(written, encoding="utf-8")
    return original


def snapshot_vault(vault_dir: Path, dest_root: Path) -> Path:
    """Kopiert den gesamten Vault read-only nach ``dest_root/<ts>`` (Pre-Write-Snapshot)."""
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_root / f"keyphrase_backfill_{ts}"
    shutil.copytree(vault_dir, dest)
    return dest


@dataclass(frozen=True)
class WriteResult:
    """Ergebnis eines Note-Writes."""

    relpath: str
    status: str  # "written" | "skip-existing" | "skip-empty"
    n_phrases: int
