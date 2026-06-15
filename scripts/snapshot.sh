#!/usr/bin/env bash
# ============================================================================
# snapshot.sh — Backup-Snapshot der Daten-Ordner (pkm-pipeline)
# ----------------------------------------------------------------------------
# Erstellt einen Snapshot der Recovery-relevanten pkm-pipeline-Ordner
# (input/ work/ drafts/ output/ review/) als .tar.gz plus SHA-256-Manifest
# für Integritäts-Check beim Restore. archive/ wird ausgespart (= Backup-Ziel).
# Zweck: Recovery/Resume der PIPELINE-Daten (#2). Der produktive Vault (#3)
# wird separat über `make backup-vault` gesichert.
#
# Layout: pipeline/_paths.py (PKM_PIPELINE_ROOT, default ~/projects/aktiv/pkm-pipeline).
# Aufruf:   bash scripts/snapshot.sh
# Output:   <PKM_PIPELINE_ROOT>/archive/backups/snapshot_YYYY-MM-DD_HHMM/
# ============================================================================

set -euo pipefail

# --- Konfiguration (PKM_PIPELINE_ROOT überschreibbar) ---
readonly PIPELINE_ROOT="${PKM_PIPELINE_ROOT:-${HOME}/projects/aktiv/pkm-pipeline}"
readonly BACKUPS_DIR="${PIPELINE_ROOT}/archive/backups"
readonly TIMESTAMP=$(date +%Y-%m-%d_%H%M)
readonly SNAPSHOT_DIR="${BACKUPS_DIR}/snapshot_${TIMESTAMP}"

# --- Vorbedingungen prüfen ---
if [[ ! -d "${PIPELINE_ROOT}" ]]; then
  echo "✗ Fehler: ${PIPELINE_ROOT} existiert nicht" >&2
  exit 1
fi

# --- Snapshot-Verzeichnis anlegen ---
mkdir -p "${SNAPSHOT_DIR}"
echo "→ Snapshot-Ziel: ${SNAPSHOT_DIR}"

# --- Funktion: Archiv + SHA-256 erstellen ---
make_archive() {
  local label="$1"          # z.B. "output"
  local source_subdir="$2"  # Unterordner relativ zu PIPELINE_ROOT
  local archive="${SNAPSHOT_DIR}/${label}.tar.gz"

  if [[ ! -d "${PIPELINE_ROOT}/${source_subdir}" ]]; then
    echo "⊘ Übersprungen (nicht vorhanden): ${source_subdir}"
    return 0
  fi

  echo "→ Archiviere: ${source_subdir} → ${label}.tar.gz"
  tar -czf "${archive}" -C "${PIPELINE_ROOT}" "${source_subdir}"

  # SHA-256 des Archivs
  shasum -a 256 "${archive}" | awk '{print $1}' > "${archive}.sha256"

  # SHA-256-Manifest aller Inhalte (für Restore-Verifikation)
  (
    cd "${PIPELINE_ROOT}/${source_subdir}"
    find . -type f -print0 \
      | sort -z \
      | xargs -0 shasum -a 256 \
      > "${SNAPSHOT_DIR}/${label}.manifest.sha256"
  )

  local size
  size=$(du -h "${archive}" | awk '{print $1}')
  echo "  ✓ ${label}.tar.gz (${size})"
}

# --- pkm-pipeline-Layout: alle Recovery-relevanten Ordner ---
# archive/ selbst wird NICHT gesichert (= Backup-Ziel, enthält frühere Snapshots).
make_archive "input"  "input"
make_archive "work"   "work"
make_archive "drafts" "drafts"
make_archive "output" "output"
make_archive "review" "review"

# --- Run-State falls vorhanden ---
readonly RUN_STATE="${PIPELINE_ROOT}/work/state.json"
if [[ -f "${RUN_STATE}" ]]; then
  cp "${RUN_STATE}" "${SNAPSHOT_DIR}/"
  echo "  ✓ state.json kopiert"
fi

# --- Metadaten-File ---
cat > "${SNAPSHOT_DIR}/snapshot.meta.json" <<EOF
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "$(hostname -s)",
  "user": "${USER}",
  "pipeline_root": "${PIPELINE_ROOT}",
  "script_version": "0.2.0"
}
EOF

# --- Abschlussbericht ---
echo ""
echo "─────────────────────────────────────────"
echo "✓ Snapshot fertig: ${SNAPSHOT_DIR}"
echo "─────────────────────────────────────────"
ls -lah "${SNAPSHOT_DIR}"
