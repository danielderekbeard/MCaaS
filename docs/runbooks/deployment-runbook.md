# MCaaS Deployment Runbook

> **Step-by-step procedures for deploying, maintaining, and troubleshooting MCaaS**

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Initial Deployment](#initial-deployment)
3. [Post-Deployment Verification](#post-deployment-verification)
4. [Adding a New Client](#adding-a-new-client)
5. [Backup and Recovery](#backup-and-recovery)
6. [Scaling and Maintenance](#scaling-and-maintenance)
7. [Troubleshooting Guide](#troubleshooting-guide)

---

## Pre-Deployment Checklist

### Infrastructure Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Kubernetes Nodes | 3 | 5+ |
| CPU (cores) | 8 | 16+ |
| Memory (GB) | 16 | 32+ |
| Storage (GB) | 100 | 500+ |
| Network | 1 Gbps | 10 Gbps |

### Required Tools

- [ ] `kubectl` configured and working
- [ ] `helm` v3.x installed
- [ ] Python 3.7+ with `requests` library
- [ ] Git for cloning manifests
- [ ] Access to container registries

### Kubernetes Requirements

```bash
# Verify cluster is ready
kubectl cluster-info
kubectl get nodes
kubectl get pods -A

# Check storage class
kubectl get storageclass

# Verify ingress controller
kubectl get pods -n ingress-nginx  # or traefik, nginx-ingress
```

### Environment Variables

```bash
# Required environment variables
cat > .env << EOF
MCAAS_POSTGRES_PASSWORD=$(openssl rand -base64 32)
MCAAS_OPENSEARCH_PASSWORD=$(openssl rand -base64 32)
MCAAS_REDIS_PASSWORD=$(openssl rand -base64 32)
MCAAS_DJANGO_SECRET_KEY=$(openssl rand -base64 50)
EOF
```

---

## Initial Deployment

### Step 1: Clone Repository

```bash
cd /projects/skyddex/MCaaS
git clone https://github.com/your-org/mcaas.git .
cd mcaas
```

### Step 2: Run Prerequisites Check

```bash
# Verify all tools are available
python scripts/check-prerequisites.py

# Expected output:
# ✅ kubectl version: v1.28.x
# ✅ helm version: v3.12.x
# ✅ git version: 2.40.x
# ✅ python version: 3.11.x
```

### Step 3: Configure Environment

```bash
# Copy example environment file
cp scripts/.env.example .env

# Edit .env with your passwords
nano .env

# Required values:
# - MCAAS_POSTGRES_PASSWORD
# - MCAAS_OPENSEARCH_PASSWORD
# - MCAAS_REDIS_PASSWORD (optional, defaults to 'zammad')
# - MCAAS_DJANGO_SECRET_KEY (optional, auto-generated)
```

### Step 4: Deploy Core Infrastructure

```bash
# Deploy namespaces and secrets
python deploy.py --skip-apps

# Or manually:
kubectl apply -f deploy/namespaces.yaml
kubectl apply -k deploy/
```

### Step 5: Verify Core Services

```bash
# Wait for PostgreSQL
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=postgresql \
  -n managed-it --timeout=300s

# Wait for OpenSearch
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=opensearch \
  -n security-ops --timeout=300s

# Verify secrets
kubectl get secrets -n managed-it
kubectl get secrets -n security-ops
```

### Step 6: Deploy Applications

```bash
# Deploy all applications
python deploy.py

# Or deploy individually:
python deploy.py --component wazuh
python deploy.py --component shuffle
python deploy.py --component zammad
python deploy.py --component ciso-assistant
```

### Step 7: Configure Integrations

```bash
# Configure Wazuh webhook for Shuffle
./scripts/configure-wazuh-shuffle.sh

# Configure Shuffle credentials for Zammad
./scripts/configure-shuffle-zammad.sh

# Verify integrations
./scripts/test-integrations.sh
```

---

## Post-Deployment Verification

### Service Health Check

```bash
# Check all pods are running
kubectl get pods -n managed-it
kubectl get pods -n security-ops
kubectl get pods -n grc
kubectl get pods -n wazuh

# Check services
kubectl get svc -n managed-it
kubectl get svc -n security-ops
kubectl get svc -n grc
kubectl get svc -n wazuh
```

### Access Verification

```bash
# Port-forward to test services

# Wazuh Dashboard
kubectl port-forward -n wazuh svc/wazuh-dashboard 5601:443
# Access: https://localhost:5601

# Shuffle
kubectl port-forward -n security-ops svc/shuffle-backend 3008:3008
# Access: http://localhost:3008

# Zammad
kubectl port-forward -n managed-it svc/zammad-web 8080:80
# Access: http://localhost:8080

# CISO Assistant
kubectl port-forward -n grc svc/ciso-assistant-frontend 8443:443
# Access: https://localhost:8443
```

### Integration Testing

```bash
# Test Wazuh → Shuffle webhook
curl -X POST \
  "http://shuffle-backend.security-ops:3008/api/v1/webhooks/WEBHOOK_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "rule": {"description": "Test alert", "level": 10},
    "agent": {"id": "001", "name": "test-agent"}
  }'

# Test Shuffle → Zammad ticket creation
# (Verify in Zammad UI)

# Test Zammad email notifications
# (Send test email via SMTP relay)
```

---

## Adding a New Client

### Step 1: Prepare Client Namespace

```bash
# Create client-specific namespace
kubectl create namespace client-xyz

# Add to kustomization
```

### Step 2: Deploy Client-Specific Wazuh Agents

```bash
# Get Wazuh registration password
kubectl -n wazuh get secret wazuh-api-credentials \
  -o jsonpath='{.data.password}' | base64 -d

# Install agent on client system
# Download agent from Wazuh
# Configure WAZUH_MANAGER to point to cluster
```

### Step 3: Configure Client Groups

```bash
# Add agent to group
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  /var/ossec/bin/agent_groups -a -g client-xyz

# Assign agent to group
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  /var/ossec/bin/agent_groups -a -i 001 -g client-xyz
```

### Step 4: Client-Specific Rules

```bash
# Create client-specific rules
# Mount custom rules to Wazuh manager
kubectl create configmap client-xyz-rules \
  --from-file=rules/ \
  -n wazuh

# Patch Wazuh deployment to include rules
```

### Step 5: Client Isolation (Optional)

```bash
# Create network policies
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: client-xyz-isolation
  namespace: wazuh
spec:
  podSelector:
    matchLabels:
      client: xyz
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: wazuh
EOF
```

---

## Backup and Recovery

### Backup Strategy

#### Daily Backups

```bash
#!/bin/bash
# backup-daily.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/mcaas/${DATE}"
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
kubectl exec -n managed-it mcaas-postgresql-0 -- \
  pg_dumpall -U postgres > ${BACKUP_DIR}/postgresql.sql

# Backup OpenSearch
kubectl exec -n security-ops mcaas-opensearch-0 -- \
  /usr/share/opensearch/bin/opensearch-dump \
  --input=http://localhost:9200 \
  --output=${BACKUP_DIR}/opensearch.json

# Backup Wazuh configuration
kubectl cp n wazuh/wazuh-manager-master-0:/var/ossec/etc \
  ${BACKUP_DIR}/wazuh-etc/

# Backup secrets
kubectl get secrets --all-namespaces -o yaml \
  > ${BACKUP_DIR}/secrets.yaml

# Compress
zip -r ${BACKUP_DIR}.zip ${BACKUP_DIR}
rm -rf ${BACKUP_DIR}

# Upload to S3 (optional)
aws s3 cp ${BACKUP_DIR}.zip s3://mcaas-backups/
```

### Restore Procedures

#### Restore PostgreSQL

```bash
# Restore from backup
kubectl exec -i -n managed-it mcaas-postgresql-0 -- \
  psql -U postgres < backup-file.sql
```

#### Restore OpenSearch

```bash
# Restore indices
kubectl exec -n security-ops mcaas-opensearch-0 -- \
  /usr/share/opensearch/bin/opensearch-dump \
  --input=/backup/opensearch.json \
  --output=http://localhost:9200
```

#### Full Disaster Recovery

```bash
# 1. Reinstall MCaaS
python deploy.py

# 2. Restore databases
./restore-databases.sh /path/to/backup

# 3. Restore configurations
kubectl apply -f backup/secrets.yaml

# 4. Verify services
./scripts/test-services.sh
```

---

## Scaling and Maintenance

### Horizontal Scaling

```bash
# Scale PostgreSQL (read replicas)
kubectl patch statefulset mcaas-postgresql \
  -n managed-it --patch '{"spec":{"replicas":3}}'

# Scale OpenSearch
kubectl patch statefulset mcaas-opensearch \
  -n security-ops --patch '{"spec":{"replicas":3}}'

# Scale Zammad workers
kubectl patch deployment zammad-zammad-railsserver \
  -n managed-it --patch '{"spec":{"replicas":3}}'
```

### Vertical Scaling

```bash
# Update resource requests/limits
kubectl patch statefulset mcaas-postgresql \
  -n managed-it --type='json' -p='[
    {"op": "replace", "path": "/spec/template/spec/containers/0/resources", 
     "value": {"requests": {"memory": "4Gi", "cpu": "2"}}}
  ]'
```

### Certificate Renewal

```bash
# Check certificate expiration
kubectl get certificates -A

# Renew certificates
cert-manager renew cert-name

# Or regenerate Wazuh certificates
./scripts/regenerate-wazuh-certs.sh
```

### Updates and Patches

```bash
# Check for updates
helm list -A

# Update a component
helm upgrade --install mcaas-shuffle shuffle \
  --repo oci://ghcr.io/shuffle/charts/shuffle \
  --namespace security-ops

# Rolling restart
kubectl rollout restart deployment/APP -n NAMESPACE
```

---

## Troubleshooting Guide

### Issue: Wazuh Dashboard Not Accessible

**Symptoms:**
- Connection refused on port 5601
- SSL certificate errors

**Diagnostic:**
```bash
# Check pod status
kubectl get pods -n wazuh -l app=wazuh-dashboard

# Check logs
kubectl logs -n wazuh -l app=wazuh-dashboard

# Verify service
kubectl get svc -n wazuh wazuh-dashboard
```

**Resolution:**
```bash
# Restart dashboard
kubectl rollout restart deployment/wazuh-dashboard -n wazuh

# Regenerate certificates if expired
./scripts/regenerate-wazuh-certs.sh
```

### Issue: PostgreSQL Connection Failed

**Symptoms:**
- Applications can't connect to database
- Connection timeout errors

**Diagnostic:**
```bash
# Check PostgreSQL pod
kubectl get pods -n managed-it -l app.kubernetes.io/name=postgresql

# Check logs
kubectl logs -n managed-it -l app.kubernetes.io/name=postgresql

# Test connection
kubectl exec -n managed-it mcaas-postgresql-0 -- \
  pg_isready -U postgres
```

**Resolution:**
```bash
# Restart PostgreSQL
kubectl delete pod -n managed-it -l app.kubernetes.io/name=postgresql

# Verify secret exists
kubectl get secret mcaas-postgresql-secret -n managed-it
```

### Issue: Shuffle Workflow Failing

**Symptoms:**
- Webhooks return 500 errors
- Workflows not executing

**Diagnostic:**
```bash
# Check Shuffle pods
kubectl get pods -n security-ops -l app=shuffle

# Check logs
kubectl logs -n security-ops -l app=shuffle-backend

# Test API connectivity
curl http://shuffle-backend.security-ops:3008/api/v1/health
```

**Resolution:**
```bash
# Check OpenSearch connection
# Shuffle requires OpenSearch to be healthy

# Verify credentials in Shuffle
# Access Shuffle UI and check Admin -> Credentials

# Restart Shuffle
kubectl rollout restart deployment/shuffle-backend -n security-ops
```

### Issue: Zammad Email Not Sending

**Symptoms:**
- Tickets created but no email notifications
- Email stuck in queue

**Diagnostic:**
```bash
# Check SMTP relay
kubectl logs -n security-ops -l app=smtp-relay

# Test SMTP connection
kubectl exec -n security-ops smtp-relay-xxx -- \
  nc -zv smtp.zoho.com 587

# Check Zammad email settings
kubectl logs -n managed-it -l app=zammad-railsserver
```

**Resolution:**
```bash
# Verify SMTP secret
kubectl get secret zoho-smtp-secret -n security-ops

# Restart SMTP relay
kubectl rollout restart deployment/smtp-relay -n security-ops

# Check Zammad settings
# Access Zammad UI -> Admin -> Channels -> Email
```

### Issue: Agent Not Reporting

**Symptoms:**
- Agent shows "Never connected"
- No logs from specific agent

**Diagnostic:**
```bash
# Check agent status
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  /var/ossec/bin/agent_control -l

# Check agent logs (on agent host)
cat /var/ossec/logs/ossec.log

# Verify network connectivity
# From agent: telnet wazuh-manager.wazuh 1514
```

**Resolution:**
```bash
# Re-register agent
# On agent:
systemctl stop wazuh-agent
rm -rf /var/ossec/etc/client.keys
/var/ossec/bin/agent-auth -m WAZUH_MANAGER_IP
systemctl start wazuh-agent
```

### Issue: High Memory Usage

**Symptoms:**
- Pods OOMKilled
- Cluster under memory pressure

**Diagnostic:**
```bash
# Check resource usage
kubectl top pods -A

# Check node resources
kubectl top nodes

# Check OOM events
kubectl get events -A --field-selector reason=OOMKilled
```

**Resolution:**
```bash
# Increase memory limits
kubectl patch deployment APP -n NAMESPACE --patch '
  {"spec":{"template":{"spec":{"containers":[{"name":"APP",
   "resources":{"limits":{"memory":"4Gi"}}}]}}}}
'

# Add nodes to cluster
# Or enable HPA
kubectl autoscale deployment APP --min=2 --max=5 \
  --cpu-percent=80 -n NAMESPACE
```

### Issue: Certificate Expired

**Symptoms:**
- SSL errors in browser
- API connections failing

**Diagnostic:**
```bash
# Check certificate expiration
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  openssl x509 -in /var/ossec/etc/sslmanager.cert -noout -dates

# Check cert-manager status
kubectl get certificates -A
```

**Resolution:**
```bash
# Regenerate certificates
./scripts/regenerate-wazuh-certs.sh

# Restart Wazuh components
kubectl rollout restart statefulset/wazuh-manager-master -n wazuh
kubectl rollout restart statefulset/wazuh-indexer -n wazuh
kubectl rollout restart deployment/wazuh-dashboard -n wazuh
```

---

## Emergency Procedures

### Full Platform Shutdown

```bash
# Emergency shutdown (preserve data)
kubectl scale --replicas=0 deployment --all -n security-ops
kubectl scale --replicas=0 deployment --all -n managed-it
kubectl scale --replicas=0 deployment --all -n grc
kubectl scale --replicas=0 statefulset --all -n wazuh
```

### Emergency Access

```bash
# Get direct shell to database
kubectl exec -it -n managed-it mcaas-postgresql-0 -- psql -U postgres

# Get direct shell to Wazuh manager
kubectl exec -it -n wazuh wazuh-manager-master-0 -- /bin/bash

# Port-forward for emergency access
kubectl port-forward -n wazuh svc/wazuh-manager 55000:55000
```

---

*Last updated: January 2026 | For MCaaS v1.0*
