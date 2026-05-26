#!/usr/bin/env bash
set -euo pipefail

echo "=== Tracked Files ==="
git ls-files | head -50
echo
echo "=== Persona-Check ==="
if git ls-files | grep -q persona; then
  echo "STOP: Persona im Repo!" && exit 1
else
  echo "OK: Persona gitignored"
fi
echo
echo "=== Secrets-Check ==="
if git ls-files | grep -qiE '\.env|secret|token|password|\.key|\.pem'; then
  echo "STOP: Secrets gefunden!" && exit 1
else
  echo "OK: keine Secrets"
fi
echo
echo "=== README-Stichprobe ==="
head -20 README.md
