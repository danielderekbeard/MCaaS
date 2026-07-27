# MCaaS Integrations

This directory contains integration scripts and tools for the Managed Compliance as a Service (MCaaS) platform.

## Directory Structure

```
integrations/
├── patch-wazuh-configmap-enhanced.py  # Enhanced ConfigMap patcher with error handling
├── shuffle/                           # Shuffle SOAR integration
│   ├── workflow-enhancer.py          # Workflow enhancement script
│   └── requirements.txt
├── wazuh-zammad/                      # Wazuh to Zammad ticket integration
│   ├── ticket-creator.py             # Ticket creation script with deduplication
│   └── requirements.txt
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

### shuffle/workflow-enhancer.py

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
