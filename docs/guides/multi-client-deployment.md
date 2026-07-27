# Multi-Client Branch Deployment Guide

This guide explains how to use Git branches and configuration overlays to deploy the MCaaS stack for multiple clients (tenants) from a single repository. Each client gets isolated Kubernetes resources — namespaces, secrets, Helm releases, and services — while sharing the same deployment automation and upstream chart versions.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Branch Naming Convention](#2-branch-naming-convention)
3. [Client Configuration Structure](#3-client-configuration-structure)
4. [How Client Overlays Work](#4-how-client-overlays-work)
5. [Client-Specific Values Files](#5-client-specific-values-files)
6. [Secret Management Strategy](#6-secret-management-strategy)
7. [Deploying with `--client`](#7-deploying-with---client)
8. [GitHub Actions Per-Client Workflow](#8-github-actions-per-client-workflow)
9. [Step-by-Step: Onboarding a New Client](#9-step-by-step-onboarding-a-new-client)
10. [Teardown for a Client](#10-teardown-for-a-client)
11. [Reference: Hardcoded Names and Parameterization Map](#11-reference-hardcoded-names-and-parameterization-map)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

The MCaaS stack deploys six services into four namespaces:

| Service | Default Namespace | Helm Release | Chart Source |
|---------|-------------------|---------------|-------------|
| PostgreSQL | `managed-it` | `mcaas-postgresql` | Bitnami Helm |
| OpenSearch | `security-ops` | `mcaas-opensearch` | Opensearch Helm |
| Wazuh | `wazuh` | *(kustomize)* | wazuh-kubernetes repo |
| Shuffle | `security-ops` | `mcaas-shuffle` | OCI Helm |
| Zammad | `managed-it` | `mcaas-zammad` | OCI Helm |
| CISO Assistant | `grc` | `mcaas-ciso` | OCI Helm |

In the default (single-client) setup, all names are hardcoded in `scripts/deploy.py`, `deploy/values/*.yaml`, and `deploy/namespaces.yaml`. For multi-client deployments, each client gets its own prefix that isolates resources:

| Resource | Single-Client (default) | Multi-Client (e.g., `acme`) |
|----------|------------------------|------------------------------|
| PostgreSQL release | `mcaas-postgresql` | `acme-postgresql` |
| PostgreSQL namespace | `managed-it` | `acme-managed-it` |
| OpenSearch release | `mcaas-opensearch` | `acme-opensearch` |
| OpenSearch namespace | `security-ops` | `acme-security-ops` |
| Shuffle release | `mcaas-shuffle` | `acme-shuffle` |
| Zammad release | `mcaas-zammad` | `acme-zammad` |
| CISO release | `mcaas-ciso` | `acme-ciso` |
| Wazuh namespace | `wazuh` | `acme-wazuh` |
| Secret: PostgreSQL | `mcaas-postgresql-secret` | `acme-postgresql-secret` |
| Secret: OpenSearch | `mcaas-opensearch-secret` | `acme-opensearch-secret` |
| Secret: Redis | `mcaas-zammad-redis-pass` | `acme-zammad-redis-pass` |
| Secret: CISO | `mcaas-ciso-secret` | `acme-ciso-secret` |
| DB name | `mcaas_db` | `acme_db` |
| Ingress: Zammad | `zammad.mcaas.example.com` | `zammad.acme.example.com` |
| Ingress: CISO | `ciso.mcaas.example.com` | `ciso.acme.example.com` |

---

## 2. Branch Naming Convention

Each client deployment lives on its own Git branch following the pattern:

```
client/<client-name>
```

**Examples:**

| Branch | Client |
|--------|--------|
| `client/acme` | ACME Corporation |
| `client/globex` | Globex International |
| `client/initech` | Initech LLC |

**Rules:**

- Use lowercase, hyphenated names: `client/big-corp` ✅ — not `client/BigCorp` ❌
- The `<client-name>` becomes the Kubernetes resource prefix
- The `main` branch always represents the **default/single-client** deployment (no prefix)
- Never deploy directly from `main` for a client — always create a `client/` branch

**Why branches?**

- Git branches provide natural audit trails per client
- Client-specific values files are version-controlled alongside the automation
- Pull requests can review client configuration changes before deployment
- The same CI/CD pipeline works for all clients via the `--client` parameter

---

## 3. Client Configuration Structure

Each client branch adds a `clients/<client-name>/` directory with overlay configuration:

```
MCaaS/
├── deploy/
│   ├── namespaces.yaml          # Base namespaces (used when no client prefix)
│   ├── kustomization.yaml
│   ├── cicd-service-account.yaml
│   └── values/
│       ├── postgresql.yaml       # Base values
│       ├── opensearch.yaml
│       ├── shuffle.yaml
│       ├── wazuh.yaml
│       ├── zammad.yaml
│       └── ciso-assistant.yaml
├── clients/                      # ★ NEW — per-client overlay directory
│   ├── _template/                 # Template for new clients (copy this)
│   │   ├── config.yaml           # Client metadata and domain settings
│   │   ├── namespaces.yaml       # Client-prefixed namespace definitions
│   │   └── values/
│   │       ├── postgresql.yaml
│   │       ├── opensearch.yaml
│   │       ├── shuffle.yaml
│   │       ├── zammad.yaml
│   │       └── ciso-assistant.yaml
│   ├── acme/                      # Example: ACME Corporation
│   │   ├── config.yaml
│   │   ├── namespaces.yaml
│   │   └── values/
│   │       ├── postgresql.yaml
│   │       ├── opensearch.yaml
│   │       ├── shuffle.yaml
│   │       ├── zammad.yaml
│   │       └── ciso-assistant.yaml
│   └── globex/                    # Example: Globex International
│       ├── config.yaml
│       ├── namespaces.yaml
│       └── values/
│           └── ...
├── scripts/
│   ├── deploy.py
│   └── teardown.py
├── .env.example
└── .github/
    └── workflows/
        └── ...
```

The key file is `clients/<client-name>/config.yaml`, which drives all parameterization:

```yaml
# clients/acme/config.yaml
client:
  name: "acme"
  display_name: "ACME Corporation"

  # Domain suffix for ingress hosts
  domain: "acme.example.com"

  # Resource prefix applied to all Helm releases, secrets, and DB names
  # This replaces "mcaas-" in all resource names
  prefix: "acme"

  # Namespace mapping (base → client-specific)
  namespaces:
    managed-it: "acme-managed-it"
    security-ops: "acme-security-ops"
    grc: "acme-grc"
    wazuh: "acme-wazuh"

  # Kubernetes cluster context (optional — uses current context if not set)
  # kube_context: "acme-production"

  # Wazuh version (pinned per client for stability)
  wazuh_version: "4.14.6"

  # PostgreSQL database name
  database_name: "acme_db"

  # Ingress configuration
  ingress:
    zammad_host: "zammad.acme.example.com"
    ciso_host: "ciso.acme.example.com"
```

---

## 4. How Client Overlays Work

When you run `scripts/deploy.py --client acme`, the script:

1. **Reads** `clients/acme/config.yaml` to get the client prefix, namespaces, and domains
2. **Generates namespaces** from `clients/acme/namespaces.yaml` instead of the base `deploy/namespaces.yaml`
3. **Merges** client values on top of base values:
   - For each service, if `clients/acme/values/<service>.yaml` exists, it is used **instead** of the base `deploy/values/<service>.yaml`
   - Client values files contain all the same keys but with client-prefixed resource names
4. **Creates secrets** with client-prefixed names in client-prefixed namespaces
5. **Installs Helm releases** with client-prefixed release names and client-specific namespaces
6. **Configures ingress** with client-specific domain names

If `--client` is **not** specified, `scripts/deploy.py` behaves exactly as before — using `mcaas-` prefix and base values — ensuring full backward compatibility.

---

## 5. Client-Specific Values Files

Each client values file must update all cross-references to use client-prefixed names. Here's a comparison for the **Zammad** values:

### Base (`deploy/values/zammad.yaml`)
```yaml
zammadConfig:
  postgresql:
    host: "mcaas-postgresql.managed-it.svc.cluster.local"
    # ...
secrets:
  postgresql:
    secretName: "mcaas-postgresql-secret"
  redis:
    secretName: "mcaas-zammad-redis-pass"
ingress:
  hosts:
    - host: zammad.mcaas.example.com
```

### Client Overlay (`clients/acme/values/zammad.yaml`)
```yaml
zammadConfig:
  postgresql:
    host: "acme-postgresql.acme-managed-it.svc.cluster.local"
    # ...
secrets:
  postgresql:
    secretName: "acme-postgresql-secret"
  redis:
    secretName: "acme-zammad-redis-pass"
ingress:
  hosts:
    - host: zammad.acme.example.com
```

### Key Changes in Every Client Values File

| Field | Base | Client `acme` |
|-------|------|----------------|
| PostgreSQL host | `mcaas-postgresql.managed-it.svc.cluster.local` | `acme-postgresql.acme-managed-it.svc.cluster.local` |
| OpenSearch host | `opensearch-cluster-master.security-ops.svc.cluster.local` | `opensearch-cluster-master.acme-security-ops.svc.cluster.local` |
| OpenSearch secret | `mcaas-opensearch-secret` | `acme-opensearch-secret` |
| PostgreSQL secret | `mcaas-postgresql-secret` | `acme-postgresql-secret` |
| Redis secret | `mcaas-zammad-redis-pass` | `acme-zammad-redis-pass` |
| Django secret | `mcaas-ciso-secret` | `acme-ciso-secret` |
| Database name | `mcaas_db` | `acme_db` |
| Ingress hosts | `*.mcaas.example.com` | `*.acme.example.com` |

### Client-Specific `namespaces.yaml`

```yaml
# clients/acme/namespaces.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: acme-security-ops
---
apiVersion: v1
kind: Namespace
metadata:
  name: acme-managed-it
---
apiVersion: v1
kind: Namespace
metadata:
  name: acme-grc
---
apiVersion: v1
kind: Namespace
metadata:
  name: acme-wazuh
```

---

## 6. Secret Management Strategy

Each client needs its own set of secrets. There are two approaches:

### Option A: GitHub Repository Secrets (Recommended for CI/CD)

Store per-client secrets in GitHub with a naming convention:

| GitHub Secret | Value |
|---------------|-------|
| `ACME_POSTGRES_PASSWORD` | `<password>` |
| `ACME_OPENSEARCH_PASSWORD` | `<password>` |
| `ACME_REDIS_PASSWORD` | `<password>` |
| `ACME_DJANGO_SECRET_KEY` | `<key>` |
| `GLOBEX_POSTGRES_PASSWORD` | `<password>` |
| `GLOBEX_OPENSEARCH_PASSWORD` | `<password>` |
| `GLOBEX_REDIS_PASSWORD` | `<password>` |
| `GLOBEX_DJANGO_SECRET_KEY` | `<key>` |

The GitHub Actions workflow reads the client name from the `workflow_dispatch` input and maps it to the correct secrets.

### Option B: Per-Client `.env` Files (Local/Manual Deployments)

Each client branch can include a committed `.env.<client-name>` template (never `.env` itself, which is gitignored):

```bash
# .env.acme (committed as a template, values filled from secure storage)
ACME_POSTGRES_PASSWORD=
ACME_OPENSEARCH_PASSWORD=
ACME_REDIS_PASSWORD=
ACME_DJANGO_SECRET_KEY=
```

When deploying locally:

```bash
cp .env.acme .env
# Fill in values
python scripts/deploy.py --client acme
```

### Option C: External Secret Management (Production)

For production multi-client deployments, consider:

- **HashiCorp Vault** with per-client paths: `secret/data/mcaas/acme/postgresql`
- **AWS Secrets Manager** with per-client prefixes: `mcaas/acme/postgres-password`
- **Azure Key Vault** per client subscription
- **Sealed Secrets** (Bitnami) — encrypt secrets in Git, decrypt in-cluster

---

## 7. Deploying with `--client`

### Prerequisites

Before deploying for a client, ensure:

1. You are on the client branch: `git checkout client/acme`
2. The `clients/acme/` directory exists with `config.yaml` and values files
3. Your kubeconfig targets the correct cluster
4. Environment variables for that client are set (or auto-generated)

### Deployment Command

```bash
# Deploy the ACME client stack
python scripts/deploy.py --client acme

# Dry run first (recommended)
python scripts/deploy.py --client acme --dry-run

# Deploy with verbose logging
python scripts/deploy.py --client acme 2>&1 | tee logs/acme-deploy.log
```

### What `--client` Changes

When `--client acme` is specified, `scripts/deploy.py` internally:

1. Loads `clients/acme/config.yaml` to get the prefix, namespaces, and domain settings
2. Replaces all `mcaas-` prefixed resource names with `acme-` prefix
3. Uses `clients/acme/namespaces.yaml` instead of `deploy/namespaces.yaml`
4. Uses `clients/acme/values/*.yaml` instead of `deploy/values/*.yaml`
5. Creates secrets named `acme-postgresql-secret`, `acme-opensearch-secret`, etc.
6. Creates the database `acme_db` instead of `mcaas_db`
7. Installs Helm releases: `acme-postgresql`, `acme-opensearch`, `acme-shuffle`, `acme-zammad`, `acme-ciso`
8. Deploys Wazuh into `acme-wazuh` namespace
9. Sets ingress hosts to `zammad.acme.example.com` and `ciso.acme.example.com`

### Deploying Multiple Clients on the Same Cluster

Each client's resources are fully isolated by namespace and release name prefix. You can deploy multiple clients to the same cluster:

```bash
# Deploy ACME stack
python scripts/deploy.py --client acme

# Deploy Globex stack (on the same cluster)
python scripts/deploy.py --client globex

# Both stacks coexist — different namespaces and release names
kubectl get namespaces | grep -E 'acme|globex'
# acme-managed-it      Active
# acme-security-ops    Active
# acme-grc             Active
# acme-wazuh           Active
# globex-managed-it    Active
# globex-security-ops  Active
# globex-grc           Active
# globex-wazuh         Active

helm list -A | grep -E 'acme|globex'
# acme-postgresql     acme-managed-it     deployed
# acme-opensearch     acme-security-ops   deployed
# acme-shuffle        acme-security-ops   deployed
# acme-zammad         acme-managed-it     deployed
# acme-ciso           acme-grc            deployed
# globex-postgresql   globex-managed-it   deployed
# globex-opensearch   globex-security-ops deployed
# ...
```

### Deploying to Different Clusters

For clients on different clusters, use kubeconfig contexts:

```bash
# Switch to ACME's cluster context
kubectl config use-context acme-production

# Deploy ACME
python scripts/deploy.py --client acme

# Switch to Globex's cluster context
kubectl config use-context globex-production

# Deploy Globex
python scripts/deploy.py --client globex
```

Or set the `kube_context` field in the client config and let `scripts/deploy.py` switch automatically.

---

## 8. GitHub Actions Per-Client Workflow

The `deploy.yml` workflow accepts a `client` input parameter to select which client to deploy:

### Workflow Dispatch UI

When triggering the workflow manually:

1. Go to **Actions** → **Deploy MCaaS**
2. Click **Run workflow**
3. Select from the dropdown:
   - **Client**: `default`, `acme`, `globex`, etc.
   - **Skip health check**: ☐ (optional)

### Updated `deploy.yml` Snippet

```yaml
on:
  workflow_dispatch:
    inputs:
      client:
        description: 'Client name (leave empty for default/single-client deployment)'
        required: false
        default: ''
        type: string
      skip_health_check:
        description: 'Skip post-deployment health check'
        required: false
        default: false
        type: boolean

jobs:
  deploy:
    runs-on: [self-hosted, linux]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Deploy MCaaS
        env:
          MCAAS_POSTGRES_PASSWORD: ${{ inputs.client != '' && secrets[format('{0}_POSTGRES_PASSWORD', inputs.client)] || secrets.MCAAS_POSTGRES_PASSWORD }}
          MCAAS_OPENSEARCH_PASSWORD: ${{ inputs.client != '' && secrets[format('{0}_OPENSEARCH_PASSWORD', inputs.client)] || secrets.MCAAS_OPENSEARCH_PASSWORD }}
          MCAAS_REDIS_PASSWORD: ${{ inputs.client != '' && secrets[format('{0}_REDIS_PASSWORD', inputs.client)] || secrets.MCAAS_REDIS_PASSWORD }}
          MCAAS_DJANGO_SECRET_KEY: ${{ inputs.client != '' && secrets[format('{0}_DJANGO_SECRET_KEY', inputs.client)] || secrets.MCAAS_DJANGO_SECRET_KEY }}
        run: |
          ARGS=""
          if [ -n "${{ inputs.client }}" ]; then
            ARGS="--client ${{ inputs.client }}"
          fi
          python scripts/deploy.py $ARGS

      - name: Health Check
        if: ${{ inputs.skip_health_check != true }}
        run: |
          ARGS=""
          if [ -n "${{ inputs.client }}" ]; then
            ARGS="--client ${{ inputs.client }}"
          fi
          python scripts/check-health.py $ARGS || true
```

> **Note**: GitHub Actions does not support dynamic secret references directly. The `format('{0}_POSTGRES_PASSWORD', inputs.client)` pattern shown above is conceptual. In practice, you'll need to either:
> - Use a **matrix strategy** with hard-coded client-to-secret mappings
> - Use a **wrapper script** that reads the correct secret based on the client name
> - Use **environment secrets** with per-client GitHub environments (e.g., `acme-production`, `globex-production`)

### Recommended: Per-Client GitHub Environments

The most robust approach for CI/CD is to use GitHub **Environments** with protection rules:

1. Create environments: `acme-production`, `globex-production`, etc.
2. Add per-client secrets to each environment
3. The workflow uses the client input to select the environment:

```yaml
jobs:
  deploy:
    runs-on: [self-hosted, linux]
    environment: ${{ inputs.client != '' && format('{0}-production', inputs.client) || 'production' }}
    steps:
      - name: Deploy
        env:
          MCAAS_POSTGRES_PASSWORD: ${{ secrets.MCAAS_POSTGRES_PASSWORD }}
          MCAAS_OPENSEARCH_PASSWORD: ${{ secrets.MCAAS_OPENSEARCH_PASSWORD }}
          MCAAS_REDIS_PASSWORD: ${{ secrets.MCAAS_REDIS_PASSWORD }}
          MCAAS_DJANGO_SECRET_KEY: ${{ secrets.MCAAS_DJANGO_SECRET_KEY }}
        run: |
          ARGS=""
          if [ -n "${{ inputs.client }}" ]; then
            ARGS="--client ${{ inputs.client }}"
          fi
          python scripts/deploy.py $ARGS
```

Each environment has its own set of `MCAAS_*` secrets, so the same secret names work across all clients.

---

## 9. Step-by-Step: Onboarding a New Client

Follow this checklist every time you onboard a new client.

### 1. Create the Client Branch

```bash
git checkout main
git pull origin main
git checkout -b client/<client-name>

# Example:
git checkout -b client/acme
```

### 2. Create the Client Configuration Directory

```bash
# Copy the template
cp -r clients/_template clients/<client-name>

# Example:
cp -r clients/_template clients/acme
```

### 3. Edit `clients/<client-name>/config.yaml`

```yaml
client:
  name: "acme"                    # Must match the directory name
  display_name: "ACME Corporation"
  domain: "acme.example.com"
  prefix: "acme"
  namespaces:
    managed-it: "acme-managed-it"
    security-ops: "acme-security-ops"
    grc: "acme-grc"
    wazuh: "acme-wazuh"
  wazuh_version: "4.14.6"
  database_name: "acme_db"
  ingress:
    zammad_host: "zammad.acme.example.com"
    ciso_host: "ciso.acme.example.com"
```

### 4. Edit `clients/<client-name>/namespaces.yaml`

Replace all namespace names with client-prefixed versions:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: acme-security-ops
---
apiVersion: v1
kind: Namespace
metadata:
  name: acme-managed-it
---
apiVersion: v1
kind: Namespace
metadata:
  name: acme-grc
---
apiVersion: v1
kind: Namespace
metadata:
  name: acme-wazuh
```

### 5. Edit Each Values File

Update all cross-references in `clients/<client-name>/values/`:

#### `postgresql.yaml`
```yaml
global:
  postgresql:
    auth:
      existingSecret: "acme-postgresql-secret"    # ← client prefix
      secretKeys:
        postgresPasswordKey: "postgres-password"
database: "acme_db"                                # ← client DB name
primary:
  persistence:
    enabled: true
    size: 10Gi
```

#### `opensearch.yaml`
```yaml
singleNode: true
extraEnvs:
  - name: OPENSEARCH_INITIAL_ADMIN_PASSWORD
    valueFrom:
      secretKeyRef:
        name: "acme-opensearch-secret"             # ← client prefix
        key: "opensearch-password"
persistence:
  enabled: true
  size: 20Gi
```

#### `shuffle.yaml`
```yaml
fullnameOverride: shuffle
opensearch:
  enabled: false
backend:
  openSearch:
    url: "https://opensearch-cluster-master.acme-security-ops.svc.cluster.local:9200"  # ← client namespace
    username: admin
    skipSSLVerify: true
  extraEnvVarsSecret: acme-opensearch-secret      # ← client prefix
orborus:
  enabled: true
  persistence:
    enabled: true
    size: 10Gi
```

#### `zammad.yaml`
```yaml
zammadConfig:
  postgresql:
    enabled: false
    host: "acme-postgresql.acme-managed-it.svc.cluster.local"  # ← client prefix + namespace
    port: 5432
    user: "postgres"
    pass: ""
    db: "zammad"
  elasticsearch:
    enabled: false
    initialisation: false
  redis:
    enabled: true
    host: "acme-zammad-redis"
    port: 6379
    pass: "zammad"
secrets:
  postgresql:
    useExisting: true
    secretName: "acme-postgresql-secret"           # ← client prefix
    secretKey: "postgres-password"
  redis:
    useExisting: true
    secretName: "acme-zammad-redis-pass"           # ← client prefix
    secretKey: "redis-password"
postgresql:
  enabled: false
elasticsearch:
  enabled: false
redis:
  auth:
    existingSecret: "acme-zammad-redis-pass"       # ← client prefix
    existingSecretPasswordKey: "redis-password"
ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: zammad.acme.example.com                 # ← client domain
      paths:
        - path: /
```

#### `ciso-assistant.yaml`
```yaml
postgresql:
  enabled: false
global:
  domain: ciso.acme.example.com                   # ← client domain
backend:
  config:
    databaseType: externalPgsql
    djangoSecretKey: ""
    djangoExistingSecretKey: "acme-ciso-secret"    # ← client prefix
externalPgsql:
  host: "acme-postgresql.acme-managed-it.svc.cluster.local"  # ← client prefix + namespace
  port: 5432
  user: "postgres"
  existingSecret: "acme-postgresql-secret"         # ← client prefix
  database: "ciso-assistant"
ingress:
  enabled: true
```

### 6. Set Up Client Secrets

#### For Local Deployment

```bash
# Create .env.acme with the client's passwords
cat > .env.acme <<EOF
ACME_POSTGRES_PASSWORD=$(openssl rand -base64 24)
ACME_OPENSEARCH_PASSWORD=$(openssl rand -base64 24)
ACME_REDIS_PASSWORD=$(openssl rand -base64 24)
ACME_DJANGO_SECRET_KEY=$(openssl rand -base64 32)
EOF

# Copy to .env for deployment
cp .env.acme .env
```

#### For GitHub Actions

Add secrets to the GitHub repository (Settings → Secrets → Actions):

| Secret Name | Value |
|-------------|-------|
| `ACME_POSTGRES_PASSWORD` | *(generate a strong password)* |
| `ACME_OPENSEARCH_PASSWORD` | *(generate a strong password)* |
| `ACME_REDIS_PASSWORD` | *(generate a strong password)* |
| `ACME_DJANGO_SECRET_KEY` | *(generate a strong key)* |

Or, if using environments:

1. Create a GitHub Environment named `acme-production`
2. Add secrets `MCAAS_POSTGRES_PASSWORD`, `MCAAS_OPENSEARCH_PASSWORD`, `MCAAS_REDIS_PASSWORD`, `MCAAS_DJANGO_SECRET_KEY` to that environment

### 7. Verify the Configuration (Dry Run)

```bash
python scripts/deploy.py --client acme --dry-run
```

Review the dry-run output to confirm:
- ✅ Release names use `acme-` prefix
- ✅ Namespaces use `acme-` prefix
- ✅ Secret names use `acme-` prefix
- ✅ Cross-references point to correct client-prefixed services
- ✅ Ingress hosts use client domain

### 8. Deploy

```bash
python scripts/deploy.py --client acme
```

### 9. Verify Deployment

```bash
# Check all client namespaces
kubectl get namespaces | grep acme

# Check all client pods
kubectl get pods -n acme-managed-it
kubectl get pods -n acme-security-ops
kubectl get pods -n acme-grc
kubectl get pods -n acme-wazuh

# Check Helm releases
helm list -n acme-managed-it
helm list -n acme-security-ops
helm list -n acme-grc

# Test ingress (if DNS is configured)
curl -k https://zammad.acme.example.com
curl -k https://ciso.acme.example.com
```

### 10. Commit and Push

```bash
git add clients/acme/
git commit -m "feat: add ACME client configuration"
git push -u origin client/acme
```

### 11. Create a Pull Request (Optional)

Create a PR from `client/acme` → `main` to review the client configuration before merging.

---

## 10. Teardown for a Client

Use `scripts/teardown.py` with the same `--client` parameter to remove all resources for a specific client:

```bash
# Remove ACME's entire stack
python scripts/teardown.py --client acme

# Dry run first
python scripts/teardown.py --client acme --dry-run
```

This will:
1. Uninstall all Helm releases with the `acme-` prefix
2. Remove all client-prefixed namespaces (`acme-managed-it`, `acme-security-ops`, `acme-grc`, `acme-wazuh`)
3. Delete all client-prefixed secrets
4. Remove the Wazuh kustomize resources in the `acme-wazuh` namespace
5. Delete client databases (PostgreSQL `acme_db`, `zammad`, `ciso-assistant`)

> ⚠️ **Warning**: Teardown is destructive. Always use `--dry-run` first and back up any persistent volumes.

### Targeted Teardown (Single Service)

To tear down a single service for a client:

```bash
# Remove only Zammad for ACME
helm uninstall acme-zammad -n acme-managed-it

# Remove only CISO Assistant for ACME
helm uninstall acme-ciso -n acme-grc
```

---

## 11. Reference: Hardcoded Names and Parameterization Map

This table shows every hardcoded string in the codebase that must change for multi-client deployments. Use this as a checklist when creating client configuration files.

| Category | Base Value | Client Pattern | Files Affected |
|----------|-----------|----------------|----------------|
| **Helm Releases** | | | |
| PostgreSQL release | `mcaas-postgresql` | `{prefix}-postgresql` | `scripts/deploy.py` |
| OpenSearch release | `mcaas-opensearch` | `{prefix}-opensearch` | `scripts/deploy.py` |
| Shuffle release | `mcaas-shuffle` | `{prefix}-shuffle` | `scripts/deploy.py` |
| Zammad release | `mcaas-zammad` | `{prefix}-zammad` | `scripts/deploy.py` |
| CISO release | `mcaas-ciso` | `{prefix}-ciso` | `scripts/deploy.py` |
| **Namespaces** | | | |
| managed-it | `managed-it` | `{prefix}-managed-it` | `scripts/deploy.py`, `namespaces.yaml`, all values |
| security-ops | `security-ops` | `{prefix}-security-ops` | `scripts/deploy.py`, `namespaces.yaml`, all values |
| grc | `grc` | `{prefix}-grc` | `scripts/deploy.py`, `namespaces.yaml`, all values |
| wazuh | `wazuh` | `{prefix}-wazuh` | `scripts/deploy.py`, `namespaces.yaml` |
| **Secrets** | | | |
| PostgreSQL | `mcaas-postgresql-secret` | `{prefix}-postgresql-secret` | `scripts/deploy.py`, `postgresql.yaml`, `zammad.yaml`, `ciso-assistant.yaml` |
| OpenSearch | `mcaas-opensearch-secret` | `{prefix}-opensearch-secret` | `scripts/deploy.py`, `opensearch.yaml`, `shuffle.yaml`, `wazuh.yaml` |
| Redis | `mcaas-zammad-redis-pass` | `{prefix}-zammad-redis-pass` | `scripts/deploy.py`, `zammad.yaml` |
| CISO Django | `mcaas-ciso-secret` | `{prefix}-ciso-secret` | `scripts/deploy.py`, `ciso-assistant.yaml` |
| **Service FQDNs** | | | |
| PostgreSQL host | `mcaas-postgresql.managed-it.svc.cluster.local` | `{prefix}-postgresql.{prefix}-managed-it.svc.cluster.local` | `zammad.yaml`, `ciso-assistant.yaml` |
| OpenSearch host | `opensearch-cluster-master.security-ops.svc.cluster.local` | `opensearch-cluster-master.{prefix}-security-ops.svc.cluster.local` | `shuffle.yaml`, `wazuh.yaml` |
| Redis host | `mcaas-zammad-redis` | `{prefix}-zammad-redis` | `zammad.yaml` |
| **Database** | | | |
| Main DB | `mcaas_db` | `{prefix}_db` | `scripts/deploy.py`, `postgresql.yaml` |
| Zammad DB | `zammad` | `zammad` (unchanged) | `zammad.yaml` |
| CISO DB | `ciso-assistant` | `ciso-assistant` (unchanged) | `ciso-assistant.yaml` |
| **Ingress** | | | |
| Zammad host | `zammad.mcaas.example.com` | `zammad.{domain}` | `zammad.yaml` |
| CISO host | `ciso.mcaas.example.com` | `ciso.{domain}` | `ciso-assistant.yaml` |
| **Environment Variables** | | | |
| `MCAAS_POSTGRES_PASSWORD` | base | `{PREFIX}_POSTGRES_PASSWORD` | `.env`, `scripts/deploy.py`, workflows |
| `MCAAS_OPENSEARCH_PASSWORD` | base | `{PREFIX}_OPENSEARCH_PASSWORD` | `.env`, `scripts/deploy.py`, workflows |
| `MCAAS_REDIS_PASSWORD` | base | `{PREFIX}_REDIS_PASSWORD` | `.env`, `scripts/deploy.py`, workflows |
| `MCAAS_DJANGO_SECRET_KEY` | base | `{PREFIX}_DJANGO_SECRET_KEY` | `.env`, `scripts/deploy.py`, workflows |

---

## 12. Troubleshooting

### "Namespace not found" errors

Make sure you applied the client-specific `namespaces.yaml`:

```bash
kubectl apply -f clients/acme/namespaces.yaml
```

### "Secret not found" errors

Verify secrets were created in the correct client-prefixed namespaces:

```bash
kubectl get secrets -n acme-managed-it
kubectl get secrets -n acme-security-ops
kubectl get secrets -n acme-grc
```

### Cross-namespace service references fail

Check that the FQDN in values files uses the client-prefixed namespace:

```bash
# Test DNS resolution
kubectl run -it --rm dnsutils --image=busybox --restart=Never -- \
  nslookup acme-postgresql.acme-managed-it.svc.cluster.local
```

### Multiple clients on same cluster interfering

Each client's resources are isolated by namespace and release name. If you see conflicts:

1. Check that release names include the client prefix:
   ```bash
   helm list -A | grep acme
   ```

2. Check that namespaces are distinct:
   ```bash
   kubectl get namespaces | grep acme
   ```

3. Verify no two clients share a namespace:
   ```bash
   # This should return nothing
   kubectl get namespaces | grep -E 'acme.*globex|globex.*acme'
   ```

### Wazuh deployment fails for a client

Wazuh uses kustomize (not Helm) and has its own namespace configuration. When deploying for a client:

1. The Wazuh namespace in `clients/<client>/namespaces.yaml` must be `{prefix}-wazuh`
2. `scripts/deploy.py` must pass the client-prefixed namespace to `kubectl apply -k` for the Wazuh overlay
3. Wazuh's internal references to OpenSearch must use the client-prefixed namespace

### Deploy script doesn't recognize `--client`

Make sure you're running the updated version of `scripts/deploy.py` that includes the `--client` argument:

```bash
python scripts/deploy.py --help
# Should show: --client CLIENT  Client name for multi-client deployment
```

If not, pull the latest changes from the `client/<name>` branch.

---

## Appendix: Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│              MCaaS Multi-Client Deployment                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  New Client Onboarding:                                       │
│    1. git checkout -b client/<name>                           │
│    2. cp -r clients/_template clients/<name>                  │
│    3. Edit config.yaml, namespaces.yaml, values/*.yaml        │
│    4. python scripts/deploy.py --client <name> --dry-run              │
│    5. python scripts/deploy.py --client <name>                        │
│                                                               │
│  Deploy:    python scripts/deploy.py --client <name>                  │
│  Teardown:  python scripts/teardown.py --client <name>                │
│  Dry run:   Add --dry-run to either command                   │
│                                                               │
│  Branch:    client/<name> (e.g., client/acme)                │
│  Config:    clients/<name>/config.yaml                        │
│  Values:    clients/<name>/values/*.yaml                      │
│  Secrets:   {PREFIX}_POSTGRES_PASSWORD, etc.                  │
│                                                               │
│  Naming:    mcaas- → {prefix}- (e.g., acme-)                 │
│  Namespaces: managed-it  → {prefix}-managed-it                │
│  Hosts:     *.mcaas.example.com → *.<domain>                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```