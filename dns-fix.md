# DNS Fix Required

## ✅ Services Are Working!

All services are running and accessible through Traefik:

| Service | Status | Internal Test Result |
|---------|--------|---------------------|
| **Shuffle** | ✅ Working | HTTP 200 |
| **Zammad** | ✅ Working | HTTP 200 (Zammad Helpdesk) |
| **CISO Assistant** | ✅ Working | HTTP 302 (redirect) |
| **Wazuh Dashboard** | ✅ Working | Running |

## The Problem

Your browser cannot resolve `*.mcaas.example.com` domains to the cluster IP `192.168.127.2`.

## The Fix

### Option 1: Edit Hosts File (Recommended for Testing)

**Run PowerShell as Administrator** and execute:

```powershell
$hostsContent = @"
192.168.127.2 shuffle.mcaas.example.com
192.168.127.2 zammad.mcaas.example.com
192.168.127.2 ciso.mcaas.example.com
192.168.127.2 wazuh.mcaas.example.com
"@

Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value $hostsContent
```

**Or manually edit** `C:\Windows\System32\drivers\etc\hosts` and add:
```
192.168.127.2 shuffle.mcaas.example.com
192.168.127.2 zammad.mcaas.example.com
192.168.127.2 ciso.mcaas.example.com
192.168.127.2 wazuh.mcaas.example.com
```

### Option 2: Use Port-Forwarding (No DNS needed)

```powershell
# Shuffle
kubectl port-forward -n security-ops svc/shuffle-frontend 8080:80
# Access: http://localhost:8080

# Zammad
kubectl port-forward -n managed-it svc/mcaas-zammad-nginx 8081:8080
# Access: http://localhost:8081

# CISO
kubectl port-forward -n grc svc/mcaas-ciso-ciso-assistant-frontend 8082:80
# Access: http://localhost:8082

# Wazuh
kubectl port-forward -n wazuh svc/dashboard 8083:443
# Access: https://localhost:8083 (accept certificate warning)
```

## Verification

After adding hosts entries, test with:
```powershell
ping shuffle.mcaas.example.com
# Should resolve to 192.168.127.2
```

Then open in browser:
- https://shuffle.mcaas.example.com
- https://zammad.mcaas.example.com
- https://ciso.mcaas.example.com
- https://wazuh.mcaas.example.com

**Note:** You will get certificate warnings because we're using self-signed certificates. Click "Advanced" → "Proceed anyway" (or add the CA cert to your trusted store).
