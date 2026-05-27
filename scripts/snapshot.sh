#!/usr/bin/env bash
# ============================================================================
# snapshot.sh — Backup-Snapshot für PKM-rebuild
# ----------------------------------------------------------------------------
# Erstellt einen Snapshot von 01_corpus_input/ und (falls vorhanden) 04_vault/
# als .tar.gz, plus SHA-256-Manifest für Integritäts-Check beim Restore.
#
# Aufruf:   bash scripts/snapshot.sh
# Output:   ~/projects/aktiv/PKM_rebuild/backups/snapshot_YYYY-MM-DD_HHMM/
# ============================================================================

set -euo pipefail

# --- Konfiguration ---
readonly DATA_ROOT="${HOME}/projects/aktiv/PKM_rebuild"
readonly DATA_DIR="${DATA_ROOT}/data"
readonly BACKUPS_DIR="${DATA_ROOT}/backups"
readonly TIMESTAMP=$(date +%Y-%m-%d_%H%M)
readonly SNAPSHOT_DIR="${BACKUPS_DIR}/snapshot_${TIMESTAMP}"

# --- Vorbedingungen prüfen ---
if [[ ! -d "${DATA_DIR}" ]]; then
  echo "✗ Fehler: ${DATA_DIR} existiert nicht" >&2
  exit 1
fi

if [[ ! -d "${DATA_DIR}/01_corpus_input" ]]; then
  echo "✗ Fehler: ${DATA_DIR}/01_corpus_input fehlt" >&2
  exit 1
fi

# --- Snapshot-Verzeichnis anlegen ---
mkdir -p "${SNAPSHOT_DIR}"
echo "→ Snapshot-Ziel: ${SNAPSHOT_DIR}"

# --- Funktion: Archiv + SHA-256 erstellen ---
make_archive() {
  local label="$1"      # z.B. "corpus_input"
  local source_subdir="$2"  # z.B. "01_corpus_input"
  local archive="${SNAPSHOT_DIR}/${label}.tar.gz"

  if [[ ! -d "${DATA_DIR}/${source_subdir}" ]]; then
    echo "⊘ Übersprungen (nicht vorhanden): ${source_subdir}"
    return 0
  fi

  echo "→ Archiviere: ${source_subdir} → ${label}.tar.gz"
  tar -czf "${archive}" -C "${DATA_DIR}" "${source_subdir}"

  # SHA-256 des Archivs
  shasum -a 256 "${archive}" | awk '{print $1}' > "${archive}.sha256"

  # SHA-256-Manifest aller Inhalte (für Restore-Verifikation)
  (
    cd "${DATA_DIR}/${source_subdir}"
    find . -type f -print0 \
      | sort -z \
      | xargs -0 shasum -a 256 \
      > "${SNAPSHOT_DIR}/${label}.manifest.sha256"
  )

  local size
  size=$(du -h "${archive}" | awk '{print $1}')
  echo "  ✓ ${label}.tar.gz (${size})"
}

# --- Korpus immer mitnehmen (read-only, sollte sich nie ändern) ---
make_archive "corpus_input" "01_corpus_input"

# --- Vault optional (existiert nur ab Phase 9) ---
make_archive "vault" "04_vault"

# --- Drafts optional ---
make_archive "drafts" "03_drafts"

# --- Pipeline-State falls vorhanden ---
readonly PIPELINE_STATE="${DATA_DIR}/02_pipeline_output/pipeline_state.json"
if [[ -f "${PIPELINE_STATE}" ]]; then
  cp "${PIPELINE_STATE}" "${SNAPSHOT_DIR}/"
  echo "  ✓ pipeline_state.json kopiert"
fi

# --- Metadaten-File ---
cat > "${SNAPSHOT_DIR}/snapshot.meta.json" <<EOF
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "$(hostname -s)",
  "user": "${USER}",
  "data_root": "${DATA_ROOT}",
  "script_version": "0.1.0"
}
EOF

# --- Abschlussbericht ---
echo ""
echo "─────────────────────────────────────────"
echo "✓ Snapshot fertig: ${SNAPSHOT_DIR}"
echo "─────────────────────────────────────────"
ls -lah "${SNAPSHOT_DIR}"
