"""A2a — Additiver NB-Feld-Backfill (`key_points`/`open_questions`/`next_steps`).

Schließt NB-4/10/11 für **Bestands-Notes**: die drei additiven Frontmatter-Felder
werden per Live-Qwen aus dem **vollen Artikel-Body** extrahiert (dedizierter
Backfill-Prompt ``prompts/v2/backfill_nb_fields.md`` — Output enthält **nur** diese
drei Felder, kein Voll-Frontmatter, kein Body-Rewrite) und dann **byte-stabil
additiv** ins Frontmatter eingefügt.

Warum dedizierter Prompt statt v2-Stage-4-Reuse: v2-``stage4_frontmatter_json.md``
erwartet Stage-2-Konzept-Metadaten (``sources_docs``/``source_chunks``) und
generiert das **vollständige** Frontmatter — für einen reinen Feld-Backfill ohne
Synthese-Lauf ungeeignet (es würde ein Voll-FM halluzinieren, das wir verwerfen).
Der Backfill-Prompt sieht denselben vollen Body, produziert aber nur die drei Felder.

Der Insert ist frontmatter-chirurgisch (Text-Insert vor dem schließenden ``---``),
**nicht** über einen YAML-Roundtrip (der würde bestehende Keys umformatieren) — wie
:mod:`pipeline.backfill_write` (A1b). **Kein Vault-Write:** die Notes werden read-only
gelesen, das Ergebnis landet als Draft in einem isolierten ``out_dir``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from pipeline import _paths
from pipeline.config import QwenConfig
from pipeline.phase_8_synthesis import _load_prompt, _run_json_stage
from pipeline.restructure import _as_str_list

log = structlog.get_logger()

#: Die drei additiven NB-Felder (feste Reihenfolge = Insert-Reihenfolge).
NB_FIELDS = ("key_points", "open_questions", "next_steps")

#: Frontmatter-Block am Datei-Anfang: (öffnendes ---, FM-Body inkl. \n, schließendes ---).
_FM_BLOCK_RE = re.compile(r"\A(---\r?\n)(.*?\n)(---[ \t]*\r?\n)", re.DOTALL)


class BackfillError(RuntimeError):
    """Sauberer Fehler bei nicht-additiv-schreibbarer Note (kein Draft erzeugt)."""


@dataclass(frozen=True)
class NbFields:
    """Die drei extrahierten Felder (leere Listen erlaubt für open/next)."""

    key_points: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "key_points": self.key_points,
            "open_questions": self.open_questions,
            "next_steps": self.next_steps,
        }


@dataclass(frozen=True)
class BackfillResult:
    """Ergebnis eines Note-Backfills."""

    relpath: str
    slug: str
    status: str  # "drafted" | "skip-existing" | "skip-no-frontmatter"
    fields: NbFields
    draft_path: Path | None


def _build_user_message(body: str, today_str: str) -> str:
    """User-Message für den Backfill-Call — volles Datum + voller Body."""
    return f"## Aktuelles Datum: {today_str}\n\n## Artikel-Body\n\n{body}"


def extract_nb_fields(
    body: str,
    *,
    client: Any,
    qwen: QwenConfig,
    prompts_dir: Path | None = None,
    today_str: str | None = None,
) -> NbFields:
    """Extrahiert die drei NB-Felder per Qwen aus ``body`` (voller Artikel-Text).

    Nutzt den dedizierten Backfill-Prompt (nur drei Felder) + die restructure-Sampler
    (non-thinking, temp/top_p/presence aus ``qwen.restructure``). Fehlende Keys im
    Qwen-JSON → leere Liste (graceful, wie das Stage-4-Mapping).
    """
    prompts = prompts_dir if prompts_dir is not None else (_paths.REPO_ROOT / "prompts")
    today = today_str or datetime.now(tz=UTC).strftime("%Y-%m-%d")
    rc = qwen.restructure
    system_prompt = _load_prompt(prompts, rc.prompt_version, "backfill_nb_fields.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _build_user_message(body, today)},
    ]
    raw = _run_json_stage(
        client,
        qwen.model,
        messages,
        rc.temperature,
        rc.max_tokens_stage4,
        qwen.max_retries,
        qwen.retry_backoff_seconds,
        top_p=rc.top_p,
        presence_penalty=rc.presence_penalty,
        reasoning_effort=rc.reasoning_effort,
    )
    return NbFields(
        key_points=_as_str_list(raw.get("key_points")),
        open_questions=_as_str_list(raw.get("open_questions")),
        next_steps=_as_str_list(raw.get("next_steps")),
    )


def _render_list_block(key: str, items: list[str]) -> str:
    """Rendert einen YAML-Listen-Block (2-Space-Stil wie der Vault) oder ``key: []``.

    Jedes Item wird per ``yaml.safe_dump`` scalar-escaped (robust gegen ``:``/Quotes/
    Umlaute). Leere Liste → kanonisches ``key: []`` (eine Zeile).
    """
    if not items:
        return f"{key}: []\n"
    lines = [f"{key}:"]
    for item in items:
        scalar = yaml.safe_dump(item, allow_unicode=True, default_flow_style=False)
        scalar = scalar.strip().splitlines()[0]  # erste Zeile = der escapte Scalar
        lines.append(f"  - {scalar}")
    return "\n".join(lines) + "\n"


def _render_nb_blocks(fields: NbFields) -> str:
    """Die drei NB-Blöcke in fester Reihenfolge, direkt aneinandergehängt."""
    d = fields.as_dict()
    return "".join(_render_list_block(k, d[k]) for k in NB_FIELDS)


def add_nb_fields_to_frontmatter(text: str, fields: NbFields) -> str:
    """Fügt die drei NB-Felder additiv ins Frontmatter ein (byte-stabil sonst).

    Raises:
        BackfillError: wenn kein Frontmatter existiert oder **irgendeines** der drei
            Felder bereits gesetzt ist (additiv-only — kein Overwrite).
    """
    match = _FM_BLOCK_RE.match(text)
    if not match:
        raise BackfillError("kein parsebares Frontmatter am Datei-Anfang")
    open_d, fm_body, close_d = match.groups()
    for key in NB_FIELDS:
        if re.search(rf"(?m)^{key}:", fm_body):
            raise BackfillError(f"{key} bereits vorhanden — additiv-only, kein Overwrite")
    block = _render_nb_blocks(fields)
    return open_d + fm_body + block + close_d + text[match.end() :]


def _strip_nb_blocks(text: str) -> str:
    """Entfernt die additiv eingefügten NB-Blöcke wieder (für die Diff-Probe)."""
    match = _FM_BLOCK_RE.match(text)
    if not match:
        return text
    open_d, fm_body, close_d = match.groups()
    new_body = fm_body
    for key in NB_FIELDS:
        # Block = 'key: []' ODER 'key:\n' + Folge von '  - ...'-Zeilen.
        new_body = re.sub(rf"(?m)^{key}: \[\]\n", "", new_body)
        new_body = re.sub(rf"(?m)^{key}:\n(?:  - .*\n)*", "", new_body)
    return open_d + new_body + close_d + text[match.end() :]


def verify_additive(original: str, written: str, fields: NbFields) -> None:
    """Verifiziert: Diff **ausschließlich** die drei NB-Felder, Rest byte-stabil, Roundtrip ok.

    Raises:
        BackfillError: bei jeder Abweichung (nicht-additiv / Body geändert / Parse-Fail).
    """
    if _strip_nb_blocks(written) != original:
        raise BackfillError("Diff nicht ausschließlich die NB-Felder (Rest nicht byte-stabil)")
    fm_match = _FM_BLOCK_RE.match(written)
    if not fm_match:
        raise BackfillError("geschriebenes Frontmatter nicht mehr parsebar")
    data = yaml.safe_load(fm_match.group(2))
    if not isinstance(data, dict):
        raise BackfillError("geschriebenes Frontmatter parst nicht zu einem Mapping")
    expected = fields.as_dict()
    for key in NB_FIELDS:
        if data.get(key) != expected[key]:
            raise BackfillError(f"{key}-Roundtrip weicht vom erwarteten Wert ab")


def _slug_of(text: str, fallback: str) -> str:
    match = _FM_BLOCK_RE.match(text)
    if match:
        data = yaml.safe_load(match.group(2))
        if isinstance(data, dict) and data.get("slug"):
            return str(data["slug"])
    return fallback


def backfill_note_to_draft(
    note_path: Path,
    out_dir: Path,
    *,
    client: Any,
    qwen: QwenConfig,
    prompts_dir: Path | None = None,
    today_str: str | None = None,
    relpath: str | None = None,
) -> BackfillResult:
    """Liest ``note_path`` read-only, extrahiert die NB-Felder per Qwen und schreibt
    einen **additiven Draft** (Original + drei Felder) nach ``out_dir``.

    Der Vault wird **nicht** verändert. Existiert bereits eines der Felder → Skip
    (kein Overwrite, kein Qwen-Call). Kein Frontmatter → Skip.
    """
    original = note_path.read_text(encoding="utf-8")
    rel = relpath or note_path.name
    slug = _slug_of(original, note_path.stem)

    match = _FM_BLOCK_RE.match(original)
    if not match:
        log.warning("backfill_skip_no_frontmatter", note=rel)
        return BackfillResult(rel, slug, "skip-no-frontmatter", NbFields(), None)
    for key in NB_FIELDS:
        if re.search(rf"(?m)^{key}:", match.group(2)):
            log.info("backfill_skip_existing", note=rel, field=key)
            return BackfillResult(rel, slug, "skip-existing", NbFields(), None)

    body = original[match.end() :]
    fields = extract_nb_fields(
        body, client=client, qwen=qwen, prompts_dir=prompts_dir, today_str=today_str
    )
    written = add_nb_fields_to_frontmatter(original, fields)
    verify_additive(original, written, fields)

    out_dir.mkdir(parents=True, exist_ok=True)
    draft_path = out_dir / f"{slug}.md"
    draft_path.write_text(written, encoding="utf-8")
    log.info(
        "backfill_drafted",
        note=rel,
        slug=slug,
        key_points=len(fields.key_points),
        open_questions=len(fields.open_questions),
        next_steps=len(fields.next_steps),
    )
    return BackfillResult(rel, slug, "drafted", fields, draft_path)
