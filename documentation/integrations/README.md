# MCaaS Integration Documentation

> **Complete guide to MCaaS platform integrations**

---

## Available Integrations

| Integration | Components | Status | Documentation |
|-------------|------------|--------|---------------|
| **Wazuh → Shuffle → Zammad** | SIEM → SOAR → Ticketing | ✅ Active | [wazuh-shuffle-zammad-integration.md](wazuh-shuffle-zammad-integration.md) |
| **Shuffle → Wazuh API** | SOAR → SIEM | ✅ Active | [wazuh-shuffle-zammad-integration.md](wazuh-shuffle-zammad-integration.md) |
| **Shuffle → Threat Intel** | SOAR → External APIs | ✅ Active | See Shuffle App Store |
| **SMTP Relay → Zoho Mail** | Mail → External | ✅ Active | Configured in security-ops |
| **CISO Assistant → PostgreSQL** | GRC → Database | ✅ Active | Cross-namespace connection |
| **All Apps → OpenSearch** | Various → Indexer | ✅ Active | Shared search backend |

---

## Integration Matrix

```
                    ┌─────────────────────────────────────────┐
                    │              MCaaS Platform              │
                    └─────────────────────────────────────────┘

   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
   │  Wazuh   │───▶│  Shuffle │───▶│  Zammad  │    │   CISO   │
   │   SIEM   │    │   SOAR   │    │ Helpdesk │    │   GRC    │
   └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
        │               │               │               │
        │ Webhook       │ API           │ DB            │ DB
        ▼               ▼               ▼               ▼
   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
   │  Agents  │    │ VirusTotal│    │ PostgreSQL│    │ Framework │
   │ Endpoints│    │ AbuseIPDB│    │ Redis    │    │ Mapping   │
   │ Network  │    │ GeoIP    │    │          │    │           │
   └──────────┘    └──────────┘    └──────────┘    └──────────┘

   External        External        Data Layer        Compliance
```

---

## Integration Categories

### 1. Internal Integrations

These connect MCaaS components to each other:

- **Wazuh ↔ Shuffle:** Webhook alert forwarding
- **Shuffle ↔ Zammad:** REST API ticket creation
- **Shuffle ↔ Wazuh API:** Active response commands
- **Zammad → PostgreSQL:** Data persistence
- **CISO Assistant → PostgreSQL:** Cross-namespace DB
- **All Apps → OpenSearch:** Shared indexer

### 2. External Integrations

These connect MCaaS to external services:

- **Shuffle → VirusTotal:** File/hash reputation
- **Shuffle → AbuseIPDB:** IP reputation
- **Shuffle → GeoIP:** Geolocation data
- **SMTP Relay → Zoho Mail:** Email delivery
- **Wazuh → Agent Endpoints:** Monitoring

### 3. Identity Integrations

- **SSO (Planned):** SAML/OIDC authentication
- **LDAP (Planned):** Directory integration

---

## Configuration Overview

### Wazuh → Shuffle Configuration

```bash
# File: /var/ossec/etc/ossec.conf
<integration>
  <name>shuffle</name>
  <hook_url>http://shuffle-backend.security-ops:3008/api/v1/webhooks/ID</hook_url>
  <level>5</level>
  <format>json</format>
</integration>
```

### Shuffle → Zammad Configuration

```yaml
# In Shuffle workflow
app: zammad
action: create_ticket
parameters:
  zammad_url: "http://zammad-web.managed-it:80"
  api_key: "{{credentials.zammad-api-key}}"
  title: "[Alert] {{webhook.rule.description}}"
  group: "Security"
```

### SMTP Relay Configuration

```yaml
# Kubernetes Deployment
env:
  - name: RELAY_HOST
    value: "smtp.zoho.com"
  - name: RELAY_PORT
    value: "587"
  - name: SMTP_USERNAME
    value: "hello@danieldbeard.com"
  - name: SMTP_PASSWORD
    valueFrom:
      secretKeyRef:
        name: zoho-smtp-secret
        key: SASL_PASSWD
```

---

## Authentication Reference

| Integration | Method | Credential Location |
|-------------|--------|---------------------|
| Wazuh → Shuffle | None (internal) | N/A |
| Shuffle → Zammad | API Token | K8s Secret: shuffle-credentials |
| Shuffle → VirusTotal | API Key | K8s Secret: shuffle-credentials |
| Shuffle → Wazuh API | Basic Auth | K8s Secret: wazuh-api-credentials |
| SMTP Relay → Zoho | SASL Auth | K8s Secret: zoho-smtp-secret |
| All → PostgreSQL | Password | K8s Secret: mcaas-postgresql-secret |

---

## Monitoring Integrations

### Health Check Endpoints

| Service | Health Endpoint | Expected Response |
|---------|-----------------|-------------------|
| Shuffle | `GET /api/v1/health` | `{"status": "ok"}` |
| Zammad | `GET /api/v1/health_check` | HTTP 200 |
| Wazuh | `GET /` | Wazuh info JSON |

### Integration Testing Commands

```bash
# Test Wazuh → Shuffle
curl -X POST \
  "http://shuffle-backend.security-ops:3008/api/v1/webhooks/TEST_ID" \
  -d '{"test":"data"}'

# Test Shuffle → Zammad
curl -H "Authorization: Token token=$TOKEN" \
  "http://zammad-web.managed-it:80/api/v1/tickets"

# Test SMTP Relay
telnet smtp-relay.security-ops 25

# Test Database connections
kubectl exec -n managed-it mcaas-postgresql-0 -- \
  pg_isready -U postgres
```

---

## Troubleshooting Integrations

### Common Issues

1. **Webhook not receiving data**
   - Check Wazuh `ossec.conf` integration block
   - Verify Shuffle webhook ID is correct
   - Test network connectivity between namespaces

2. **API authentication failing**
   - Verify API tokens are current
   - Check token permissions (ticket.agent for Zammad)
   - Ensure secrets are mounted correctly

3. **Database connection refused**
   - Verify PostgreSQL is running
   - Check service name resolution
   - Confirm credentials in secrets

### Debugging Commands

```bash
# Check integration logs
kubectl logs -n wazuh wazuh-manager-master-0 | grep -i shuffle
kubectl logs -n security-ops -l app=shuffle-backend | grep -i zammad

# Verify service endpoints
kubectl get endpoints -n security-ops shuffle-backend
kubectl get endpoints -n managed-it zammad-web

# Test connectivity between pods
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  curl -s http://shuffle-backend.security-ops:3008/api/v1/health
```

---

## Integration Roadmap

### Q2 2026

- [ ] Jira integration for dev team tickets
- [ ] Slack notifications for critical alerts
- [ ] Microsoft Teams integration

### Q3 2026

- [ ] ServiceNow CMDB sync
- [ ] Active Directory SSO
- [ ] GitHub Security Advisory integration

### Q4 2026

- [ ] AWS Security Hub integration
- [ ] Azure Sentinel connector
- [ ] Splunk data export

---

*Integration Documentation Version: 1.0*  
*Last Updated: January 2026*
