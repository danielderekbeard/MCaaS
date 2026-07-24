# MCaaS Deployment Automation

This workspace contains a repeatable deployment automation scaffold for the MCaaS stack described in `mcaas.md`.

## What is included

- `deploy/namespaces.yaml` and `deploy/kustomization.yaml` for namespace provisioning
- `deploy/values/*.yaml` Helm values for the core services
- `scripts/` automation scripts for secrets, deployment, and teardown
- `.github/workflows/deploy.yml` GitHub Actions deployment workflow
- `.gitignore` to protect local secrets and generated files
- `logs/` directory for per-run deployment logs

## Prerequisites

### Common (All Platforms)

- `kubectl` configured for the target cluster
- `helm` installed and available in PATH
- `git` installed
- Python 3.7+
- A running Kubernetes cluster (Docker Desktop, Rancher Desktop, Minikube, or remote cluster)

### Windows-Specific

On Windows, you have **two deployment options**:

#### Option 1: Native Windows Deployment (Recommended)

1. Install required tools:
   - **Python**: Download from https://www.python.org/ or `choco install python`
   - **kubectl**: Download from https://kubernetes.io/docs/tasks/tools/#kubectl or `choco install kubernetes-cli`
   - **helm**: Download from https://helm.sh/docs/intro/install/ or `choco install kubernetes-helm`
   - **git**: Download from https://git-scm.com/download/win or `choco install git`
   - **Docker Desktop** or **Rancher Desktop**: For the Kubernetes runtime

2. Verify prerequisites:
   ```powershell
   python scripts/check-prerequisites.py
   ```

3. Follow the quick start below

#### Option 2: Windows Subsystem for Linux (WSL2)

If you prefer a Unix-like environment or encounter issues with Option 1:

1. Install WSL2:
   ```powershell
   wsl --install
   ```

2. Inside WSL, install prerequisites:
   ```bash
   sudo apt-get update
   sudo apt-get install -y kubectl helm git python3
   ```

3. Configure kubeconfig inside WSL (copy from Windows if using Docker Desktop):
   ```bash
   mkdir -p ~/.kube
   cp /mnt/c/Users/YourUsername/.kube/config ~/.kube/config
   ```

4. Run deployment from WSL terminal (see Quick Start)

## Quick Start

### Verify Prerequisites

Before deploying, verify all required tools are installed:

**Windows (PowerShell):**
```powershell
python scripts/check-prerequisites.py
```

**Linux/macOS/WSL (bash):**
```bash
python scripts/check-prerequisites.py
# or
python3 scripts/check-prerequisites.py
```

### Setup Environment Variables

1. Copy the example environment file:
   ```
   Copy-Item scripts\.env.example .env  # Windows PowerShell
   cp scripts/.env.example .env          # Linux/macOS/WSL bash
   ```

2. Edit `.env` and set:
   - `MCAAS_POSTGRES_PASSWORD`: Strong password for PostgreSQL
   - `MCAAS_OPENSEARCH_PASSWORD`: Strong password for OpenSearch
   - `MCAAS_REDIS_PASSWORD`: Redis auth password for Zammad (defaults to `zammad` if not set)

### Deploy

Choose one deployment method:

**Option A: Python (Recommended for Windows)**
```powershell
python deploy.py
```

**Option B: PowerShell Wrapper (Windows)**
```powershell
.\scripts\deploy.ps1
```

**Option C: Shell Scripts (Linux/macOS/WSL)**
```bash
# Initialize secrets
./scripts/init-secrets.sh

# Deploy
./scripts/deploy.sh

# Verify services
./scripts/test-services.sh

# Cleanup (if needed)
./scripts/teardown.sh
```

### Monitor Deployment

The deployment scripts create detailed logs in the `logs/` directory:

```powershell
Get-ChildItem logs/ | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 50
```

## Secrets

The deployment uses the following Kubernetes secrets:

| Secret | Namespace | Keys | Purpose |
|--------|-----------|------|---------|
| `mcaas-postgresql-secret` | `managed-it`, `grc` | `postgres-password`, `password` | PostgreSQL auth (Bitnami key + CISO Assistant key) |
| `mcaas-opensearch-secret` | `security-ops` | `opensearch-password`, `SHUFFLE_OPENSEARCH_PASSWORD` | OpenSearch auth (chart key + Shuffle env var) |
| `mcaas-zammad-redis-pass` | `managed-it` | `redis-password` | Redis auth for Zammad |
| `mcaas-ciso-secret` | `grc` | `django-secret-key` | CISO Assistant Django secret key |

The PostgreSQL secret is created in both the `managed-it` and `grc` namespaces because CISO Assistant (in `grc`) needs cross-namespace access to the PostgreSQL credentials.

When using `deploy.py`, secrets are created automatically via kubectl commands embedded in the script. Passwords are sourced from environment variables (`MCAAS_POSTGRES_PASSWORD`, `MCAAS_OPENSEARCH_PASSWORD`, `MCAAS_REDIS_PASSWORD`, `MCAAS_DJANGO_SECRET_KEY`) or auto-generated and persisted to `.env`.

## CI / GitHub Actions

This repository includes six GitHub Actions workflows for automated deployment, teardown, and health checks. All workflows use the `workflow_dispatch` trigger, meaning they are run manually from the **Actions** tab in the GitHub repository.

### Available Workflows

| Workflow | File | Runner | Description |
|----------|------|--------|-------------|
| Deploy MCaaS | `deploy.yml` | `self-hosted, linux` | Full stack deployment |
| Deploy MCaaS (Windows) | `deploy-windows.yml` | `self-hosted, windows` | Full stack deployment on Windows |
| Teardown MCaaS | `teardown.yml` | `self-hosted, linux` | Remove all MCaaS resources |
| Teardown MCaaS (Windows) | `teardown-windows.yml` | `self-hosted, windows` | Remove all MCaaS resources on Windows |
| Health Check MCaaS | `health-check.yml` | `self-hosted, linux` | Verify all services are healthy |
| Health Check MCaaS (Windows) | `health-check-windows.yml` | `self-hosted, windows` | Verify all services are healthy on Windows |

### Setting Up Self-Hosted Runners

Since these workflows deploy to your local or private Kubernetes cluster, they require **self-hosted GitHub Actions runners**. To set one up:

1. Go to your repository on GitHub → **Settings** → **Actions** → **Runners** → **New self-hosted runner**
2. Follow the OS-specific instructions to download and configure the runner
3. Make sure the runner machine has the following installed:
   - `kubectl` (configured with access to your cluster)
   - `helm` v3+
   - `python` 3.7+ (the workflow uses `actions/setup-python@v5`)
   - `git`
4. Start the runner service

### Required Repository Secrets

Configure these in **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Required | Description |
|--------|----------|-------------|
| `KUBE_CONFIG_DATA` | ✅ Yes | Base64-encoded kubeconfig file for your cluster |
| `MCAAS_POSTGRES_PASSWORD` | ✅ Yes | PostgreSQL superuser password |
| `MCAAS_OPENSEARCH_PASSWORD` | ✅ Yes | OpenSearch admin password |
| `MCAAS_REDIS_PASSWORD` | No | Redis password for Zammad (defaults to `zammad`) |
| `MCAAS_DJANGO_SECRET_KEY` | No | Django secret key for CISO Assistant (auto-generated if not set) |

#### Creating the KUBE_CONFIG_DATA secret

Encode your kubeconfig as base64:

**Linux/macOS:**
```bash
base64 -w 0 ~/.kube/config
```

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$HOME\.kube\config")))
```

Copy the output and paste it as the `KUBE_CONFIG_DATA` repository secret value.

### Running a Workflow

1. Go to **Actions** tab in your GitHub repository
2. Select the workflow you want to run (e.g., "Deploy MCaaS")
3. Click **Run workflow**
4. For deploy workflows, you can optionally check **Skip health check** to skip the post-deployment verification
5. Monitor the run in real-time from the Actions tab

### Health Check Details

The health check workflows verify:

- ✅ Kubernetes cluster connectivity (`kubectl cluster-info`)
- ✅ All required namespaces exist (`managed-it`, `security-ops`, `grc`, `wazuh`)
- ✅ All pods are in `Running` or `Completed` state
- ✅ Helm releases are deployed and listed
- ✅ Service endpoints exist for all six MCaaS services

## Windows Deployment Notes

### Cross-Platform Deployment Script

The primary deployment orchestrator (`deploy.py`) now supports Windows, Linux, and macOS:

- Uses Python's `pathlib` for cross-platform path handling
- Detects OS and handles platform-specific commands
- Handles Wazuh repository symlink issues gracefully
- Provides clear error messages when tools are missing

### PowerShell Wrapper

The `deploy.ps1` script on Windows:

- Validates prerequisites (Python, kubectl, helm, git)
- Loads environment variables from `.env`
- Configures Kubernetes context automatically
- Delegates deployment to the Python orchestrator
- Provides comprehensive logging

### Wazuh Deployment on Windows

Wazuh manifests contain symbolic links that Windows doesn't handle natively. The deployment script handles this by:

1. Attempting to clone with `--no-checkout` on Windows
2. Checking out only the needed files
3. Falling back to remote GitHub URLs if cloning fails

This ensures consistent Wazuh deployment across all platforms.

## Troubleshooting

### "kubectl: command not found" or similar

**Solution**: Ensure the tool is installed and in your PATH:

```powershell
# Check if in PATH
$env:Path -split ';' | Select-String 'kubectl'

# Or run the prerequisite checker
python scripts/check-prerequisites.py
```

### Python not found on Windows

**Solutions**:
- Install Python from https://www.python.org/
- Add Python to your PATH: `python -m pip install --upgrade pip`
- Use `py` instead: `py deploy.py`

### kubeconfig not configured

**Solution**: Set up kubeconfig for your cluster:

```powershell
# For Docker Desktop
kubectl config use-context docker-desktop

# For Rancher Desktop
kubectl config use-context rancher-desktop

# Or point to your cluster's config
$env:KUBECONFIG = "C:\path\to\kubeconfig"
```

### "Waiting for deployment timeout" errors

**Solutions**:
- Check if services are running: `kubectl get pods -A`
- Increase timeout in `deploy.py` (search for `--timeout`)
- Check resource availability: `kubectl top nodes`

### Wazuh deployment failures (Windows-specific)

**Solutions**:
1. If symlink errors occur, the deployment automatically falls back to remote manifests
2. Verify your kubeconfig can access the internet for remote manifests
3. Check logs in `logs/` directory for detailed error messages

## Notes

- Chart repository URLs and release names are configured in `deploy.py`.
- The `shuffle` chart is installed from OCI registry (`oci://ghcr.io/shuffle/charts/shuffle`).
- The `zammad` chart is installed from OCI registry (`oci://ghcr.io/zammad/charts/zammad`).
- The `ciso-assistant` chart is installed from its OCI registry on GHCR (`oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant`), version `0.11.4`.
- The `wazuh` deployment uses the official manifest-based installation from the `wazuh-kubernetes` GitHub repository.
- The helm values in `deploy/values/` are derived from the infrastructure manifest definitions in `mcaas.md`.
- On Windows, deployment logs are written to `logs/deploy-*.log` files in UTC timestamps.

### Architecture Details

- **PostgreSQL** is the shared database backend for Zammad and CISO Assistant, deployed once in `managed-it` namespace.
- **Redis** is deployed as a Bitnami sub-chart of Zammad, providing in-memory caching for the helpdesk.
- **OpenSearch** is the shared search/indexing backend for Wazuh and Shuffle, deployed once in `security-ops` namespace.
- Database names use hyphens (e.g. `ciso-assistant`, not `ciso_assistant`) and are created by `deploy.py` before their respective Helm releases.
- The PostgreSQL service is named `mcaas-postgresql` (not `mcaas-postgresql-postgresql`) — the Bitnami chart's `fullnameOverride` removes the chart-name suffix.
- On Windows, `deploy.py` pipes SQL commands via stdin to `kubectl exec -i` instead of using psql's `-c` flag to avoid PowerShell stripping double-quotes around hyphenated identifiers.

