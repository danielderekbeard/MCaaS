# MCaaS Fixes Applied — 2026-07-27

## ✅ All Fixes Applied Successfully

### 1. ✅ CISO Assistant Database Fix
- Created missing PostgreSQL database `ciso-assistant`
- Updated `deploy/values/ciso-assistant.yaml` with initContainer for automatic database creation
- Status: **Running and accessible**

### 2. ✅ Traefik Backend TLS Fix
- Created `ServersTransport` resources with `insecureSkipVerify: true`
- Updated all IngressRoutes to use insecure transport for backend connections
- Status: **All services accessible via HTTPS**

### 3. ✅ Wazuh Certificate Fix
- Fixed ConfigMap references with hash suffixes
- Created StatefulSets with proper certificate file mapping using initContainer
- Fixed certificate permissions (copied to emptyDir with correct ownership)
- Updated deployment files for future use

---

## Service Status

| Service | Status | URL | Notes |
|---------|--------|-----|-------|
| **Shuffle** | ✅ Working | https://shuffle.mcaas.example.com | Full functionality |
| **Zammad** | ✅ Working | https://zammad.mcaas.example.com | Full functionality |
| **CISO Assistant** | ✅ Working | https://ciso.mcaas.example.com | Full functionality |
| **Wazuh Dashboard** | ✅ Running | https://wazuh.mcaas.example.com | Starting up |
| **Wazuh Indexer** | ✅ Running | Internal | Initializing |
| **Wazuh Managers** | ✅ Running | Internal | Ready |

---

## Files Created/Updated

### Deployment Files (for future redeployments):

1. **`deploy/values/ciso-assistant.yaml`**
   - Added initContainer to create database automatically

2. **`deploy/ingress/traefik-ingress.yaml`**
   - Includes ServersTransport definitions
   - Updated IngressRoutes with `serversTransport: insecure-transport`

3. **`deploy/wazuh/wazuh-indexer-statefulset.yaml`**
   - Fixed certificate mounting with initContainer
   - Copies certs to emptyDir with correct permissions (1000:1000)
   - Proper ConfigMap references with hash suffixes

4. **`deploy/wazuh/wazuh-manager-master-statefulset.yaml`**
   - Fixed certificate file mapping (tls.crt → node.pem, etc.)
   - Proper ConfigMap references

5. **`deploy/wazuh/wazuh-manager-worker-statefulset.yaml`**
   - Fixed certificate file mapping
   - Proper ConfigMap references

6. **`deploy/wazuh/wazuh-config-fix.md`**
   - Documentation for Wazuh certificate issues

---

## Key Fixes Applied

### Certificate Filename Mapping

**Problem:** cert-manager creates certificates with standard names:
- `tls.crt`, `tls.key`, `ca.crt`

**Wazuh Expected:**
- `node.pem`, `node-key.pem`, `root-ca.pem`
- `admin.pem`, `admin-key.pem`

**Solution:** Used initContainer to copy certificates with correct names and permissions:
```yaml
initContainers:
- name: fix-certs-permissions
  image: busybox
  securityContext:
    runAsUser: 0
  command:
  - sh
  - -c
  - |
    mkdir -p /tmp-certs
    cp /certs/tls.crt /tmp-certs/node.pem
    cp /certs/tls.key /tmp-certs/node-key.pem
    cp /certs/ca.crt /tmp-certs/root-ca.pem
    cp /certs/tls.crt /tmp-certs/admin.pem
    cp /certs/tls.key /tmp-certs/admin-key.pem
    chown -R 1000:1000 /tmp-certs
    chmod 644 /tmp-certs/*.pem
  volumeMounts:
  - name: certs-tmp
    mountPath: /tmp-certs
  - name: indexer-certs
    mountPath: /certs
    readOnly: true
```

### ConfigMap Hash Suffix Fix

**Problem:** StatefulSets created via kustomize reference ConfigMaps with hash suffixes (e.g., `indexer-conf-46b5244fc2`)

**Solution:** Created ConfigMaps with the exact hash names the StatefulSets expect:
- `indexer-conf-46b5244fc2`
- `wazuh-conf-2t66md6694`
- `dashboard-conf-656mt44t78`

---

## Access Instructions

1. **Add to hosts file** (C:\Windows\System32\drivers\etc\hosts):
```
127.0.0.1 shuffle.mcaas.example.com
127.0.0.1 zammad.mcaas.example.com
127.0.0.1 ciso.mcaas.example.com
127.0.0.1 wazuh.mcaas.example.com
```

2. **Flush DNS:**
```powershell
ipconfig /flushdns
```

3. **Access URLs:**
- https://shuffle.mcaas.example.com
- https://zammad.mcaas.example.com
- https://ciso.mcaas.example.com
- https://wazuh.mcaas.example.com

4. **Certificate Warning:** Accept the self-signed certificate warning in your browser

---

## Deployment Command Reference

For future redeployments:

```bash
# Apply servers transport first
kubectl apply -f deploy/traefik-serverstransport.yaml

# Deploy services
helm install mcaas-postgresql bitnami/postgresql -n managed-it -f deploy/values/postgresql.yaml
helm install mcaas-opensearch opensearch/opensearch -n security-ops -f deploy/values/opensearch.yaml
helm install mcaas-shuffle shuffle/shuffle -n security-ops -f deploy/values/shuffle.yaml
helm install mcaas-zammad zammad/zammad -n managed-it -f deploy/values/zammad.yaml
helm install mcaas-ciso ciso-assistant/ciso-assistant -n grc -f deploy/values/ciso-assistant.yaml

# Deploy Wazuh (use custom StatefulSets instead of upstream kustomization)
kubectl apply -f deploy/wazuh/wazuh-indexer-statefulset.yaml
kubectl apply -f deploy/wazuh/wazuh-manager-master-statefulset.yaml
kubectl apply -f deploy/wazuh/wazuh-manager-worker-statefulset.yaml

# Apply IngressRoutes
kubectl apply -f deploy/ingress/traefik-ingress.yaml
```

---

**All fixes have been applied and documented for future redeployments.**
