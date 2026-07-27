# MCaaS API Integration Guide

> **Complete API reference for Wazuh, Shuffle, and Zammad integrations**

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Wazuh API](#wazuh-api)
4. [Shuffle API](#shuffle-api)
5. [Zammad API](#zammad-api)
6. [Integration Examples](#integration-examples)
7. [Common Workflows](#common-workflows)

---

## Overview

MCaaS exposes REST APIs for each component:

| Component | Base URL | Protocol | Version |
|-----------|----------|----------|---------|
| Wazuh API | `https://wazuh-manager.wazuh:55000` | HTTPS | 4.7.0 |
| Shuffle API | `http://shuffle-backend.security-ops:3008` | HTTP | 1.3.0 |
| Zammad API | `http://zammad-web.managed-it:80/api/v1` | HTTP | 6.0 |
| OpenSearch | `https://mcaas-opensearch.security-ops:9200` | HTTPS | 2.11 |

---

## Authentication

### Wazuh API Authentication

Wazuh uses Basic Authentication with JWT tokens.

```bash
# Step 1: Get JWT token
curl -k -u wazuh-wui:PASSWORD \
  -X POST "https://wazuh-manager.wazuh:55000/security/user/authenticate"

# Response:
# {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}

# Step 2: Use token in subsequent requests
curl -k \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  "https://wazuh-manager.wazuh:55000/agents"
```

**Python Example:**

```python
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
WAZUH_HOST = "wazuh-manager.wazuh"
WAZUH_PORT = "55000"
WAZUH_USER = "wazuh-wui"
WAZUH_PASS = "your-password"

# Authenticate
auth_url = f"https://{WAZUH_HOST}:{WAZUH_PORT}/security/user/authenticate"
response = requests.post(
    auth_url,
    auth=(WAZUH_USER, WAZUH_PASS),
    verify=False
)
token = response.json()["data"]["token"]

# Use API
headers = {"Authorization": f"Bearer {token}"}
agents_url = f"https://{WAZUH_HOST}:{WAZUH_PORT}/agents"
response = requests.get(agents_url, headers=headers, verify=False)
agents = response.json()["data"]["affected_items"]
```

---

### Shuffle API Authentication

Shuffle uses API keys passed in the `Authorization` header.

```bash
# Get your API key from Shuffle UI: Admin -> Settings -> API Keys

# Use in requests
curl -X GET \
  "http://shuffle-backend.security-ops:3008/api/v1/workflows" \
  -H "Authorization: Bearer YOUR_SHUFFLE_API_KEY"
```

**Python Example:**

```python
import requests

SHUFFLE_HOST = "shuffle-backend.security-ops"
SHUFFLE_PORT = "3008"
SHUFFLE_API_KEY = "your-shuffle-api-key"

headers = {
    "Authorization": f"Bearer {SHUFFLE_API_KEY}",
    "Content-Type": "application/json"
}

# Get workflows
workflows_url = f"http://{SHUFFLE_HOST}:{SHUFFLE_PORT}/api/v1/workflows"
response = requests.get(workflows_url, headers=headers)
workflows = response.json()
```

---

### Zammad API Authentication

Zammad supports Token-based authentication.

```bash
# Get API token from Zammad UI: Profile -> Token Access

# Use in requests
curl -X GET \
  "http://zammad-web.managed-it:80/api/v1/tickets" \
  -H "Authorization: Token token=YOUR_ZAMMAD_TOKEN"
```

**Python Example:**

```python
import requests

ZAMMAD_HOST = "zammad-web.managed-it"
ZAMMAD_PORT = "80"
ZAMMAD_TOKEN = "your-zammad-token"

headers = {
    "Authorization": f"Token token={ZAMMAD_TOKEN}",
    "Content-Type": "application/json"
}

# Get tickets
tickets_url = f"http://{ZAMMAD_HOST}:{ZAMMAD_PORT}/api/v1/tickets"
response = requests.get(tickets_url, headers=headers)
tickets = response.json()
```

---

## Wazuh API

### Agents Management

#### List All Agents

```bash
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/agents"
```

**Response:**

```json
{
  "data": {
    "affected_items": [
      {
        "id": "001",
        "name": "workstation-001",
        "ip": "192.168.1.50",
        "status": "active",
        "os": {
          "name": "Microsoft Windows 10 Pro",
          "platform": "windows"
        },
        "lastKeepAlive": "2026-01-15T10:30:00Z",
        "dateAdd": "2026-01-01T00:00:00Z"
      }
    ],
    "total_affected_items": 1
  }
}
```

#### Get Agent Details

```bash
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/agents/001"
```

#### Get Agent Key

```bash
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/agents/001/key"
```

---

### Security Events

#### Get Security Alerts

```bash
# Get alerts from last 24 hours
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/security/alerts?time=1d"

# Get high severity alerts
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/security/alerts?rule.level=gte:10"

# Get alerts by agent
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/security/alerts?agents_list=001"
```

**Query Parameters:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `time` | Time range | `1h`, `1d`, `1w` |
| `rule.level` | Alert severity | `gte:10` |
| `rule.id` | Specific rule | `31533` |
| `agents_list` | Agent IDs | `001,002` |
| `limit` | Results per page | `100` |
| `offset` | Pagination offset | `0` |

---

### Active Response

#### Run Active Response

```bash
# Isolate a host
curl -k -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "firewall-drop",
    "arguments": ["add", "192.168.1.100"]
  }' \
  "https://wazuh-manager.wazuh:55000/active-response?agents_list=001"
```

**Available Commands:**

| Command | Description | Arguments |
|---------|-------------|-----------|
| `firewall-drop` | Block IP | `add/remove`, IP |
| `host-deny` | Deny host | `add/remove`, IP |
| `restart-wazuh` | Restart agent | `agent` |

---

### Syscheck (FIM)

#### Get File Integrity Events

```bash
# Get file changes for agent
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/syscheck/001"

# Get specific file checksum
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/syscheck/001?file=/etc/passwd"
```

---

## Shuffle API

### Workflows

#### List Workflows

```bash
curl -X GET \
  "http://shuffle-backend.security-ops:3008/api/v1/workflows" \
  -H "Authorization: Bearer $SHUFFLE_KEY"
```

#### Get Workflow Details

```bash
curl -X GET \
  "http://shuffle-backend.security-ops:3008/api/v1/workflows/WORKFLOW_ID" \
  -H "Authorization: Bearer $SHUFFLE_KEY"
```

#### Execute Workflow

```bash
# Trigger workflow manually
curl -X POST \
  "http://shuffle-backend.security-ops:3008/api/v1/workflows/WORKFLOW_ID/execute" \
  -H "Authorization: Bearer $SHUFFLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "start_node": "INITIAL_NODE_ID",
    "execution_argument": {
      "agent_name": "workstation-001",
      "alert_level": 10,
      "description": "Malware detected"
    }
  }'
```

---

### Webhooks

#### List Webhooks

```bash
curl -X GET \
  "http://shuffle-backend.security-ops:3008/api/v1/webhooks" \
  -H "Authorization: Bearer $SHUFFLE_KEY"
```

#### Create Webhook

```bash
curl -X POST \
  "http://shuffle-backend.security-ops:3008/api/v1/webhooks" \
  -H "Authorization: Bearer $SHUFFLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Wazuh Alert Handler",
    "workflow_id": "WORKFLOW_ID",
    "active": true
  }'
```

#### Trigger Webhook

```bash
# Send alert to Shuffle webhook
curl -X POST \
  "http://shuffle-backend.security-ops:3008/api/v1/webhooks/WEBHOOK_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "rule": {
      "description": "Multiple authentication failures",
      "level": 10
    },
    "agent": {
      "id": "001",
      "name": "workstation-001",
      "ip": "192.168.1.50"
    },
    "full_log": "Log content here..."
  }'
```

---

### Apps and Actions

#### List Available Apps

```bash
curl -X GET \
  "http://shuffle-backend.security-ops:3008/api/v1/apps" \
  -H "Authorization: Bearer $SHUFFLE_KEY"
```

#### Get App Actions

```bash
curl -X GET \
  "http://shuffle-backend.security-ops:3008/api/v1/apps/wazuh/actions" \
  -H "Authorization: Bearer $SHUFFLE_KEY"
```

---

## Zammad API

### Tickets

#### List Tickets

```bash
# All tickets
curl -X GET \
  "http://zammad-web.managed-it:80/api/v1/tickets" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN"

# Filter by state
curl -X GET \
  "http://zammad-web.managed-it:80/api/v1/tickets?state_id=1" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN"

# Filter by owner
curl -X GET \
  "http://zammad-web.managed-it:80/api/v1/tickets?owner_id=3" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN"
```

**Ticket States:**

| ID | State |
|----|-------|
| 1 | New |
| 2 | Open |
| 3 | Pending reminder |
| 4 | Closed |

#### Create Ticket

```bash
curl -X POST \
  "http://zammad-web.managed-it:80/api/v1/tickets" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "[ALERT] Multiple authentication failures",
    "group_id": 1,
    "state_id": 1,
    "priority_id": 3,
    "customer_id": 2,
    "article": {
      "subject": "Security Alert Details",
      "body": "Alert from Wazuh SIEM...",
      "type": "note",
      "internal": false
    }
  }'
```

#### Get Ticket Details

```bash
curl -X GET \
  "http://zammad-web.managed-it:80/api/v1/tickets/TICKET_ID" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN"
```

#### Update Ticket

```bash
curl -X PUT \
  "http://zammad-web.managed-it:80/api/v1/tickets/TICKET_ID" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "state_id": 2,
    "owner_id": 3,
    "note": "Investigation started"
  }'
```

---

### Ticket Articles

#### Add Article to Ticket

```bash
curl -X POST \
  "http://zammad-web.managed-it:80/api/v1/tickets/TICKET_ID/articles" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Investigation Update",
    "body": "Found suspicious process execution at 2026-01-15 10:30:00",
    "type": "note",
    "internal": true
  }'
```

---

### Users

#### List Users

```bash
curl -X GET \
  "http://zammad-web.managed-it:80/api/v1/users" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN"
```

#### Create User

```bash
curl -X POST \
  "http://zammad-web.managed-it:80/api/v1/users" \
  -H "Authorization: Token token=$ZAMMAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "firstname": "Security",
    "lastname": "Analyst",
    "email": "analyst@mcaas.example.com",
    "roles": ["Agent"]
  }'
```

---

## Integration Examples

### Example 1: Alert to Ticket Pipeline

```python
"""
Complete pipeline: Wazuh Alert → Shuffle → Zammad Ticket
"""
import requests
import json
import urllib3
from datetime import datetime

urllib3.disable_warnings()

# Configuration
WAZUH_HOST = "wazuh-manager.wazuh"
SHUFFLE_HOST = "shuffle-backend.security-ops"
SHUFFLE_WEBHOOK_ID = "webhook-uuid-here"

def get_wazuh_token():
    """Authenticate with Wazuh API"""
    url = f"https://{WAZUH_HOST}:55000/security/user/authenticate"
    response = requests.post(url, auth=("wazuh-wui", "password"), verify=False)
    return response.json()["data"]["token"]

def get_recent_alerts(token, hours=1):
    """Get alerts from last N hours"""
    url = f"https://{WAZUH_HOST}:55000/security/alerts?time={hours}h"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, verify=False)
    return response.json()["data"]["affected_items"]

def send_to_shuffle(alert):
    """Send alert to Shuffle webhook"""
    url = f"http://{SHUFFLE_HOST}:3008/api/v1/webhooks/{SHUFFLE_WEBHOOK_ID}"
    
    payload = {
        "rule": {
            "id": alert.get("rule", {}).get("id"),
            "description": alert.get("rule", {}).get("description"),
            "level": alert.get("rule", {}).get("level")
        },
        "agent": {
            "id": alert.get("agent", {}).get("id"),
            "name": alert.get("agent", {}).get("name"),
            "ip": alert.get("agent", {}).get("ip")
        },
        "full_log": alert.get("full_log"),
        "timestamp": alert.get("timestamp")
    }
    
    response = requests.post(url, json=payload)
    return response.status_code == 200

def main():
    # Authenticate
    token = get_wazuh_token()
    
    # Get recent high-severity alerts
    alerts = get_recent_alerts(token)
    
    for alert in alerts:
        level = alert.get("rule", {}).get("level", 0)
        if level >= 7:
            print(f"Processing alert: {alert.get('rule', {}).get('description')}")
            if send_to_shuffle(alert):
                print("  → Sent to Shuffle successfully")
            else:
                print("  → Failed to send to Shuffle")

if __name__ == "__main__":
    main()
```

---

### Example 2: Ticket Automation

```python
"""
Create Zammad ticket from security event
"""
import requests

ZAMMAD_HOST = "zammad-web.managed-it"
ZAMMAD_TOKEN = "your-token-here"

def create_security_ticket(alert_data):
    """Create a security incident ticket"""
    
    url = f"http://{ZAMMAD_HOST}:80/api/v1/tickets"
    headers = {
        "Authorization": f"Token token={ZAMMAD_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Determine priority based on alert level
    level = alert_data.get("rule", {}).get("level", 0)
    priority_id = 1 if level < 8 else (2 if level < 11 else 3)
    
    # Format the body
    body = f"""
Security Alert Details:

Severity: {level}
Rule: {alert_data.get("rule", {}).get("description")}
Agent: {alert_data.get("agent", {}).get("name")} ({alert_data.get("agent", {}).get("ip")})
Time: {alert_data.get("timestamp")}

Full Log:
```
{alert_data.get("full_log")}
```

Please investigate immediately.
    """
    
    payload = {
        "title": f"[SEV-{level}] {alert_data.get('rule', {}).get('description')}",
        "group_id": 1,  # Security group
        "state_id": 1,  # New
        "priority_id": priority_id,
        "customer_id": 1,  # System customer
        "article": {
            "subject": "Alert Details",
            "body": body,
            "type": "note",
            "internal": False
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Example usage
alert = {
    "rule": {
        "id": "31533",
        "description": "Multiple web authentication failures",
        "level": 10
    },
    "agent": {
        "id": "001",
        "name": "workstation-001",
        "ip": "192.168.1.50"
    },
    "timestamp": "2026-01-15T10:30:00Z",
    "full_log": "Jan 15 10:30:00 workstation-001 sshd[1234]: Failed password for user..."
}

result = create_security_ticket(alert)
print(f"Ticket created: #{result.get('number')}")
```

---

### Example 3: Complete Incident Response

```python
"""
Full incident response automation
"""
import requests
import urllib3

urllib3.disable_warnings()

class MCaaSAPI:
    def __init__(self):
        self.wazuh_token = None
        self.wazuh_host = "wazuh-manager.wazuh"
        self.shuffle_host = "shuffle-backend.security-ops"
        self.zammad_host = "zammad-web.managed-it"
        self.zammad_token = "your-zammad-token"
    
    def wazuh_auth(self, username, password):
        """Authenticate with Wazuh"""
        url = f"https://{self.wazuh_host}:55000/security/user/authenticate"
        resp = requests.post(url, auth=(username, password), verify=False)
        self.wazuh_token = resp.json()["data"]["token"]
        return self.wazuh_token
    
    def isolate_host(self, agent_id):
        """Isolate a host via Wazuh active response"""
        url = f"https://{self.wazuh_host}:55000/active-response"
        headers = {"Authorization": f"Bearer {self.wazuh_token}"}
        
        payload = {
            "command": "firewall-drop",
            "arguments": ["add", "0.0.0.0"]  # Block all traffic
        }
        
        resp = requests.put(
            url,
            headers=headers,
            params={"agents_list": agent_id},
            json=payload,
            verify=False
        )
        return resp.json()
    
    def create_incident_ticket(self, alert, action_taken):
        """Create incident ticket in Zammad"""
        url = f"http://{self.zammad_host}:80/api/v1/tickets"
        headers = {
            "Authorization": f"Token token={self.zammad_token}",
            "Content-Type": "application/json"
        }
        
        body = f"""
INCIDENT REPORT

Alert ID: {alert.get('id')}
Severity: {alert.get('rule', {}).get('level')}
Agent: {alert.get('agent', {}).get('name')}
Description: {alert.get('rule', {}).get('description')}

ACTIONS TAKEN:
- Host isolated: {action_taken.get('isolated', False)}
- Ticket created: {datetime.now()}

NEXT STEPS:
- [ ] Full forensic analysis
- [ ] Malware scanning
- [ ] Credential reset
- [ ] Document in CISO Assistant
        """
        
        payload = {
            "title": f"[INCIDENT] {alert.get('rule', {}).get('description')}",
            "group_id": 1,
            "state_id": 2,  # Open
            "priority_id": 4,  # Critical
            "article": {
                "subject": "Incident Details",
                "body": body,
                "type": "note",
                "internal": True
            }
        }
        
        resp = requests.post(url, headers=headers, json=payload)
        return resp.json()

# Usage
api = MCaaSAPI()
api.wazuh_auth("wazuh-wui", "password")

# Example incident response
alert_data = {...}  # Alert from Wazuh
isolation_result = api.isolate_host(alert_data["agent"]["id"])
ticket = api.create_incident_ticket(alert_data, {"isolated": True})

print(f"Ticket created: #{ticket.get('number')}")
```

---

## Common Workflows

### Workflow 1: Daily Alert Review

```
1. Query Wazuh API for alerts (last 24h, level >= 5)
2. Filter by severity
3. For each level 8+ alert:
   - Send to Shuffle webhook
   - Shuffle enriches data
   - Shuffle creates Zammad ticket
4. Analyst reviews tickets in Zammad
```

### Workflow 2: Incident Escalation

```
1. Wazuh detects critical alert (level 12+)
2. Shuffle automatically:
   - Creates critical ticket
   - Isolates host
   - Sends email to security team
3. Analyst investigates in Zammad
4. Analysis results added to ticket
5. CISO Assistant updated for compliance
```

### Workflow 3: Threat Hunting

```
1. Analyst queries Wazuh for suspicious patterns
2. Results exported via API
3. Shuffle workflow cross-references with:
   - Threat intelligence feeds
   - Historical data
4. Findings documented in Zammad
5. Recommendations tracked in CISO Assistant
```

---

## Error Handling

### Common HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Continue |
| 401 | Unauthorized | Check credentials |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Check resource ID |
| 500 | Server Error | Check service health |

### Python Error Handling Pattern

```python
import requests
from requests.exceptions import RequestException

def safe_api_call(func):
    """Decorator for safe API calls"""
    def wrapper(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            print(f"HTTP Error: {e}")
            return None
        except RequestException as e:
            print(f"Request failed: {e}")
            return None
    return wrapper

@safe_api_call
def get_wazuh_agents():
    return requests.get(url, headers=headers, verify=False)
```

---

## API Rate Limits

| API | Rate Limit | Notes |
|-----|------------|-------|
| Wazuh | 100 req/min | Configurable in wazuh.yml |
| Shuffle | No limit | Internal network only |
| Zammad | 50 req/min | Configurable per user |

---

*Last updated: January 2026 | MCaaS v1.0*
