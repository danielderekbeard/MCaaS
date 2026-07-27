# MCaaS Deployment Summary

| Field | Value |
|-------|-------|
| **Client** | `default` |
| **Prefix** | `mcaas` |
| **Domain** | `mcaas.example.com` |
| **Generated** | 2026-07-27 13:05:02 UTC |
| **Mode** | Dry-run (no changes applied) |

---

## Web Interfaces (Ingress)

All services are exposed via Traefik Ingress (built-in on k3s) with TLS
(cert-manager selfsigned-issuer) by adding the host entries to your hosts
file (see Local Access Setup below).

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| **Alala** (Zammad Ticketing) | [https://alala.mcaas.example.com](https://alala.mcaas.example.com) | `admin` / set on first login |
| **Strategos** (CISO Assistant GRC) | [https://strategos.mcaas.example.com](https://strategos.mcaas.example.com) | `admin` / set on first login |
| **Kydoimos** (Shuffle SOAR) | [https://kydoimos.mcaas.example.com](https://kydoimos.mcaas.example.com) | OpenID / configured at first setup |
| **Deimos** (Wazuh SIEM) | [https://deimos.mcaas.example.com](https://deimos.mcaas.example.com) | `admin` / `SecretPassword` — change immediately |

## Local Access Setup (Windows)

Add the following entries to your Windows hosts file so that the
ingress domains resolve to the LoadBalancer IP:

1.  Get the LoadBalancer IP:
    ```bash
    kubectl get svc -n traefik
    ```
    For Docker Desktop / Rancher Desktop the EXTERNAL-IP is typically
    `127.0.0.1` or `localhost`.

2.  Edit `C:\Windows\System32\drivers\etc\hosts` (run as Administrator):
    ```
    127.0.0.1 alala.mcaas.example.com strategos.mcaas.example.com kydoimos.mcaas.example.com deimos.mcaas.example.com
    ```

3.  Open any of the URLs listed above in your browser.

---

## Internal Services (Cluster-Only)

| Service | Host | Port | Notes |
|---------|------|------|-------|
| **PostgreSQL** | `mcaas-postgresql.managed-it.svc.cluster.local` | 5432 | Primary database |
| **OpenSearch** | `mcaas-opensearch.security-ops.svc.cluster.local` | 9200 | REST API (HTTPS) |
| **Zammad Redis** | `mcaas-zammad-redis.managed-it.svc.cluster.local` | 6379 | Session/cache store |
| **Shuffle Backend** | `shuffle.security-ops.svc.cluster.local` | 80 | SOAR engine |

---

## Kubernetes Secrets

| Secret | Namespace | Keys |
|--------|-----------|------|
| `mcaas-postgresql-secret` | `managed-it` | `postgres-password`, `password` |
| `mcaas-opensearch-secret` | `security-ops` | `opensearch-password`, `SHUFFLE_OPENSEARCH_PASSWORD` |
| `mcaas-zammad-redis-pass` | `managed-it` | `redis-password` |
| `mcaas-postgresql-secret` | `grc` | `postgres-password`, `password` (for CISO Assistant) |
| `mcaas-ciso-secret` | `grc` | `django-secret-key` |

---

## Credentials

### PostgreSQL

- **Host:** `{pg_host}:5432`
- **Username:** `postgres`
- **Password:** `nwjNp4QHEWtzfo3S6LgXZuhe`
- **Database names:** `mcaas_db` (default), `zammad`, `ciso-assistant`

### OpenSearch

- **Host:** `{os_host}:9200`
- **Username:** `admin`
- **Password:** `BEJtCaOrd0Sv8IuzpGmDiF3w`

### Zammad Redis

- **Host:** `{zammad_redis}:6379`
- **Password:** `zammad`

### Wazuh Dashboard

- **Username:** `admin`
- **Default password:** `SecretPassword` — **change this immediately** after first login
- **Port-forward:** `kubectl port-forward svc/wazuh-dashboard -n wazuh 8443:5601`

### CISO Assistant

- **Django Secret Key:** `iMy5xr2RLtO86U3Waqk7ec4zdnhVlm0F`
- **PostgreSQL connection:** uses `mcaas-postgresql-secret` in `grc` namespace
- **Ingress:** standalone Traefik Ingress (`deploy/ingress/ciso-assistant-ingress.yaml`) — not Helm-managed

### Shuffle

- **OpenSearch connection:** uses `mcaas-opensearch-secret` (key `SHUFFLE_OPENSEARCH_PASSWORD`)
- **OpenSearch URL:** `mcaas-opensearch.security-ops.svc.cluster.local:9200`

---

## Namespaces

| Purpose | Namespace |
|---------|-----------|
| Managed IT / Zammad / PostgreSQL / Redis | `managed-it` |
| Security Ops / OpenSearch / Shuffle | `security-ops` |
| GRC / CISO Assistant | `grc` |
| Wazuh (Manager + Dashboard + Indexer) | `wazuh` |
| cert-manager | `cert-manager` |

---

## Helm Releases

| Release | Chart | Namespace |
|---------|-------|-----------|
| `mcaas-postgresql` | `bitnami/postgresql` | `managed-it` |
| `mcaas-opensearch` | `opensearch/opensearch` | `security-ops` |
| `mcaas-shuffle` | `oci://ghcr.io/shuffle/charts/shuffle` | `security-ops` |
| `mcaas-zammad` | `oci://ghcr.io/zammad/charts/zammad` | `managed-it` |
| `mcaas-ciso` | `oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant` | `grc` |
| `cert-manager` | static manifest v1.16.3 | `cert-manager` |

---

## Port-Forward Quick Reference

All four web services have Traefik Ingress with TLS. Use the HTTPS URLs above
for browser access. These port-forward commands are for debugging only:

```bash
# CISO Assistant (debugging — ingress is preferred)
kubectl port-forward -n grc svc/mcaas-ciso-ciso-assistant-frontend 8443:80

# Wazuh Dashboard (debugging — ingress is preferred)
kubectl port-forward svc/wazuh-dashboard -n wazuh 8443:5601

# PostgreSQL (debugging)
kubectl port-forward svc/mcaas-postgresql -n managed-it 5432:5432

# OpenSearch (debugging)
kubectl port-forward svc/mcaas-opensearch -n security-ops 9200:9200
```

---

_This file was auto-generated by `scripts/deploy.py` on 2026-07-27 13:05:02 UTC._
