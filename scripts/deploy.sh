#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_ROOT}/.."
source "${PROJECT_ROOT}/.env" 2>/dev/null || true

# Logging setup: create logs directory and capture stdout/stderr to a per-run logfile
LOG_DIR="${PROJECT_ROOT}/logs"
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

# Helper: generate a random password
generate_password() {
    openssl rand -base64 24 | tr -d '=/+' | head -c 24
}

# Create required Kubernetes secrets (must happen BEFORE Helm installs)
create_secrets() {
    local env_file="${PROJECT_ROOT}/.env"
    local postgres_pw="${MCAAS_POSTGRES_PASSWORD:-}"
    local opensearch_pw="${MCAAS_OPENSEARCH_PASSWORD:-}"

    # Generate passwords if not set
    if [[ -z "$postgres_pw" || -z "$opensearch_pw" ]]; then
        if [[ ! -f "$env_file" ]]; then
            log "No .env file found. Generating passwords and creating .env file..."
            postgres_pw="${postgres_pw:-$(generate_password)}"
            opensearch_pw="${opensearch_pw:-$(generate_password)}"
            printf "MCAAS_POSTGRES_PASSWORD=%s\nMCAAS_OPENSEARCH_PASSWORD=%s\nMCAAS_REDIS_PASSWORD=zammad\n" "$postgres_pw" "$opensearch_pw" > "$env_file"
            log "Created ${env_file} with generated passwords. Back this file up for redeployments."
        else
            if [[ -z "$postgres_pw" ]]; then
                log "ERROR: MCAAS_POSTGRES_PASSWORD is not set. Set it in your .env file or environment."
                exit 1
            fi
            if [[ -z "$opensearch_pw" ]]; then
                log "ERROR: MCAAS_OPENSEARCH_PASSWORD is not set. Set it in your .env file or environment."
                exit 1
            fi
        fi
    fi

    # Generate Redis and Django secrets if not set
    local redis_pw="${MCAAS_REDIS_PASSWORD:-zammad}"
    local django_key="${MCAAS_DJANGO_SECRET_KEY:-}"

    # Generate Django secret key if not provided
    if [[ -z "$django_key" ]]; then
        django_key="$(generate_password)"
        # Append to .env file for future use
        if [[ -f "$env_file" ]]; then
            printf "\nMCAAS_DJANGO_SECRET_KEY=%s\n" "$django_key" >> "$env_file"
            log "Generated MCAAS_DJANGO_SECRET_KEY and appended to ${env_file}."
        fi
    fi

    log "Creating/updating Kubernetes secrets..."

    # 1. PostgreSQL secret in managed-it namespace (for Bitnami chart + Zammad)
    kubectl -n managed-it create secret generic mcaas-postgresql-secret \
        --from-literal=postgres-password="${postgres_pw}" \
        --from-literal=password="${postgres_pw}" \
        --dry-run=client -o yaml | kubectl apply -f -
    log "PostgreSQL secret created/updated in managed-it namespace."

    # 2. OpenSearch secret in security-ops namespace (for OpenSearch chart + Shuffle)
    kubectl -n security-ops create secret generic mcaas-opensearch-secret \
        --from-literal=opensearch-password="${opensearch_pw}" \
        --from-literal=SHUFFLE_OPENSEARCH_PASSWORD="${opensearch_pw}" \
        --dry-run=client -o yaml | kubectl apply -f -
    log "OpenSearch secret created/updated in security-ops namespace."

    # 3. Redis secret in managed-it namespace (for Zammad's Redis sub-chart)
    kubectl -n managed-it create secret generic mcaas-zammad-redis-pass \
        --from-literal=redis-password="${redis_pw}" \
        --dry-run=client -o yaml | kubectl apply -f -
    log "Redis secret created/updated in managed-it namespace."

    # 4. Cross-namespace PostgreSQL secret in grc namespace (for CISO Assistant)
    kubectl -n grc create secret generic mcaas-postgresql-secret \
        --from-literal=postgres-password="${postgres_pw}" \
        --from-literal=password="${postgres_pw}" \
        --dry-run=client -o yaml | kubectl apply -f -
    log "PostgreSQL secret created/updated in grc namespace (for CISO Assistant)."

    # 5. Django secret key for CISO Assistant in grc namespace
    kubectl -n grc create secret generic mcaas-ciso-secret \
        --from-literal=django-secret-key="${django_key}" \
        --dry-run=client -o yaml | kubectl apply -f -
    log "CISO Assistant Django secret created/updated in grc namespace."
}

# Create a database in the PostgreSQL instance (idempotent).
# Usage: create_database <db_name>
create_database() {
    local db_name="$1"
    local pod_name="mcaas-postgresql-0"
    local namespace="managed-it"
    local secret_name="mcaas-postgresql-secret"
    local secret_key="postgres-password"

    log "Ensuring database '${db_name}' exists in PostgreSQL..."
    local pw
    pw=$(kubectl get secret "${secret_name}" -n "${namespace}" -o "jsonpath={.data.${secret_key}}" 2>/dev/null | base64 -d)
    if [[ -z "$pw" ]]; then
        log "ERROR: Failed to retrieve password from secret '${secret_name}'."
        exit 1
    fi

    # Use stdin to pass SQL (avoids PowerShell quoting issues on Windows cross-compat)
    printf 'CREATE DATABASE "%s";\n' "${db_name}" | \
        kubectl exec -i -n "${namespace}" "${pod_name}" -- \
        env PGPASSWORD="${pw}" psql -U postgres -d postgres 2>/dev/null || true
    log "Database '${db_name}' ensured in PostgreSQL."
}

# Generate self-signed TLS certificates for Wazuh
ensure_wazuh_certs() {
    local wazuh_dir="$1"
    local certs_dir
    certs_dir="${wazuh_dir}/config"

    # Check if root CA already exists
    if [[ -f "${certs_dir}/root-ca/certs/root-ca.pem" ]]; then
        log "Wazuh TLS certificates already exist, skipping generation."
        return 0
    fi

    log "Generating self-signed TLS certificates for Wazuh..."

    # Create directories
    mkdir -p "${certs_dir}/root-ca/certs"
    mkdir -p "${certs_dir}/indexer/certs"
    mkdir -p "${certs_dir}/dashboard/certs"
    mkdir -p "${certs_dir}/manager/certs"

    # Generate root CA
    openssl genrsa -out "${certs_dir}/root-ca/certs/root-ca-key.pem" 4096
    openssl req -new -x509 -key "${certs_dir}/root-ca/certs/root-ca-key.pem" \
        -out "${certs_dir}/root-ca/certs/root-ca.pem" \
        -days 3650 -subj "/O=MCaaS/CN=Wazuh-Root-CA"

    # Generate indexer certificate
    openssl genrsa -out "${certs_dir}/indexer/certs/indexer-key.pem" 2048
    openssl req -new -key "${certs_dir}/indexer/certs/indexer-key.pem" \
        -out "${certs_dir}/indexer/certs/indexer.csr" \
        -subj "/O=MCaaS/CN=wazuh-indexer"
    openssl x509 -req -in "${certs_dir}/indexer/certs/indexer.csr" \
        -CA "${certs_dir}/root-ca/certs/root-ca.pem" \
        -CAkey "${certs_dir}/root-ca/certs/root-ca-key.pem" \
        -CAcreateserial -out "${certs_dir}/indexer/certs/indexer.pem" -days 3650
    cp "${certs_dir}/root-ca/certs/root-ca.pem" "${certs_dir}/indexer/certs/root-ca.pem"

    # Generate dashboard certificate
    openssl genrsa -out "${certs_dir}/dashboard/certs/dashboard-key.pem" 2048
    openssl req -new -key "${certs_dir}/dashboard/certs/dashboard-key.pem" \
        -out "${certs_dir}/dashboard/certs/dashboard.csr" \
        -subj "/O=MCaaS/CN=wazuh-dashboard"
    openssl x509 -req -in "${certs_dir}/dashboard/certs/dashboard.csr" \
        -CA "${certs_dir}/root-ca/certs/root-ca.pem" \
        -CAkey "${certs_dir}/root-ca/certs/root-ca-key.pem" \
        -CAcreateserial -out "${certs_dir}/dashboard/certs/dashboard.pem" -days 3650
    cp "${certs_dir}/root-ca/certs/root-ca.pem" "${certs_dir}/dashboard/certs/root-ca.pem"

    # Generate manager certificate
    openssl genrsa -out "${certs_dir}/manager/certs/manager-key.pem" 2048
    openssl req -new -key "${certs_dir}/manager/certs/manager-key.pem" \
        -out "${certs_dir}/manager/certs/manager.csr" \
        -subj "/O=MCaaS/CN=wazuh-manager"
    openssl x509 -req -in "${certs_dir}/manager/certs/manager.csr" \
        -CA "${certs_dir}/root-ca/certs/root-ca.pem" \
        -CAkey "${certs_dir}/root-ca/certs/root-ca-key.pem" \
        -CAcreateserial -out "${certs_dir}/manager/certs/manager.pem" -days 3650
    cp "${certs_dir}/root-ca/certs/root-ca.pem" "${certs_dir}/manager/certs/root-ca.pem"

    log "Wazuh TLS certificates generated successfully."
}

log "Adding and updating Helm repositories..."
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add opensearch https://opensearch-project.github.io/helm-charts
helm repo add zammad https://zammad.github.io/zammad-helm
helm repo update

log "Creating required Kubernetes secrets..."
create_secrets

log "Applying namespaces and base manifests..."
kubectl apply -k "${PROJECT_ROOT}/deploy"

log "Deploying PostgreSQL..."
helm upgrade --install mcaas-postgresql bitnami/postgresql \
  --namespace managed-it \
  --values "${PROJECT_ROOT}/deploy/values/postgresql.yaml" \
  --wait --timeout 5m
wait_for_deployment "managed-it" "mcaas-postgresql"

log "Deploying OpenSearch..."
helm upgrade --install mcaas-opensearch opensearch/opensearch \
  --namespace security-ops \
  --values "${PROJECT_ROOT}/deploy/values/opensearch.yaml" \
  --wait --timeout 5m
wait_for_deployment "security-ops" "mcaas-opensearch"

# Clone or use Wazuh repo
WAZUH_DIR="${PROJECT_ROOT}/.tmp/wazuh-kubernetes"
if [[ -d "${WAZUH_DIR}" ]]; then
    log "Using existing Wazuh repository at ${WAZUH_DIR}"
else
    log "Cloning Wazuh repository..."
    git clone --depth 1 --branch v4.14.6 https://github.com/wazuh/wazuh-kubernetes.git "${WAZUH_DIR}"
fi

# Generate TLS certificates for Wazuh
ensure_wazuh_certs "${WAZUH_DIR}"

log "Deploying Wazuh from manifests..."
kubectl apply -k "${WAZUH_DIR}/envs/local-env"

log "Waiting for Wazuh components to be ready..."
kubectl wait --for=condition=ready pod -l app=wazuh-manager -n wazuh --timeout=5m || true
kubectl wait --for=condition=ready pod -l app=wazuh-indexer -n wazuh --timeout=5m || true
kubectl wait --for=condition=ready pod -l app=wazuh-dashboard -n wazuh --timeout=5m || true

log "Deploying Shuffle..."
helm upgrade --install mcaas-shuffle oci://ghcr.io/shuffle/charts/shuffle \
  --namespace security-ops \
  --values "${PROJECT_ROOT}/deploy/values/shuffle.yaml" \
  --wait --timeout 5m
wait_for_deployment "security-ops" "mcaas-shuffle"

# Create the zammad database before deploying Zammad.
# Zammad's init job needs this database to exist when using an external DB.
create_database "zammad"

log "Deploying Zammad..."
helm upgrade --install mcaas-zammad zammad/zammad \
  --namespace managed-it \
  --values "${PROJECT_ROOT}/deploy/values/zammad.yaml" \
  --wait --timeout 5m
wait_for_deployment "managed-it" "mcaas-zammad-zammad-scheduler"
wait_for_deployment "managed-it" "mcaas-zammad-zammad-websocket"
wait_for_deployment "managed-it" "mcaas-zammad-zammad-web"

# Create the ciso-assistant database before deploying CISO Assistant.
create_database "ciso-assistant"

log "Deploying CISO Assistant..."
helm upgrade --install mcaas-ciso oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant \
  --version 0.11.4 \
  --namespace grc \
  --values "${PROJECT_ROOT}/deploy/values/ciso-assistant.yaml" \
  --wait --timeout 5m
wait_for_deployment "grc" "mcaas-ciso-frontend"
wait_for_deployment "grc" "mcaas-ciso-backend"

log "Deployment complete. Logs written to ${LOG_FILE}"
