#!/usr/bin/env bash
# ============================================================
# generate-kubeconfig.sh
#
# Creates a kubeconfig for the github-actions-deployer
# ServiceAccount and prints the base64-encoded value ready
# for the KUBE_CONFIG_DATA GitHub Actions secret.
#
# Prerequisites:
#   - kubectl pointing at the target cluster (active context)
#   - deploy/cicd-service-account.yaml already applied
#
# Usage:
#   ./scripts/generate-kubeconfig.sh
#   ./scripts/generate-kubeconfig.sh > my-kubeconfig.yaml
# ============================================================

set -euo pipefail

SERVICE_ACCOUNT="github-actions-deployer"
NAMESPACE="kube-system"
SECRET_NAME="github-actions-deployer-token"

# --- 1. Grab the bearer token from the Secret ---
echo "Fetching token from Secret/${SECRET_ACCOUNT}..." >&2
TOKEN=$(kubectl -n "${NAMESPACE}" get secret "${SECRET_NAME}" \
    -o jsonpath='{.data.token}' | base64 -d)

if [ -z "${TOKEN}" ]; then
    echo "ERROR: Could not retrieve token. Make sure deploy/cicd-service-account.yaml is applied." >&2
    exit 1
fi

# --- 2. Grab cluster info ---
CLUSTER_NAME=$(kubectl config current-context 2>/dev/null || echo "local")
SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CA_DATA=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')

# --- 3. Build the kubeconfig ---
KUBECONFIG=$(cat <<EOF
apiVersion: v1
kind: Config
clusters:
  - cluster:
      certificate-authority-data: ${CA_DATA}
      server: ${SERVER}
      insecure-skip-tls-verify: true
    name: ${CLUSTER_NAME}
contexts:
  - context:
      cluster: ${CLUSTER_NAME}
      user: ${SERVICE_ACCOUNT}
      namespace: default
    name: ${SERVICE_ACCOUNT}-context
current-context: ${SERVICE_ACCOUNT}-context
preferences: {}
users:
  - name: ${SERVICE_ACCOUNT}
    user:
      token: ${TOKEN}
EOF
)

# --- 4. Output ---
echo "Kubeconfig generated successfully." >&2
echo "Base64-encoded value for KUBE_CONFIG_DATA GitHub secret:" >&2
echo "---" >&2
echo "${KUBECONFIG}" | base64 -w0
echo "" >&2
echo "---" >&2
echo "" >&2
echo "Raw kubeconfig:" >&2
echo "${KUBECONFIG}"