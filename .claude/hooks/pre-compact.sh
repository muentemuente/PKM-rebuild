#!/usr/bin/env bash
# Wird vor Auto-Compaction ausgeführt — schreibt Git-Kontext als Snapshot-File.
set -euo pipefail

SNAPSHOT_DIR="$(dirname "$0")/../snapshots"
mkdir -p "$SNAPSHOT_DIR"
TS=$(date +%Y%m%d-%H%M)
OUTPUT="${SNAPSHOT_DIR}/pre-compact-${TS}.md"

{
  echo "## Pre-Compact Snapshot — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "### Branch"
  git branch --show-current 2>/dev/null || echo "unknown"
  echo ""
  echo "### Git-Status"
  git status --short 2>/dev/null | head -30 || echo "(nicht verfügbar)"
  echo ""
  echo "### Letzte 10 Commits"
  git log --oneline -10 2>/dev/null || echo "(nicht verfügbar)"
  echo ""
  echo "### Pipeline-State"
  STATE="${HOME}/projects/aktiv/PKM_rebuild/data/02_pipeline_output/pipeline_state.json"
  if [[ -f "$STATE" ]]; then
    cat "$STATE"
  else
    echo "(pipeline_state.json nicht vorhanden)"
  fi
} > "$OUTPUT"

echo "Pre-compact snapshot gespeichert: $OUTPUT"
