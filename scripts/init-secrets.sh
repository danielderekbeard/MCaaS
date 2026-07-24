#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging setup
LOG_DIR="${SCRIPT_ROOT}/../logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/init-secrets-$(date -u +%Y%m%d-%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1
log() { printf "[%s] %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
trap 'log "Script exited with status $?"' EXIT

# Load environment variables from .env file if present
ENV_FILE="${SCRIPT_ROOT}/../.env"
if [ -f "${ENV_FILE}" ]; then
    log "Loading environment from ${ENV_FILE}"
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
else
    log "Warning: No .env file found at ${ENV_FILE}."
    log "Ensure MCAAS_POSTGRES_PASSWORD and MCAAS_OPENSEARCH_PASSWORD are set in the environment."
fi

# Validate required environment variables
if [ -z "${MCAAS_POSTGRES_PASSWORD:-}" ]; then
    log "ERROR: MCAAS_POSTGRES_PASSWORD is not set. Set it in .env or export it before running this script."
    exit 1
fi
if [ -z "${MCAAS_OPENSEARCH_PASSWORD:-}" ]; then
    log "ERROR: MCAAS_OPENSEARCH_PASSWORD is not set. Set it in .env or export it before running this script."
    exit 1
fi

kubectl create namespace managed-it --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace security-ops --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace grc --dry-run=client -o yaml | kubectl apply -f -

# PostgreSQL secret: includes both 'postgres-password' (Bitnami) and 'password' (CISO Assistant) keys
kubectl -n managed-it create secret generic mcaas-postgresql-secret \
  --from-literal=postgres-password="${MCAAS_POSTGRES_PASSWORD}" \
  --from-literal=password="${MCAAS_POSTGRES_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n security-ops create secret generic mcaas-opensearch-secret \
  --from-literal=opensearch-password="${MCAAS_OPENSEARCH_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

log "Secrets created. Logs written to ${LOG_FILE}"
