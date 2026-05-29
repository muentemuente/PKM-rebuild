#!/usr/bin/env bash
# Wird bei jedem SessionStart ausgeführt — lädt Git-Kontext in den Session-Kontext.
set -euo pipefail

echo "## Git-Kontext (SessionStart)"
echo ""
echo "### Branch"
git branch --show-current 2>/dev/null || echo "(kein Branch erkannt)"
echo ""
echo "### Status"
git status --short 2>/dev/null | head -20 || echo "(git status fehlgeschlagen)"
echo ""
echo "### Letzte 5 Commits"
git log --oneline -5 2>/dev/null || echo "(kein Log verfügbar)"
echo ""
