# Wazuh Dashboard Ingress Fix

## Problem

After initial deployment, accessing `https://deimos.mcaas.example.com/` resulted in a **404 error**.

## Root Cause Analysis

1. **Original Configuration Issue**: The initial setup used a Kubernetes standard `Ingress` resource which couldn't properly handle the Wazuh dashboard's self-signed HTTPS certificate on the backend.

2. **TLS Certificate Verification Error**: Wazuh dashboard serves HTTPS on port 5601 with a self-signed certificate. Traefik was failing with:
   ```
   tls: failed to verify certificate: x509: cannot validate certificate for 10.42.0.184 because it doesn't contain any IP SANs
   ```

3. **Port/Protocol Mismatch**: The original ingress was configured to use HTTP backend protocol, but Wazuh dashboard only accepts HTTPS connections.

## Solution

Replaced the standard Kubernetes Ingress with Traefik-native resources:

1. **ServersTransport** (`wazuh-insecure-transport`): Configures Traefik to skip TLS verification when connecting to the Wazuh backend.

2. **ClusterIP Service** (`dashboard`): Changed from LoadBalancer to ClusterIP since ingress handles external access. Maps service port 443 to pod port 5601.

3. **IngressRoute** (`mcaas-wazuh-dashboard`): Traefik-native ingress that:
   - Routes `deimos.mcaas.example.com` traffic
   - Uses HTTPS entrypoint (`websecure`)
   - References the custom ServersTransport for backend TLS handling
   - Terminates TLS with the `wazuh-dashboard-tls` certificate

## Files

| File | Purpose |
|------|---------|
| `wazuh-ingress-config.yaml` | Complete configuration (apply this) |
| `wazuh-dashboard-service.yaml` | Service definition only |
| `wazuh-ingressroute.yaml` | IngressRoute + ServersTransport |

## Application

### Fresh Deployment

Apply the complete configuration:

```bash
kubectl apply -f wazuh-ingress-config.yaml
```

### After Power On (State Restore)

If restoring from powered-off state and the ingress isn't working:

```bash
# Check current ingress status
kubectl get ingressroute -n wazuh
kubectl get service dashboard -n wazuh

# Re-apply if needed
kubectl apply -f wazuh-ingress-config.yaml
```

## Verification

```bash
# Test from inside cluster
kubectl run test-wazuh --rm -i --restart=Never --image=curlimages/curl -- \
  curl -k -L -H "Host: deimos.mcaas.example.com" https://<traefik-lb-ip>

# Expected output: Wazuh dashboard HTML
```

## References

- Traefik ServersTransport: https://doc.traefik.io/traefik/routing/services/#serverstransport
- Traefik IngressRoute: https://doc.traefik.io/traefik/routing/providers/kubernetes-crd/
- Wazuh Dashboard TLS: https://documentation.wazuh.com/current/user-manual/wazuh-dashboard/configuring-indices.html
