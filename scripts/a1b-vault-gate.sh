#!/usr/bin/env bash
# a1b-vault-gate.sh — öffnet das Brain-Vault-Write-Deny für A1b und stellt es garantiert wieder her.
# Usage:
#   ./a1b-vault-gate.sh           # guarded: öffnen → warten (Enter) → schließen + Gegenprobe
#   ./a1b-vault-gate.sh open      # nur öffnen (Backup anlegen)
#   ./a1b-vault-gate.sh close     # nur schließen (aus Backup restaurieren)
#   ./a1b-vault-gate.sh status    # aktuelle Deny-Einträge zeigen
set -euo pipefail

PATTERN='Brain-Vault|09_Brain'
FILES=(
  ".claude/settings.json"
  ".claude/settings.local.json"
  "$HOME/.claude/settings.local.json"
)
SUFFIX=".a1b.bak"

command -v jq >/dev/null || { echo "jq fehlt: brew install jq"; exit 1; }

show() {
  for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue
    local hits; hits=$(jq -r '(.permissions.deny // [])[] | select(test("'"$PATTERN"'"))' "$f" 2>/dev/null || true)
    [ -n "$hits" ] && echo "DENY in $f:" && echo "$hits" | sed 's/^/  - /'
  done
}

open_gate() {
  for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue
    if [ -f "$f$SUFFIX" ]; then echo "WARN: $f$SUFFIX existiert schon (offenes Fenster?) — überspringe"; continue; fi
    cp -p "$f" "$f$SUFFIX"
    jq 'if .permissions.deny then .permissions.deny |= map(select(test("'"$PATTERN"'")|not)) else . end' \
      "$f$SUFFIX" > "$f"
    echo "geöffnet: $f (Backup: $f$SUFFIX)"
  done
}

close_gate() {
  local restored=0
  for f in "${FILES[@]}"; do
    if [ -f "$f$SUFFIX" ]; then
      mv -f "$f$SUFFIX" "$f"
      echo "wiederhergestellt: $f"
      restored=1
    fi
  done
  [ "$restored" = 1 ] || echo "kein Backup gefunden — nichts zu restaurieren"
  echo "--- Gegenprobe (Deny muss wieder da sein) ---"
  show
}

case "${1:-guarded}" in
  status) show ;;
  open)   open_gate; echo "--- offen ---"; show ;;
  close)  close_gate ;;
  guarded)
    trap 'echo; echo "Abbruch erkannt — stelle Deny wieder her..."; close_gate' INT TERM
    open_gate
    echo
    echo ">>> Vault-Write ist JETZT offen. Starte A1b in CC."
    read -r -p ">>> Enter drücken, sobald A1b (Audit-Verify 165/165) fertig ist… " _
    trap - INT TERM
    close_gate
    ;;
  *) echo "Usage: $0 [open|close|status|guarded]"; exit 1 ;;
esac
