# MCaaS Installation Guide

> **Status: DRAFT — Not for commit**  
> Generated from session analysis of scripts/deploy.py and deployment stack configuration.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Deployment Sequence & Expected Wait Times](#deployment-sequence--expected-wait-times)
4. [Step-by-Step Walkthrough](#step-by-step-walkthrough)
5. [Post-Deployment Verification](#post-deployment-verification)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Minimum Version | Verify Command |
|------|----------------|----------------|
| **kubectl** | v1.25+ | `kubectl version --client` |
| **helm** | v3.8+ | `helm version` |
| **git** | 2.30+ | `git --version` |
| **openssl** | Any | `openssl version` |
| **Python** | 3.8+ | `python --version` |
| **k3s/k3d/Rancher Desktop** | Any | `kubectl cluster-info` |

> **Windows users**: Git Bash or WSL2 is recommended. `scripts/deploy.py` handles Windows
> edge cases (symlinks, path separators, OpenSSL discovery), but ensure
> `git` is on your PATH.

### Cluster Requirements

- Single-node k3s or compatible Kubernetes cluster
- At least **8 GB RAM** and **4 CPU cores** allocated to the cluster
- **40 GB** of available storage for PersistentVolume claims
- Default StorageClass with a dynamic provisioner (e.g., `local-path`)

---

## Quick Start

```bash
# 1. Set required environment variables (or create .env file)
export MCAAS_POSTGRES_PASSWORD="your-secure-password"
export MCAAS_OPENSEARCH_PASSWORD="your-secure-password"

# 2. Run the deployer
python scripts/deploy.py

# 3. Wait approximately 45–60 minutes for all components to come online.

# 4. Access services (see Services Matrix for URLs and credentials)
```

> If you omit the passwords, `scripts/deploy.py` will generate random 24-character
> passwords and save them to a `.env` file in the project root. **Back this
> file up** — it is required for redeployments.

---

## Deployment Sequence & Expected Wait Times

The table below shows the order in which components are deployed, the timeout
configured in `scripts/deploy.py`, and the **expected real-world wait time** on a
single-node k3s cluster (8 GB RAM, 4 vCPU, SSD storage).

| # | Component | Helm Timeout | Additional Waits | Expected Wall-Clock Time | Cumulative |
|---|-----------|-------------|-------------------|--------------------------|------------|
| 0 | Namespaces + ServiceAccount | — | — | < 5 sec | ~0 min |
| 1 | Secrets creation | — | — | < 5 sec | ~0 min |
| 2 | Helm repo add + update | — | — | 10–30 sec | ~0.5 min |
| 3 | **PostgreSQL** | 5m | `wait_for_resource` | 2–4 min | ~4 min |
| 4 | **OpenSearch** | 10m | `wait_for_resource` | 5–10 min | ~14 min |
| 5 | **Wazuh** | — | 3× `kubectl wait` 10m each | 8–15 min | ~29 min |
| 6 | **Shuffle** | 8m | `wait_for_resource` | 4–8 min | ~37 min |
| 7 | **Zammad** | 8m | 3× `wait_for_resource` | 5–10 min | ~47 min |
| 8 | **CISO Assistant** | 8m | 2× `wait_for_resource` | 4–8 min | ~55 min |

### Total Estimated Deployment Time: **45–60 minutes**

> **Why OpenSearch takes so long**: The OpenSearch container image is ~1.2 GB.
> On first deployment, pulling and extracting the image can take 3–5 minutes
> alone. The init containers then run security plugins, which adds another
> 2–5 minutes before the pod reports Ready.

> **Why Wazuh has three wait lines**: Wazuh deploys three separate workloads
> (manager, indexer, dashboard), each with its own `kubectl wait` command.
> They deploy in parallel via kustomize, but each pod may take several minutes
> to become ready.

---

## Step-by-Step Walkthrough

### Step 0: Configure Environment

Create a `.env` file in the project root:

```env
MCAAS_POSTGRES_PASSWORD=MySecurePostgresP@ssw0rd!
MCAAS_OPENSEARCH_PASSWORD=MySecureOpenSearchP@ssw0rd!
```

Or export them directly:

```bash
export MCAAS_POSTGRES_PASSWORD="..."
export MCAAS_OPENSEARCH_PASSWORD="..."
```

### Step 1: Run scripts/deploy.py

```bash
python scripts/deploy.py
```

**What happens automatically:**

1. ✅ Prerequisites check (kubectl, helm, git, openssl)
2. ✅ Namespaces created (`security-ops`, `managed-it`, `grc`, `wazuh`)
3. ✅ ServiceAccount created (`github-actions-deployer`)
4. ✅ Secrets created (`mcaas-postgresql-secret`, `mcaas-opensearch-secret`)
5. ✅ Helm repos added (bitnami, opensearch, zammad)
6. ✅ PostgreSQL deployed via Helm
7. ✅ OpenSearch deployed via Helm
8. ✅ Wazuh repo cloned + deployed via kustomize
9. ✅ Shuffle deployed via OCI Helm chart
10. ✅ Zammad deployed via Helm
11. ✅ CISO Assistant deployed via OCI Helm chart

### Step 2: Monitor Progress

In a separate terminal, watch pod status:

```bash
# All namespaces
kubectl get pods -A -w

# Per-component
kubectl get pods -n managed-it -w    # PostgreSQL, Zammad
kubectl get pods -n security-ops -w   # OpenSearch, Shuffle
kubectl get pods -n wazuh -w          # Wazuh
kubectl get pods -n grc -w            # CISO Assistant
```

### Step 3: Check Helm Releases

```bash
helm list -A
```

Expected output:

| NAME | NAMESPACE | STATUS | CHART | APP VERSION |
|------|-----------|--------|-------|-------------|
| mcaas-postgresql | managed-it | deployed | postgresql-*.x.x | 16.x |
| mcaas-opensearch | security-ops | deployed | opensearch-*.x.x | 2.x |
| mcaas-shuffle | security-ops | deployed | shuffle-*.x.x | 2.x |
| zammad | managed-it | deployed | zammad-*.x.x | *.x |
| ciso-assistant | grc | deployed | ciso-assistant-*.x.x | 0.x |

---

## Post-Deployment Verification

After all pods are Running and Helm releases show "deployed":

```bash
# Verify PostgreSQL connectivity
kubectl run psql-test --rm -it --restart=Never \
  --image=postgres:16 --namespace managed-it -- \
  pg_isready -h mcaas-postgresql-postgresql -p 5432 -U postgres

# Verify OpenSearch health
kubectl port-forward -n security-ops svc/mcaas-opensearch 9200:9200 &
curl -k -u admin:$(grep MCAAS_OPENSEARCH_PASSWORD .env | cut -d= -f2) \
  https://localhost:9200/_cluster/health?pretty

# Verify Wazuh Dashboard
kubectl port-forward -n wazuh svc/wazuh-dashboard 5601:443 &
# Open https://localhost:5601 in browser (accept self-signed cert)

# Verify Shuffle
kubectl port-forward -n security-ops svc/shuffle-backend 3008:3008 &
# Open http://localhost:3008 in browser

# Verify Zammad (via port-forward if no ingress)
kubectl port-forward -n managed-it svc/zammad-web 8080:80 &
# Open http://localhost:8080 in browser

# Verify CISO Assistant (via ingress — https://strategos.mcaas.example.com)
# Or via port-forward for debugging:
# kubectl port-forward -n grc svc/mcaas-ciso-ciso-assistant-frontend 8443:80
```

---

## Troubleshooting

### OpenSearch Helm Release Shows "failed" But Pod Is Running

This can happen if Helm times out before OpenSearch finishes initializing,
but the pod eventually becomes Ready on its own.

**Fix**: Re-run the Helm install command:

```bash
helm upgrade --install mcaas-opensearch opensearch/opensearch \
  --namespace security-ops \
  --values deploy/values/opensearch.yaml \
  --wait --timeout 10m
```

### Pod Stuck in `ImagePullBackOff`

The container image is still downloading. Wait a few more minutes or check:

```bash
kubectl describe pod <pod-name> -n <namespace>
```

### PVC Stuck in `Pending`

The StorageClass provisioner hasn't bound the volume yet. Verify:

```bash
kubectl get storageclass
kubectl get pvc -A
```

Wazuh uses `wazuh-storage` (mapped to `rancher.io/local-path` by scripts/deploy.py).
Other components use the default `local-path` StorageClass.

### Wazuh Certificates Missing

On Windows, `scripts/deploy.py` automatically generates self-signed certificates
using `ensure_wazuh_certs()`. If this fails:

1. Verify OpenSSL is discoverable: `python -c "import shutil; print(shutil.which('openssl'))"`
2. Check `scripts/deploy.py` logs for the OpenSSL discovery path

### Shuffle Frontend CrashLoopBackOff

If the Shuffle frontend pod fails with DNS errors, verify that
`fullnameOverride: shuffle` is set in `deploy/values/shuffle.yaml`. This
ensures the backend service is named `shuffle-backend`, which the frontend
nginx configuration expects.

---

## Teardown

To remove all MCaaS resources from your local/single-node cluster:

```bash
# Default (mcaas) deployment
python scripts/teardown.py

# Client-specific deployment
python scripts/teardown.py --client <client-name>

# Skip PVC deletion if you want to preserve data volumes
python scripts/teardown.py --skip-pvcs

# Skip namespace deletion (useful for shared clusters)
python scripts/teardown.py --skip-namespaces

# Skip .tmp/ cleanup (keeps cloned chart repos for inspection)
python scripts/teardown.py --skip-cleanup
```

### What scripts/teardown.py Does

| Step | Action | Resources Removed |
|------|--------|-------------------|
| 1 | Verify cluster connectivity | — (pre-check) |
| 2 | Uninstall Helm releases | PostgreSQL, OpenSearch, Shuffle, Zammad, CISO Assistant |
| 3 | Delete Wazuh kustomize resources | Wazuh manager, indexer, dashboard |
| 4 | Delete secrets | `mcaas-postgresql-secret`, `mcaas-opensearch-secret`, etc. |
| 5 | Delete PVCs | All persistent volume claims in MCaaS namespaces |
| 6 | Delete namespaces | `managed-it`, `security-ops`, `grc`, `wazuh` (or client-prefixed) |
| 7 | Clean up `.tmp/` | Remove cloned chart repos |

> **Note:** `scripts/teardown.py` injects `--insecure-skip-tls-verify` automatically for self-signed clusters (k3s, Rancher Desktop).

### ⚠️ For AWS/EKS Deployments — Two Steps Required

If you are running on AWS EKS, `scripts/teardown.py` only removes Kubernetes resources (Step 1). You must **also** destroy the EKS cluster separately:

```bash
# Step 1: Remove K8s resources (triggers ALB/NLB/EBS cleanup)
python scripts/teardown.py --client aws

# Step 2: Destroy the EKS cluster
python scripts/deploy-aws.py --tear-down
```

> **CRITICAL:** Always run Step 1 **before** Step 2. If you delete the EKS cluster first, Kubernetes cannot issue the delete calls that trigger cleanup of AWS load balancers and EBS volumes — leaving orphaned resources that continue to incur costs.

See [AWS Deployment Guide — Teardown](./aws-deployment.md#teardown) for the complete AWS teardown procedure including post-teardown cleanup verification.

---

*See also: [Services Matrix](./services-matrix.md) | [Configuration Matrix](./configuration-matrix.md) | [Retry & Timeout Recommendations](./retry-timeout-recommendations.md) | [AWS Deployment Guide](./aws-deployment.md)*