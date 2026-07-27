# MCaaS Deployment Summary
**Date:** 2026-07-27  
**Domain:** *.mcaas.example.com

---

## ✅ Deployment Status

| Service | Namespace | Status | URL |
|---------|-----------|--------|-----|
| PostgreSQL | managed-it | ✅ Running | Internal |
| OpenSearch | security-ops | ✅ Running | Internal |
| Shuffle | security-ops | ✅ Deployed | https://shuffle.mcaas.example.com |
| Zammad | managed-it | ✅ Deployed | https://zammad.mcaas.example.com |
| CISO Assistant | grc | ✅ Deployed | https://ciso.mcaas.example.com |
| Wazuh | wazuh | ⚠️ Requires Certs | https://wazuh.mcaas.example.com |

---

## Certificate Configuration

### Let's Encrypt (External-facing)
- **Issuer:** letsencrypt-prod
- **Domain:** *.mcaas.example.com
- **Services:** wazuh, shuffle, zammad, ciso
- **Type:** HTTP-01 Challenge via Traefik

### Self-Signed (Internal)
- For internal service-to-service communication
- Managed by cert-manager CA issuer

---

## Ingress Configuration

All services exposed via Traefik IngressRoute with TLS:

```yaml
# Example: Shuffle
Host: shuffle.mcaas.example.com
Port: 80 (internal) → 443 (external)
TLS Secret: shuffle-tls-secret
```

---

## Next Steps

### 1. Complete Wazuh Deployment
Wazuh requires TLS certificates for indexer/manager/dashboard. Options:
- A. Generate self-signed certs and apply via ConfigMap
- B. Skip Wazuh and use existing Wazuh instance

### 2. Configure Integrations
- Deploy enhanced Shuffle workflow for Wazuh alerts
- Configure Wazuh webhook to send alerts to Shuffle
- Verify Zammad ticket creation from alerts

### 3. DNS Configuration
Ensure DNS records point to cluster:
```
wazuh.mcaas.example.com  → <cluster-ip>
shuffle.mcaas.example.com → <cluster-ip>
zammad.mcaas.example.com → <cluster-ip>
ciso.mcaas.example.com → <cluster-ip>
```

---

## Credentials

Stored in `.env` file and Kubernetes secrets:
- PostgreSQL: `mcaas-postgresql-secret`
- OpenSearch: `mcaas-opensearch-secret`
- Redis: `mcaas-zammad-redis-pass`
- Django: `mcaas-ciso-secret`

---

## Wazuh TLS Certificate Workaround

Since OpenSSL is not available in the Windows environment, here are options:

### Option A: Use Pre-existing Certificates
```powershell
# Copy existing certs from backup if available
kubectl create secret tls wazuh-tls-secret \
  --cert=wazuh-cert.pem \
  --key=wazuh-key.pem \
  -n wazuh
```

### Option B: Generate via WSL with openssl
```bash
# If WSL distro with openssl is available:
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout wazuh-key.pem \
  -out wazuh-cert.pem \
  -subj "/CN=wazuh.mcaas.example.com"
```

### Option C: Use cert-manager self-signed CA
```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: wazuh-internal
  namespace: wazuh
spec:
  secretName: wazuh-internal-tls
  issuerRef:
    name: selfsigned-ca
    kind: ClusterIssuer
  dnsNames:
  - wazuh-indexer
  - wazuh-dashboard
  - wazuh-manager
```

---

## Summary

**Successfully Deployed:**
- ✅ PostgreSQL (Bitnami)
- ✅ OpenSearch
- ✅ Shuffle SOAR
- ✅ Zammad Ticketing
- ✅ CISO Assistant GRC
- ✅ Cert-manager with Let's Encrypt
- ✅ Traefik Ingress with TLS

**Pending:**
- ⚠️ Wazuh SIEM (requires TLS certificates)

**Time to Complete:** ~7 minutes (excluding Wazuh)
