#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging setup
LOG_DIR="${SCRIPT_ROOT}/../logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/teardown-$(date -u +%Y%m%d-%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1
log() { printf "[%s] %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
trap 'log "Script exited with status $?"' EXIT

declare -A releases=(
    ["ciso-assistant"]="grc"
    ["zammad"]="managed-it"
    ["mcaas-wazuh"]="security-ops"
    ["mcaas-shuffle"]="security-ops"
    ["mcaas-opensearch"]="security-ops"
    ["mcaas-postgresql"]="managed-it"
)

for release in "${!releases[@]}"; do
    namespace="${releases[$release]}"
    log "Uninstalling Helm release '$release' from namespace '$namespace'..."
    if helm status "$release" --namespace "$namespace" &> /dev/null; then
        helm uninstall "$release" --namespace "$namespace"
    else
        log "Release '$release' not found, skipping."
    fi
done

log "Deleting Wazuh resources and namespace..."
TMP_DIR="$(cd "${SCRIPT_ROOT}/.." && pwd)/.tmp"
WAZUH_ENV="${TMP_DIR}/wazuh-kubernetes/envs/local-env"
if [ -d "$WAZUH_ENV" ]; then
    kubectl delete -k "$WAZUH_ENV" --ignore-not-found=true
fi
kubectl delete namespace wazuh --ignore-not-found=true

log "Cleaning up cloned repositories..."
mkdir -p "${TMP_DIR}"
log "Cleaning up cloned repositories in ${TMP_DIR}..."
rm -rf "${TMP_DIR}/wazuh-kubernetes" "${TMP_DIR}/shuffle"

log "Deleting persistent volume claims..."
kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=true
kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=true

kubectl delete -k "${SCRIPT_ROOT}/../deploy" --ignore-not-found=true

log "Teardown complete. Logs written to ${LOG_FILE}"
