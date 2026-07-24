#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging setup
LOG_DIR="${SCRIPT_ROOT}/../logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/test-services-$(date -u +%Y%m%d-%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1
log() { printf "[%s] %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
trap 'log "Script exited with status $?"' EXIT

log "Starting service health checks..."

declare -A services=(
    ["Wazuh Dashboard"]="wazuh:wazuh-dashboard:443:8443:https"
    ["Shuffle UI"]="security-ops:mcaas-shuffle:5001:8081:http"
    ["Zammad Web"]="managed-it:zammad-zammad-web:80:8082:http"
    ["CISO Assistant Frontend"]="grc:ciso-assistant-frontend:80:8083:http"
)

all_ok=true

for name in "${!services[@]}"; do
    IFS=':' read -r namespace service_name service_port local_port protocol <<< "${services[$name]}"
    
    log "Testing '$name' (service/$service_name in $namespace)..."
    
    # Start port-forward in the background
    kubectl port-forward -n "$namespace" "service/$service_name" "$local_port:$service_port" &> /dev/null &
    pf_pid=$!
    
    # Give it a moment to establish the connection
    sleep 3
    
    # Check the service with curl
    # Use --insecure for self-signed certs (like Wazuh)
    # Use -L to follow redirects
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --insecure -L --max-time 10 "${protocol}://localhost:${local_port}" || true)
    
    # Kill the background port-forward process
    kill "$pf_pid"
    wait "$pf_pid" 2>/dev/null || true
    
    if [[ "$http_code" == "200" || "$http_code" == "302" ]]; then
        log "✅ '$name' is UP. Received HTTP status $http_code."
    else
        log "❌ '$name' is DOWN or not responding correctly. Received HTTP status '$http_code'."
        all_ok=false
    fi
done

if [[ "$all_ok" == "true" ]]; then
    log "All services are up and running."
    exit 0
else
    log "One or more services failed the health check."
    exit 1
fi