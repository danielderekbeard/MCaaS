# MCaaS Deployment Summary

| Field | Value |
|-------|-------|
| **Client** | `default` |
| **Prefix** | `mcaas` |
| **Domain** | `mcaas.example.com` |
| **Generated** | 2026-07-25 23:53:25 UTC |
| **Mode** | Dry-run (no changes applied) |

---

## Web Interfaces (Ingress)

All services are exposed via the NGINX Ingress Controller.  Access them
by adding the host entries to your hosts file (see Local Access Setup below).

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| **Zammad** (Ticketing) | [http://alala.mcaas.example.com](http://alala.mcaas.example.com) | `admin` / set on first login |
| **CISO Assistant** (GRC) | [http://strategos.mcaas.example.com](http://strategos.mcaas.example.com) | `admin` / set on first login |
| **Shuffle** (SOAR) | [http://kydoimos.mcaas.example.com](http://kydoimos.mcaas.example.com) | OpenID / configured at first setup |
| **Wazuh Dashboard** (SIEM) | [http://deimos.mcaas.example.com](http://deimos.mcaas.example.com) | `admin` / `MYPASSWORD_` — change immediately |

## Local Access Setup (Windows)

Add the following entries to your Windows hosts file so that the
ingress domains resolve to the LoadBalancer IP:

1.  Get the LoadBalancer IP:
    ```bash
    kubectl get svc -n ingress-nginx
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
- **Password:** `vpS%kNlbAVs*IgKNay&yUtSV`
- **Database names:** `mcaas_db` (default), `zammad`, `ciso-assistant`

### OpenSearch

- **Host:** `{os_host}:9200`
- **Username:** `admin`
- **Password:** `W$yA7DoOUPbgvx!EBb3u#HXT`

### Zammad Redis

- **Host:** `{zammad_redis}:6379`
- **Password:** `<redis-password (dry-run: not retrieved)>`

### Wazuh Dashboard

- **Username:** `admin`
- **Default password:** `MYPASSWORD_` — **change this immediately** after first login
- **Port-forward:** `kubectl port-forward svc/wazuh-dashboard -n wazuh 8443:5601`

### CISO Assistant

- **Django Secret Key:** `qWGz9@Ri#PDZ4NTrndD2E$g*WcoIQpcWxWwQ6vadIFcBP5VePn`
- **PostgreSQL connection:** uses `mcaas-postgresql-secret` in `grc` namespace

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
| NGINX Ingress Controller | `ingress-nginx` |

---

## Helm Releases

| Release | Chart | Namespace |
|---------|-------|-----------|
| `mcaas-postgresql` | `bitnami/postgresql` | `managed-it` |
| `mcaas-opensearch` | `opensearch/opensearch` | `security-ops` |
| `mcaas-shuffle` | `oci://ghcr.io/shuffle/charts/shuffle` | `security-ops` |
| `mcaas-zammad` | `oci://ghcr.io/zammad/charts/zammad` | `managed-it` |
| `mcaas-ciso` | `oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant` | `grc` |
| `ingress-nginx` | `ingress-nginx/ingress-nginx` | `ingress-nginx` |

---

## Port-Forward Quick Reference

Prefer the Ingress URLs above for local access.  These commands are
provided as fallbacks for debugging or when ingress is unavailable:

```bash
# Zammad (if ingress is disabled)
# kubectl port-forward svc/mcaas-zammad -n managed-it 8080:8080

# CISO Assistant (if ingress is disabled)
# kubectl port-forward svc/mcaas-ciso -n grc 8443:8443

# Wazuh Dashboard
kubectl port-forward svc/wazuh-dashboard -n wazuh 8443:5601

# Shuffle
kubectl port-forward svc/shuffle -n security-ops 3000:80

# PostgreSQL (debugging)
kubectl port-forward svc/mcaas-postgresql -n managed-it 5432:5432

# OpenSearch (debugging)
kubectl port-forward svc/mcaas-opensearch -n security-ops 9200:9200
```

---

_This file was auto-generated by `deploy.py` on 2026-07-25 23:53:25 UTC._
