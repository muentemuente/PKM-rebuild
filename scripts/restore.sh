#!/usr/bin/env bash
# ============================================================================
# restore.sh — Recovery-Drill für PKM-rebuild Snapshots
# ----------------------------------------------------------------------------
# Stellt einen Snapshot in ein temporäres Verzeichnis wieder her UND
# verifiziert die Integrität gegen das SHA-256-Manifest aus snapshot.sh.
#
# Aufruf:   bash scripts/restore.sh snapshot_YYYY-MM-DD_HHMM
# Output:   ~/tmp/pkm-restore-test_HHMMSS/
# ============================================================================

set -euo pipefail

# --- Argument prüfen ---
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <snapshot_name>" >&2
  echo "Verfügbare Snapshots:" >&2
  ls -1 "${HOME}/projects/aktiv/PKM_rebuild/backups/" 2>/dev/null | grep -E '^snapshot_' >&2 || echo "  (keine vorhanden)" >&2
  exit 1
fi

readonly SNAPSHOT_NAME="$1"
readonly DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"
readonly SNAPSHOT_DIR="${DATA_ROOT}/backups/${SNAPSHOT_NAME}"
readonly RESTORE_TIMESTAMP=$(date +%H%M%S)
readonly RESTORE_DIR="${HOME}/tmp/pkm-restore-test_${RESTORE_TIMESTAMP}"

# --- Vorbedingungen ---
if [[ ! -d "${SNAPSHOT_DIR}" ]]; then
  echo "✗ Fehler: Snapshot nicht gefunden: ${SNAPSHOT_DIR}" >&2
  exit 1
fi

mkdir -p "${RESTORE_DIR}"
echo "→ Restore-Ziel: ${RESTORE_DIR}"
echo "→ Quelle:       ${SNAPSHOT_DIR}"
echo ""

# --- Funktion: Archiv entpacken + verifizieren ---
restore_archive() {
  local label="$1"
  local archive="${SNAPSHOT_DIR}/${label}.tar.gz"
  local manifest="${SNAPSHOT_DIR}/${label}.manifest.sha256"
  local archive_hash="${SNAPSHOT_DIR}/${label}.tar.gz.sha256"

  if [[ ! -f "${archive}" ]]; then
    echo "⊘ Übersprungen (nicht im Snapshot): ${label}.tar.gz"
    return 0
  fi

  # 1. Hash des Archivs prüfen
  echo "→ Verifiziere Archiv-Hash: ${label}.tar.gz"
  local expected actual
  expected=$(cat "${archive_hash}")
  actual=$(shasum -a 256 "${archive}" | awk '{print $1}')
  if [[ "${expected}" != "${actual}" ]]; then
    echo "  ✗ Archiv-Hash mismatch!" >&2
    echo "    Expected: ${expected}" >&2
    echo "    Actual:   ${actual}" >&2
    return 1
  fi
  echo "  ✓ Archiv-Hash ok"

  # 2. Entpacken
  echo "→ Entpacke: ${label}.tar.gz"
  tar -xzf "${archive}" -C "${RESTORE_DIR}"

  # 3. Datei-Hashes gegen Manifest prüfen
  if [[ -f "${manifest}" ]]; then
    # Subdir-Name aus Manifest-Pfaden ableiten (z.B. "01_corpus_input")
    local subdir
    subdir=$(tar -tzf "${archive}" | head -1 | cut -d/ -f1)

    echo "→ Verifiziere Datei-Hashes: ${label}"
    local failed=0
    while IFS= read -r line; do
      local hash file
      hash=$(echo "${line}" | awk '{print $1}')
      file=$(echo "${line}" | sed 's/^[a-f0-9]*  //')

      local restored_file="${RESTORE_DIR}/${subdir}/${file#./}"
      if [[ ! -f "${restored_file}" ]]; then
        echo "  ✗ Fehlt: ${file}" >&2
        failed=$((failed + 1))
        continue
      fi

      local restored_hash
      restored_hash=$(shasum -a 256 "${restored_file}" | awk '{print $1}')
      if [[ "${hash}" != "${restored_hash}" ]]; then
        echo "  ✗ Hash mismatch: ${file}" >&2
        failed=$((failed + 1))
      fi
    done < "${manifest}"

    if [[ ${failed} -gt 0 ]]; then
      echo "  ✗ ${failed} Datei(en) korrupt oder fehlend" >&2
      return 1
    fi

    local count
    count=$(wc -l < "${manifest}" | tr -d ' ')
    echo "  ✓ ${count} Dateien verifiziert"
  else
    echo "  ⚠ Kein Manifest vorhanden für ${label} — nur Archiv-Hash geprüft"
  fi
}

# --- Alle Archive im Snapshot wiederherstellen ---
for archive in "${SNAPSHOT_DIR}"/*.tar.gz; do
  [[ -f "${archive}" ]] || continue
  label=$(basename "${archive}" .tar.gz)
  restore_archive "${label}"
done

# --- Abschlussbericht ---
echo ""
echo "─────────────────────────────────────────"
echo "✓ Restore fertig: ${RESTORE_DIR}"
echo "─────────────────────────────────────────"
ls -la "${RESTORE_DIR}"
echo ""
echo "→ Vergleichs-Befehl:"
echo "  diff -r ${DATA_ROOT}/data/01_corpus_input ${RESTORE_DIR}/01_corpus_input"
echo ""
echo "→ Aufräumen nach Drill:"
echo "  rm -rf ${RESTORE_DIR}"
