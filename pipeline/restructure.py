"""WP3c-1 — ``restructure-review``: review-Tier-Transform + Single-File-Draft.

Gerüst für die semantische Re-Strukturierung eines einzelnen Files via Qwen. Es
**reused** die kanonischen v1-Prompts (Stage 3 Body + Stage 4 Frontmatter) und die
injizierbare Call-Layer aus :mod:`pipeline.phase_8_synthesis` — kein Re-Implement,
kein neuer Prompt.

Invarianten (Locked Design):

* **review-Tier** — :data:`pipeline.transforms.TIER_REVIEW`, ``mutating=True``. Der
  D4-Driver (:func:`pipeline.driver.apply_to_vault`) blockiert damit jeden Auto-Write
  (``_chain_writable`` lässt nur ``safe`` zu).
* **Output = Draft** in ``drafts/`` (Default ``_paths.DRAFTS``), **nie** in den Vault.
* **Opt-in pro File** — die CLI ``pkm restructure --file <path>`` verarbeitet genau
  ein File, kein Batch, kein Cross-Doc-Merge (Option B).
* Quell-File bleibt unberührt (read-only).

Draft-Frontmatter-Kontrakt: ``review_status: ai_drafted`` · ``confidence:
<low|medium|high>`` (Vault-SSoT-Enum, ``CLAUDE.md`` §6) · ``provenance`` (Quelle-Slug,
Modell, Prompt-Version, Timestamp). Liefert Stage 4 keine valide confidence →
konservativ ``low`` + ``confidence_fallback: true``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from openai import APIConnectionError, APITimeoutError

from pipeline import _paths
from pipeline.config import QwenConfig, QwenRestructureConfig
from pipeline.phase_8_synthesis import (
    _load_prompt,
    _run_json_stage,
    _run_text_stage,
    _slugify_ck,
)
from pipeline.taxonomy import ALLOWED_CONFIDENCE
from pipeline.transforms import TIER_REVIEW, TransformResult
from pipeline.vault_audit import split_frontmatter

#: Default-Wert, wenn Stage 4 keine valide confidence liefert (konservativ).
_CONFIDENCE_FALLBACK = "low"


class RestructureError(RuntimeError):
    """Sauberer Fehler statt rohem Traceback bei einem fehlgeschlagenen Qwen-Call.

    Wird bei Timeout/Verbindungsabbruch geworfen; die CLI fängt ihn ab und gibt
    eine actionable Fehlerzeile aus. **Kein Draft** wird geschrieben, das Quell-File
    bleibt unberührt (review-Tier-Garantie).
    """


def _guarded[T](stage: str, qwen: QwenConfig, call: Callable[[], T]) -> T:
    """Führt einen Qwen-Stage-Call aus; Timeout/Connection → :class:`RestructureError`.

    Verhindert den rohen ``openai``-Traceback. Bei Fehler ist garantiert **kein**
    Draft geschrieben (der Write passiert erst nach beiden Stages) und das Quell-File
    unberührt.
    """
    try:
        return call()
    except (APITimeoutError, APIConnectionError) as exc:
        raise RestructureError(
            f"{stage} fehlgeschlagen: {type(exc).__name__} nach {qwen.timeout_seconds}s. "
            "Kein Draft geschrieben, Quell-File unberührt. "
            "Hinweis: qwen.timeout_seconds erhöhen oder Speicher prüfen "
            "(während Qwen-Läufen andere Apps schließen)."
        ) from exc


# === review-Tier-Transform ====================================================


@dataclass(frozen=True)
class RestructureReviewTransform:
    """Body → re-strukturierter Body via Qwen Stage 3 (review-Tier).

    Implementiert das :class:`pipeline.transforms.Transform`-Protokoll (Felder
    ``name``/``tier``/``mutating`` analog :class:`FunctionTransform`). ``apply``
    macht ausschließlich den Body-Schritt — die volle Draft-Erzeugung (inkl.
    Stage 4 + Frontmatter + provenance) liegt in :func:`restructure_file`.

    Der Qwen-Client wird injiziert (``client: Any`` mit
    ``.chat.completions.create``), womit der Transform ohne realen LLM mockbar ist.
    """

    client: Any
    model: str
    system_prompt: str
    temperature: float
    max_tokens: int
    max_retries: int = 2
    backoff_seconds: int = 0
    top_p: float | None = None
    presence_penalty: float | None = None
    reasoning_effort: str | None = None
    name: str = "restructure-review"
    tier: str = TIER_REVIEW
    mutating: bool = True

    def apply(self, text: str) -> TransformResult:
        """Re-strukturiert ``text`` (Body) über die kanonische Stage-3-Prompt."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": _build_restructure_user_message(text)},
        ]
        new_body = _run_text_stage(
            self.client,
            self.model,
            messages,
            self.temperature,
            self.max_tokens,
            self.max_retries,
            self.backoff_seconds,
            top_p=self.top_p,
            presence_penalty=self.presence_penalty,
            reasoning_effort=self.reasoning_effort,
        )
        report = ["restructure-review: Body via Qwen Stage-3 re-strukturiert"]
        return TransformResult(text=new_body, changed=new_body != text, report=report)


def _build_restructure_user_message(body: str) -> str:
    """Single-File-User-Message für Stage 3 (Body als Quelle, ohne Segment-Koppelung)."""
    return f"## Quell-Dokument (Body)\n\n{body}"


def _build_stage4_user_message(body: str, today_str: str) -> str:
    """Single-File-User-Message für Stage 4 (re-strukturierter Body + Datum)."""
    return f"## Aktuelles Datum: {today_str}\n\n## Artikel-Body\n\n{body}"


# === Confidence-Normalisierung ================================================


def _normalize_confidence(raw: Any) -> tuple[str, bool]:
    """Stage-4-confidence → Vault-Enum (``low|medium|high``).

    Returns:
        ``(confidence, fallback_used)`` — bei fehlendem/ungültigem Wert
        ``(_CONFIDENCE_FALLBACK, True)``.
    """
    if isinstance(raw, str) and raw.strip().lower() in ALLOWED_CONFIDENCE:
        return raw.strip().lower(), False
    return _CONFIDENCE_FALLBACK, True


# === Draft-Erzeugung ==========================================================


@dataclass(frozen=True)
class RestructureDraft:
    """Ergebnis eines :func:`restructure_file`-Laufs."""

    slug: str
    draft_path: Path
    confidence: str
    confidence_fallback: bool


def _source_slug(fm: dict[str, Any] | None, source_path: Path) -> str:
    """Slug aus Quell-Frontmatter (``slug``) oder — fehlend — aus dem Dateinamen."""
    if fm:
        slug = fm.get("slug")
        if isinstance(slug, str) and slug.strip():
            return slug.strip()
    return _slugify_ck(source_path.stem)


def _build_draft_frontmatter(
    *,
    stage4: dict[str, Any],
    confidence: str,
    fallback: bool,
    source_slug: str,
    model: str,
    prompt_version: str,
    timestamp: str,
) -> dict[str, Any]:
    """Baut das Draft-Frontmatter (deterministische Schlüssel-Reihenfolge)."""
    fm: dict[str, Any] = {
        "title": stage4.get("title", source_slug),
        "slug": source_slug,
        "type": stage4.get("type", "knowledge-article"),
        "summary": stage4.get("summary", ""),
        "review_status": "ai_drafted",
        "confidence": confidence,
        "prompt_version": prompt_version,
        "provenance": {
            "source": source_slug,
            "model": model,
            "prompt_version": prompt_version,
            "generated_at": timestamp,
        },
    }
    if fallback:
        fm["confidence_fallback"] = True
    return fm


def _render_draft(frontmatter: dict[str, Any], body: str) -> str:
    """Serialisiert Frontmatter (YAML) + Body zu einem Draft-Markdown-String."""
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"---\n{fm_yaml}---\n\n{body}\n"


def restructure_file(
    source_path: Path,
    *,
    client: Any,
    qwen: QwenConfig,
    out_dir: Path | None = None,
    prompts_dir: Path | None = None,
    timestamp: str | None = None,
) -> RestructureDraft:
    """Erzeugt aus ``source_path`` einen review-Draft (Stage 3 + Stage 4).

    Schreibt **ausschließlich** nach ``out_dir`` (Default ``_paths.DRAFTS``); das
    Quell-File bleibt unberührt; kein Vault-Write.

    Args:
        source_path: Quell-Markdown-File.
        client: Injizierter Qwen-Client (``.chat.completions.create``).
        qwen: Qwen-Konfiguration (Endpoint, Modell, Prompt-Version, Temps, Token).
        out_dir: Draft-Zielordner. ``None`` → ``_paths.DRAFTS``.
        prompts_dir: Prompt-Wurzel. ``None`` → ``_paths.REPO_ROOT / "prompts"``.
        timestamp: ISO-Timestamp für provenance (injizierbar für Determinismus).
            ``None`` → aktueller UTC-Zeitpunkt.

    Returns:
        :class:`RestructureDraft` mit Slug, Draft-Pfad, confidence und Fallback-Flag.
    """
    out = out_dir if out_dir is not None else _paths.DRAFTS
    prompts = prompts_dir if prompts_dir is not None else (_paths.REPO_ROOT / "prompts")
    ts = timestamp if timestamp is not None else datetime.now(tz=UTC).isoformat(timespec="seconds")
    rc: QwenRestructureConfig = qwen.restructure

    raw = source_path.read_text(encoding="utf-8")
    fm_text, body, _ = split_frontmatter(raw)
    source_fm = yaml.safe_load(fm_text) if fm_text else None
    if not isinstance(source_fm, dict):
        source_fm = None
    src_slug = _source_slug(source_fm, source_path)

    # Stage 3 — Body-Restructure (review-Tier-Transform), non-thinking + Sampler.
    stage3_prompt = _load_prompt(prompts, qwen.prompt_version, "stage3_synthesis.md")
    transform = RestructureReviewTransform(
        client=client,
        model=qwen.model,
        system_prompt=stage3_prompt,
        temperature=rc.temperature,
        max_tokens=rc.max_tokens_stage3,
        max_retries=qwen.max_retries,
        backoff_seconds=qwen.retry_backoff_seconds,
        top_p=rc.top_p,
        presence_penalty=rc.presence_penalty,
        reasoning_effort=rc.reasoning_effort,
    )
    restructured = _guarded("Stage 3 (Body)", qwen, lambda: transform.apply(body).text)

    # Stage 4 — Frontmatter als Confidence-Quelle, gleiche Sampler-Einstellung.
    stage4_prompt = _load_prompt(prompts, qwen.prompt_version, "stage4_frontmatter_json.md")
    stage4_messages = [
        {"role": "system", "content": stage4_prompt},
        {"role": "user", "content": _build_stage4_user_message(restructured, ts)},
    ]
    stage4_fm = _guarded(
        "Stage 4 (Frontmatter)",
        qwen,
        lambda: _run_json_stage(
            client,
            qwen.model,
            stage4_messages,
            rc.temperature,
            rc.max_tokens_stage4,
            qwen.max_retries,
            qwen.retry_backoff_seconds,
            top_p=rc.top_p,
            presence_penalty=rc.presence_penalty,
            reasoning_effort=rc.reasoning_effort,
        ),
    )
    confidence, fallback = _normalize_confidence(stage4_fm.get("confidence"))

    draft_fm = _build_draft_frontmatter(
        stage4=stage4_fm,
        confidence=confidence,
        fallback=fallback,
        source_slug=src_slug,
        model=qwen.model,
        prompt_version=qwen.prompt_version,
        timestamp=ts,
    )
    out.mkdir(parents=True, exist_ok=True)
    draft_path = out / f"{src_slug}.md"
    draft_path.write_text(_render_draft(draft_fm, restructured), encoding="utf-8")
    return RestructureDraft(
        slug=src_slug,
        draft_path=draft_path,
        confidence=confidence,
        confidence_fallback=fallback,
    )
