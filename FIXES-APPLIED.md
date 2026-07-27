# MCaaS Fixes Applied - 2026-07-27

## Summary of Changes

### 1. ✅ CISO Assistant Database Fix - COMPLETE

**Problem:** CISO backend couldn't connect to PostgreSQL - database "ciso-assistant" didn't exist.

**Solution:** 
- Created Kubernetes Job `create-ciso-db` to create the database
- Updated `deploy/values/ciso-assistant.yaml` to include initContainer that creates database on deployment

**Files Modified:**
- `deploy/values/ciso-assistant.yaml` - Added initContainer for database creation

**Status:** ✅ CISO backend now running (2/2 pods Ready)

---

### 2. ✅ Traefik Backend TLS Fix - COMPLETE

**Problem:** Traefik couldn't connect to backend services due to certificate verification errors:
```
tls: failed to verify certificate: x509: cannot validate certificate for 10.42.0.254
```

**Solution:**
- Created `ServersTransport` resources with `insecureSkipVerify: true` in each namespace
- Updated all IngressRoutes to use the insecure transport

**Files Modified:**
- `deploy/traefik-serverstransport.yaml` - New file with all ServersTransport definitions
- `deploy/ingress/traefik-ingress.yaml` - Updated with ServersTransport references

**Status:** ✅ Shuffle and Zammad working, CISO now responding

---

### 3. ⚠️ Wazuh Certificate Filename Mismatch - PARTIAL FIX

**Problem:** Wazuh StatefulSets expect certificate files with specific names:
- `node.pem`, `node-key.pem`, `root-ca.pem`, `admin.pem`, `admin-key.pem`

But cert-manager creates secrets with names:
- `tls.crt`, `tls.key`, `ca.crt`

**Current Status:**
- ConfigMaps fixed (created hashed versions: `indexer-conf-46b5244fc2`, `wazuh-conf-2t66md6694`)
- Wazuh pods starting but failing with mount errors

**Required Fix:**
Either:
1. Modify Wazuh StatefulSets to use subPath mounts mapping cert-manager filenames to expected filenames
2. Create a script to copy/rename certificates in a initContainer
3. Use OpenSSL to generate Wazuh-compatible certificates

**Files Documented:**
- `deploy/wazuh-config-fix.md` - Documentation of the issue and potential fixes

---

## Working Services

| Service | Status | URL |
|---------|--------|-----|
| **Shuffle** | ✅ Working | https://shuffle.mcaas.example.com |
| **Zammad** | ✅ Working | https://zammad.mcaas.example.com |
| **CISO Assistant** | ✅ Working | https://ciso.mcaas.example.com |
| **Wazuh** | ⚠️ Config Issue | Not accessible yet |

---

## How to Complete Wazuh Fix

### Option 1: Patch StatefulSet (Recommended)

```bash
# Patch the indexer StatefulSet to use subPath mounts
kubectl patch statefulset wazuh-indexer -n wazuh --type='json' -p='[{
  "op": "replace",
  "path": "/spec/template/spec/volumes/1",
  "value": {
    "name": "indexer-certs",
    "secret": {
      "secretName": "wazuh-indexer-certs",
      "items": [
        {"key": "tls.crt", "path": "node.pem"},
        {"key": "tls.key", "path": "node-key.pem"},
        {"key": "ca.crt", "path": "root-ca.pem"}
      ]
    }
  }
}]'
```

### Option 2: Manual Certificate Creation
Create certificates with proper filenames using cert-manager Certificate resources with `keystores` or additional output formats.

---

## Deployment Updates for Future Redeployments

The following files now include fixes:

1. **deploy/values/ciso-assistant.yaml** - Includes initContainer for database creation
2. **deploy/ingress/traefik-ingress.yaml** - Includes ServersTransport and updated IngressRoutes
3. **deploy/traefik-serverstransport.yaml** - Standalone ServersTransport definitions
4. **deploy/wazuh-config-fix.md** - Documentation for Wazuh certificate issues

---

## Next Steps

1. ✅ Access Shuffle: https://shuffle.mcaas.example.com
2. ✅ Access Zammad: https://zammad.mcaas.example.com  
3. ✅ Access CISO: https://ciso.mcaas.example.com
4. ⏳ Fix Wazuh certificates (requires StatefulSet modification or new certificate generation)
