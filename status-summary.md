# MCaaS Services Status - 2026-07-27 11:15

## ✅ WORKING Services

| Service | Status | URL | Notes |
|---------|--------|-----|-------|
| **Shuffle** | ✅ HTTP 200 | https://shuffle.mcaas.example.com | Fully functional |
| **Zammad** | ✅ HTTP 200 | https://zammad.mcaas.example.com | Fully functional |

## ❌ NOT WORKING

| Service | Issue | Details |
|---------|-------|---------|
| **CISO Assistant** | Database missing | Backend cannot connect to PostgreSQL - `ciso-assistant` database doesn't exist |
| **Wazuh** | Still initializing | Indexer pod stuck in Init:0/2, manager pods ContainerCreating |

---

## What Was Fixed

The root cause was **certificate verification between Traefik and backend services**.

### Problem
Traefik was trying to verify TLS certificates when connecting to backend services,
but the certificates didn't have IP SANs, causing 500 errors:
```
tls: failed to verify certificate: x509: cannot validate certificate for 10.42.0.254
```

### Solution
Created `ServersTransport` resources with `insecureSkipVerify: true` in each namespace
to allow Traefik to connect to backends without certificate verification.

---

## To Access Working Services

Your hosts file should have:
```
127.0.0.1 shuffle.mcaas.example.com
127.0.0.1 zammad.mcaas.example.com
127.0.0.1 ciso.mcaas.example.com
127.0.0.1 wazuh.mcaas.example.com
```

Then open:
- https://shuffle.mcaas.example.com
- https://zammad.mcaas.example.com

(You'll get certificate warnings - click Advanced → Proceed anyway)

---

## Remaining Issues to Fix

### CISO Assistant
```bash
# Create the missing database in PostgreSQL
kubectl exec -n managed-it mcaas-postgresql-0 -- psql -U postgres -c "CREATE DATABASE ciso_assistant;"
```

### Wazuh
Still initializing. Check status:
```bash
kubectl get pods -n wazuh -w
```

May need to check ConfigMaps or logs if stuck.
