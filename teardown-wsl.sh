#!/bin/sh
# MCaaS Teardown Script - POSIX sh Version

set -e

SCRIPT_ROOT="/mnt/c/projects/skyddex/MCaaS"
LOG_DIR="${SCRIPT_ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/teardown-$(date -u +%Y%m%d-%H%M%SZ).log"

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting MCaaS teardown..." | tee -a "${LOG_FILE}"

# --- Uninstall Helm Releases ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Uninstalling Helm releases..." | tee -a "${LOG_FILE}"

for release in mcaas-ciso mcaas-zammad mcaas-shuffle mcaas-opensearch mcaas-postgresql; do
    case $release in
        mcaas-ciso) namespace="grc" ;;
        mcaas-zammad) namespace="managed-it" ;;
        mcaas-shuffle) namespace="security-ops" ;;
        mcaas-opensearch) namespace="security-ops" ;;
        mcaas-postgresql) namespace="managed-it" ;;
    esac
    
    if helm status "$release" --namespace "$namespace" 2>/dev/null >/dev/null; then
        echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Uninstalling Helm release '$release' from namespace '$namespace'..." | tee -a "${LOG_FILE}"
        helm uninstall "$release" --namespace "$namespace" 2>&1 | tee -a "${LOG_FILE}"
    else
        echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Helm release '$release' not found, skipping." | tee -a "${LOG_FILE}"
    fi
done

# --- Delete Manifest-Based Deployments (Wazuh) ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Deleting Wazuh resources and namespace..." | tee -a "${LOG_FILE}"
TMP_DIR="${SCRIPT_ROOT}/.tmp"
WAZUH_ENV="${TMP_DIR}/wazuh-kubernetes/envs/local-env"
if [ -d "$WAZUH_ENV" ]; then
    kubectl delete -k "$WAZUH_ENV" --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true
fi
kubectl delete namespace wazuh --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true

# --- Delete Persistent Volume Claims ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Deleting persistent volume claims..." | tee -a "${LOG_FILE}"
kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true
kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true
kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-zammad --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true
kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-shuffle --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true
kubectl delete pvc -n wazuh -l app=wazuh-indexer --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true
kubectl delete pvc -n wazuh -l app=wazuh-manager --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true

# --- Delete Kubernetes Secrets ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Deleting Kubernetes secrets..." | tee -a "${LOG_FILE}"
kubectl delete secret mcaas-postgresql-secret --namespace managed-it --ignore-not-found=true 2>/dev/null || true
kubectl delete secret mcaas-opensearch-secret --namespace security-ops --ignore-not-found=true 2>/dev/null || true
kubectl delete secret mcaas-postgresql-secret --namespace grc --ignore-not-found=true 2>/dev/null || true
kubectl delete secret mcaas-zammad-redis-pass --namespace managed-it --ignore-not-found=true 2>/dev/null || true
kubectl delete secret mcaas-ciso-secret --namespace grc --ignore-not-found=true 2>/dev/null || true

# --- Delete Namespaces and other base resources ---
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Deleting resources from kustomization..." | tee -a "${LOG_FILE}"
kubectl delete -k "${SCRIPT_ROOT}/deploy" --ignore-not-found=true 2>&1 | tee -a "${LOG_FILE}" || true

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Cleaning up temporary files..." | tee -a "${LOG_FILE}"
rm -rf "${TMP_DIR}/wazuh-kubernetes" "${TMP_DIR}/shuffle" 2>&1 | tee -a "${LOG_FILE}" || true
rm -f "${SCRIPT_ROOT}/.env" 2>&1 | tee -a "${LOG_FILE}" || true

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Teardown complete. Logs written to ${LOG_FILE}" | tee -a "${LOG_FILE}"
echo "✅ Teardown completed successfully!"
