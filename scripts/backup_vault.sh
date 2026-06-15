#!/usr/bin/env bash
# ============================================================================
# backup_vault.sh — expliziter Snapshot des PRODUKTIVEN Vaults (#3)
# ----------------------------------------------------------------------------
# Sichert den produktiven Obsidian-Vault (09_Brain-Vault) als .tar.gz + SHA-256
# (Archiv-Hash + Datei-Manifest). Schließt die kritische Backup-Lücke: der Vault
# ist das nicht-reproduzierbare Endprodukt (manuelle Reviews), das von snapshot.sh
# (= Pipeline-Daten #2) NICHT erfasst wird.
#
# Vault-Pfad: $PKM_VAULT_ROOT bzw. $PKM_BRAIN_VAULT (Codebase-Var, _paths.py),
#             Default ~/Zentrale/09_Brain-Vault.
# Ziel:       Default <pkm-pipeline>/archive/backups/vault_<ts>.tar.gz
#             oder --target <dir> (externes Medium / Off-Volume).
#
# Aufruf:   bash scripts/backup_vault.sh [--target /Volumes/Backup]
#           make backup-vault
# ============================================================================

set -euo pipefail

# --- Vault-Quelle (#3): PKM_VAULT_ROOT > PKM_BRAIN_VAULT > Default ---
readonly VAULT_ROOT="${PKM_VAULT_ROOT:-${PKM_BRAIN_VAULT:-${HOME}/Zentrale/09_Brain-Vault}}"
readonly PIPELINE_ROOT="${PKM_PIPELINE_ROOT:-${HOME}/projects/aktiv/pkm-pipeline}"
readonly TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)

# --- Ziel-Verzeichnis (--target überschreibt den Default) ---
TARGET_DIR="${PIPELINE_ROOT}/archive/backups"
if [[ "${1:-}" == "--target" ]]; then
  if [[ -z "${2:-}" ]]; then
    echo "✗ Fehler: --target braucht ein Verzeichnis" >&2
    exit 2
  fi
  TARGET_DIR="$2"
fi
readonly TARGET_DIR

# --- Vorbedingungen ---
if [[ ! -d "${VAULT_ROOT}" ]]; then
  echo "✗ Fehler: Vault nicht gefunden: ${VAULT_ROOT}" >&2
  echo "  (setze PKM_VAULT_ROOT / PKM_BRAIN_VAULT, falls abweichend)" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"
readonly ARCHIVE="${TARGET_DIR}/vault_${TIMESTAMP}.tar.gz"
readonly MANIFEST="${TARGET_DIR}/vault_${TIMESTAMP}.manifest.sha256"

echo "→ Vault-Quelle: ${VAULT_ROOT}"
echo "→ Ziel:         ${ARCHIVE}"

# --- tar-Snapshot (Vault-Ordner als Top-Level-Eintrag) ---
vault_parent="$(dirname "${VAULT_ROOT}")"
vault_name="$(basename "${VAULT_ROOT}")"
tar -czf "${ARCHIVE}" -C "${vault_parent}" "${vault_name}"

# --- Archiv-Hash ---
shasum -a 256 "${ARCHIVE}" | awk '{print $1}' > "${ARCHIVE}.sha256"

# --- Datei-Manifest (für Restore-Verifikation, Pfade relativ zum Vault) ---
(
  cd "${VAULT_ROOT}"
  find . -type f -print0 \
    | sort -z \
    | xargs -0 shasum -a 256 \
    > "${MANIFEST}"
)

size=$(du -h "${ARCHIVE}" | awk '{print $1}')
files=$(wc -l < "${MANIFEST}" | tr -d ' ')

echo ""
echo "─────────────────────────────────────────"
echo "✓ Vault-Backup fertig: ${ARCHIVE} (${size}, ${files} Dateien)"
echo "  Archiv-Hash: $(cat "${ARCHIVE}.sha256")"
echo "─────────────────────────────────────────"
