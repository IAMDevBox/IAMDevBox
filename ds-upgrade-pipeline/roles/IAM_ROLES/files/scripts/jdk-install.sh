#!/bin/bash
#
# JDK Install/Rollback Script
#
# Usage:
#   ./jdk-upgrade.sh upgrade   # Install JDK 17
#   ./jdk-upgrade.sh restore  # Rollback to JDK 11
#
# All variables can be overridden via environment:
#   JAVA_11=/opt/app/java/jdk-11 ./jdk-install.sh upgrade

set -euo pipefail

JAVA_11="${JAVA_11:-/opt/sso/java/jdk-11.0.12+7}"
JAVA_17="${JAVA_17:-/opt/sso/java/jdk-17}"
JAVA_BASE="$(dirname "${JAVA_17}")"
INSTALL_DIR="${INSTALL_DIR:-/opt/sso/install}"
JDK_TAR_FILE="${JDK_TAR_FILE:-openjdk-17.0.2_linux-x64_bin.tar.gz}"

ACTION="${1:-}"
JDK_TAR="${INSTALL_DIR}/${JDK_TAR_FILE}"

###############################################################################
# upgrade — Install JDK 17 if not already present
###############################################################################
do_upgrade() {
  if [ -x "${JAVA_17}/bin/java" ]; then
    echo "[INFO] JDK 17 already installed at ${JAVA_17}"
    "${JAVA_17}/bin/java" -version 2>&1
    return 0
  fi

  echo "--- Installing JDK 17 ---"

  if [ ! -f "${JDK_TAR}" ]; then
    echo "[FAIL] JDK 17 package not found: ${JDK_TAR}"
    exit 1
  fi

  mkdir -p "${JAVA_BASE}"

  # Extract — tar.gz contains jdk-17.x.x/ directory
  echo "[INFO] Extracting $(du -h "${JDK_TAR}" | cut -f1) to ${JAVA_BASE} ..."
  tar -xzf "${JDK_TAR}" -C "${JAVA_BASE}"
  echo "[INFO] Extraction complete"

  # Rename extracted jdk-17.* directory to the generic JAVA_17 path
  _extracted=$(ls -d "${JAVA_BASE}"/jdk-17.* 2>/dev/null | head -1)
  if [ -n "${_extracted}" ] && [ "${_extracted}" != "${JAVA_17}" ]; then
    echo "[INFO] Renaming ${_extracted} → ${JAVA_17}"
    mv "${_extracted}" "${JAVA_17}"
  fi

  # Verify
  if [ ! -x "${JAVA_17}/bin/java" ]; then
    echo "[FAIL] JDK 17 installation failed — ${JAVA_17}/bin/java not found"
    exit 1
  fi

  "${JAVA_17}/bin/java" -version 2>&1
  echo "[INFO] JDK 17 installed at ${JAVA_17}"

  # Update JAVA_HOME in bash_profile
  if grep -q '^export JAVA_HOME=' ~/.bash_profile 2>/dev/null; then
    sed -i "s|^export JAVA_HOME=.*|export JAVA_HOME=${JAVA_17}|" ~/.bash_profile
  else
    echo "export JAVA_HOME=${JAVA_17}" >> ~/.bash_profile
    echo 'export PATH=$JAVA_HOME/bin:$PATH' >> ~/.bash_profile
  fi
  echo "[INFO] Java 17 settings applied to ~/.bash_profile"
  echo ""
  echo "[INFO] Run 'source ~/.bash_profile' to activate in current session"
}

###############################################################################
# restore — Switch back to JDK 11
###############################################################################
do_restore() {
  echo "--- Rollback to Java 11 ---"

  # Update JAVA_HOME back to Java 11 in bash_profile
  if grep -q '^export JAVA_HOME=' ~/.bash_profile 2>/dev/null; then
    sed -i "s|^export JAVA_HOME=.*|export JAVA_HOME=${JAVA_11}|" ~/.bash_profile
  else
    echo "export JAVA_HOME=${JAVA_11}" >> ~/.bash_profile
    echo 'export PATH=$JAVA_HOME/bin:$PATH' >> ~/.bash_profile
  fi
  echo "[INFO] Java 11 settings applied to ~/.bash_profile"

  export JAVA_HOME="${JAVA_11}"
  export PATH="${JAVA_HOME}/bin:${PATH}"
  hash -r

  echo "[INFO] JAVA_HOME=${JAVA_11}"
  java -version 2>&1
  echo ""
  echo "[INFO] Run 'source ~/.bash_profile' to activate in current session"
}

###############################################################################
# Main
###############################################################################
case "${ACTION}" in
  upgrade)
    do_upgrade
    ;;
  restore)
    do_restore
    ;;
  *)
    echo "Usage: $0 {upgrade|restore}"
    echo ""
    echo "  upgrade  Install JDK 17"
    echo "  restore  Switch back to JDK 11"
    exit 1
    ;;
esac
