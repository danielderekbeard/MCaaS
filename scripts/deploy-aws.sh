#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# MCaaS AWS/EKS Deployment Wrapper Script
# ==============================================================================
# This script validates AWS-specific prerequisites, loads environment
# variables, and delegates to the Python deployment orchestrator.
#
# Usage:
#   ./deploy-aws.sh                          # Full deployment
#   ./deploy-aws.sh --dry-run                # Preview changes
#   ./deploy-aws.sh --client aws             # Use AWS client config
#   ./deploy-aws.sh --skip-cluster            # Skip EKS cluster creation
#   ./deploy-aws.sh --skip-infrastructure     # Skip infrastructure setup
#   ./deploy-aws.sh --tear-down               # Delete EKS cluster
# ==============================================================================

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_ROOT}/.."
DEPLOYER="${PROJECT_ROOT}/scripts/deploy-aws.py"
LOG_DIR="${PROJECT_ROOT}/logs"

# Logging setup
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/deploy-aws-$(date -u +%Y%m%d-%H%M%SZ).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() { printf "[%s] %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
trap 'log "Script exited with status $?"' EXIT

# ── Prerequisite Checks ──────────────────────────────────────────────────────

check_tool() {
    local tool="$1"
    if command -v "${tool}" &>/dev/null; then
        local version
        version=$("${tool}" --version 2>/dev/null | head -1 || echo "unknown")
        log "✅ ${tool}: ${version}"
        return 0
    else
        log "❌ ${tool}: NOT FOUND"
        return 1
    fi
}

missing_tools=()

log "Checking AWS deployment prerequisites..."

check_tool python || missing_tools+=("python")
check_tool aws || missing_tools+=("aws")
check_tool eksctl || missing_tools+=("eksctl")
check_tool kubectl || missing_tools+=("kubectl")
check_tool helm || missing_tools+=("helm")
check_tool git || missing_tools+=("git")
check_tool openssl || missing_tools+=("openssl")

if [[ ${#missing_tools[@]} -gt 0 ]]; then
    log "ERROR: Missing required tools: ${missing_tools[*]}"
    log ""
    log "Install missing tools:"
    log "  aws:     https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    log "  eksctl:  https://eksctl.io/"
    log "  kubectl: https://kubernetes.io/docs/tasks/tools/"
    log "  helm:    https://helm.sh/docs/intro/install/"
    exit 1
fi

log "✅ All prerequisites present"

# ── AWS Credentials Check ────────────────────────────────────────────────────

log "Checking AWS credentials..."
if aws sts get-caller-identity &>/dev/null; then
    local_identity=$(aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null || echo "unknown")
    log "✅ AWS credentials configured: ${local_identity}"
else
    log "ERROR: AWS credentials not configured."
    log "Run 'aws configure' or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY environment variables."
    exit 1
fi

# ── Load Environment ─────────────────────────────────────────────────────────

ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    log "Loading environment from .env file..."
    set -a
    source "${ENV_FILE}"
    set +a
else
    log "⚠️  No .env file found. Using existing environment variables."
fi

# ── Run Python Deployment Orchestrator ───────────────────────────────────────

log "========================================"
log "MCaaS AWS/EKS Deployment"
log "========================================"
log "Invoking Python deployment orchestrator..."
log "Command: python ${DEPLOYER} $*"

python "${DEPLOYER}" "$@"
exit_code=$?

if [[ ${exit_code} -eq 0 ]]; then
    log "========================================"
    log "✅ AWS deployment completed successfully!"
    log "========================================"
    log "Logs written to: ${LOG_FILE}"
else
    log "========================================"
    log "❌ AWS deployment failed with exit code ${exit_code}"
    log "========================================"
    log "Check logs at: ${LOG_FILE}"
fi

exit ${exit_code}