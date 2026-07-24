#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_ROOT}/../.env" 2>/dev/null || true

# Logging setup: create logs directory and capture stdout/stderr to a per-run logfile
LOG_DIR="${SCRIPT_ROOT}/../logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/deploy-$(date -u +%Y%m%d-%H%M%SZ).log"
# tee preserves console output while appending to logfile
exec > >(tee -a "${LOG_FILE}") 2>&1
log() { printf "[%s] %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
trap 'log "Script exited with status $?"' EXIT

# Helper function to wait for a deployment to be ready
wait_for_deployment() {
    local namespace="$1"
    local deployment_name="$2"
    local timeout="${3:-5m}"
    log "Waiting for deployment '$deployment_name' in namespace '$namespace' to be ready..."
    kubectl wait --for=condition=available --namespace "$namespace" "deployment/$deployment_name" --timeout="$timeout"
    log "Deployment '$deployment_name' is ready."
}

log "Adding and updating Helm repositories..."
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add opensearch https://opensearch-project.github.io/helm-charts # Wazuh uses this for its indexer
helm repo add zammad https://zammad.github.io/zammad-helm
helm repo update

kubectl apply -k "${SCRIPT_ROOT}/../deploy"

helm upgrade --install mcaas-postgresql bitnami/postgresql \
  --namespace managed-it \
  --values "${SCRIPT_ROOT}/../deploy/values/postgresql.yaml" \
  --wait --timeout 5m

helm upgrade --install mcaas-opensearch opensearch/opensearch \
  --namespace security-ops \
  --values "${SCRIPT_ROOT}/../deploy/values/opensearch.yaml" \
  --wait --timeout 5m

log "Cloning Wazuh and Shuffle repositories..."
[[ -d /tmp/wazuh-kubernetes ]] || git clone --depth 1 https://github.com/wazuh/wazuh-kubernetes.git /tmp/wazuh-kubernetes
[[ -d /tmp/shuffle ]] || git clone --depth 1 https://github.com/shuffle/shuffle.git /tmp/shuffle

log "Deploying Wazuh from manifests..."
kubectl apply -k /tmp/wazuh-kubernetes/envs/local-env

log "Waiting for Wazuh components to be ready..."
kubectl wait --for=condition=ready pod -l app=wazuh-manager -n security-ops --timeout=5m
kubectl wait --for=condition=ready pod -l app=wazuh-indexer -n security-ops --timeout=5m
kubectl wait --for=condition=ready pod -l app=wazuh-dashboard -n security-ops --timeout=5m

log "Deploying Shuffle..."
helm upgrade --install mcaas-shuffle /tmp/shuffle/deploy/helm/shuffle \
  --namespace security-ops \
  --values "${SCRIPT_ROOT}/../deploy/values/shuffle.yaml" \
  --wait --timeout 5m
wait_for_deployment "security-ops" "mcaas-shuffle"

log "Deploying Zammad..."
helm upgrade --install zammad zammad/zammad \
  --namespace managed-it \
  --values "${SCRIPT_ROOT}/../deploy/values/zammad.yaml" \
  --wait --timeout 5m
wait_for_deployment "managed-it" "zammad-zammad-scheduler"
wait_for_deployment "managed-it" "zammad-zammad-websocket"
wait_for_deployment "managed-it" "zammad-zammad-web"

log "Deploying CISO Assistant..."
helm upgrade --install ciso-assistant oci://ghcr.io/intuitem/ca-helm-chart/ciso-assistant \
  --version 0.1.0 \
  --namespace grc \
  --values "${SCRIPT_ROOT}/../deploy/values/ciso-assistant.yaml" \
  --wait --timeout 5m
wait_for_deployment "grc" "ciso-assistant-frontend"
wait_for_deployment "grc" "ciso-assistant-backend"

log "Deployment complete. Logs written to ${LOG_FILE}"
