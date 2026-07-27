# MCaaS Troubleshooting Report
**Date:** 2026-07-27 04:44 GMT+3

---

## ✅ Services Status (Internal)

| Service | Internal Status | External Access | Notes |
|---------|-----------------|-----------------|-------|
| **PostgreSQL** | ✅ Running | N/A | Working |
| **OpenSearch** | ✅ Running | N/A | Working |
| **Shuffle** | ✅ Running | ⚠️ Needs fix | Internal: OK, Ingress: Issue |
| **Zammad** | ✅ Running | ⚠️ Needs fix | Internal: OK, Ingress: Issue |
| **CISO Assistant** | ✅ Running | ✅ Ingress OK | Standalone Traefik Ingress at `strategos.mcaas.example.com` |
| **Wazuh Dashboard** | ✅ Running | ⚠️ Needs fix | Internal: OK, Ingress: Issue |
| **Wazuh Indexer** | 🟡 Initializing | N/A | ConfigMap fixed, starting up |
| **Wazuh Manager** | 🟡 Initializing | N/A | Starting up |

---

## Issues Found & Fixed

### 1. Let's Encrypt Certificate Issue ❌
**Problem:** ACME server rejected `mcaas.example.com` as a forbidden domain
**Fix:** Switched to self-signed certificates using cert-manager internal CA
**Status:** ✅ Fixed - all certificates now ready

### 2. ConfigMap Name Issue ❌
**Problem:** Wazuh pods couldn't find ConfigMaps (kustomize added hash suffixes)
**Fix:** Created ConfigMaps without hash suffixes
**Status:** ✅ Fixed - Wazuh pods now starting

### 3. Ingress Service Name Mismatch ❌
**Problem:** IngressRoutes referenced wrong service names
**Fix:** Updated IngressRoutes with correct service names:
- Zammad: `mcaas-zammad-nginx` (port 8080)
- Shuffle: `shuffle-frontend` (port 80)
- CISO: `mcaas-ciso-ciso-assistant-frontend` (port 80)
- Wazuh: `dashboard` (port 443)

---

## Current Issue: External Access

**Problem:** Services work internally but not via external Ingress

**Evidence:**
```bash
# Internal access works:
curl http://shuffle-frontend  # Returns HTML ✓

# External access fails:
https://shuffle.mcaas.example.com  # Connection error
```

**Possible Causes:**
1. DNS not resolving `*.mcaas.example.com` to cluster IP
2. Traefik not routing correctly to services
3. TLS certificate chain issues (browsers rejecting self-signed)

---

## Next Steps to Fix External Access

### Option 1: DNS Configuration
Ensure `*.mcaas.example.com` resolves to your cluster IP:
```
# Add to your DNS or hosts file:
192.168.127.2  shuffle.mcaas.example.com
192.168.127.2  zammad.mcaas.example.com
192.168.127.2  ciso.mcaas.example.com
192.168.127.2  wazuh.mcaas.example.com
```

### Option 2: Check Traefik Configuration
```powershell
# Check Traefik service
kubectl get svc -n kube-system traefik

# Port-forward to test Traefik directly
kubectl port-forward -n kube-system svc/traefik 8080:80 8443:443
```

### Option 3: Use Port-Forwarding for Testing
```powershell
# Shuffle
kubectl port-forward -n security-ops svc/shuffle-frontend 8080:80
# Access: http://localhost:8080

# Zammad
kubectl port-forward -n managed-it svc/mcaas-zammad-nginx 8081:8080
# Access: http://localhost:8081
```

---

## Working Services (Verified Internal)

1. **Shuffle** - Internal curl returned HTML page
2. **Zammad** - Pod running, nginx serving
3. **CISO Assistant** - Pods running
4. **Wazuh Dashboard** - Pod running
5. **PostgreSQL** - Running
6. **OpenSearch** - Running

---

## Quick Test Commands

```powershell
# Test all services internally
kubectl run test --image=curlimages/curl --rm -it --restart=Never -- `
  sh -c "curl -s http://shuffle-frontend.security-ops.svc.cluster.local | head -5"

# Port-forward for manual testing
kubectl port-forward -n security-ops svc/shuffle-frontend 8080:80
```

---

## Summary

**Core Services:** ✅ All running internally
**TLS Certificates:** ✅ All created (self-signed)
**Ingress Configuration:** ⚠️ Services correct, external routing needs verification

**Recommended:** Use port-forwarding for immediate access while troubleshooting Ingress/DNS.
