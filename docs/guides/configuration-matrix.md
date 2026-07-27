# MCaaS Configuration Matrix

> **Status: DRAFT — Not for commit**  
> Complete reference of all configuration items, how to customize them, and how to make deployments unique with custom hostnames.

---

## Configuration Items by Component

### 1. PostgreSQL (`deploy/values/postgresql.yaml`)

| Config Item | Current Value | How to Customize | Notes |
|-------------|--------------|------------------|-------|
| Auth method | `existingSecret` | Change `global.postgresql.auth.existingSecret` to point to a different K8s secret | Must match the secret created by `create_secrets()` in scripts/deploy.py |
| Secret name | `mcaas-postgresql-secret` | Update in both this file AND `create_secrets()` in scripts/deploy.py | Secret must exist in `managed-it` namespace |
| Secret key (password) | `postgres-password` | Change `secretKeys.postgresPasswordKey` and recreate the secret | CISO Assistant also reads key `password` from the same secret |
| Database name | `mcaas_db` | Change `database` value | Must also update Zammad and CISO Assistant database references |
| PVC size | `10Gi` | Change `primary.persistence.size` | Requires PVC recreation if reducing |
| StorageClass | Default (local-path) | Add `primary.persistence.storageClassName: <class>` | Uses cluster default if not specified |
| Namespace | `managed-it` | Change in `deploy/namespaces.yaml` and scripts/deploy.py | All consumers must be updated |

**Making it unique**: Change the Helm release name prefix in `scripts/deploy.py` (default `mcaas-postgresql`), update all downstream references to the service FQDN.

---

### 2. OpenSearch (`deploy/values/opensearch.yaml`)

| Config Item | Current Value | How to Customize | Notes |
|-------------|--------------|------------------|-------|
| Single node mode | `true` | Set `singleNode: false` for cluster mode | Cluster mode requires 3+ nodes and different resource config |
| Admin password | From `mcaas-opensearch-secret` | Change the `OPENSEARCH_INITIAL_ADMIN_PASSWORD` env var source | Secret must exist in `security-ops` namespace |
| Secret name | `mcaas-opensearch-secret` | Update `extraEnvs[0].valueFrom.secretKeyRef.name` | Also update `create_secrets()` in scripts/deploy.py |
| Secret key | `opensearch-password` | Update `extraEnvs[0].valueFrom.secretKeyRef.key` | |
| PVC size | `20Gi` | Change `persistence.size` | OpenSearch needs more space than other components |
| StorageClass | Default (local-path) | Add `persistence.storageClassName: <class>` | |
| Namespace | `security-ops` | Change in `deploy/namespaces.yaml` and scripts/deploy.py | |

**Making it unique**: Change release name prefix (default `mcaas-opensearch`). If running multiple instances, each needs a unique release name and separate secret.

---

### 3. Wazuh (kustomize — not Helm values)

> ⚠️ Wazuh is deployed via kustomize from the upstream `wazuh-kubernetes` repo.
> `deploy/values/wazuh.yaml` is **documentation-only** and is NOT applied to the deployment.

| Config Item | Current Value | How to Customize | Notes |
|-------------|--------------|------------------|-------|
| Deployment method | kustomize (git clone) | Create a kustomize overlay in `deploy/wazuh-overlay/` | scripts/deploy.py clones `wazuh-kubernetes` repo with `--no-checkout` |
| Overlay used | `local-env` | Change `WAZUH_OVERLAY` in scripts/deploy.py or create custom overlay | The upstream overlay includes its own indexer |
| Indexer | Enabled (upstream default) | Create kustomize patch to disable indexer | Desired: disabled, using external OpenSearch |
| External OpenSearch | `mcaas-opensearch.security-ops:9200` | Patch the indexer config in a kustomize overlay | Not yet applied |
| Dashboard credentials | `admin` / `MYPASSWORD_` | Patch the `wazuh-api-credentials` secret | **Change this for production!** |
| Dashboard host | N/A (ClusterIP) | Add an Ingress or NodePort service | Currently accessible only via port-forward |
| Manager API port | 55000 | Patch the service in kustomize overlay | |
| Agent enrollment port | 1514 | Standard Wazuh agent port | |
| StorageClass | `wazuh-storage` (created by scripts/deploy.py) | Change the StorageClass manifest in `deploy_wazuh()` | Uses rancher.io/local-path provisioner with WaitForFirstConsumer |
| Namespace | `wazuh` | Change in `deploy/namespaces.yaml` and scripts/deploy.py | |

**Making it unique**: Create a kustomize overlay directory at `deploy/wazuh-overlay/` with patches for custom credentials, external OpenSearch, and custom ingress hostnames.

---

### 4. Shuffle (`deploy/values/shuffle.yaml`)

| Config Item | Current Value | How to Customize | Notes |
|-------------|--------------|------------------|-------|
| **fullnameOverride** | `shuffle` | Change with caution — frontend nginx config expects `shuffle-backend` service name | **Critical**: Do NOT remove this. Removing it causes DNS mismatch in the frontend pod. |
| OpenSearch host | `mcaas-opensearch.security-ops.svc.cluster.local` | Change `backend.opensearch.host` | Must match the OpenSearch service FQDN |
| OpenSearch port | `9200` | Change `backend.opensearch.port` | |
| OpenSearch secret | `mcaas-opensearch-secret` / `opensearch-password` | Change `backend.opensearch.secret.name` and `key` | Secret must exist in `security-ops` namespace |
| Orborus | enabled | Set `orborus.enabled: false` to disable the orchestration engine | Orborus is Shuffle's workflow execution engine |
| Orborus persistence | `10Gi` | Change `orborus.persistence.size` | |
| Namespace | `security-ops` | Change in `deploy/namespaces.yaml` and scripts/deploy.py | |
| Release name | `mcaas-shuffle` | Change the `helm upgrade --install` release name in scripts/deploy.py | |

**Making it unique**: The `fullnameOverride` makes Shuffle's service names predictable (`shuffle-backend`, `shuffle-frontend`). Custom hostnames require an Ingress resource (not yet configured in values).

---

### 5. Zammad (`deploy/values/zammad.yaml`)

| Config Item | Current Value | How to Customize | Notes |
|-------------|--------------|------------------|-------|
| PostgreSQL enabled | `false` (external) | Set `postgresql.enabled: true` to use the bundled PostgreSQL | Not recommended — MCaaS uses shared PostgreSQL |
| Database host | `mcaas-postgresql-postgresql.managed-it.svc.cluster.local` | Change `externalDatabase.host` | |
| Database port | `5432` | Change `externalDatabase.port` | |
| Database user | `postgres` | Change `externalDatabase.user` | |
| Database password | From `mcaas-postgresql-secret` key `postgres-password` | Change `passwordSecret.name` and `passwordSecret.key` | |
| Database name | `zammad` | Change `database` | Must create the database on the PostgreSQL instance first |
| Elasticsearch | Disabled | Set `elasticsearch.enabled: true` to enable bundled ES | MCaaS uses external OpenSearch instead |
| **Ingress enabled** | `true` | Set `ingress.enabled: false` to use port-forward only | |
| **Ingress host** | `zammad.mcaas.example.com` | Change `ingress.hosts[0].host` | **Replace with your actual domain** |
| Ingress class | `nginx` | Change `ingress.className` | Must match your cluster's ingress controller |
| Namespace | `managed-it` | Change in `deploy/namespaces.yaml` and scripts/deploy.py | |
| Release name | `zammad` | Change the helm upgrade release name in scripts/deploy.py | |

**Making it unique with custom hostname**: Change `ingress.hosts[0].host` to your domain (e.g., `helpdesk.yourcompany.com`). Ensure DNS resolves to your cluster's ingress controller.

---

### 6. CISO Assistant (`deploy/values/ciso-assistant.yaml`)

| Config Item | Current Value | How to Customize | Notes |
|-------------|--------------|------------------|-------|
| PostgreSQL enabled | `false` (external) | Set `postgresql.enabled: true` for bundled PostgreSQL | Not recommended — MCaaS uses shared PostgreSQL |
| Database type | `externalPgsql` | Change `backend.config.databaseType` | Options: `externalPgsql` or `sqlite` |
| Database host | `mcaas-postgresql-postgresql.managed-it.svc.cluster.local` | Change `externalPgsql.host` | |
| Database port | `5432` | Change `externalPgsql.port` | |
| Database user | `postgres` | Change `externalPgsql.user` | |
| Database password | From `mcaas-postgresql-secret` | Change `externalPgsql.existingSecret` | CISO Assistant reads both `postgres-password` and `password` keys from this secret |
| Database name | `ciso-assistant` | Change `externalPgsql.database` | Must create the database on the PostgreSQL instance first |
| **Ingress enabled** | `true` | Set `ingress.enabled: false` to use port-forward only | |
| **Ingress host** | `ciso.mcaas.example.com` | Change `ingress.hosts[0].host` | **Replace with your actual domain** |
| SSL passthrough | `true` (nginx annotation) | Remove `ssl-passthrough` annotation if terminating TLS at ingress | CISO Assistant's frontend handles TLS internally |
| Namespace | `grc` | Change in `deploy/namespaces.yaml` and scripts/deploy.py | |
| Release name | `ciso-assistant` | Change the helm upgrade release name in scripts/deploy.py | |

**Making it unique with custom hostname**: Change `ingress.hosts[0].host` to your domain (e.g., `grc.yourcompany.com`). Ensure DNS resolves to your cluster's ingress controller.

---

## Custom Hostname Reference

All ingress-based services use placeholder hostnames that must be replaced for production:

| Component | Placeholder Hostname | Values File Key | Production Example |
|-----------|---------------------|-----------------|-------------------|
| Zammad | `zammad.mcaas.example.com` | `deploy/values/zammad.yaml` → `ingress.hosts[0].host` | `helpdesk.acme.com` |
| CISO Assistant | `ciso.mcaas.example.com` | `deploy/values/ciso-assistant.yaml` → `ingress.hosts[0].host` | `grc.acme.com` |

**Non-ingress services** (PostgreSQL, OpenSearch, Wazuh, Shuffle) are accessed via ClusterIP services inside the cluster. To expose them externally:

1. **NodePort**: Add `service.type: NodePort` to the Helm values
2. **LoadBalancer**: Add `service.type: LoadBalancer` to the Helm values
3. **Ingress**: Add an ingress section to the Helm values (Shuffle and Wazuh Dashboard support this)

---

## Namespace Mapping

| Namespace | Purpose | Components |
|-----------|---------|------------|
| `security-ops` | Security operations | OpenSearch, Shuffle |
| `managed-it` | IT management | PostgreSQL, Zammad |
| `grc` | Governance, Risk, Compliance | CISO Assistant |
| `wazuh` | Wazuh security monitoring | Wazuh Manager, Indexer, Dashboard |

To change namespaces:
1. Update `deploy/namespaces.yaml`
2. Update `deploy/kustomization.yaml` if needed
3. Update all Helm values files that reference cross-namespace services (e.g., `externalDatabase.host`, `backend.opensearch.host`)
4. Update `scripts/deploy.py` (namespace arguments in `helm upgrade --install` and `kubectl` commands)
5. Update `deploy/cicd-service-account.yaml` if namespace-scoped RBAC changes

---

## Secrets Reference

| Secret Name | Namespace | Keys | Used By |
|-------------|-----------|------|---------|
| `mcaas-postgresql-secret` | `managed-it` | `postgres-password`, `password` | PostgreSQL, Zammad, CISO Assistant |
| `mcaas-opensearch-secret` | `security-ops` | `opensearch-password` | OpenSearch, Shuffle |

**Creating custom secrets**: If you change secret names, update these locations:
1. `deploy/values/postgresql.yaml` → `global.postgresql.auth.existingSecret`
2. `deploy/values/opensearch.yaml` → `extraEnvs[0].valueFrom.secretKeyRef.name`
3. `deploy/values/shuffle.yaml` → `backend.opensearch.secret.name`
4. `deploy/values/zammad.yaml` → `passwordSecret.name`
5. `deploy/values/ciso-assistant.yaml` → `externalPgsql.existingSecret`
6. `scripts/deploy.py` → `create_secrets()` function

---

## PVC Storage Summary

| Component | PVC Name Pattern | Size | StorageClass | Namespace |
|-----------|-----------------|------|-------------|-----------|
| PostgreSQL | `data-mcaas-postgresql-postgresql-0` | 10Gi | local-path (default) | managed-it |
| OpenSearch | `opensearch-data-mcaas-opensearch-0` | 20Gi | local-path (default) | security-ops |
| Wazuh Indexer | `wazuh-indexer-*` | 10Gi (upstream default) | wazuh-storage | wazuh |
| Wazuh Manager | `wazuh-manager-var-wazuh-*` | 10Gi (upstream default) | wazuh-storage | wazuh |
| Shuffle Orborus | `shuffle-orborus-*` | 10Gi | local-path (default) | security-ops |

**Total estimated storage**: ~60 Gi minimum

---

*See also: [Installation Guide](./installation-guide.md) | [Services Matrix](./services-matrix.md) | [Retry & Timeout Recommendations](./retry-timeout-recommendations.md)*