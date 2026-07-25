#!/bin/bash
# Wazuh NLB Service Annotations for AWS EKS
# ============================================
# Configure which Wazuh services are internet-facing vs internal.
#
# Dashboard and Manager need to be internet-facing (accessed by users/agents).
# Indexer and Workers should be internal-only (cluster-internal communication).
#
# IMPORTANT: Do NOT use `service.beta.kubernetes.io/aws-load-balancer-internal: 0.0.0.0/0`
# This is a legacy annotation that conflicts with the `scheme` annotation and causes
# the AWS LB Controller to fail reconciliation with: "failed to parse bool annotation"
#
# Note: Changing the scheme annotation causes AWS LB Controller to delete the old NLB
# and create a new one. This results in a new DNS name and ~60-120 seconds of downtime.
#
# Note: The Wazuh kustomize deployment creates two "indexer" services:
#   - indexer (LoadBalancer) - the NLB service for external access
#   - wazuh-indexer (ClusterIP headless) - internal cluster communication
# Make sure to annotate the correct service! Use `kubectl get svc -n wazuh` to verify.

set -e

NAMESPACE="wazuh"

echo "Setting Wazuh NLB annotations..."

# Dashboard - internet-facing (users access via browser)
echo "  dashboard: internet-facing"
kubectl annotate svc dashboard -n "$NAMESPACE" \
  service.beta.kubernetes.io/aws-load-balancer-scheme=internet-facing \
  --overwrite

# Manager - internet-facing (agents connect over the internet)
echo "  wazuh (manager): internet-facing"
kubectl annotate svc wazuh -n "$NAMESPACE" \
  service.beta.kubernetes.io/aws-load-balancer-scheme=internet-facing \
  --overwrite

# Indexer - internal-only (cluster-internal search engine)
echo "  indexer: internal"
kubectl annotate svc indexer -n "$NAMESPACE" \
  service.beta.kubernetes.io/aws-load-balancer-scheme=internal \
  --overwrite

# Workers - internal-only (internal agent communication)
echo "  wazuh-workers: internal"
kubectl annotate svc wazuh-workers -n "$NAMESPACE" \
  service.beta.kubernetes.io/aws-load-balancer-scheme=internal \
  --overwrite

# Remove any conflicting legacy internal annotation from all services
echo "Removing conflicting legacy annotations..."
for svc in dashboard wazuh indexer wazuh-workers; do
  kubectl annotate svc "$svc" -n "$NAMESPACE" \
    service.beta.kubernetes.io/aws-load-balancer-internal- \
    --overwrite 2>/dev/null || true
done

echo ""
echo "Done! NLB annotations applied."
echo ""
echo "Note: If scheme changed from internet-facing to internal (or vice versa),"
echo "the AWS LB Controller will delete the old NLB and create a new one."
echo "This takes ~60-120 seconds. Check with:"
echo "  kubectl get svc -n wazuh -o wide"
echo "  aws elbv2 describe-load-balancers --region eu-west-1 --query 'LoadBalancers[?contains(LoadBalancerName, \`wazuh\`)].[LoadBalancerName, Scheme, State.Code]'"