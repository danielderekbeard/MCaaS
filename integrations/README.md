# MCaaS Integrations

This directory contains integration components for the Managed Compliance as a Service platform.

## Directory Structure

```
integrations/
├── README.md                 # This file
├── common/                   # Shared utilities
│   └── alert_filter.py      # Intelligent alert filtering
├── wazuh-zammad/            # Wazuh → Zammad integration
│   ├── ticket_creator.py    # Ticket creation script
│   ├── webhook_server.py    # HTTP webhook receiver
│   ├── Dockerfile           # Container image
│   └── k8s-deployment.yaml  # Kubernetes manifests
└── shuffle/                 # Shuffle workflow enhancements
    └── (in development)
```

## Integrations

### 1. Wazuh → Zammad Ticket Automation

Automatically creates tickets in Zammad from Wazuh security alerts.

**Features:**
- Deduplication (prevents duplicate tickets for same alert)
- Severity-based priority mapping
- Rich ticket body with alert details
- Kubernetes-native deployment

**Quick Start:**

1. **Configure Zammad API token:**
   ```bash
   kubectl create secret generic zammad-credentials \
     --namespace=integrations \
     --from-literal=ZAMMAD_URL="http://alala.mcaas.example.com" \
     --from-literal=ZAMMAD_API_TOKEN="your-token-here"
   ```

2. **Deploy the connector:**
   ```bash
   kubectl apply -f integrations/wazuh-zammad/k8s-deployment.yaml
   ```

3. **Test the webhook:**
   ```bash
   kubectl run test --rm -i --restart=Never --image=curlimages/curl \
     -- curl -X POST http://wazuh-zammad-connector.integrations.svc/webhook/wazuh \
     -H "Content-Type: application/json" \
     -d '{"rule": {"id": "100001", "description": "Test Alert", "level": 5}, "agent": {"name": "test-server"}}'
   ```

**Configuration:**

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `ZAMMAD_URL` | Zammad instance URL | Required |
| `ZAMMAD_API_TOKEN` | API authentication token | Required |
| `ZAMMAD_GROUP` | Target ticket group | SOC |
| `DEDUP_WINDOW_HOURS` | Deduplication window | 24 |

### 2. Alert Filtering & Routing

Intelligent filtering of Wazuh alerts before processing.

**Features:**
- Filter by rule groups
- Exclude noisy rule IDs
- Severity-based filtering
- Time-based routing (e.g., after-hours alerts)
- Custom filter rules with Python expressions

**Usage:**

```bash
# Generate sample config
python integrations/common/alert_filter.py --generate-config > filters.yaml

# Filter alerts
python integrations/common/alert_filter.py \
  --alert-file alert.json \
  --config filters.yaml \
  --stdout
```

**Sample Configuration:**

```yaml
min_level: 3
max_level: 15
excluded_rules:
  - '5710'  # SSH brute force
  - '5712'  # SSH scan
included_groups:
  - syslog
  - ossec
  - attack
  - vulnerability-detection
after_hours_only:
  - '550'   # Informational alerts

custom_filters:
  - name: critical_to_pagerduty
    condition: 'level >= 10'
    action: route
    destination: pagerduty
    priority: 100
```

### 3. Shuffle Workflow Enhancements (TODO)

Planned enhancements to the Shuffle workflow:
- Email notifications for critical alerts
- Slack/Teams integration
- IP geolocation enrichment
- Threat intelligence lookups

## Architecture

```
Wazuh SIEM
    │
    ├───► Shuffle SOAR (via webhook)
    │       └─── Automated workflows
    │
    └───► Zammad Ticketing (via webhook_server)
            └─── SOC team triage
```

## Development

### Running Tests

```bash
# Test ticket creator
python integrations/wazuh-zammad/ticket_creator.py \
  --alert-json '{"rule": {"id": "100", "description": "Test", "level": 5}}' \
  --dry-run

# Test alert filter
python integrations/common/alert_filter.py --generate-config
```

### Building Docker Image

```bash
cd integrations/wazuh-zammad
docker build -t mcaas/wazuh-zammad-connector:latest .
```

## Security Considerations

- All API tokens are stored in Kubernetes Secrets
- No hardcoded credentials in source code
- Webhook endpoints should be protected (consider adding API key auth)
- Network policies restrict pod-to-pod communication

## Contributing

1. Create feature branch
2. Add integration to appropriate subdirectory
3. Include README with usage examples
4. Submit PR for review

## References

- [Wazuh API Documentation](https://documentation.wazuh.com/current/user-manual/api/reference.html)
- [Zammad REST API](https://docs.zammad.org/en/latest/api/intro.html)
- [Shuffle Webhooks](https://shuffler.io/docs/webhooks)
