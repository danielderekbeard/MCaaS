# MCaaS Documentation

> **Managed Compliance as a Service - Complete Documentation Suite**

---

## Documentation Overview

This directory contains comprehensive documentation for the MCaaS (Managed Compliance as a Service) platform, covering architecture, operations, integration, and incident response.

---

## Quick Navigation

### 📊 Architecture & Diagrams

| Document | Description |
|----------|-------------|
| [`diagrams/mcaas-architecture.html`](diagrams/mcaas-architecture.html) | Full platform architecture diagram |
| [`diagrams/alert-flow-workflow.html`](diagrams/alert-flow-workflow.html) | Security alert data flow |
| [`diagrams/integration-overview.html`](diagrams/integration-overview.html) | Integration specifications |

### 📚 User Guides

| Document | Target Audience | Description |
|----------|----------------|-------------|
| [`guides/soc-analyst-quickstart.md`](guides/soc-analyst-quickstart.md) | SOC Analysts | Day-to-day operations guide |
| [`guides/wazuh-investigation-guide.md`](guides/wazuh-investigation-guide.md) | Security Engineers | Advanced threat hunting |

### 💼 Executive Materials

| Document | Target Audience | Description |
|----------|----------------|-------------|
| [`presentations/executive-summary.md`](presentations/executive-summary.md) | C-Suite, Managers | Business value and overview |

### 🔌 API & Integration

| Document | Description |
|----------|-------------|
| [`api/api-integration-guide.md`](api/api-integration-guide.md) | Complete API reference with examples |

### 🔧 Runbooks

| Document | Description |
|----------|-------------|
| [`runbooks/incident-response-runbook.md`](runbooks/incident-response-runbook.md) | Security incident procedures |
| [`runbooks/deployment-runbook.md`](runbooks/deployment-runbook.md) | Deployment and maintenance procedures |

---

## Platform Overview

MCaaS is an integrated, Kubernetes-based security operations platform combining:

| Component | Purpose | Code Name |
|-----------|---------|-----------|
| **Wazuh** | SIEM & XDR (Threat Detection) | Deimos |
| **Shuffle** | SOAR (Security Automation) | Kydoimos |
| **Zammad** | IT Helpdesk (Incident Tracking) | Alala |
| **CISO Assistant** | GRC (Governance, Risk, Compliance) | Strategos |
| **OpenSearch** | Security Data Indexer | - |
| **PostgreSQL** | Shared Database | - |

### Namespace Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
├─────────────────────────────────────────────────────────────┤
│  security-ops    │    managed-it    │    grc              │
│  ────────────    │    ──────────    │    ────              │
│  • Wazuh         │    • PostgreSQL  │    • CISO Asst     │
│  • Shuffle       │    • Zammad       │                     │
│  • OpenSearch    │    • Redis        │                     │
│  • SMTP Relay    │                   │                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Alert Flow

```
Detection → Alert → Enrichment → Ticket → Investigation → Response

1. Wazuh Agent detects threat
2. Wazuh Manager generates alert (Level 5+)
3. Shuffle webhook receives alert
4. Shuffle enriches data (VirusTotal, GeoIP)
5. Shuffle creates Zammad ticket
6. SOC Analyst investigates ticket
7. Analyst triggers response via Shuffle
8. CISO Assistant tracks for compliance
```

---

## Getting Started

### For SOC Analysts

1. Read the [SOC Analyst Quickstart](guides/soc-analyst-quickstart.md)
2. Review daily workflow procedures
3. Practice with test alerts

### For Administrators

1. Follow the [Deployment Runbook](runbooks/deployment-runbook.md)
2. Verify post-deployment health checks
3. Configure integrations (Wazuh → Shuffle → Zammad)

### For Developers

1. Review the [API Integration Guide](api/api-integration-guide.md)
2. Explore integration examples
3. Build custom workflows in Shuffle

---

## Key URLs

| Service | Internal URL | External URL |
|---------|--------------|--------------|
| Wazuh Dashboard | `wazuh-dashboard.wazuh:443` | `https://deimos.mcaas.example.com` |
| Shuffle | `shuffle-backend.security-ops:3008` | `https://kydoimos.mcaas.example.com` |
| Zammad | `zammad-web.managed-it:80` | `https://alala.mcaas.example.com` |
| CISO Assistant | `ciso-assistant-frontend.grc:443` | `https://strategos.mcaas.example.com` |
| OpenSearch | `mcaas-opensearch.security-ops:9200` | - |
| PostgreSQL | `mcaas-postgresql.managed-it:5432` | - |

---

## Integration Points

### Wazuh → Shuffle

**Protocol:** HTTP Webhook  
**Trigger:** Wazuh alerts (Level 3+)  
**Data:** JSON alert payload  
**Configuration:** `ossec.conf` integration block

### Shuffle → Zammad

**Protocol:** REST API  
**Action:** Create ticket  
**Auth:** API Token  
**Data:** Enriched alert with threat intel

### Shuffle → Wazuh API

**Protocol:** HTTPS REST  
**Action:** Query agent info, isolate host  
**Auth:** Basic Auth  
**Data:** Command execution

### Zammad → PostgreSQL

**Protocol:** PostgreSQL wire  
**Purpose:** Ticket persistence  
**Namespace:** managed-it

### CISO Assistant → PostgreSQL

**Protocol:** PostgreSQL wire  
**Purpose:** GRC data  
**Cross-namespace:** Yes (managed-it → grc)

---

## Common Commands

```bash
# Port-forward to services
kubectl port-forward -n wazuh svc/wazuh-dashboard 5601:443
kubectl port-forward -n security-ops svc/shuffle-backend 3008:3008
kubectl port-forward -n managed-it svc/zammad-web 8080:80

# Check service health
python scripts/check-prerequisites.py

# Deploy full stack
python deploy.py

# Check logs
kubectl logs -n wazuh -l app=wazuh-manager --tail=100
kubectl logs -n security-ops -l app=shuffle-backend
kubectl logs -n managed-it -l app=zammad-web
```

---

## Troubleshooting Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Wazuh Dashboard 500 | `kubectl rollout restart deployment/wazuh-dashboard -n wazuh` |
| PostgreSQL connection | Check secrets: `kubectl get secrets -n managed-it` |
| Shuffle workflow failing | Verify OpenSearch is healthy |
| Agent not connected | Re-register agent |
| High memory | Scale up resources or enable HPA |
| Certificate expired | Run `./scripts/regenerate-wazuh-certs.sh` |

---

## Support

| Resource | Contact |
|----------|---------|
| Technical Support | devops@mcaas.example.com |
| Security Issues | security@mcaas.example.com |
| Documentation | Open an issue in this repository |

---

## Contributing

To contribute to documentation:

1. Fork the repository
2. Create a feature branch
3. Update relevant documentation
4. Submit a pull request

---

*Documentation Version: 1.0*  
*Last Updated: January 2026*
