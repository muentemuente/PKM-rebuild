#!/usr/bin/env bash
# =============================================================================
# PKM-rebuild Snapshot-Script
# =============================================================================
# Erstellt einen Zeitstempel-Snapshot von Korpus + Vault.
# Aufruf: bash scripts/snapshot.sh
#
# Siehe docs/07_backup_strategy.md Sektion 3 fuer die Strategie.
# =============================================================================

set -euo pipefail

# === Pfade ===================================================================
DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
SNAPSHOT_DIR="${DATA_ROOT}/backups/snapshot_${TIMESTAMP}"

# === Vorbedingungen ==========================================================
if [[ ! -d "${DATA_ROOT}/data" ]]; then
    echo "FEHLER: Daten-Verzeichnis ${DATA_ROOT}/data nicht gefunden." >&2
    echo "Erst Daten-Struktur anlegen (Block 0.C Schritt 1)." >&2
    exit 1
fi

mkdir -p "${SNAPSHOT_DIR}"

# === Korpus snapshotten ======================================================
if [[ -d "${DATA_ROOT}/data/01_corpus_input" ]] && \
   [[ -n "$(ls -A "${DATA_ROOT}/data/01_corpus_input" 2>/dev/null)" ]]; then
    echo "→ Snapshotting Korpus-Input..."
    tar -czf "${SNAPSHOT_DIR}/corpus_input.tar.gz" \
        -C "${DATA_ROOT}/data" "01_corpus_input"

    # SHA-256 fuer spaetere Integritaets-Checks
    (cd "${DATA_ROOT}/data" && \
     find "01_corpus_input" -type f -name "*.md" -exec sha256sum {} \; | \
     sort > "${SNAPSHOT_DIR}/corpus_input.sha256")

    echo "  ✓ corpus_input.tar.gz + corpus_input.sha256"
else
    echo "→ Korpus leer/fehlt, ueberspringe."
fi

# === Vault snapshotten =======================================================
if [[ -d "${DATA_ROOT}/data/04_vault" ]] && \
   [[ -n "$(ls -A "${DATA_ROOT}/data/04_vault" 2>/dev/null)" ]]; then
    echo "→ Snapshotting Vault..."
    tar -czf "${SNAPSHOT_DIR}/vault.tar.gz" \
        -C "${DATA_ROOT}/data" "04_vault"
    echo "  ✓ vault.tar.gz"
else
    echo "→ Vault leer/fehlt, ueberspringe."
fi

# === Pipeline-State snapshotten ==============================================
STATE_FILE="${DATA_ROOT}/data/02_pipeline_output/pipeline_state.json"
if [[ -f "${STATE_FILE}" ]]; then
    cp "${STATE_FILE}" "${SNAPSHOT_DIR}/"
    echo "  ✓ pipeline_state.json"
fi

# === Metadaten ===============================================================
cat > "${SNAPSHOT_DIR}/SNAPSHOT_INFO.txt" << EOF
PKM-rebuild Snapshot
Timestamp:  ${TIMESTAMP}
Created:    $(date)
Hostname:   $(hostname)
DataRoot:   ${DATA_ROOT}
EOF

# === Zusammenfassung =========================================================
echo
echo "✓ Snapshot abgeschlossen: ${SNAPSHOT_DIR}"
echo
ls -lah "${SNAPSHOT_DIR}"
