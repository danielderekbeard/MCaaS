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

- `kubectl` configured for the target cluster
- `helm` installed
- `bash` / `PowerShell` for local script execution
- `KUBE_CONFIG` or cluster credentials for CI deployment

## Quick start

1. Copy `scripts/.env.example` to `.env` or set the required environment variables.
2. Run the secret bootstrap script:
   - Linux/macOS: `scripts/init-secrets.sh`
   - Windows PowerShell: `.\scripts\init-secrets.ps1`
3. Deploy the stack:
   - Linux/macOS: `scripts/deploy.sh`
   - Windows PowerShell: `.\scripts\deploy.ps1`
4. Teardown when needed:
   - Linux/macOS: `scripts/teardown.sh`
   - Windows PowerShell: `.\scripts\teardown.ps1`

## Secrets

The deployment uses two Kubernetes secrets:

- `mcaas-postgresql-secret` with key `postgres-password`
- `mcaas-opensearch-secret` with key `opensearch-password`

The `init-secrets` scripts create these secrets in the correct namespaces.

## CI / GitHub Actions

This repository includes a GitHub Actions workflow at `.github/workflows/deploy.yml`.
The workflow uses the following repository secrets:

- `KUBE_CONFIG_DATA` (base64-encoded kubeconfig)
- `MCAAS_POSTGRES_PASSWORD`
- `MCAAS_OPENSEARCH_PASSWORD`

## Notes

- Chart repository URLs and release names are configured in `scripts/deploy.sh` and `scripts/deploy.ps1`.
- The `shuffle` chart is installed from a local clone of its GitHub repository, as a public Helm repository is not available.
- The `ciso-assistant` chart is installed from its OCI registry on GHCR.
- The `wazuh` deployment uses the official manifest-based installation from the `wazuh-kubernetes` GitHub repository, as the Helm chart is deprecated.
- The helm values in `deploy/values/` are derived from the infrastructure manifest definitions in `mcaas.md`.
