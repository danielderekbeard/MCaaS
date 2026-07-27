# MCaaS Full Redeployment Status
**Date:** 2026-07-27 04:35 GMT+3  
**Domain:** *.mcaas.example.com

---

## ✅ Deployment Complete

| Service | Namespace | Status | External URL |
|---------|-----------|--------|--------------|
| **PostgreSQL** | managed-it | ✅ Running | Internal |
| **OpenSearch** | security-ops | ✅ Running | Internal |
| **Shuffle** | security-ops | ✅ Running | https://shuffle.mcaas.example.com |
| **Zammad** | managed-it | ✅ Running | https://zammad.mcaas.example.com |
| **CISO Assistant** | grc | ✅ Running | https://ciso.mcaas.example.com |
| **Wazuh Dashboard** | wazuh | ✅ Running | https://wazuh.mcaas.example.com |
| **Wazuh Indexer** | wazuh | 🟡 Initializing | Internal |
| **Wazuh Manager** | wazuh | 🟡 Initializing | Internal |

---

## Certificate Configuration

### External-facing (Let's Encrypt)
- **Issuer:** letsencrypt-prod
- **Domain:** *.mazuh.mcaas.example.com
- **Challenge:** HTTP-01 via Traefik

### Internal (Self-signed CA)
- **Issuer:** wazuh-internal-issuer
- **Used for:** Wazuh indexer, dashboard, manager internal communication

---

## Pod Status

```
NAMESPACE      NAME                                              READY   STATUS
wazuh          wazuh-dashboard-5c6588d5f4-tpnjx                  1/1     Running
wazuh          wazuh-indexer-0                                   0/1     Init:0/2
wazuh          wazuh-manager-master-0                            0/1     ContainerCreating
wazuh          wazuh-manager-worker-0                            0/1     ContainerCreating
wazuh          wazuh-manager-worker-1                            0/1     ContainerCreating
```

**Note:** Wazuh indexer and managers are initializing. This can take 2-5 minutes as they:
1. Initialize OpenSearch indices
2. Generate security admin certificates
3. Initialize Wazuh cluster

---

## Next Steps

1. **Wait for Wazuh StatefulSets** (2-5 minutes)
   ```powershell
   kubectl get pods -n wazuh -w
   ```

2. **Configure Wazuh Integrations**
   - Update Shuffle workflow webhook
   - Configure Zammad ticket creation

3. **Verify TLS Certificates**
   - Check cert-manager certificate status:
   ```powershell
   kubectl get certificates --all-namespaces
   ```

---

## Issues Resolved

1. ✅ **TLS Certificates:** Created cert-manager ClusterIssuer and Certificates
2. ✅ **Storage Class:** Patched PVCs to use local-path
3. ✅ **Dashboard Config:** Added missing ConfigMap volume mounts
4. ✅ **Secret Mapping:** Mapped cert-manager secrets to expected cert file names

---

## Commands

### Check Wazuh Status
```powershell
kubectl get pods -n wazuh
kubectl logs -n wazuh -l app=wazuh-indexer --tail=50
kubectl logs -n wazuh -l app=wazuh-manager --tail=50
```

### Port-forward for Testing
```powershell
# Wazuh Dashboard
kubectl port-forward -n wazuh svc/dashboard 5601:443

# Shuffle
kubectl port-forward -n security-ops svc/shuffle-frontend 8080:80
```

---

## Deployment Duration: ~12 minutes
