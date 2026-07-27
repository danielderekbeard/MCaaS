# MCaaS Session Changes & Conclusions

> **Status: DRAFT — Not for commit**  
> Log of all changes, findings, and conclusions from this deployment session.

---

## Changes Made to `scripts/deploy.py`

### 1. OpenSearch Helm Timeout Increase
- **What**: Increased OpenSearch deployment timeout from 5 minutes to 10 minutes
- **Where**: `deploy_wazuh()` → `wait_for_resource()` call for OpenSearch
- **Why**: OpenSearch 3.7.0 image is ~1.3 GB and requires extensive init-container work (plugin loading, security index creation). On first deployment, the pod consistently takes >5 minutes to become Ready.
- **Impact**: Prevents false timeout failures on fresh deployments

### 2. Wazuh kubectl-wait Timeout Increases
- **What**: Increased all Wazuh-related `kubectl wait` timeouts from 5 minutes to 10 minutes each
- **Where**: `deploy_wazuh()` function — all `kubectl wait` commands for Wazuh manager, indexer, and dashboard
- **Why**: Wazuh pods pull large images and perform initialization (certificate setup, indexer bootstrap). 5 minutes was insufficient on k3s/Rancher Desktop.
- **Impact**: More resilient Wazuh deployment on slower environments

### 3. Shuffle Timeout Increase
- **What**: Increased Shuffle deployment timeout from 5 minutes to 8 minutes
- **Where**: `deploy_shuffle()` → `wait_for_resource()` call
- **Why**: Shuffle frontend depends on backend readiness. Backend must connect to OpenSearch before the frontend nginx can route traffic.
- **Impact**: Prevents premature timeout during Shuffle startup

### 4. Zammad Timeout Increase
- **What**: Increased Zammad deployment timeout from 5 minutes to 8 minutes
- **Where**: `deploy_zammad()` → `wait_for_resource()` call
- **Why**: Zammad has multiple init containers and must wait for PostgreSQL availability.
- **Impact**: More reliable Zammad deployment

### 5. CISO Assistant Timeout Increase
- **What**: Increased CISO Assistant deployment timeout from 5 minutes to 8 minutes
- **Where**: `deploy_ciso_assistant()` → `wait_for_resource()` call
- **Why**: CISO Assistant backend must initialize the database schema before reporting Ready.
- **Impact**: Prevents false timeout on fresh deployments

### 6. StorageClass Delete+Recreate Strategy
- **What**: Changed from `kubectl patch storageclass` to `kubectl delete --ignore-not-found` followed by `kubectl apply`
- **Where**: `deploy_wazuh()` function — `wazuh-storage` StorageClass creation
- **Why**: StorageClass `provisioner` field is immutable. Patching fails with: `StorageClass.storage.k8s.io "wazuh-storage" is invalid: spec.provisioner: Forbidden: updates to this field are not allowed`
- **Impact**: Allows redeployment without manual StorageClass cleanup. The `--ignore-not-found` flag makes this idempotent.

### 7. Shuffle fullnameOverride Fix
- **What**: Added `fullnameOverride: shuffle` to `deploy/values/shuffle.yaml`
- **Where**: Top-level key in shuffle.yaml values
- **Why**: Without this, Helm generates release-name-prefixed service names (e.g., `mcaas-shuffle-backend`). The Shuffle frontend's nginx config hardcodes `shuffle-backend` as the upstream hostname, causing DNS resolution failures and 502 errors.
- **Impact**: Shuffle frontend pod can now correctly resolve the backend service, making the UI functional.

### 8. Windows Symlink Handling Improvement
- **What**: Changed Wazuh repo clone strategy from standard clone to `--no-checkout` + selective checkout
- **Where**: `clone_or_use_wazuh_repo()` function
- **Why**: Windows/WSL2 environments may have symlink creation restrictions that cause git checkout failures on the wazuh-kubernetes repo
- **Impact**: More reliable cloning on Windows environments

### 9. StorageClass Pre-Delete Before kustomize Apply
- **What**: Added `kubectl delete storageclass wazuh-storage --ignore-not-found` BEFORE the `kubectl apply -k` for Wazuh
- **Where**: `deploy_wazuh()` function — before the kustomize apply command
- **Why**: The upstream Wazuh kustomize overlay creates a `wazuh-storage` StorageClass with `microk8s.io/hostpath` provisioner and `Immediate` volumeBindingMode. On redeployment, kustomize apply tries to update the existing StorageClass, but the `provisioner` and `volumeBindingMode` fields are immutable. The delete-after-apply fix (#6) wasn't enough because the kustomize apply itself fails with exit code 1 when it can't update the immutable StorageClass. Deleting before apply ensures the kustomize apply succeeds (creating a fresh StorageClass), then we delete+recreate it again with the correct k3s-compatible values.
- **Impact**: Redeployments of Wazuh no longer fail with `StorageClass "wazuh-storage" is invalid: provisioner: Invalid value / volumeBindingMode: Invalid value`
- **What**: Changed Wazuh repo clone strategy from standard clone to `--no-checkout` + selective checkout
- **Where**: `clone_or_use_wazuh_repo()` function
- **Why**: Windows/WSL2 environments may have symlink creation restrictions that cause git checkout failures on the wazuh-kubernetes repo
- **Impact**: More reliable cloning on Windows environments

---

## Issues Identified But NOT Yet Fixed

### OpenSearch Helm Release "Failed" State
- **Symptom**: Pod is Running 1/1 and Healthy, but `helm list` shows the release in "failed" status
- **Root Cause**: The original Helm install timed out before OpenSearch completed startup. Helm marks the release as failed even though the pod eventually became Ready.
- **Fix**: Run `helm upgrade --install mcaas-opensearch opensearch/opensearch --namespace security-ops --values deploy/values/opensearch.yaml` to re-sync Helm state. This is what `scripts/deploy.py` already does on re-run.
- **Status**: Known issue. Will self-heal on next deployment run.

### Wazuh Values Not Applied (kustomize Limitation)
- **Symptom**: `deploy/values/wazuh.yaml` is not used by the deployment
- **Root Cause**: Wazuh is deployed via kustomize from the upstream `wazuh-kubernetes` repository, not via Helm. The values file serves as documentation of desired configuration only.
- **Impact**: Wazuh currently deploys with the upstream `local-env` overlay including its own embedded OpenSearch indexer (redundant with the MCaaS shared OpenSearch).
- **Desired State**: Disable Wazuh's indexer, point Wazuh to the shared OpenSearch instance at `mcaas-opensearch.security-ops.svc.cluster.local:9200`
- **Fix**: Create a kustomize overlay at `deploy/wazuh-overlay/` with strategic merge patches to disable the indexer and configure the external OpenSearch connection.
- **Status**: Documented. Not yet implemented.

---

## Deployment Status Summary

| Component | Namespace | Status | Notes |
|-----------|-----------|--------|-------|
| Namespaces | — | ✅ Created | security-ops, managed-it, grc, wazuh |
| PostgreSQL | managed-it | ✅ Running | Bitnami Helm chart, healthy |
| OpenSearch | security-ops | ✅ Running | Pod Running 1/1, Helm release "failed" (self-heals on re-run) |
| Wazuh | wazuh | ✅ Running | Kustomize deploy, all NLBs active |
| Shuffle | security-ops | ✅ Running | OCI chart v2.2.1, ALB ingress with ACM cert |
| Zammad | managed-it | ✅ Running | Official Helm chart, ALB ingress with ACM cert |
| CISO Assistant | grc | ✅ Running | OCI chart v0.11.4, ALB ingress with ACM cert |
| Secrets | — | ✅ Created | Both K8s secrets created |
| Cloudflare DNS | — | ✅ Created | CNAME records for all 4 services (DNS only) |
| ACM Certificates | — | ✅ Imported | 3 ACM certs for Shuffle, Zammad, CISO |
| Wazuh NLBs | wazuh | ✅ Configured | Dashboard+Manager: internet-facing, Indexer+Workers: internal |

---

## AWS/EKS Deployment Session Changes (2025-07-25)

### 10. Wazuh NLB Scheme Configuration
- **What**: Configured Wazuh services with appropriate NLB scheme annotations
- **Where**: Live cluster — `kubectl annotate` on `dashboard`, `wazuh`, `indexer`, `wazuh-workers` services in `wazuh` namespace
- **Why**: By default, all Wazuh NLBs are created as `internal` scheme, making them inaccessible from the internet. Only the dashboard and manager need to be internet-facing. The indexer and workers should remain internal for security.
- **How**: 
  - `dashboard` and `wazuh` (manager): `service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing`
  - `indexer` and `wazuh-workers`: `service.beta.kubernetes.io/aws-load-balancer-scheme: internal`
- **Pitfall**: Do NOT use the legacy `service.beta.kubernetes.io/aws-load-balancer-internal: 0.0.0.0/0` annotation. The AWS LB Controller v2.x tries to parse it as a boolean and fails with "failed to parse bool annotation". Use only the `scheme` annotation.
- **Pitfall**: The Wazuh kustomize creates TWO indexer services: `indexer` (LoadBalancer) and `wazuh-indexer` (ClusterIP headless). Make sure to annotate `indexer`, not `wazuh-indexer`.
- **Impact**: Changing the scheme annotation causes the AWS LB Controller to delete the old NLB and create a new one with a different DNS name (~60-120 seconds of downtime).
- **Script**: `scripts/wazuh-nlb-annotations.sh` and `scripts/wazuh-nlb-annotations.ps1`

### 11. Cloudflare DNS Records for MCaaS Services
- **What**: Created CNAME records in Cloudflare for all four services
- **Where**: Cloudflare DNS zone `socom.co.il`
- **Records**:
  - `shuffle.testcustomer.socom.co.il` → ALB DNS (DNS only, not proxied)
  - `zammad.testcustomer.socom.co.il` → ALB DNS (DNS only, not proxied)
  - `ciso.testcustomer.socom.co.il` → ALB DNS (DNS only, not proxied)
  - `wazuh.testcustomer.socom.co.il` → ALB DNS (DNS only, not proxied)
- **Pitfall**: Cloudflare proxy mode (orange cloud) does NOT work with AWS NLBs. NLBs are Layer 4 (TCP) and Cloudflare proxy requires Layer 7 (HTTP/HTTPS). Always set Wazuh CNAME records to "DNS only" (grey cloud).
- **Impact**: Services accessible via friendly domain names instead of raw AWS load balancer hostnames.

### 12. ACM Certificate Integration for ALB Ingresses
- **What**: Imported ACM certificates and added ARN annotations to Shuffle, Zammad, and CISO Assistant ALB ingresses
- **Why**: AWS ALB Ingress Controller does NOT read Kubernetes TLS secrets. It requires ACM certificate ARNs via the `alb.ingress.kubernetes.io/certificate-arn` annotation.
- **ACM Certificate ARNs** (account `891612549926`, region `eu-west-1`):
  - Wazuh: `arn:aws:acm:eu-west-1:891612549926:certificate/ea018fb1-e052-432d-95ef-9fd2dbe29e15`
  - Shuffle: `arn:aws:acm:eu-west-1:891612549926:certificate/3ff23afd-a25e-4e8b-b9c1-3df3ebec6552`
  - Zammad: `arn:aws:acm:eu-west-1:891612549926:certificate/b3266045-5939-4a83-8ccb-6afed011abec`
  - CISO Assistant: `arn:aws:acm:eu-west-1:891612549926:certificate/1bc0d964-9224-4552-9357-3a0ea2134b0a`
- **Impact**: All ALB ingresses now serve valid ACM-issued TLS certificates on port 443.

### 13. Cloudflare API Token Management
- **What**: Created `cloudflare-api-token-secret` in `cert-manager` namespace for DNS01 challenges
- **Why**: cert-manager uses this token for Let's Encrypt DNS01 challenges via Cloudflare
- **Pitfall**: Cloudflare API tokens can expire or be revoked. If cert-manager certificate renewals fail with DNS01 challenge errors, check the token validity.
- **Update token**: `kubectl create secret generic cloudflare-api-token-secret --from-literal=api-token=<NEW_TOKEN> --namespace=cert-manager --dry-run=client -o yaml | kubectl apply -f -`

### 14. Wazuh Dashboard Access via ALB Ingress
- **What**: `wazuh.testcustomer.socom.co.il` resolves to Wazuh dashboard ALB
- **Access**: `https://wazuh.testcustomer.socom.co.il` → Wazuh dashboard (HTTP 200)
- **Note**: Wazuh now uses an ALB ingress with ACM certificate for proper TLS termination, replacing the previous NLB setup.

---

## Session 3 Changes (2025-07-28): SMTP Relay, Pipeline Integration & Documentation

### 15. SMTP Relay Deployment with Full Postfix Configuration
- **What**: Deployed Postfix SMTP relay (`mwader/postfix-relay`) to EKS as a Kubernetes Deployment with all configuration persisted via environment variables
- **Where**: `aws/smtp-relay-deployment.yaml` — complete manifest with Secret, ConfigMap, Deployment, and Service
- **Key Config (all via `POSTFIX_` env vars)**:
  - `POSTFIX_syslog_facility=mail` — Critical fix: image defaults to `local0` which breaks logging
  - `POSTFIX_maillog_file=/var/log/postfix.log` — Direct file logging for Postfix
  - `POSTFIX_smtp_generic_maps=hash:/etc/postfix/generic` — Rewrites both envelope AND headers at SMTP delivery time (From: `@socom.co.il` → `hello@danieldbeard.com`)
  - `POSTFIX_sender_canonical_maps=hash:/etc/postfix/sender_canonical` — Rewrites envelope sender on local submission
  - `POSTFIX_debug_peer_level=3`, `POSTFIX_debug_peer_list=smtp.zoho.com`, `POSTFIX_smtp_tls_loglevel=1` — Debug settings for Zoho SMTP
  - `POSTFIX_relayhost=[smtp.zoho.com]:587`, `POSTFIX_smtp_tls_security_level=encrypt` — Zoho relay with mandatory STARTTLS
- **Key Config (via `POSTMAP_` env vars)**:
  - `POSTMAP_generic` — Maps `@socom.co.il` → `hello@danieldbeard.com`
  - `POSTMAP_sender_canonical` — Maps `@socom.co.il` → `hello@danieldbeard.com`
  - `POSTMAP_sasl_passwd` — Stores `[smtp.zoho.com]:587 hello@danieldbeard.com:GLJkJ6cWcHLW`
- **Impact**: Fresh pods start with complete Postfix configuration — no manual intervention required

### 16. POSTMAP_ Environment Variables Confirmed Auto-Working
- **What**: Verified that `POSTMAP_<filename>` env vars in `mwader/postfix-relay` image auto-create lookup table files AND run `postmap` on fresh pod starts
- **Verification**: Deleted pod, waited for new pod, confirmed all three files (`generic`, `sender_canonical`, `sasl_passwd`) were auto-created with correct content and `.db` files
- **Impact**: No need for manual `postmap` commands or configMap mounting for lookup tables

### 17. rsyslog ConfigMap for Postfix Mail Logging
- **What**: Created `rsyslog-postfix` ConfigMap in `security-ops` namespace with custom rsyslog config
- **Where**: Defined in `aws/smtp-relay-deployment.yaml` and mounted at `/etc/rsyslog.d/postfix.conf`
- **Content**:
  - `$AddUnixListenSocket /var/spool/postfix/dev/log` — Ensures rsyslog listens in Postfix chroot
  - `mail.* /var/log/postfix.log` — Routes all mail facility messages to dedicated log file
- **Why**: Without this, Postfix logs go to default syslog facility (`local0`) and are lost in the general syslog noise
- **Impact**: All Postfix mail logs are captured in `/var/log/postfix.log` on every pod start

### 18. Disconnected HTTP Action Removed from Shuffle Workflow
- **What**: Removed a disconnected HTTP action from the Shuffle workflow that was left over from earlier configuration attempts
- **Where**: Shuffle workflow `8d264034-0040-48c6-86f2-aeb5294df90a`, action ID removed via Shuffle API
- **Why**: The Parse action (v2) already handles Zammad ticket creation internally via the Zammad API, making the separate HTTP action redundant and confusing
- **Impact**: Cleaner workflow graph — only Webhook trigger → Parse action (with all logic inside)

### 19. Email Delivery Confirmed End-to-End
- **What**: Verified complete email delivery pipeline: Wazuh alert → Shuffle webhook → Parse action (enrich + create ticket) → Postfix SMTP relay → Zoho Mail → inbox
- **Verification**: Postfix logs show `status=sent (250 Message received)` from `smtp.zoho.com`. User confirmed email receipt in Zoho Mail inbox.
- **Key findings**:
  - `sender_canonical_maps` only rewrites envelope sender (not From: header)
  - `smtp_generic_maps` rewrites both envelope AND headers at SMTP delivery time — this is what makes Zoho accept the email
  - Zoho requires envelope sender AND From: header to match the authenticated SASL user (`hello@danieldbeard.com`)
- **Impact**: Full alert notification pipeline operational — security alerts now generate Zammad tickets AND email notifications

---

## Conclusions

1. **Timeouts are the #1 deployment issue**: On k3s/Rancher Desktop, image pulls and init containers take significantly longer than default 5-minute timeouts. All timeouts have been increased, but further increases may be needed on slower connections.

2. **Helm release state can diverge from pod state**: A Helm timeout doesn't mean the deployment failed — it means Helm gave up waiting. The pod may still be progressing toward Ready. Running `scripts/deploy.py` again (which uses `helm upgrade --install`) is the correct recovery action.

3. **kustomize and Helm don't mix for Wazuh**: The current architecture uses Helm for 5 components and kustomize for Wazuh. This creates a configuration gap where `wazuh.yaml` values are not applied. A kustomize overlay strategy is needed.

4. **fullnameOverride is critical for Shuffle**: Services with embedded nginx configurations (like Shuffle's frontend) hardcode service names. The `fullnameOverride` pattern ensures predictable service names that match the application's expectations.

5. **StorageClass immutability requires delete+recreate**: k3s and Kubernetes enforce immutable provisioner fields on StorageClass. Redeployments must delete and recreate rather than patch.

6. **Cross-namespace service references use FQDN**: All inter-service communication uses the full Kubernetes DNS name (`<service>.<namespace>.svc.cluster.local`). This is correct for cross-namespace access but must be updated if namespaces change.

7. **Windows compatibility requires special handling**: Git clone with `--no-checkout`, OpenSSL path discovery, and symlink workarounds are all necessary for k3s/Rancher Desktop on Windows/WSL2.

8. **AWS LB Controller requires `scheme` annotation, not `internal`**: The `service.beta.kubernetes.io/aws-load-balancer-internal: 0.0.0.0/0` annotation is a legacy annotation that causes the AWS LB Controller v2.x to fail with "failed to parse bool annotation". Always use `service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing|internal` instead.

9. **Cloudflare proxy mode is incompatible with AWS NLBs**: NLBs are Layer 4 (TCP) load balancers. Cloudflare's proxy mode requires Layer 7 (HTTP/HTTPS) origin servers. Always set CNAME records pointing to NLBs as "DNS only" (grey cloud) in Cloudflare.

10. **ACM certificates are required for ALB ingresses**: The AWS ALB Ingress Controller does not read Kubernetes TLS secrets. It requires ACM certificate ARNs via the `alb.ingress.kubernetes.io/certificate-arn` annotation on each ingress resource.

11. **Wazuh has two "indexer" services**: The kustomize deployment creates `indexer` (LoadBalancer type) and `wazuh-indexer` (ClusterIP headless). Always annotate `indexer` for NLB configuration, not `wazuh-indexer`.

12. **NLB scheme changes cause recreation**: When you change the `aws-load-balancer-scheme` annotation on a service, the AWS LB Controller deletes the old NLB and creates a new one with a different DNS name. Plan for ~60-120 seconds of downtime and DNS propagation delays.

---

*See also: [Installation Guide](./installation-guide.md) | [Services Matrix](./services-matrix.md) | [Configuration Matrix](./configuration-matrix.md) | [Retry & Timeout Recommendations](./retry-timeout-recommendations.md)*