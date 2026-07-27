# SOC Analyst Quickstart Guide

> **MCaaS Platform** - Your integrated security operations environment

Welcome to the Managed Compliance as a Service (MCaaS) platform. This guide will get you up and running as a SOC analyst using the integrated Wazuh, Shuffle, and Zammad stack.

---

## Platform Overview

MCaaS provides a unified security operations stack with four core components:

| Component | Purpose | Access | Your Role |
|-----------|---------|--------|-----------|
| **Wazuh** | SIEM & XDR - threat detection | Dashboard | Monitor alerts, investigate threats |
| **Shuffle** | SOAR - automation workflows | Web UI | Trigger actions, review automation |
| **Zammad** | IT Ticketing | Web UI | Track incidents, document findings |
| **CISO Assistant** | GRC management | Web UI | Compliance tracking, reporting |

---

## Daily Workflow

### Step 1: Review Wazuh Dashboard (Deimos)

**URL:** `https://deimos.mcaas.example.com` (or port-forward if internal)

#### Morning Checklist

1. **Login** with Wazuh credentials
2. **Navigate to Security Events** (left sidebar → Security Events)
3. **Filter by Severity:**
   - Click the filter bar
   - Select `rule.level >= 5`
   - Review high-severity events from overnight

4. **Check for Critical Alerts (Level 10+):**
   ```
   rule.level >= 10 AND time > "24h"
   ```

5. **Review Agent Health:**
   - Management → Agents
   - Check "Last keep-alive" column
   - Investigate agents not reporting >15 minutes

#### Key Wazuh Dashboard Sections

| Section | Purpose | How Often |
|---------|---------|-----------|
| Security Events | View alerts | Every shift |
| Integrity Monitoring | File changes | Daily |
| Vulnerabilities | CVE data | Weekly |
| Compliance | PCI/DSS, HIPAA | Monthly reports |

---

### Step 2: Respond to Shuffle-Generated Tickets (Alala)

**URL:** `https://alala.mcaas.example.com`

#### Ticket Lifecycle

```
Wazuh Alert → Shuffle Enrichment → Zammad Ticket → You Investigate
```

#### Working a Ticket

1. **Access Your Queue:**
   - Login to Zammad
   - Tickets → My assigned tickets
   - Filter by "New" or "Open"

2. **Review Ticket Contents:**
   Each Shuffle-generated ticket contains:
   - **Subject:** Alert description from Wazuh
   - **Description:** Full JSON alert payload
   - **Enrichment data:** VirusTotal results, IP reputation, etc.

3. **Example Ticket Structure:**
   ```
   Subject: [ALERT] Multiple web authentication failures
   
   Alert Details:
   - Agent: workstation-001 (192.168.1.50)
   - Rule: Multiple web authentication failures
   - Level: 10 (High)
   - Timestamp: 2026-01-15T08:23:00Z
   
   Enrichment:
   - IP Reputation: Clean (AbuseIPDB)
   - Geo: United States
   - User: admin (failed 5 times)
   ```

4. **Update Ticket Status:**
   - **Open** → Investigating
   - Add internal notes with your findings
   - **Pending** → Waiting for user response
   - **Closed** → Resolved (add resolution summary)

---

### Step 3: Use Shuffle for Automation (Kydoimos)

**URL:** `https://kydoimos.mcaas.example.com`

#### Accessing Workflows

1. **Login** to Shuffle
2. **Navigate to Workflows** (left sidebar)
3. **Find the SOC workflow:** "Wazuh Alert Handler"

#### Running a Workflow Manually

Sometimes you need to trigger automation manually:

1. **Open the workflow** "Wazuh Alert Handler"
2. **Click "Run"** in the top-right
3. **Provide test data** (if prompted):
   ```json
   {
     "agent_name": "test-workstation",
     "alert_level": 7,
     "description": "Test authentication failure"
   }
   ```
4. **Review execution results** in the workflow run view

#### Common Shuffle Actions

| Action | When to Use |
|--------|-------------|
| Create Zammad Ticket | New high-severity alert |
| VirusTotal Lookup | Suspicious file hash or IP |
| Send Email | Notify manager of critical incident |
| Wazuh API Query | Get agent details, isolate host |

---

## Alert Severity Reference

### Wazuh Alert Levels

| Level | Severity | Response Time | Action |
|-------|----------|---------------|--------|
| 0-2 | Info | None | Log only |
| 3-5 | Low | 4 hours | Review daily |
| 6-8 | Medium | 1 hour | Create ticket |
| 9-11 | High | 15 minutes | Immediate response |
| 12+ | Critical | Immediate | Escalate + isolate |

### Common Alert Types

#### Authentication Alerts (Levels 5-10)
- **Multiple failed logins** → Check for brute force
- **Successful login after failures** → Possible compromise
- **Login from new location** → Verify with user

#### Malware Alerts (Levels 10-15)
- **File hash match** → Immediate isolation
- **Suspicious process** → Memory analysis
- **Known malware signature** → Full incident response

#### Network Alerts (Levels 8-12)
- **Port scanning** → Check source, may be internal tool
- **Suspicious outbound connection** → C2 check
- **IDS/IPS alert** → Review traffic capture

---

## Common Procedures

### Procedure: Isolate a Compromised Host

When you suspect a host is compromised:

1. **Document in Zammad ticket**
2. **Access Shuffle** → "Host Isolation" workflow
3. **Run workflow** with agent ID:
   ```
   Agent ID: 001 (from Wazuh alert)
   Action: isolate
   ```
4. **Verify isolation** in Wazuh:
   - Management → Agents → Select agent
   - Check "Status" shows "Never connected" after isolation
5. **Update ticket** with isolation timestamp
6. **Coordinate with IT** for cleanup

### Procedure: Investigate Suspicious IP

1. **Extract IP from alert** (source.ip or destination.ip)
2. **Check Shuffle enrichment** already in ticket
3. **Manual checks:**
   - VirusTotal: https://www.virustotal.com
   - AbuseIPDB: https://www.abuseipdb.com
   - Your threat intel feeds
4. **Document findings** in Zammad ticket
5. **Block if malicious:**
   - Wazuh active response
   - Firewall rule

### Procedure: Escalate Critical Incident

For Level 12+ alerts or confirmed compromise:

1. **Immediate actions:**
   - Isolate affected host(s)
   - Preserve logs (Wazuh archives)
   - Create critical Zammad ticket

2. **Notification:**
   - Email: security-team@mcaas.example.com
   - Slack: #security-incidents
   - Phone: On-call manager

3. **Documentation:**
   - Zammad ticket with "CRITICAL" prefix
   - Initial timeline in ticket
   - Affected systems list

---

## Troubleshooting

### Can't Access Wazuh Dashboard

1. **Check URL** - Use correct hostname or port-forward:
   ```bash
   kubectl port-forward -n wazuh svc/wazuh-dashboard 5601:443
   ```
2. **Verify SSL warning** - Self-signed cert, click "Advanced → Proceed"
3. **Reset password if needed:**
   ```bash
   kubectl exec -n wazuh wazuh-manager-master-0 -- /var/ossec/bin/wazuh-passwords-tool.sh -u wazuh-wui -p NEW_PASSWORD
   ```

### No Tickets in Zammad

1. **Check Shuffle workflow** is running
2. **Verify Wazuh webhook** configured:
   ```bash
   kubectl exec -n wazuh wazuh-manager-master-0 -- cat /var/ossec/etc/ossec.conf | grep -A5 shuffle
   ```
3. **Check Zammad API token** in Shuffle credentials

### Shuffle Workflow Failing

1. **Check workflow execution logs** in Shuffle UI
2. **Verify credentials** are configured:
   - Zammad API token
   - Wazuh API credentials
3. **Test connections** manually:
   ```bash
   curl -k -u admin:password https://wazuh-manager.wazuh:55000
   ```

---

## Reference: Key URLs and Ports

| Service | URL | Internal Service | Port |
|---------|-----|------------------|------|
| Wazuh Dashboard | https://deimos.mcaas.example.com | wazuh-dashboard.wazuh | 443 |
| Shuffle | https://kydoimos.mcaas.example.com | shuffle-backend.security-ops | 3008 |
| Zammad | https://alala.mcaas.example.com | zammad-web.managed-it | 80 |
| CISO Assistant | https://strategos.mcaas.example.com | ciso-assistant-frontend.grc | 443 |
| OpenSearch API | - | mcaas-opensearch.security-ops | 9200 |
| PostgreSQL | - | mcaas-postgresql.managed-it | 5432 |

---

## Next Steps

1. **Complete onboarding:** Request access to all systems
2. **Shadow a senior analyst:** Learn investigation patterns
3. **Review past incidents:** Search closed Zammad tickets
4. **Read the Runbooks:** See `/docs/runbooks/`
5. **Join the SOC channel:** Slack #soc-team

---

*Last updated: 2026-01-15 | For MCaaS v1.0*
