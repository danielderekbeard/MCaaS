# MCaaS Integrations

This directory contains integration scripts and tools for the Managed Compliance as a Service (MCaaS) platform.

## Directory Structure

```
integrations/
├── patch-wazuh-configmap-enhanced.py  # Enhanced ConfigMap patcher
├── common/                            # Shared utilities
│   └── alert_filter.py               # Intelligent alert filtering
├── shuffle/                           # Shuffle SOAR integration
│   ├── workflow-enhancer.py          # Workflow enhancement script
│   └── requirements.txt
├── wazuh-zammad/                      # Wazuh to Zammad ticket integration
│   ├── ticket_creator.py             # Ticket creation script
│   ├── webhook_server.py             # Webhook receiver
│   ├── Dockerfile
│   ├── k8s-deployment.yaml
│   └── requirements.txt
├── ciso-assistant/                    # CISO Assistant compliance mapping
│   ├── compliance_mapper.py          # Compliance mapper script
│   └── k8s-deployment.yaml
├── multi-channel/                     # Multi-channel alert distribution
│   ├── webhook_handler.py            # Teams/Slack/PagerDuty/Email handler
│   └── k8s-deployment.yaml
├── threat-intel/                      # Threat intelligence enrichment
│   ├── enricher.py                   # VirusTotal/AbuseIPDB/MISP client
│   └── k8s-deployment.yaml
└── health/                            # Health monitoring
    ├── health-check.py               # Integration health checker
    └── requirements.txt
```

## Scripts

### patch-wazuh-configmap-enhanced.py

Enhanced version of the Wazuh ConfigMap patcher with comprehensive features:

- **Label Selectors**: Find ConfigMaps by labels instead of hardcoded names
- **Error Handling**: Comprehensive exception handling with specific error types
- **Logging**: Structured logging with configurable levels
- **Dry-Run Mode**: Preview changes without applying
- **Rollback**: Automatic backup and rollback capability
- **Validation**: ConfigMap syntax validation before applying

```bash
# Basic usage
python integrations/patch-wazuh-configmap-enhanced.py

# Dry run
python integrations/patch-wazuh-configmap-enhanced.py --dry-run

# Rollback
python integrations/patch-wazuh-configmap-enhanced.py --rollback

# List backups
python integrations/patch-wazuh-configmap-enhanced.py --list-backups
```

### wazuh-zammad/ticket-creator.py

Creates Zammad tickets from Wazuh security alerts with deduplication:

- **Alert Mapping**: Maps Wazuh alerts to Zammad tickets
- **Deduplication**: Prevents duplicate tickets using signature-based tracking
- **Severity Mapping**: Automatic priority assignment based on alert level
- **Markdown Formatting**: Rich ticket descriptions with alert metadata

```bash
# Create tickets from file
python integrations/wazuh-zammad/ticket-creator.py --alert-file alerts.json

# Dry run to preview
python integrations/wazuh-zammad/ticket-creator.py --alert-file alerts.json --dry-run

# Cleanup old state entries
python integrations/wazuh-zammad/ticket-creator.py --cleanup-state
```

**Environment Variables:**
- `ZAMMAD_URL` - Zammad instance URL
- `ZAMMAD_API_TOKEN` - API authentication token
- `ZAMMAD_GROUP_ID` - Default ticket group (default: 1)
- `ZAMMAD_CUSTOMER_ID` - Default customer ID (default: 2)
- `TICKET_DEDUPLICATION_WINDOW` - Hours for deduplication (default: 24)

### ciso-assistant/compliance_mapper.py

Maps Wazuh alerts to compliance frameworks (ISO 27001, NIST, SOC2) and creates findings:

- **Framework Mapping**: Automatic control mapping based on alert groups
- **Multi-Framework**: Support for ISO27001, NIST, SOC2
- **Finding Creation**: Auto-create compliance findings in CISO Assistant
- **Evidence Tracking**: Include alert data as compliance evidence

```bash
# Map alert to ISO 27001
python integrations/ciso-assistant/compliance_mapper.py --alert-file alert.json --framework iso27001

# Map to all frameworks
python integrations/ciso-assistant/compliance_mapper.py --alert-file alert.json --all-frameworks

# List available mappings
python integrations/ciso-assistant/compliance_mapper.py --list-mappings
```

**Environment Variables:**
- `CISO_ASSISTANT_URL` - CISO Assistant API URL
- `CISO_ASSISTANT_API_KEY` - API authentication key
- `DEFAULT_FRAMEWORK` - Default framework (iso27001, nist, soc2)
- `AUTO_CREATE_FINDINGS` - Automatically create findings (true/false)

### multi-channel/webhook_handler.py

Multi-channel alert distribution to Teams, Slack, PagerDuty, and Email:

- **Severity Routing**: Automatic channel selection based on alert level
- **Microsoft Teams**: Rich card notifications
- **Slack**: Block-based messages with markdown
- **PagerDuty**: Events API v2 integration with dedup key
- **Email**: SMTP notifications to SOC team

```bash
# Start webhook server
python integrations/multi-channel/webhook_handler.py --port 8081

# Test with sample alert
python integrations/multi-channel/webhook_handler.py --test

# Send test via curl
curl -X POST http://localhost:8081/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"rule": {"id": "100001", "description": "Test", "level": 10}, "agent": {"name": "test"}}'
```

**Environment Variables:**
- `TEAMS_WEBHOOK_URL` - Microsoft Teams webhook URL
- `SLACK_WEBHOOK_URL` - Slack webhook URL
- `PAGERDUTY_ROUTING_KEY` - PagerDuty Events API routing key
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` - Email configuration
- `SOC_EMAIL` - SOC team email address

### threat-intel/enricher.py

Threat intelligence enrichment with VirusTotal, AbuseIPDB, and MISP:

- **IOC Extraction**: Automatic extraction of IPs, hashes, and URLs from alerts
- **VirusTotal**: File hash and IP reputation lookups
- **AbuseIPDB**: IP abuse confidence scoring
- **MISP**: Threat sharing platform integration
- **Threat Scoring**: Combined threat score calculation
- **Caching**: Results cached to minimize API calls

```bash
# Enrich alert from file
python integrations/threat-intel/enricher.py --alert-file alert.json --stdout

# Enrich specific IP
python integrations/threat-intel/enricher.py --ip 1.2.3.4

# Enrich specific hash
python integrations/threat-intel/enricher.py --hash abc123...
```

**Environment Variables:**
- `VIRUSTOTAL_API_KEY` - VirusTotal API key
- `ABUSEIPDB_API_KEY` - AbuseIPDB API key
- `MISP_URL`, `MISP_API_KEY` - MISP configuration
- `ENRICHMENT_CACHE_TTL` - Cache time-to-live in seconds (default: 3600)

### common/alert_filter.py

Intelligent alert filtering and routing:

- **Rule Filtering**: Filter by groups, IDs, or severity
- **Time-Based**: After-hours alert handling
- **Custom Rules**: Python expression-based filters
- **Multi-Destination**: Route to different outputs

```bash
# Generate sample config
python integrations/common/alert_filter.py --generate-config > filters.yaml

# Filter alerts
python integrations/common/alert_filter.py --alert-file alerts.json --config filters.yaml --stdout
```

Enhances Shuffle workflows with advanced features:

- **Conditional Logic**: Branching based on alert severity
- **Email Notifications**: Critical alert emails to SOC team
- **Slack Notifications**: SOC channel notifications
- **Threat Intel Enrichment**: IP and hash analysis
- **Auto-Remediation**: Automated response actions

```bash
# Export current workflow
python integrations/shuffle/workflow-enhancer.py --workflow-id ID --export

# Enhance workflow
python integrations/shuffle/workflow-enhancer.py --workflow-id ID

# Dry run
python integrations/shuffle/workflow-enhancer.py --workflow-id ID --dry-run
```

### health/health-check.py

Comprehensive health monitoring for all integrations:

- **Kubernetes Checks**: Namespace, ConfigMap, pod status
- **Shuffle Checks**: API and webhook accessibility
- **Zammad Checks**: API connectivity
- **Flow Validation**: End-to-end integration testing

```bash
# Run all checks
python integrations/health/health-check.py

# Check specific integration
python integrations/health/health-check.py --integration shuffle

# JSON output
python integrations/health/health-check.py --json

# Continuous monitoring
python integrations/health/health-check.py --continuous --interval 300
```

## Code Quality Standards

All scripts follow these standards:

- **Environment Variables**: All secrets via env vars (no hardcoded tokens)
- **Error Handling**: Comprehensive try/except with specific exceptions
- **Logging**: Structured logging with configurable levels
- **Docstrings**: Google-style docstrings for all functions
- **PEP 8**: Code formatted per PEP 8 style guide
- **Type Hints**: Type annotations for function signatures

## Installation

```bash
# Install dependencies for a specific integration
cd integrations/wazuh-zammad
pip install -r requirements.txt

# Or install all dependencies
cd integrations
pip install */requirements.txt
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration/missing credentials |
| 3 | API error |
| 4 | Validation/duplicate error |
| 5 | Rollback failed |

## Contributing

When adding new integrations:

1. Create a subdirectory under `integrations/`
2. Add `requirements.txt` with dependencies
3. Include comprehensive docstrings
4. Follow error handling patterns from existing scripts
5. Update this README
