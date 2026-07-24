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

log "Starting MCaaS teardown..."

# --- Uninstall Helm Releases ---
# Use a map to store release names and their namespaces.
declare -A releases=(
    ["ciso-assistant"]="grc"
    ["zammad"]="managed-it"
    ["mcaas-shuffle"]="security-ops"
    ["mcaas-opensearch"]="security-ops"
    ["mcaas-postgresql"]="managed-it"
)

for release in "${!releases[@]}"; do
    namespace="${releases[$release]}"
    # Check if the release exists before trying to uninstall
    if helm status "$release" --namespace "$namespace" &> /dev/null; then
        log "Uninstalling Helm release '$release' from namespace '$namespace'..."
        helm uninstall "$release" --namespace "$namespace"
    else
        log "Helm release '$release' not found, skipping."
    fi
done

# --- Delete Manifest-Based Deployments (Wazuh) ---
log "Deleting Wazuh resources from manifests..."
# Clone the repo to get the kustomization files for deletion
[[ -d /tmp/wazuh-kubernetes ]] || git clone --depth 1 https://github.com/wazuh/wazuh-kubernetes.git /tmp/wazuh-kubernetes
kubectl delete -k /tmp/wazuh-kubernetes/envs/local-env --ignore-not-found=true

# --- Delete Persistent Volume Claims ---
log "Deleting persistent volume claims..."
kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=true
kubectl delete pvc -n security-ops -l app=wazuh-indexer --ignore-not-found=true
kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=true

# --- Delete Namespaces and other base resources ---
log "Deleting resources from kustomization (including namespaces)..."
kubectl delete -k "${SCRIPT_ROOT}/../deploy" --ignore-not-found=true

log "Cleaning up cloned repositories..."
rm -rf /tmp/wazuh-kubernetes /tmp/shuffle

log "Teardown complete. Logs written to ${LOG_FILE}"