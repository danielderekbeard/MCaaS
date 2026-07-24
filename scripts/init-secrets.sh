#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_ROOT}/../.env"

# Logging setup
LOG_DIR="${SCRIPT_ROOT}/../logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/init-secrets-$(date -u +%Y%m%d-%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1
log() { printf "[%s] %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
trap 'log "Script exited with status $?"' EXIT

kubectl create namespace managed-it --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace security-ops --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace grc --dry-run=client -o yaml | kubectl apply -f -

kubectl -n managed-it create secret generic mcaas-postgresql-secret \
  --from-literal=postgres-password="${MCAAS_POSTGRES_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n security-ops create secret generic mcaas-opensearch-secret \
  --from-literal=opensearch-password="${MCAAS_OPENSEARCH_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

log "Secrets created. Logs written to ${LOG_FILE}"
