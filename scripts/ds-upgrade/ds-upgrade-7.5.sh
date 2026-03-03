#!/bin/bash
#
# DS Upgrade Script: 7.1 → 7.5
#
# Usage (standalone):
#   ./ds-upgrade-7.5.sh backup    # Step 1: Backup current state (run once)
#   ./ds-upgrade-7.5.sh upgrade   # Step 2: Perform Java + DS upgrade
#   ./ds-upgrade-7.5.sh verify    # Step 3: Post-upgrade verification
#   ./ds-upgrade-7.5.sh restore   # Restore to pre-upgrade state (for re-testing)
#
# Usage (Ansible / Harness):
#   ansible-playbook ds-upgrade-7.5.yml -e "action=backup"
#   ansible-playbook ds-upgrade-7.5.yml -e "action=upgrade"
#   ansible-playbook ds-upgrade-7.5.yml -e "action=verify"
#   ansible-playbook ds-upgrade-7.5.yml -e "action=restore"
#
# Test cycle:
#   backup → upgrade → verify → restore → upgrade → verify → restore → ...
#
# Configuration:
#   All config variables below support environment variable override:
#     DS_HOME=/opt/app/forgerock/opendj ./ds-upgrade-7.5.sh upgrade
#   When running via Ansible, set them in the playbook's environment: block.
#   When running standalone, edit the defaults in the Configuration section.
#
# Prerequisites:
#   - DS 7.5 zip in ${INSTALL_DIR}
#   - Java 17 installed at ${JAVA_17}
#   - Upgrade one server at a time (do NOT upgrade all replicas simultaneously)

set -euo pipefail

###############################################################################
# Configuration — override via environment variables, or edit defaults below
###############################################################################
DS_HOME="${DS_HOME:-/opt/app/forgerock/opendj}"
JAVA_11="${JAVA_11:-/opt/app/java/jdk-11}"
JAVA_17="${JAVA_17:-/opt/app/java/jdk-17}"
BACKUP_DIR="${BACKUP_DIR:-/opt/app/backup}"
INSTALL_DIR="${INSTALL_DIR:-/opt/app/install/opendj}"
BASE_DN="${BASE_DN:-dc=example,dc=com}"
DS_ZIP_FILE="${DS_ZIP_FILE:-DS-7.5.3.zip}"
DS_ADMIN_PORT="${DS_ADMIN_PORT:-4444}"
DS_LDAPS_PORT="${DS_LDAPS_PORT:-6036}"

# dsrepl connection settings
DSREPL_HOST="${DSREPL_HOST:-ds.example.com}"
DSREPL_BIND_DN="${DSREPL_BIND_DN:-cn=dsadmin}"
DSREPL_BIND_PASSWORD="${DSREPL_BIND_PASSWORD:-password}"

# Backup tag — used for backup/restore pairing
BACKUP_TAG="ds_upgrade"
BACKUP_DS="${BACKUP_DIR}/opendj_${BACKUP_TAG}"
BACKUP_BASH_PROFILE="${BACKUP_DIR}/bash_profile_${BACKUP_TAG}"
BACKUP_BASHRC="${BACKUP_DIR}/bashrc_${BACKUP_TAG}"
BACKUP_CACERTS="${BACKUP_DIR}/cacerts_java17_original_${BACKUP_TAG}"

# Derived from DS_HOME — unzip target (parent of opendj/)
DS_EXTRACT_DIR="${DS_HOME%/opendj}"  # e.g., /opt/app/forgerock

# DS upgrade zip file (full path)
DS_ZIP="${INSTALL_DIR}/${DS_ZIP_FILE}"

# Log directory for each run
RUN_ID=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${BACKUP_DIR}/upgrade_logs_${RUN_ID}"

###############################################################################
# Pre-flight — ensure required directories exist
###############################################################################
mkdir -p "${BACKUP_DIR}"
mkdir -p "${LOG_DIR}"

###############################################################################
# Global logging — all output goes to both screen and log file
###############################################################################
setup_logging() {
  local action="$1"
  FULL_LOG="${LOG_DIR}/${action}_${RUN_ID}.log"
  exec > >(tee -a "${FULL_LOG}") 2>&1
  echo "[INFO] Full log: ${FULL_LOG}"
}

###############################################################################
# Helper functions
###############################################################################
check_ldap_alive() {
  local result
  result=$("${DS_HOME}/bin/ldapsearch" \
    --hostname localhost \
    --port ${DS_LDAPS_PORT} \
    --useSsl \
    --trustAll \
    --baseDN "" \
    --searchScope base "(objectClass=*)" alive 2>&1)

  echo "${result}"

  if echo "${result}" | grep -q "alive"; then
    echo "[PASS] LDAP is responding"
    return 0
  else
    echo "[FAIL] LDAP is not responding"
    return 1
  fi
}

check_replication() {
  "${DS_HOME}/bin/dsrepl" status \
    --hostname "${DSREPL_HOST}" \
    --port ${DS_ADMIN_PORT} \
    --bindDN "${DSREPL_BIND_DN}" \
    --bindPassword "${DSREPL_BIND_PASSWORD}" \
    --showGroups \
    --showReplicas \
    --showChangelogs \
    -X 2>&1
}

stop_ds() {
  echo "--- Stopping DS ---"
  "${DS_HOME}/bin/stop-ds" 2>&1 || echo "[WARN] stop-ds returned non-zero (DS may not have been running)"
  echo "[INFO] DS stopped"
}

start_ds() {
  echo "--- Starting DS ---"
  "${DS_HOME}/bin/start-ds"
  echo "[INFO] DS started"
}

###############################################################################
# backup — Save current state (run once before first upgrade)
###############################################################################
do_backup() {
  setup_logging "backup"
  echo "========================================="
  echo " DS Backup"
  echo " Date: $(date)"
  echo " Server: $(hostname)"
  echo "========================================="

  if [ -d "${BACKUP_DS}" ]; then
    echo "[WARN] Backup already exists: ${BACKUP_DS}"
    echo "[WARN] Skipping backup. Delete it manually if you want a fresh backup."
    return 0
  fi

  # Verify DS_HOME exists
  if [ ! -d "${DS_HOME}" ]; then
    echo "[FAIL] DS_HOME not found: ${DS_HOME}"
    exit 1
  fi

  # Backup bash_profile and bashrc
  cp ~/.bash_profile "${BACKUP_BASH_PROFILE}"
  cp ~/.bashrc "${BACKUP_BASHRC}"
  echo "[INFO] bash_profile and bashrc backed up"

  # Backup entire DS installation
  echo "--- Backing up DS installation (this may take a while) ---"
  cp -r "${DS_HOME}" "${BACKUP_DS}"
  echo "[INFO] DS backup completed: ${BACKUP_DS}"

  echo ""
  echo "========================================="
  echo " Backup Complete"
  echo " Next: ./ds-upgrade-7.5.sh upgrade"
  echo "========================================="
}

###############################################################################
# restore — Restore to pre-upgrade state for re-testing
###############################################################################
do_restore() {
  setup_logging "restore"
  echo "========================================="
  echo " DS Restore to Pre-Upgrade State"
  echo " Date: $(date)"
  echo " Server: $(hostname)"
  echo "========================================="

  # Verify backup exists
  if [ ! -d "${BACKUP_DS}" ]; then
    echo "[FAIL] Backup not found: ${BACKUP_DS}"
    echo "[FAIL] Run './ds-upgrade-7.5.sh backup' first"
    exit 1
  fi

  # Safety check — DS_HOME must be a non-empty, absolute path containing "opendj"
  if [ -z "${DS_HOME}" ] || [[ "${DS_HOME}" != /* ]] || [[ "${DS_HOME}" != *opendj* ]]; then
    echo "[FAIL] DS_HOME looks invalid: '${DS_HOME}' — aborting to prevent data loss"
    exit 1
  fi

  # Stop DS
  stop_ds

  # Restore DS installation
  echo "--- Restoring DS installation ---"
  rm -rf "${DS_HOME}"
  cp -r "${BACKUP_DS}" "${DS_HOME}"
  echo "[INFO] DS installation restored from ${BACKUP_DS}"

  # Restore bash_profile and bashrc
  cp "${BACKUP_BASH_PROFILE}" ~/.bash_profile
  cp "${BACKUP_BASHRC}" ~/.bashrc
  echo "[INFO] bash_profile and bashrc restored"

  # Switch back to Java 11
  echo "--- Switch to Java 11 ---"
  export JAVA_HOME="${JAVA_11}"
  export PATH="${JAVA_HOME}/bin:${PATH}"
  hash -r
  echo "[INFO] JAVA_HOME set to ${JAVA_11}"
  java -version 2>&1

  # Start DS with old version
  start_ds

  # Verify restore
  echo "--- Verify DS version ---"
  "${DS_HOME}/bin/start-ds" --version 2>&1 || true

  echo "--- Verify LDAP alive ---"
  check_ldap_alive || echo "[WARN] LDAP check failed after restore"

  echo "--- Verify Replication ---"
  check_replication || echo "[WARN] Replication check returned non-zero (may still be converging)"

  echo ""
  echo "========================================="
  echo " Restore Complete — back to DS 7.1"
  echo " Next: ./ds-upgrade-7.5.sh upgrade"
  echo "========================================="
}

###############################################################################
# upgrade — Perform Java 17 + DS 7.5 upgrade
###############################################################################
do_upgrade() {
  setup_logging "upgrade"

  echo "========================================="
  echo " DS Upgrade 7.1 → 7.5"
  echo " Date: $(date)"
  echo " Server: $(hostname)"
  echo " Logs: ${LOG_DIR}"
  echo "========================================="

  # Verify backup exists
  if [ ! -d "${BACKUP_DS}" ]; then
    echo "[FAIL] No backup found. Run './ds-upgrade-7.5.sh backup' first"
    exit 1
  fi

  # Verify zip file exists before starting
  if [ ! -f "${DS_ZIP}" ]; then
    echo "[FAIL] DS upgrade zip not found: ${DS_ZIP}"
    exit 1
  fi

  #--- Pre-upgrade checks ---
  echo ""
  echo "=== Pre-Upgrade Checks ==="

  java -version 2>&1 | tee "${LOG_DIR}/pre_java_version.log"
  "${DS_HOME}/bin/start-ds" --version 2>&1 | tee "${LOG_DIR}/pre_ds_version.log" || true
  check_ldap_alive | tee "${LOG_DIR}/pre_ldap_alive.log" || true
  check_replication | tee "${LOG_DIR}/pre_replication.log" || true

  #--- Java 17 upgrade ---
  echo ""
  echo "=== Java 17 Upgrade ==="

  export JAVA_HOME="${JAVA_17}"
  export OPENDJ_JAVA_HOME="${JAVA_17}"
  export PATH="${JAVA_HOME}/bin:${PATH}"

  # Update bash_profile
  if ! grep -q "JAVA_HOME=${JAVA_17}" ~/.bash_profile 2>/dev/null; then
    cat >> ~/.bash_profile << PROFILE_EOF
export JAVA_HOME=${JAVA_17}
export PATH=\$JAVA_HOME/bin:\$PATH
PROFILE_EOF
    echo "[INFO] Java 17 config added to ~/.bash_profile"
  else
    echo "[INFO] Java 17 config already in ~/.bash_profile, skipping"
  fi

  # Update bashrc
  if ! grep -q "JAVA_HOME=${JAVA_17}" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc << BASHRC_EOF
export JAVA_HOME=${JAVA_17}
export PATH=\$JAVA_HOME/bin:\$PATH
BASHRC_EOF
    echo "[INFO] Java 17 config added to ~/.bashrc"
  else
    echo "[INFO] Java 17 config already in ~/.bashrc, skipping"
  fi

  # Copy cacerts from Java 11 to Java 17 (internal CA certs needed for replication)
  JAVA_11_CACERTS="${JAVA_11}/lib/security/cacerts"
  JAVA_17_CACERTS="${JAVA_17}/lib/security/cacerts"
  if [ -f "${JAVA_11_CACERTS}" ]; then
    # Only backup the original Java 17 cacerts once (first run)
    if [ ! -f "${BACKUP_CACERTS}" ]; then
      cp "${JAVA_17_CACERTS}" "${BACKUP_CACERTS}"
      echo "[INFO] Original Java 17 cacerts saved to ${BACKUP_CACERTS}"
    fi
    cp "${JAVA_11_CACERTS}" "${JAVA_17_CACERTS}"
    echo "[INFO] cacerts copied from Java 11 to Java 17"
  else
    echo "[WARN] Java 11 cacerts not found: ${JAVA_11_CACERTS}"
  fi

  # Update DS java.properties
  sed -i "s|^default.java-home=.*|default.java-home=${JAVA_17}|" "${DS_HOME}/config/java.properties"

  # Verify Java 17
  hash -r
  java -version 2>&1 | tee "${LOG_DIR}/post_java_version.log"
  JAVA_VER=$(java -version 2>&1 | head -1)
  if echo "${JAVA_VER}" | grep -q "17\."; then
    echo "[PASS] Java 17 is active"
  else
    echo "[FAIL] Java 17 is NOT active: ${JAVA_VER}"
    exit 1
  fi

  #--- DS upgrade ---
  echo ""
  echo "=== DS Upgrade ==="

  stop_ds

  # Extract new version
  unzip -o "${DS_ZIP}" -d "${DS_EXTRACT_DIR}"

  # Verify upgrade command exists after extraction
  if [ ! -f "${DS_HOME}/upgrade" ]; then
    echo "[FAIL] Upgrade command not found: ${DS_HOME}/upgrade"
    echo "[FAIL] Check zip file structure (expected opendj/upgrade in zip root)"
    exit 1
  fi

  # Run upgrade
  "${DS_HOME}/upgrade" --no-prompt --force 2>&1 | tee "${LOG_DIR}/upgrade_output.log"

  # Rebuild indexes
  "${DS_HOME}/bin/rebuild-index" \
    --offline \
    --baseDn "${BASE_DN}" \
    --rebuildAll 2>&1 | tee "${LOG_DIR}/rebuild_index.log"

  start_ds

  echo ""
  echo "========================================="
  echo " Upgrade Complete"
  echo " Logs: ${LOG_DIR}"
  echo " Next: ./ds-upgrade-7.5.sh verify"
  echo "========================================="
}

###############################################################################
# verify — Post-upgrade verification
###############################################################################
do_verify() {
  setup_logging "verify"

  # Find the upgrade run's log directory (not verify's own LOG_DIR)
  UPGRADE_LOG=$(ls -dt "${BACKUP_DIR}"/upgrade_logs_* 2>/dev/null \
    | grep -v "^${LOG_DIR}$" | head -1)
  if [ -z "${UPGRADE_LOG}" ]; then
    echo "[WARN] No upgrade log directory found. Run './ds-upgrade-7.5.sh upgrade' first."
    UPGRADE_LOG="${LOG_DIR}"
  fi

  echo "========================================="
  echo " Post-Upgrade Verification"
  echo " Date: $(date)"
  echo " Upgrade logs: ${UPGRADE_LOG}"
  echo " Verify logs:  ${LOG_DIR}"
  echo "========================================="

  # Upgrade log
  echo "--- Upgrade log ---"
  if [ -f "${DS_HOME}/logs/upgrade.log" ]; then
    cp "${DS_HOME}/logs/upgrade.log" "${UPGRADE_LOG}/upgrade.log"
    cat "${UPGRADE_LOG}/upgrade.log"
  else
    echo "[WARN] No upgrade.log found at ${DS_HOME}/logs/upgrade.log"
  fi

  # DS version
  echo "--- DS version ---"
  "${DS_HOME}/bin/start-ds" --version 2>&1 | tee "${UPGRADE_LOG}/post_ds_version.log" || true

  # LDAP alive
  VERIFY_FAILED=0
  echo "--- LDAP alive check ---"
  if check_ldap_alive | tee "${UPGRADE_LOG}/post_ldap_alive.log"; then
    echo "[PASS] LDAP is responding after upgrade"
  else
    echo "[FAIL] LDAP is NOT responding after upgrade"
    VERIFY_FAILED=1
  fi

  # Replication
  echo "--- Replication status ---"
  check_replication | tee "${UPGRADE_LOG}/post_replication.log" || echo "[WARN] Replication check returned non-zero (may still be converging)"

  # Summary
  echo ""
  if [ "${VERIFY_FAILED}" -eq 1 ]; then
    echo "========================================="
    echo " Verification FAILED"
    echo "========================================="
  else
    echo "========================================="
    echo " Verification Complete"
    echo "========================================="
  fi
  echo ""
  if [ -f "${UPGRADE_LOG}/pre_java_version.log" ]; then
    echo " Pre/Post comparison:"
    echo "   diff ${UPGRADE_LOG}/pre_java_version.log ${UPGRADE_LOG}/post_java_version.log"
    echo "   diff ${UPGRADE_LOG}/pre_ds_version.log ${UPGRADE_LOG}/post_ds_version.log"
    echo "   diff ${UPGRADE_LOG}/pre_replication.log ${UPGRADE_LOG}/post_replication.log"
  fi
  echo ""
  echo " To re-test: ./ds-upgrade-7.5.sh restore"
  echo "========================================="

  if [ "${VERIFY_FAILED}" -eq 1 ]; then
    exit 1
  fi
}

###############################################################################
# Main
###############################################################################
ACTION="${1:-}"

case "${ACTION}" in
  backup)
    do_backup
    ;;
  upgrade)
    do_upgrade
    ;;
  verify)
    do_verify
    ;;
  restore)
    do_restore
    ;;
  *)
    echo "Usage: $0 {backup|upgrade|verify|restore}"
    echo ""
    echo "  backup   Save current state (run once before first upgrade)"
    echo "  upgrade  Perform Java 17 + DS 7.5 upgrade"
    echo "  verify   Post-upgrade verification"
    echo "  restore  Restore to pre-upgrade state (for re-testing)"
    echo ""
    echo "Test cycle: backup → upgrade → verify → restore → upgrade → verify → ..."
    exit 1
    ;;
esac
