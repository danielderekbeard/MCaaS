# MCaaS Services Matrix

> **Status: DRAFT — Not for commit**  
> Complete reference of all deployed services, their ports, UIs, and default credentials.

---

## Service Overview

| Component | Namespace | Service Name | Type | Purpose |
|-----------|-----------|-------------|------|---------|
| PostgreSQL | managed-it | `mcaas-postgresql-postgresql` | StatefulSet | Central relational database |
| OpenSearch | security-ops | `mcaas-opensearch` | StatefulSet | Search & log analytics engine |
| Wazuh Manager | wazuh | `wazuh-manager` | Deployment | Security monitoring agent manager |
| Wazuh Indexer | wazuh | `wazuh-indexer` | StatefulSet | Wazuh's built-in indexer (OpenSearch-based) |
| Wazuh Dashboard | wazuh | `wazuh-dashboard` | Deployment | Wazuh web UI |
| Shuffle | security-ops | `shuffle-backend` | Deployment | SOAR automation platform |
| Zammad | managed-it | `zammad-web` | Deployment | IT helpdesk / ticketing |
| Zammad Scheduler | managed-it | `zammad-zammad-scheduler` | Deployment | Background job processor |
| Zammad WebSocket | managed-it | `zammad-zammad-websocket` | Deployment | Real-time notification server |
| CISO Assistant | grc | `ciso-assistant-frontend` | Deployment | GRC web frontend |
| CISO Assistant | grc | `ciso-assistant-backend` | Deployment | GRC API backend |
| SMTP Relay | security-ops | `smtp-relay` | Deployment | Postfix relay to Zoho Mail |

---

## Ports & Endpoints

### PostgreSQL

| Property | Value |
|----------|-------|
| **Service** | `mcaas-postgresql-postgresql.managed-it.svc.cluster.local` |
| **Port** | 5432 |
| **Protocol** | TCP (PostgreSQL wire protocol) |
| **UI** | None (database only) |
| **External Access** | Port-forward: `kubectl port-forward -n managed-it svc/mcaas-postgresql-postgresql 5432:5432` |

### OpenSearch

| Property | Value |
|----------|-------|
| **Service** | `mcaas-opensearch.security-ops.svc.cluster.local` |
| **Port** | 9200 (REST API), 9300 (transport) |
| **Protocol** | HTTPS (REST), TCP (transport) |
| **UI** | None built-in (REST API only) |
| **External Access** | Port-forward: `kubectl port-forward -n security-ops svc/mcaas-opensearch 9200:9200` |
| **Health Check** | `curl -k -u admin:<password> https://localhost:9200/_cluster/health?pretty` |

### Wazuh Dashboard

| Property | Value |
|----------|-------|
| **Service** | `wazuh-dashboard.wazuh.svc.cluster.local` |
| **Port** | 443 (HTTPS), 5601 (HTTP internally) |
| **Protocol** | HTTPS |
| **UI** | ✅ Web dashboard |
| **External Access** | Port-forward: `kubectl port-forward -n wazuh svc/wazuh-dashboard 5601:443` → `https://localhost:5601` |
| **Note** | Uses self-signed certificates; browser will show security warning |

### Wazuh Manager

| Property | Value |
|----------|-------|
| **Service** | `wazuh-manager.wazuh.svc.cluster.local` |
| **Ports** | 1514 (agent enrollment), 55000 (API) |
| **Protocol** | TCP |
| **UI** | API accessible at `https://<node>:55000` |
| **External Access** | Port-forward: `kubectl port-forward -n wazuh svc/wazuh-manager 55000:55000` |

### Wazuh Indexer

| Property | Value |
|----------|-------|
| **Service** | `wazuh-indexer.wazuh.svc.cluster.local` |
| **Port** | 9200 (REST) |
| **Protocol** | HTTPS |
| **UI** | None (internal use only) |

### Shuffle

| Property | Value |
|----------|-------|
| **Service** | `shuffle-backend.security-ops.svc.cluster.local` |
| **Port** | 3008 (HTTP backend), 3443 (HTTPS frontend) |
| **Protocol** | HTTP/HTTPS |
| **UI** | ✅ SOAR workflow builder |
| **External Access** | Port-forward: `kubectl port-forward -n security-ops svc/shuffle-backend 3008:3008` → `http://localhost:3008` |

### Zammad

| Property | Value |
|----------|-------|
| **Services** | `zammad-web`, `zammad-zammad-scheduler`, `zammad-zammad-websocket` |
| **Port** | 80 (web), 443 (HTTPS via ingress) |
| **Protocol** | HTTP/HTTPS |
| **UI** | ✅ Helpdesk / ticketing interface |
| **Ingress** | `zammad.mcaas.example.com` (configured in values) |
| **External Access** | Port-forward: `kubectl port-forward -n managed-it svc/zammad-web 8080:80` → `http://localhost:8080` |
| **Elasticsearch** | Disabled in values (uses external OpenSearch) |

### CISO Assistant

| Property | Value |
|----------|-------|
| **Services** | `ciso-assistant-frontend`, `ciso-assistant-backend` |
| **Ports** | 443 (frontend HTTPS), 8443 (backend API) |
| **Protocol** | HTTPS |
| **UI** | ✅ GRC management interface |
| **Ingress** | `ciso.mcaas.example.com` (configured in values, with ssl-passthrough) |
| **External Access** | Port-forward: `kubectl port-forward -n grc svc/ciso-assistant-frontend 8443:443` → `https://localhost:8443` |

### SMTP Relay (Postfix → Zoho Mail)

| Property | Value |
|----------|-------|
| **Service** | `smtp-relay.security-ops.svc.cluster.local` |
| **Port** | 25 |
| **Protocol** | SMTP |
| **UI** | None (relay service only) |
| **Image** | `mwader/postfix-relay:latest` |
| **External Access** | Port-forward: `kubectl port-forward -n security-ops svc/smtp-relay 1025:25` → SMTP on `localhost:1025` |
| **Upstream Relay** | `smtp.zoho.com:587` (STARTTLS with SASL auth) |
| **Sender Rewriting** | `@socom.co.il` → `hello@danieldbeard.com` (both envelope and headers via `smtp_generic_maps`) |
| **ConfigMap** | `rsyslog-postfix` (mail.* → `/var/log/postfix.log`) |
| **Secret** | `zoho-smtp-secret` (SASL password for Zoho) |
| **Deployment YAML** | `aws/smtp-relay-deployment.yaml` |

---

## Default Credentials

> ⚠️ **All passwords should be changed from defaults before production use.**

### PostgreSQL

| Property | Value |
|----------|-------|
| **Username** | `postgres` |
| **Password** | Value of `MCAAS_POSTGRES_PASSWORD` from `.env` |
| **Database** | `mcaas_db` |
| **Secret** | `mcaas-postgresql-secret` in `managed-it` namespace |
| **Secret Keys** | `postgres-password` (used by Bitnami chart), `password` (used by CISO Assistant) |

### OpenSearch

| Property | Value |
|----------|-------|
| **Username** | `admin` |
| **Password** | Value of `MCAAS_OPENSEARCH_PASSWORD` from `.env` |
| **Secret** | `mcaas-opensearch-secret` in `security-ops` namespace |
| **Secret Key** | `opensearch-password` |

### Wazuh Dashboard

| Property | Value |
|----------|-------|
| **Username** | `admin` |
| **Password** | Looked up from: `kubectl -n wazuh get secret wazuh-api-credentials -o jsonpath='{.data.password}' \| base64 -d` |
| **Default** | `MYPASSWORD_` (upstream default — **change immediately!**) |
| **Note** | The upstream kustomize overlay sets default credentials. For production, patch the secret. |

### Shuffle

| Property | Value |
|----------|-------|
| **First-Access** | No default credentials — first user registration creates the admin |
| **API Key** | Generated on first setup via the UI |
| **Note** | Shuffle creates its own SQLite/NATS internal state on first run |

### Zammad

| Property | Value |
|----------|-------|
| **First-Access** | No default credentials — first user registration creates the admin |
| **Database** | Uses PostgreSQL `mcaas-postgresql-postgresql` in `managed-it` namespace |
| **Database User** | `zammad` (auto-created by Helm chart) |

### CISO Assistant

| Property | Value |
|----------|-------|
| **First-Access** | Superuser created on first run via management command |
| **Default Superuser** | Check pod logs: `kubectl logs -n grc deployment/ciso-assistant-backend` |
| **Database** | Uses PostgreSQL `mcaas-postgresql-postgresql` in `managed-it` namespace |
| **Database User** | `ciso-assistant` (auto-created by Helm chart) |

### SMTP Relay (Postfix → Zoho Mail)

| Property | Value |
|----------|-------|
| **Zoho SMTP Host** | `smtp.zoho.com:587` |
| **Zoho Auth User** | `hello@danieldbeard.com` |
| **Zoho Auth Password** | Stored in K8s Secret `zoho-smtp-secret` (key: `SASL_PASSWD`) |
| **Sender Address** | `alerts@socom.co.il` (rewritten to `hello@danieldbeard.com` by smtp_generic_maps) |
| **Recipient** | `hello@danieldbeard.com` |
| **Config Persistence** | All Postfix config via `POSTFIX_*` and `POSTMAP_*` env vars (auto-applied on pod start) |

---

## Inter-Service Communication Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCaaS Stack                               │
│                                                                  │
│  ┌──────────────┐      ┌──────────────┐                         │
│  │   PostgreSQL  │◄─────│    Zammad    │  (managed-it ns)       │
│  │   :5432       │◄─────│ CISO Asst    │                         │
│  └──────┬───────┘      └──────────────┘                         │
│         │                                                        │
│  ┌──────┴───────┐                                              │
│  │  OpenSearch   │◄─────│ Wazuh Indexer │  (security-ops ns)    │
│  │   :9200       │◄─────│ Shuffle       │                        │
│  └──────────────┘      └──────┬───────┘                          │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │                     │                       │
│               ┌────▼─────┐        ┌─────▼──────┐               │
│               │  Zammad  │        │ SMTP Relay  │               │
│               │  (API)   │        │ (Postfix)   │               │
│               └──────────┘        └─────┬──────┘               │
│                                         │                        │
│  ┌──────────────┐      ┌──────────────┐  │ (external)            │
│  │Wazuh Manager  │──────│Wazuh Dashboard│  │  ──► Zoho Mail      │
│  │  :1514/:55000 │      │   :443        │  │    smtp.zoho.com     │
│  └──────────────┘      └──────────────┘  │    :587               │
│                                           │                        │
└───────────────────────────────────────────┼────────────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │   Zoho Mail     │
                                   │  (External)     │
                                   └─────────────────┘
```

**Key connections:**
- **Shuffle → OpenSearch**: Shuffle backend connects to `mcaas-opensearch.security-ops:9200` for SOAR data storage
- **Shuffle → Zammad API**: Shuffle Parse action creates tickets via `mcaas-zammad-nginx.managed-it:8080/api/v1`
- **Shuffle → SMTP Relay**: Shuffle Parse action sends email via `smtp-relay.security-ops:25`
- **SMTP Relay → Zoho Mail**: Postfix relays through `smtp.zoho.com:587` with STARTTLS + SASL auth
- **Wazuh → Shuffle**: Wazuh webhook integration posts alerts to Shuffle webhook trigger
- **Shuffle → Wazuh API**: Shuffle Parse action enriches alerts via `wazuh-manager.wazuh:55000`
- **Zammad → PostgreSQL**: Uses `mcaas-postgresql-postgresql.managed-it:5432` with database `zammad`
- **CISO Assistant → PostgreSQL**: Uses `mcaas-postgresql-postgresql.managed-it:5432` with database `ciso-assistant`
- **Wazuh Indexer**: Has its own built-in OpenSearch instance (separate from `mcaas-opensearch`)

---

*See also: [Installation Guide](./installation-guide.md) | [Configuration Matrix](./configuration-matrix.md)*