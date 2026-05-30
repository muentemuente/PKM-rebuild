"""Phase 8 — Qwen-Veredelung: Stage-3+4 Pro-Doc-Veredelung (Option B).

Option B: Stage 1 (Cluster-Analyse) und Stage 2 (Merge-Vorschlaege) entfallen.
Jedes Dokument wird direkt veredelt: 1 Doc → Stage 3 (Body) → Stage 4 (Frontmatter).

Input:  data/02_pipeline_output/segments.jsonl          (Phase 4)
Output: data/03_drafts/CK_{slug}.body.md
        data/03_drafts/CK_{slug}.frontmatter.json
        data/03_drafts/CK_{slug}.md   (kombiniert)
        data/02_pipeline_output/qwen/needs_human.jsonl

Akzeptanzkriterien (docs/02_pipeline_spec.md, Phase 8):
  - sources_docs belegt (source_doc referenziert); merged_from leer ([])
  - confidence-Feld gesetzt
  - prompt_version gesetzt
  - last_synthesized gesetzt
  - Validation gegen Pydantic-Schema gruen
  - Idempotenz: zweimaliger Lauf identische Outputs (Hash-Vergleich)

Constraints:
  - json_mode=False (LM Studio + Reasoning-Modell inkompatibel)
  - max_tokens = 10x geplante Content-Groesse (Reasoning-Overhead ~91%)
  - Stage 1+2 Funktionen bleiben als deprecated (Option-A-Referenz)
"""

import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import openai
import structlog
import yaml

from pipeline.schemas import FrontmatterDraft, SegmentRecord, StructuredDocumentRecord

log = structlog.get_logger()

# === Dataclass fuer Stage-Konfiguration =========================================


@dataclass
class _QwenStageConfig:
    """Interne Konfiguration fuer einen Phase-8-Lauf."""

    client: Any
    model: str
    context_window: int
    max_retries: int
    backoff_seconds: int
    prompts_dir: Path
    prompt_version: str
    needs_human_path: Path
    pipeline_version: str
    force: bool
    today_str: str
    # Temperaturen (Stage 1+2 deprecated, nicht verwendet in Option B)
    temp_stage1: float
    temp_stage2: float
    temp_stage3: float
    temp_stage4: float
    # Token-Budgets (Stage 1+2 deprecated, nicht verwendet in Option B)
    max_tokens_stage1: int
    max_tokens_stage2: int
    max_tokens_stage3: int
    max_tokens_stage4: int
    # Slug-Kollisionsschutz
    used_slugs: set[str] = field(default_factory=set)


# === Hilfsfunktionen ============================================================


def _sha256_str(text: str) -> str:
    """SHA-256 eines Strings."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    """Extrahiert und parst JSON aus LLM-Response (mit/ohne Reasoning-Block).

    Prueft in dieser Reihenfolge:
    1. ```json-Block
    2. Aeusserstes { ... }-Objekt
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        try:
            return cast(dict[str, Any], json.loads(candidate))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    if start == -1:
        raise ValueError("Kein JSON-Objekt in Response gefunden")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return cast(dict[str, Any], json.loads(text[start : i + 1]))
                except json.JSONDecodeError:
                    break
    raise ValueError("Konnte JSON nicht aus Response parsen")


def _extract_markdown_body(text: str) -> str:
    """Extrahiert Markdown-Body aus LLM-Response."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    m = re.search(r"```(?:markdown)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    return text.strip()


def _is_cached(output_path: Path, meta_path: Path, input_hash: str) -> bool:
    """Prueft ob Output existiert und Input-Hash stimmt."""
    if not output_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(meta.get("input_hash") == input_hash)
    except (json.JSONDecodeError, OSError):
        return False


def _write_stage_meta(meta_path: Path, input_hash: str, stage: str) -> None:
    """Schreibt einfaches Meta-File fuer Idempotenz-Tracking."""
    meta_path.write_text(
        json.dumps(
            {
                "stage": stage,
                "input_hash": input_hash,
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_prompt(prompts_dir: Path, version: str, filename: str) -> str:
    """Laedt Prompt-File und gibt nur den Body-Teil zurueck (ohne Frontmatter)."""
    path = prompts_dir / version / filename
    content = path.read_text(encoding="utf-8")
    if content.startswith("---"):
        end = content.find("\n---\n", 3)
        if end != -1:
            return content[end + 5 :].strip()
    return content


def _load_segments(path: Path) -> dict[str, SegmentRecord]:
    """Laedt SegmentRecords als {segment_id: record}."""
    records: dict[str, SegmentRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = SegmentRecord.model_validate_json(line)
            records[rec.segment_id] = rec
    return records


def _group_segments_by_doc(
    seg_map: dict[str, SegmentRecord],
) -> dict[str, list[SegmentRecord]]:
    """Gruppiert Segmente nach doc_id, sortiert nach segment_index."""
    docs: dict[str, list[SegmentRecord]] = defaultdict(list)
    for seg in seg_map.values():
        docs[seg.doc_id].append(seg)
    for segs in docs.values():
        segs.sort(key=lambda s: s.segment_index)
    return dict(docs)


def _build_doc_concept(doc_id: str, segments: list[SegmentRecord]) -> dict[str, Any]:
    """Erstellt synthetisches Konzept-Dict fuer Option-B-Veredelung (1 Doc → 1 Concept).

    Args:
        doc_id: Dokument-ID (z.B. "D_yaml-frontmatter").
        segments: Alle Segmente dieses Docs, sortiert nach segment_index.

    Returns:
        Konzept-Dict mit ck_id, title, sources_docs, source_chunks, merged_from (leer).
    """
    slug = _slugify_ck(doc_id.removeprefix("D_"))

    # Titel aus erstem nicht-leerem Heading, Fallback: doc_id
    title = doc_id.removeprefix("D_").replace("-", " ").title()
    for seg in segments:
        if seg.heading_path:
            title = seg.heading_path[0]
            break

    return {
        "ck_id": f"CK_{slug}",
        "title": title,
        "type": "knowledge-article",  # Stage 4 darf ueberschreiben
        "doc_role": [],
        "category": "",
        "subcategory": None,
        "sources_docs": [doc_id],
        "source_chunks": [seg.segment_id for seg in segments],
        "merged_from": [],
    }


def _slugify_ck(text: str) -> str:
    """Slugifiziert Text fuer CK_-IDs: lowercase, Bindestriche, keine Umlaute."""
    text = text.lower()
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        text = text.replace(old, new)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-") or "concept"


def _unique_slug(slug: str, used: set[str]) -> str:
    """Gibt eindeutigen Slug zurueck; fuegt Suffix _2, _3 an bei Kollision."""
    if slug not in used:
        used.add(slug)
        return slug
    for n in range(2, 1000):
        candidate = f"{slug}_{n}"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"Zu viele Slug-Kollisionen fuer: {slug}")


def _frontmatter_to_yaml(fm: FrontmatterDraft) -> str:
    """Serialisiert FrontmatterDraft als YAML-String."""
    data = fm.model_dump()
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)  # type: ignore[no-any-return]


def _log_needs_human(
    needs_human_path: Path,
    doc_id: str,
    ck_id: str,
    stage: str,
    reason: str,
    details: str,
) -> None:
    """Fuegt Eintrag zu needs_human.jsonl hinzu."""
    entry = {
        "doc_id": doc_id,
        "ck_id": ck_id,
        "stage": stage,
        "reason": reason,
        "details": details[:300],
        "logged_at": datetime.now(tz=UTC).isoformat(),
    }
    needs_human_path.parent.mkdir(parents=True, exist_ok=True)
    with needs_human_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# === API-Aufruf ================================================================


def _call_qwen_api(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> tuple[str, str]:
    """Einzelner API-Aufruf. Gibt (content, finish_reason) zurueck."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    return (choice.message.content or ""), (choice.finish_reason or "stop")


def _run_json_stage(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    max_retries: int,
    backoff_seconds: int,
) -> dict[str, Any]:
    """Ruft Qwen auf, erwartet JSON. Retry bei Parse-Fehler."""
    last_raw = ""
    for attempt in range(max_retries + 1):
        msgs = messages[:]
        if attempt > 0 and last_raw:
            msgs += [
                {"role": "assistant", "content": last_raw[:400]},
                {
                    "role": "user",
                    "content": (
                        "Die Ausgabe konnte nicht als JSON geparst werden. "
                        "Bitte gib ausschließlich ein valides JSON-Objekt "
                        "in einem ```json-Block aus."
                    ),
                },
            ]
            time.sleep(backoff_seconds)

        last_raw, finish_reason = _call_qwen_api(client, model, msgs, temperature, max_tokens)
        if finish_reason == "length":
            log.warning("qwen_output_truncated", attempt=attempt, max_tokens=max_tokens)

        try:
            return _extract_json(last_raw)
        except (ValueError, json.JSONDecodeError) as exc:
            if attempt >= max_retries:
                raise ValueError(
                    f"JSON-Parse fehlgeschlagen nach {max_retries + 1} Versuchen"
                ) from exc
            log.warning("qwen_json_retry", attempt=attempt, error=str(exc)[:100])

    raise RuntimeError("unreachable")


def _run_text_stage(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    max_retries: int,
    backoff_seconds: int,
) -> str:
    """Ruft Qwen auf, erwartet Markdown-Body. Kein JSON-Parse."""
    for attempt in range(max_retries + 1):
        if attempt > 0:
            time.sleep(backoff_seconds)
        raw, finish_reason = _call_qwen_api(client, model, messages, temperature, max_tokens)
        if finish_reason == "length":
            log.warning("qwen_stage3_truncated", attempt=attempt)
        extracted = _extract_markdown_body(raw)
        if extracted:
            return extracted
        log.warning("qwen_empty_body", attempt=attempt)
    return ""


# === Stage 1+2 (deprecated — Option A, nicht verwendet in Option B) ============


def _run_stage1(
    batch_path: Path,
    output_dir: Path,
    cfg: _QwenStageConfig,
) -> dict[str, Any] | None:
    """Stage 1: Batch-File → stage1_analysis.json. (deprecated — Option A)."""
    output_path = output_dir / "stage1_analysis.json"
    meta_path = output_dir / ".stage1.meta.json"
    batch_content = batch_path.read_text(encoding="utf-8")
    input_hash = _sha256_str(batch_content)

    if not cfg.force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_8_skipped", stage=1, batch=batch_path.stem)
        return cast(dict[str, Any], json.loads(output_path.read_text(encoding="utf-8")))

    system_prompt = _load_prompt(cfg.prompts_dir, cfg.prompt_version, "stage1_cluster_analysis.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": batch_content},
    ]

    try:
        data = _run_json_stage(
            cfg.client,
            cfg.model,
            messages,
            cfg.temp_stage1,
            cfg.max_tokens_stage1,
            cfg.max_retries,
            cfg.backoff_seconds,
        )
    except (ValueError, Exception) as exc:
        log.error("phase_8_stage1_error", batch=batch_path.stem, error=str(exc)[:200])
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_stage_meta(meta_path, input_hash, "stage1")
    log.info(
        "phase_8_stage1_done",
        batch=batch_path.stem,
        concepts=len(data.get("structure_proposal", {}).get("concept_candidates", [])),
    )
    return data


def _run_stage2(
    batch_path: Path,
    stage1_data: dict[str, Any],
    output_dir: Path,
    cfg: _QwenStageConfig,
) -> dict[str, Any] | None:
    """Stage 2: Stage-1-Output → stage2_merges.json. (deprecated — Option A)."""
    output_path = output_dir / "stage2_merges.json"
    meta_path = output_dir / ".stage2.meta.json"
    input_str = json.dumps(stage1_data, ensure_ascii=False)
    input_hash = _sha256_str(input_str)

    decisions_path = output_dir / "merge_decisions.json"
    if decisions_path.exists():
        log.info("phase_8_merge_decisions_found", batch=batch_path.stem)
        return cast(dict[str, Any], json.loads(decisions_path.read_text(encoding="utf-8")))

    if not cfg.force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_8_skipped", stage=2, batch=batch_path.stem)
        return cast(dict[str, Any], json.loads(output_path.read_text(encoding="utf-8")))

    system_prompt = _load_prompt(cfg.prompts_dir, cfg.prompt_version, "stage2_merge_proposal.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_str},
    ]

    try:
        data = _run_json_stage(
            cfg.client,
            cfg.model,
            messages,
            cfg.temp_stage2,
            cfg.max_tokens_stage2,
            cfg.max_retries,
            cfg.backoff_seconds,
        )
    except (ValueError, Exception) as exc:
        log.error("phase_8_stage2_error", batch=batch_path.stem, error=str(exc)[:200])
        return None

    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_stage_meta(meta_path, input_hash, "stage2")
    log.info(
        "phase_8_stage2_done",
        batch=batch_path.stem,
        proposed=len(data.get("proposed_concepts", [])),
    )
    return data


# === Stage 3+4 — aktiv in Option B ============================================


def _build_stage3_user_message(
    concept: dict[str, Any],
    seg_map: dict[str, SegmentRecord],
) -> tuple[str, int, int]:
    """Baut User-Message fuer Stage 3 aus Dokument-Infos + Quell-Segmenten.

    Returns:
        (user_message, resolved_count, missing_count)
    """
    lines = [
        "## Dokument-Informationen",
        "",
        f"ck_id: {concept['ck_id']}",
        f"title: {concept['title']}",
        f"type: {concept['type']}",
        f"doc_role: {', '.join(concept.get('doc_role', []))}",
        f"category: {concept.get('category', '')}",
    ]
    if concept.get("subcategory"):
        lines.append(f"subcategory: {concept['subcategory']}")
    lines += ["", "## Quell-Segmente", ""]

    resolved = 0
    missing = 0
    for chunk_id in concept.get("source_chunks", []):
        seg = seg_map.get(chunk_id)
        if not seg:
            log.warning(
                "phase_8_segment_id_not_found",
                segment_id=chunk_id,
                ck_id=concept.get("ck_id"),
            )
            missing += 1
            continue
        resolved += 1
        heading = " > ".join(seg.heading_path) if seg.heading_path else "(kein Heading)"
        lines += [
            "---",
            "",
            f"**[{seg.segment_id}]** | Heading: `{heading}` | Woerter: {seg.word_count}",
            "",
            seg.text,
            "",
        ]

    return "\n".join(lines), resolved, missing


def _run_stage3_concept(
    concept: dict[str, Any],
    seg_map: dict[str, SegmentRecord],
    drafts_dir: Path,
    slug: str,
    doc_id: str,
    cfg: _QwenStageConfig,
) -> str | None:
    """Stage 3: Dokument + Segmente → CK_slug.body.md."""
    output_path = drafts_dir / f"CK_{slug}.body.md"
    meta_path = drafts_dir / f".CK_{slug}.body.meta.json"

    user_message, resolved, missing = _build_stage3_user_message(concept, seg_map)
    total_chunks = resolved + missing

    if total_chunks > 0 and missing == total_chunks:
        log.error(
            "phase_8_all_chunks_missing",
            slug=slug,
            ck_id=concept.get("ck_id"),
            missing=missing,
        )
        _log_needs_human(
            cfg.needs_human_path,
            doc_id,
            concept["ck_id"],
            "stage3",
            "all_source_chunks_missing",
            f"{missing} von {total_chunks} Segment-IDs nicht aufloesbar",
        )
        return None

    if total_chunks > 0 and missing >= total_chunks / 2:
        concept["_low_confidence_chunks"] = True

    input_hash = _sha256_str(json.dumps(concept, ensure_ascii=False) + user_message)

    if not cfg.force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_8_skipped", stage=3, slug=slug)
        return output_path.read_text(encoding="utf-8")

    system_prompt = _load_prompt(cfg.prompts_dir, cfg.prompt_version, "stage3_synthesis.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    body = _run_text_stage(
        cfg.client,
        cfg.model,
        messages,
        cfg.temp_stage3,
        cfg.max_tokens_stage3,
        cfg.max_retries,
        cfg.backoff_seconds,
    )

    if not body:
        log.error("phase_8_stage3_empty", slug=slug)
        _log_needs_human(cfg.needs_human_path, doc_id, concept["ck_id"], "stage3", "empty_body", "")
        return None

    drafts_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")
    _write_stage_meta(meta_path, input_hash, "stage3")
    log.info("phase_8_stage3_done", slug=slug, chars=len(body))
    return body


def _build_stage4_user_message(
    concept: dict[str, Any],
    body_text: str,
    today_str: str,
) -> str:
    """Baut User-Message fuer Stage 4 aus Dokument-Metadaten + Artikel-Body."""
    lines = [
        "## Dokument-Metadaten",
        "",
        "```json",
        json.dumps(concept, indent=2, ensure_ascii=False),
        "```",
        "",
        f"## Aktuelles Datum: {today_str}",
        "",
        "## Artikel-Body (aus Stage 3)",
        "",
        body_text,
    ]
    return "\n".join(lines)


def _run_stage4_concept(
    concept: dict[str, Any],
    body_text: str,
    drafts_dir: Path,
    slug: str,
    doc_id: str,
    cfg: _QwenStageConfig,
) -> FrontmatterDraft | None:
    """Stage 4: Body + Dokument-Metadaten → CK_slug.frontmatter.json (Pydantic-validiert)."""
    output_path = drafts_dir / f"CK_{slug}.frontmatter.json"
    meta_path = drafts_dir / f".CK_{slug}.frontmatter.meta.json"

    user_message = _build_stage4_user_message(concept, body_text, cfg.today_str)
    input_hash = _sha256_str(user_message)

    if not cfg.force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_8_skipped", stage=4, slug=slug)
        try:
            return FrontmatterDraft.model_validate_json(output_path.read_text(encoding="utf-8"))
        except Exception:
            pass  # Cache kaputt -> neu berechnen

    system_prompt = _load_prompt(cfg.prompts_dir, cfg.prompt_version, "stage4_frontmatter_json.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        raw_fm = _run_json_stage(
            cfg.client,
            cfg.model,
            messages,
            cfg.temp_stage4,
            cfg.max_tokens_stage4,
            cfg.max_retries,
            cfg.backoff_seconds,
        )
    except (ValueError, Exception) as exc:
        log.error("phase_8_stage4_error", slug=slug, error=str(exc)[:200])
        _log_needs_human(
            cfg.needs_human_path, doc_id, concept["ck_id"], "stage4", "api_error", str(exc)[:200]
        )
        return None

    # Pflichtfelder erzwingen / korrigieren
    if concept.get("_low_confidence_chunks"):
        raw_fm["confidence"] = "low"
    raw_fm["status"] = "draft"
    raw_fm["review_status"] = "ai_drafted"
    raw_fm["last_synthesized"] = cfg.today_str
    raw_fm["prompt_version"] = cfg.prompt_version
    raw_fm["merged_from"] = []  # Option B: kein Cross-Doc-Merge
    # sources_docs + source_chunks aus Konzept-Daten sichern
    if not raw_fm.get("sources_docs"):
        raw_fm["sources_docs"] = concept.get("sources_docs", [])
    if not raw_fm.get("source_chunks"):
        raw_fm["source_chunks"] = concept.get("source_chunks", [])
    # Datum-Fallback
    if not raw_fm.get("created"):
        raw_fm["created"] = cfg.today_str
    if not raw_fm.get("updated"):
        raw_fm["updated"] = cfg.today_str

    try:
        fm = FrontmatterDraft.model_validate(raw_fm)
    except Exception as exc:
        log.error("phase_8_stage4_validation_error", slug=slug, error=str(exc)[:300])
        _log_needs_human(
            cfg.needs_human_path,
            doc_id,
            concept["ck_id"],
            "stage4",
            "pydantic_validation_error",
            str(exc)[:300],
        )
        raw_fm["confidence"] = "low"
        try:
            fm = FrontmatterDraft.model_validate(raw_fm)
        except Exception:
            return None

    drafts_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(fm.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_stage_meta(meta_path, input_hash, "stage4")
    log.info("phase_8_stage4_done", slug=slug, confidence=fm.confidence)
    return fm


def _write_combined_draft(
    body_text: str,
    fm: FrontmatterDraft,
    combined_path: Path,
) -> None:
    """Kombiniert Frontmatter-YAML + Body-Markdown → CK_slug.md."""
    fm_yaml = _frontmatter_to_yaml(fm)
    combined_path.write_text(
        f"---\n{fm_yaml}---\n\n{body_text}\n",
        encoding="utf-8",
    )


# === Doc-Verarbeitungs-Hilfsfunktion ==========================================


def _process_doc(
    doc_id: str,
    doc_segments: list[SegmentRecord],
    gedanken_doc_ids: set[str],
    seg_map: dict[str, SegmentRecord],
    drafts_dir: Path,
    force: bool,
    cfg: _QwenStageConfig,
) -> tuple[bool, bool]:
    """Verarbeitet ein einzelnes Dokument (Standard oder Gedanken-Sonderpfad).

    Returns:
        (success, needs_human) — beide Felder unabhaengig voneinander.
    """
    log.info("phase_8_doc_start", doc_id=doc_id, segments=len(doc_segments))
    concept = _build_doc_concept(doc_id, doc_segments)

    raw_slug = _slugify_ck(doc_id.removeprefix("D_"))
    body_meta_path = drafts_dir / f".CK_{raw_slug}.body.meta.json"
    if not cfg.force and body_meta_path.exists():
        slug = raw_slug
        cfg.used_slugs.add(slug)
    else:
        slug = _unique_slug(raw_slug, cfg.used_slugs)

    if doc_id in gedanken_doc_ids:
        log.info("phase_8_gedanken_bypass", doc_id=doc_id, slug=slug)
        concept["type"] = "gedanke"
        concept["category"] = "gedanken"
        concept["doc_role"] = ["wiki"]
        body: str | None = _build_gedanken_body(doc_segments)
        fm = _run_stage4_gedanken(concept, body, drafts_dir, slug, doc_id, cfg)
    else:
        body = _run_stage3_concept(concept, seg_map, drafts_dir, slug, doc_id, cfg)
        if body is None:
            return False, True
        fm = _run_stage4_concept(concept, body, drafts_dir, slug, doc_id, cfg)

    if fm is None:
        return False, True

    combined_path = drafts_dir / f"CK_{slug}.md"
    if force or not combined_path.exists():
        _write_combined_draft(body, fm, combined_path)

    log.info(
        "phase_8_doc_drafted",
        slug=slug,
        ck_id=concept["ck_id"],
        doc_id=doc_id,
        confidence=fm.confidence,
    )
    return True, False


# === Gedanken-Sonderpfad (Stage-3-Bypass) =====================================


def _load_gedanken_doc_ids(structured_docs_path: Path) -> set[str]:
    """Laedt doc_ids aller Gedanken-Files aus documents_structured.jsonl.

    Args:
        structured_docs_path: Pfad zu documents_structured.jsonl (Phase 3 Output).

    Returns:
        Set von doc_ids mit doc_type_guess.label == "gedanke".
        Leeres Set wenn Datei nicht existiert.
    """
    if not structured_docs_path.exists():
        log.warning("phase_8_structured_docs_missing", path=str(structured_docs_path))
        return set()
    gedanken: set[str] = set()
    for line in structured_docs_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = StructuredDocumentRecord.model_validate_json(line)
            if rec.doc_type_guess.label == "gedanke":
                gedanken.add(rec.doc_id)
        except Exception:
            pass
    if gedanken:
        log.info("phase_8_gedanken_detected", count=len(gedanken))
    return gedanken


def _build_gedanken_body(segments: list[SegmentRecord]) -> str:
    """Baut Body fuer Gedanken-Sonderpfad: Original-Segmenttexte unveraendert zusammenfuehren."""
    return "\n\n".join(seg.text for seg in segments if seg.text.strip())


def _run_stage4_gedanken(
    concept: dict[str, Any],
    body_text: str,
    drafts_dir: Path,
    slug: str,
    doc_id: str,
    cfg: _QwenStageConfig,
) -> FrontmatterDraft | None:
    """Stage 4 fuer Gedanken: Original-Body → Frontmatter mit gedanken-Prompt.

    Unterschiede zu _run_stage4_concept:
    - Verwendet stage4_frontmatter_gedanken.md
    - Erzwingt type="gedanke", category="gedanken", doc_role=["wiki"]
    """
    output_path = drafts_dir / f"CK_{slug}.frontmatter.json"
    meta_path = drafts_dir / f".CK_{slug}.frontmatter.meta.json"

    user_message = _build_stage4_user_message(concept, body_text, cfg.today_str)
    input_hash = _sha256_str(user_message)

    if not cfg.force and _is_cached(output_path, meta_path, input_hash):
        log.info("phase_8_skipped", stage="4_gedanken", slug=slug)
        try:
            return FrontmatterDraft.model_validate_json(output_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    system_prompt = _load_prompt(cfg.prompts_dir, cfg.prompt_version, "stage4_frontmatter_gedanken.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        raw_fm = _run_json_stage(
            cfg.client,
            cfg.model,
            messages,
            cfg.temp_stage4,
            cfg.max_tokens_stage4,
            cfg.max_retries,
            cfg.backoff_seconds,
        )
    except (ValueError, Exception) as exc:
        log.error("phase_8_stage4_gedanken_error", slug=slug, error=str(exc)[:200])
        _log_needs_human(
            cfg.needs_human_path, doc_id, concept["ck_id"], "stage4_gedanken", "api_error", str(exc)[:200]
        )
        return None

    # Festgelegte Gedanken-Pflichtfelder erzwingen
    raw_fm["type"] = "gedanke"
    raw_fm["category"] = "gedanken"
    raw_fm["doc_role"] = ["wiki"]
    raw_fm["status"] = "draft"
    raw_fm["review_status"] = "ai_drafted"
    raw_fm["last_synthesized"] = cfg.today_str
    raw_fm["prompt_version"] = cfg.prompt_version
    raw_fm["merged_from"] = []
    if not raw_fm.get("sources_docs"):
        raw_fm["sources_docs"] = concept.get("sources_docs", [])
    if not raw_fm.get("source_chunks"):
        raw_fm["source_chunks"] = concept.get("source_chunks", [])
    if not raw_fm.get("created"):
        raw_fm["created"] = cfg.today_str
    if not raw_fm.get("updated"):
        raw_fm["updated"] = cfg.today_str

    try:
        fm = FrontmatterDraft.model_validate(raw_fm)
    except Exception as exc:
        log.error("phase_8_stage4_gedanken_validation_error", slug=slug, error=str(exc)[:300])
        _log_needs_human(
            cfg.needs_human_path,
            doc_id,
            concept["ck_id"],
            "stage4_gedanken",
            "pydantic_validation_error",
            str(exc)[:300],
        )
        raw_fm["confidence"] = "low"
        try:
            fm = FrontmatterDraft.model_validate(raw_fm)
        except Exception:
            return None

    drafts_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(fm.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_stage_meta(meta_path, input_hash, "stage4_gedanken")
    log.info("phase_8_stage4_gedanken_done", slug=slug, confidence=fm.confidence)
    return fm


# === run_phase_8 ===============================================================


def run_phase_8(
    segments_path: Path,
    qwen_output_dir: Path,
    drafts_dir: Path,
    *,
    endpoint: str,
    model: str,
    context_window: int,
    prompt_version: str,
    prompts_dir: Path,
    temperature_stage3: float,
    temperature_stage4: float,
    max_retries: int,
    retry_backoff_seconds: int,
    timeout_seconds: int,
    max_tokens_stage3: int = 24000,
    max_tokens_stage4: int = 10000,
    force: bool = False,
    pipeline_version: str = "0.1.0",
    structured_docs_path: Path | None = None,
    # Deprecated (Option A) — werden ignoriert:
    batches_dir: Path | None = None,
    temperature_stage1: float = 0.3,
    temperature_stage2: float = 0.2,
    max_tokens_stage1: int = 20000,
    max_tokens_stage2: int = 14000,
) -> dict[str, Any]:
    """Phase 8 ausfuehren: Pro-Doc-Veredelung (Option B) fuer alle Docs in segments.jsonl.

    Args:
        segments_path: Pfad zu segments.jsonl (Phase 4 Output).
        qwen_output_dir: Ziel fuer needs_human.jsonl.
        drafts_dir: Ziel fuer CK_*.md Drafts.
        endpoint: LM-Studio/OpenAI-Endpunkt.
        model: Modell-ID.
        context_window: Maximales Kontext-Fenster in Tokens.
        prompt_version: Aktive Prompt-Version (z.B. "v1").
        prompts_dir: Pfad zum prompts/-Verzeichnis.
        temperature_stage3: Temperatur fuer Stage 3 (Body).
        temperature_stage4: Temperatur fuer Stage 4 (Frontmatter).
        max_retries: Max. Retry-Versuche bei Fehler.
        retry_backoff_seconds: Wartezeit zwischen Retries.
        timeout_seconds: HTTP-Timeout.
        force: Cache ignorieren, alles neu berechnen.
        pipeline_version: Fuer Meta-Files.
        structured_docs_path: Pfad zu documents_structured.jsonl fuer Gedanken-Erkennung.
            Wenn None: kein Gedanken-Sonderpfad (alle Docs normal verarbeitet).
        batches_dir: Ignoriert (deprecated, Option A).
        temperature_stage1: Ignoriert (deprecated, Option A).
        temperature_stage2: Ignoriert (deprecated, Option A).
        max_tokens_stage1: Ignoriert (deprecated, Option A).
        max_tokens_stage2: Ignoriert (deprecated, Option A).

    Returns:
        Summary-Dict mit docs_processed, concepts_drafted, needs_human, errors.

    Raises:
        FileNotFoundError: Wenn segments_path nicht existiert.
    """
    if not segments_path.exists():
        raise FileNotFoundError(f"segments_path nicht gefunden: {segments_path}")

    client = openai.OpenAI(
        base_url=endpoint,
        api_key="local",
        timeout=timeout_seconds,
    )

    seg_map = _load_segments(segments_path)
    docs = _group_segments_by_doc(seg_map)
    needs_human_path = qwen_output_dir / "needs_human.jsonl"
    today_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # Gedanken-Sonderpfad: doc_ids aus documents_structured laden
    gedanken_doc_ids: set[str] = set()
    if structured_docs_path is not None:
        gedanken_doc_ids = _load_gedanken_doc_ids(structured_docs_path)

    if not docs:
        log.warning("phase_8_no_documents", segments_path=str(segments_path))
        return {
            "docs_processed": 0,
            "docs_skipped": 0,
            "concepts_drafted": 0,
            "needs_human": 0,
            "errors": 0,
            "duration_seconds": 0.0,
        }

    # Crash-Resume: bestehende Slugs aus drafts_dir laden
    used_slugs: set[str] = set()
    _slug_re = re.compile(r"^CK_(.+?)(?:\.body|\.frontmatter)?\.(md|json)$")
    if not force and drafts_dir.exists():
        for f in drafts_dir.iterdir():
            m = _slug_re.match(f.name)
            if m:
                used_slugs.add(m.group(1))
        if used_slugs:
            log.info("phase_8_used_slugs_loaded", count=len(used_slugs))

    cfg = _QwenStageConfig(
        client=client,
        model=model,
        context_window=context_window,
        max_retries=max_retries,
        backoff_seconds=retry_backoff_seconds,
        prompts_dir=prompts_dir,
        prompt_version=prompt_version,
        needs_human_path=needs_human_path,
        pipeline_version=pipeline_version,
        force=force,
        today_str=today_str,
        temp_stage1=temperature_stage1,
        temp_stage2=temperature_stage2,
        temp_stage3=temperature_stage3,
        temp_stage4=temperature_stage4,
        max_tokens_stage1=max_tokens_stage1,
        max_tokens_stage2=max_tokens_stage2,
        max_tokens_stage3=max_tokens_stage3,
        max_tokens_stage4=max_tokens_stage4,
        used_slugs=used_slugs,
    )

    log.info(
        "phase_8_start",
        phase="phase_8_synthesis",
        doc_count=len(docs),
        force=force,
    )

    t_start = time.monotonic()
    docs_processed = 0
    docs_skipped = 0
    concepts_drafted = 0
    errors = 0
    needs_human_count = 0

    for doc_id, doc_segments in sorted(docs.items()):
        ok, human = _process_doc(
            doc_id, doc_segments, gedanken_doc_ids, seg_map, drafts_dir, force, cfg
        )
        if ok:
            docs_processed += 1
            concepts_drafted += 1
        else:
            errors += 1
        if human:
            needs_human_count += 1

    duration = time.monotonic() - t_start
    summary = {
        "docs_processed": docs_processed,
        "docs_skipped": docs_skipped,
        "concepts_drafted": concepts_drafted,
        "needs_human": needs_human_count,
        "errors": errors,
        "duration_seconds": round(duration, 2),
    }

    log.info("phase_8_done", phase="phase_8_synthesis", **summary)
    return summary
