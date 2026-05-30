"""Smoke-Test 8.A — Routing-Differenzierung + Stage 3/4.

Docs:
  - D_css-cheatsheet  → erwartet: 1:1-Passthrough (code_blocks > 0)
  - D_api-grundlagen  → erwartet: Stage-3-Veredelung (prose-lastig)

Outputs: data/03_drafts/CK_*.{body.md,frontmatter.json,md}
Gate-Vorlage wird am Ende ausgegeben.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import openai  # noqa: E402
from pipeline.phase_8_synthesis import (  # noqa: E402
    _build_doc_concept,
    _build_passthrough_body,
    _group_segments_by_doc,
    _load_passthrough_doc_ids,
    _load_segments,
    _load_tag_synonym_map,
    _load_tag_vocabulary,
    _QwenStageConfig,
    _run_stage3_concept,
    _run_stage4_concept,
    _slugify_ck,
    _unique_slug,
    _write_combined_draft,
)

DATA_ROOT = Path.home() / "projects/aktiv/PKM_rebuild/data"
SEGMENTS_PATH = DATA_ROOT / "02_pipeline_output/segments.jsonl"
STRUCTURED_DOCS_PATH = DATA_ROOT / "02_pipeline_output/documents_structured.jsonl"
DRAFTS_DIR = DATA_ROOT / "03_drafts"
QWEN_DIR = DATA_ROOT / "02_pipeline_output/qwen"
TAG_VOCAB_PATH = DATA_ROOT / "04_vault/00_Meta/tag-system.md"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# Gate: 1 strukturiertes Doc + 1 prosa-lastiges Doc
TARGET_DOCS = [
    ("D_css-cheatsheet", "compact-reference", "passthrough"),
    ("D_api-grundlagen", "knowledge-article", "stage3"),
]


def main() -> int:
    print("=== Smoke-Test 8.A — Routing-Differenzierung + Stage 3/4 ===\n")

    seg_map = _load_segments(SEGMENTS_PATH)
    docs = _group_segments_by_doc(seg_map)

    # Passthrough-Set aus Phase-3-Daten laden
    passthrough_doc_ids = _load_passthrough_doc_ids(STRUCTURED_DOCS_PATH)
    print(f"Passthrough-Docs (strukturiert): {len(passthrough_doc_ids)}")

    tag_vocab = _load_tag_vocabulary(TAG_VOCAB_PATH)
    tag_synonym_map = _load_tag_synonym_map(TAG_VOCAB_PATH)
    print(f"Tag-Vokabular: {len(tag_vocab)} kanonische Tags\n")

    client = openai.OpenAI(
        base_url="http://localhost:1234/v1",
        api_key="local",
        timeout=2400,
    )
    today_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    used_slugs: set[str] = set()

    cfg = _QwenStageConfig(
        client=client,
        model="qwen/qwen3.6-27b",
        context_window=49152,
        max_retries=2,
        backoff_seconds=5,
        prompts_dir=PROMPTS_DIR,
        prompt_version="v1",
        needs_human_path=QWEN_DIR / "needs_human.jsonl",
        pipeline_version="0.1.0",
        force=True,
        today_str=today_str,
        temp_stage1=0.3,
        temp_stage2=0.2,
        temp_stage3=0.4,
        temp_stage4=0.1,
        max_tokens_stage1=20000,
        max_tokens_stage2=14000,
        max_tokens_stage3=8000,  # Block 8.A.1: 24000 → 8000
        max_tokens_stage4=5000,
        tag_vocab=tag_vocab,
        tag_synonym_map=tag_synonym_map,
        tag_strict=False,
        used_slugs=used_slugs,
    )

    results: dict[str, dict] = {}

    for doc_id, expected_type, expected_path in TARGET_DOCS:
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"Doc:           {doc_id}")
        print(f"Typ erwartet:  {expected_type}")
        print(f"Pfad erwartet: {expected_path}")

        actual_path = "passthrough" if doc_id in passthrough_doc_ids else "stage3"
        path_ok = actual_path == expected_path
        print(
            f"Pfad tatsächl: {actual_path}  {'[OK]' if path_ok else '[FEHLER: falsches Routing!]'}"
        )

        doc_segments = docs.get(doc_id)
        if not doc_segments:
            print("  FEHLER: Keine Segmente gefunden")
            results[doc_id] = {"status": "error", "reason": "no_segments"}
            continue

        total_words = sum(s.word_count for s in doc_segments)
        print(f"Segmente: {len(doc_segments)} | Wörter: {total_words}")

        concept = _build_doc_concept(doc_id, doc_segments)
        concept["type"] = expected_type
        slug = _unique_slug(_slugify_ck(doc_id.removeprefix("D_")), used_slugs)
        print(f"CK-ID: {concept['ck_id']}  Slug: CK_{slug}")

        # --- Body (Routing) ---
        if actual_path == "passthrough":
            print("\nBody: 1:1-Passthrough (kein Stage-3-API-Aufruf)... ", end="", flush=True)
            body = _build_passthrough_body(doc_segments)
            body_path = DRAFTS_DIR / f"CK_{slug}.body.md"
            DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
            body_path.write_text(body, encoding="utf-8")
            stage3_called = False
            print(f"OK  ({len(body)} Zeichen, {body.count(chr(10))} Zeilen)")
        else:
            print("\nStage 3 (Body)... ", end="", flush=True)
            body = _run_stage3_concept(concept, seg_map, DRAFTS_DIR, slug, doc_id, cfg)
            stage3_called = True
            if not body:
                print("FEHLER")
                results[doc_id] = {"status": "stage3_fail", "routing_ok": path_ok}
                continue
            print(f"OK  ({len(body)} Zeichen, {body.count(chr(10))} Zeilen)")

        # --- Stage 4 ---
        print("Stage 4 (Frontmatter)... ", end="", flush=True)
        fm = _run_stage4_concept(concept, body, DRAFTS_DIR, slug, doc_id, cfg)
        if not fm:
            print("FEHLER")
            results[doc_id] = {
                "status": "stage4_fail",
                "routing_ok": path_ok,
                "body_chars": len(body),
            }
            continue
        print("OK")

        combined_path = DRAFTS_DIR / f"CK_{slug}.md"
        _write_combined_draft(body, fm, combined_path)

        merged_ok = fm.merged_from == []
        sources_ok = len(fm.sources_docs) > 0

        # Code-Block-Check: bei Passthrough müssen Code-Blöcke erhalten sein
        code_block_count_in_body = body.count("```")
        code_blocks_intact = code_block_count_in_body % 2 == 0  # gerade Zahl = geschlossen

        print(f"\n  type:             {fm.type}")
        print(f"  confidence:       {fm.confidence}")
        print(f"  tags ({len(fm.tags)}):         {fm.tags}")
        print(f"  merged_from:      {fm.merged_from}  {'[OK]' if merged_ok else '[FEHLER]'}")
        print(f"  sources_docs:     {fm.sources_docs}  {'[OK]' if sources_ok else '[FEHLER]'}")
        print(
            f"  code_blocks_body: {code_block_count_in_body // 2}  {'[OK]' if code_blocks_intact else '[OFFEN]'}"
        )
        print(f"  stage3_called:    {stage3_called}")

        results[doc_id] = {
            "status": "ok",
            "routing_expected": expected_path,
            "routing_actual": actual_path,
            "routing_ok": path_ok,
            "ck_id": concept["ck_id"],
            "slug": slug,
            "type_expected": expected_type,
            "type_got": fm.type,
            "type_match": fm.type == expected_type,
            "confidence": fm.confidence,
            "tags": fm.tags,
            "merged_from_ok": merged_ok,
            "sources_ok": sources_ok,
            "stage3_called": stage3_called,
            "code_blocks_intact": code_blocks_intact,
            "body_chars": len(body),
            "body_lines": body.count("\n"),
            "files": {
                "body": str(DRAFTS_DIR / f"CK_{slug}.body.md"),
                "frontmatter": str(DRAFTS_DIR / f"CK_{slug}.frontmatter.json"),
                "combined": str(combined_path),
            },
        }

    # --- Gate-Vorlage ---
    sep = "=" * 60
    print(f"\n{sep}")
    print("=== GATE — Smoke-Test 8.A Ergebnis ===\n")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    all_ok = all(r.get("status") == "ok" and r.get("routing_ok", False) for r in results.values())
    print(f"\nGesamt: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
