#!/usr/bin/env bash
# =============================================================================
# PKM-rebuild Restore-Script
# =============================================================================
# Stellt Korpus + Vault aus einem Snapshot wieder her.
#
# Aufruf:
#   bash scripts/restore.sh <snapshot-name>
#   bash scripts/restore.sh snapshot_2026-05-26_2200
#
# Wenn kein Snapshot-Name uebergeben wird, listet das Script verfuegbare auf.
# =============================================================================

set -euo pipefail

DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"
BACKUPS_DIR="${DATA_ROOT}/backups"

# === Snapshot-Name pruefen ===================================================
if [[ $# -lt 1 ]]; then
    echo "Usage: bash scripts/restore.sh <snapshot-name>"
    echo
    echo "Verfuegbare Snapshots:"
    ls -1 "${BACKUPS_DIR}" 2>/dev/null | grep "^snapshot_" || echo "  (keine gefunden)"
    exit 1
fi

SNAPSHOT_NAME="$1"
SNAPSHOT_DIR="${BACKUPS_DIR}/${SNAPSHOT_NAME}"

if [[ ! -d "${SNAPSHOT_DIR}" ]]; then
    echo "FEHLER: Snapshot ${SNAPSHOT_DIR} nicht gefunden." >&2
    exit 1
fi

# === Restore-Ziel: TEMPORAERES Verzeichnis (nie direkt ins echte Data!) =====
RESTORE_DIR="${HOME}/tmp/pkm-restore-test_$(date +%H%M%S)"
mkdir -p "${RESTORE_DIR}"

echo "→ Restore-Ziel: ${RESTORE_DIR}"
echo

# === Korpus wiederherstellen ================================================
if [[ -f "${SNAPSHOT_DIR}/corpus_input.tar.gz" ]]; then
    echo "→ Stelle Korpus wieder her..."
    tar -xzf "${SNAPSHOT_DIR}/corpus_input.tar.gz" -C "${RESTORE_DIR}"
    echo "  ✓ Korpus entpackt"
fi

# === Vault wiederherstellen =================================================
if [[ -f "${SNAPSHOT_DIR}/vault.tar.gz" ]]; then
    echo "→ Stelle Vault wieder her..."
    tar -xzf "${SNAPSHOT_DIR}/vault.tar.gz" -C "${RESTORE_DIR}"
    echo "  ✓ Vault entpackt"
fi

# === Integritaets-Check (Hash-Vergleich) ====================================
if [[ -f "${SNAPSHOT_DIR}/corpus_input.sha256" ]]; then
    echo
    echo "→ Pruefe Hash-Integritaet..."
    (cd "${RESTORE_DIR}" && \
     find "01_corpus_input" -type f -name "*.md" -exec sha256sum {} \; | \
     sort > "/tmp/pkm-restore-actual.sha256")

    if diff -q "${SNAPSHOT_DIR}/corpus_input.sha256" "/tmp/pkm-restore-actual.sha256" > /dev/null; then
        echo "  ✓ Hash-Verifikation erfolgreich"
    else
        echo "  ✗ HASH-MISMATCH!" >&2
        diff "${SNAPSHOT_DIR}/corpus_input.sha256" "/tmp/pkm-restore-actual.sha256" >&2
        exit 2
    fi
    rm -f /tmp/pkm-restore-actual.sha256
fi

# === Zusammenfassung ========================================================
echo
echo "✓ Restore abgeschlossen in: ${RESTORE_DIR}"
echo
echo "Naechste Schritte:"
echo "  1. Manuelle Stichprobe: ls ${RESTORE_DIR}/"
echo "  2. Mit Original vergleichen: diff -r ${DATA_ROOT}/data/01_corpus_input ${RESTORE_DIR}/01_corpus_input"
echo "  3. Wenn OK: rm -rf ${RESTORE_DIR}"
