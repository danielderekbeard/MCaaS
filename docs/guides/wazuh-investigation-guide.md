# Wazuh Investigation Guide

> **Advanced threat hunting and alert investigation using Wazuh SIEM**

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Alert Investigation Workflow](#alert-investigation-workflow)
3. [Common Investigation Scenarios](#common-investigation-scenarios)
4. [Advanced Queries](#advanced-queries)
5. [Threat Hunting](#threat-hunting)
6. [Forensic Data Collection](#forensic-data-collection)

---

## Getting Started

### Accessing Wazuh

**Dashboard URL:** `https://deimos.mcaas.example.com`

**Default Login:**
- Username: `admin`
- Password: Retrieved from Kubernetes secret

```bash
# Get Wazuh dashboard password
kubectl -n wazuh get secret wazuh-api-credentials -o jsonpath='{.data.password}' | base64 -d
```

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Wazuh Logo    Menu    [Search]    [Notifications] [User]   │
├────────┬────────────────────────────────────────────────────┤
│        │                                                    │
│  Home  │                    MAIN PANEL                      │
│        │                                                    │
│  Sec   │     [Security Events] [Integrity] [Vulns]         │
│  Event │                                                    │
│        │     [Panels] [Visualizations] [Discover]        │
│  Agent │                                                    │
│  Mgmt  │                                                    │
│        │                                                    │
│  Mgmt  │                                                    │
│        │                                                    │
└────────┴────────────────────────────────────────────────────┘
```

---

## Alert Investigation Workflow

### Step-by-Step Investigation Process

#### Phase 1: Triage (0-5 minutes)

1. **Identify Alert Severity**
   ```
   Level 1-4:  Informational - Review weekly
   Level 5-7:  Low - Review daily, document
   Level 8-10: Medium - Create ticket, investigate within 1 hour
   Level 11-12: High - Immediate investigation
   Level 13+:  Critical - Immediate escalation + isolation
   ```

2. **Check Agent Context**
   - Agent name and IP
   - Operating system
   - Last keep-alive time
   - Group membership

3. **Review Alert Details**
   - Rule description
   - Full log message
   - Timestamp correlation

#### Phase 2: Investigation (5-30 minutes)

**Investigation Checklist:**

- [ ] Check related alerts from same agent (time window: ±1 hour)
- [ ] Review user activity logs
- [ ] Examine network connections
- [ ] Check file integrity monitoring events
- [ ] Query Wazuh API for additional context

**Query Examples:**

```
# Same agent, same time window
agent.id:001 AND timestamp:["now-1h" TO "now+1h"]

# Same user across all agents
data.win.eventdata.targetUserName:jdoe AND timestamp:["now-1h" TO "now"]

# Network activity from agent
agent.id:001 AND (data.dstip:* OR data.srcip:*)
```

#### Phase 3: Response (30+ minutes)

1. **Containment Actions**
   - Isolate host via Wazuh active response
   - Block IP at firewall
   - Disable user account

2. **Evidence Collection**
   - Export alert details
   - Screenshot dashboard
   - Save related logs

3. **Documentation**
   - Update Zammad ticket
   - Timeline of events
   - Actions taken

---

## Common Investigation Scenarios

### Scenario 1: Brute Force Attack

**Alert:** "Multiple web authentication failures"

**Investigation Steps:**

1. **Identify attacker IP:**
   ```
   Query: rule.id:31533 AND timestamp:["now-24h" TO "now"]
   Aggregate by: data.srcip
   ```

2. **Check for successful login:**
   ```
   data.srcip:[ATTACKER_IP] AND rule.id:2501
   ```

3. **Review user lockouts:**
   ```
   rule.id:2502 AND data.srcip:[ATTACKER_IP]
   ```

**Response Actions:**
- Block source IP in firewall
- Force password reset for targeted accounts
- Enable MFA if not already active

### Scenario 2: Malware Detection

**Alert:** "File added to the system" (Malware signature match)

**Investigation Steps:**

1. **Get file details:**
   ```
   syscheck.path:*malware* OR syscheck.path:*suspicious*
   ```

2. **Check file hash:**
   ```
   # Look for syscheck.md5_after or syscheck.sha256_after
   agent.id:[ID] AND syscheck.md5_after:[HASH]
   ```

3. **VirusTotal lookup:**
   - Copy MD5/SHA256 hash
   - Query VirusTotal API or website
   - Check Shuffle enrichment if available

4. **Review process tree:**
   ```
   # Parent process of malware execution
   agent.id:[ID] AND process.pid:[PID]
   ```

**Response Actions:**
- Immediate host isolation
- Memory dump for forensics
- Full system scan
- Check lateral movement indicators

### Scenario 3: Lateral Movement

**Alert:** "Suspicious network connection"

**Investigation Steps:**

1. **Map network connections:**
   ```
   # Outbound connections from source
   agent.id:[SOURCE_ID] AND data.dstip:*
   
   # Inbound connections to destination
   agent.id:[DEST_ID] AND data.srcip:[SOURCE_IP]
   ```

2. **Check for authentication:**
   ```
   # Pass-the-hash or credential reuse
   rule.id:(2501 OR 2502) AND agent.id:[DEST_ID]
   ```

3. **Review file transfers:**
   ```
   # Large file transfers
   syscheck.size_after:>104857600 AND agent.id:[SOURCE_ID]
   ```

**Response Actions:**
- Isolate both source and destination
- Reset credentials for affected accounts
- Review all agents for compromise indicators

### Scenario 4: Data Exfiltration

**Alert:** "Large outbound data transfer"

**Investigation Steps:**

1. **Identify transferred files:**
   ```
   agent.id:[ID] AND syscheck.modified:yes AND timestamp:["now-24h" TO "now"]
   Sort by: syscheck.size_after (descending)
   ```

2. **Check destination:**
   ```
   agent.id:[ID] AND (data.dstip:[EXTERNAL_IP] OR data.url:*)
   ```

3. **Review process:**
   ```
   agent.id:[ID] AND process.name:(curl OR wget OR python OR powershell)
   ```

**Response Actions:**
- Block external destination
- Isolate host
- Review access logs for data accessed
- Determine data classification

---

## Advanced Queries

### Wazuh Query Language (WQL)

#### Basic Syntax

```
field:value                    # Exact match
field:(value1 OR value2)     # Multiple values
field:value*                 # Wildcard prefix
field:*value                 # Wildcard suffix
field:*value*                # Wildcard both sides
field:>100                     # Greater than
field:<=50                    # Less than or equal
field:[1 TO 10]              # Range
NOT field:value              # Negation
field:value AND other:val    # AND operator
field:value OR other:val     # OR operator
```

#### Field Reference

| Field | Description | Example |
|-------|-------------|---------|
| `agent.id` | Agent identifier | `agent.id:001` |
| `agent.name` | Agent hostname | `agent.name:workstation*` |
| `rule.id` | Rule ID | `rule.id:31533` |
| `rule.level` | Alert severity | `rule.level:>=7` |
| `rule.description` | Rule description | `rule.description:*authentication*` |
| `timestamp` | Event time | `timestamp:["now-1h" TO "now"]` |
| `data.srcip` | Source IP | `data.srcip:192.168.1.*` |
| `data.dstip` | Destination IP | `data.dstip:10.0.0.1` |
| `data.srcport` | Source port | `data.srcport:443` |
| `data.dstport` | Destination port | `data.dstport:3389` |
| `data.win.system.eventID` | Windows Event ID | `data.win.system.eventID:4624` |
| `syscheck.path` | File path | `syscheck.path:*.exe` |
| `syscheck.md5_after` | MD5 hash | `syscheck.md5_after:d41d8cd98f00b204e9800998ecf8427e` |

#### Saved Searches

```
# High severity alerts last 24h
rule.level:>=10 AND timestamp:["now-1d" TO "now"]

# Authentication failures by IP
data.win.eventdata.subStatus:0xc000006d AND timestamp:["now-1h" TO "now"]

# Suspicious PowerShell execution
rule.description:*powershell* AND (data.win.event.data.scriptBlock.text:*Invoke* OR data.win.event.data.scriptBlock.text:*DownloadString*)

# File integrity changes
agent.id:[ID] AND syscheck.event:(modified OR added) AND timestamp:["now-1h" TO "now"]
```

---

## Threat Hunting

### Proactive Searches

#### Weekly Hunting Queries

```
# 1. New user accounts (potential persistence)
data.win.system.eventID:4720 AND timestamp:["now-7d" TO "now"]

# 2. Services created (persistence)
data.win.system.eventID:4697 AND timestamp:["now-7d" TO "now"]

# 3. Scheduled tasks created
rule.id:6200 AND timestamp:["now-7d" TO "now"]

# 4. Privilege escalation attempts
rule.level:>=10 AND (rule.description:*privilege* OR rule.description:*escalation*)

# 5. Unusual process execution
rule.description:*unusual* OR rule.description:*anomalous*
```

#### Monthly Hunting Queries

```
# Long-term persistence check
# Services, scheduled tasks, registry keys from last 30 days

# Network anomalies
# Top 10 destinations by connection count
data.dstip:* AND timestamp:["now-30d" TO "now"]

# File system anomalies
# Large files created
syscheck.size_after:>100000000 AND timestamp:["now-30d" TO "now"]
```

### Anomaly Detection

#### Baseline Deviation

1. **Identify normal patterns:**
   - Login times per user
   - Common source IPs
   - Regular processes

2. **Query for deviations:**
   ```
   # Login outside business hours
   rule.id:2501 AND NOT timestamp:["09:00:00" TO "17:00:00"]
   
   # New source IP for user
   # (Requires historical comparison)
   ```

---

## Forensic Data Collection

### Exporting Alert Data

#### Method 1: Dashboard Export

1. **Navigate to Security Events**
2. **Apply filters** for investigation
3. **Click "Export"** button
4. **Select format:** CSV or JSON

#### Method 2: Wazuh API

```bash
# Get specific alert details
curl -k -u wazuh-wui:PASSWORD \
  "https://wazuh-manager.wazuh:55000/security/alerts?pretty=true" \
  -H "Authorization: Bearer TOKEN"

# Get alerts by rule ID
curl -k -u wazuh-wui:PASSWORD \
  "https://wazuh-manager.wazuh:55000/alerts?rule.id=31533&pretty=true"

# Get agent information
curl -k -u wazuh-wui:PASSWORD \
  "https://wazuh-manager.wazuh:55000/agents/001"
```

### Log Collection

#### Wazuh Archives

```bash
# Access archived logs on manager
kubectl exec -n wazuh wazuh-manager-master-0 -- ls -la /var/ossec/logs/archives/

# Search archives for specific time
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  grep "2026-01-15" /var/ossec/logs/archives/2026/Jan/ossec-archive-15.log.gz
```

#### Agent Logs

```bash
# Get agent ossec.log
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  cat /var/ossec/logs/agents/001-AGENT_NAME/ossec.log
```

---

## Integration with Shuffle

### Triggering Shuffle from Wazuh

When investigating, you can trigger Shuffle workflows:

```bash
# Manual webhook trigger for testing
curl -X POST \
  "https://kydoimos.mcaas.example.com/api/v1/webhooks/WEBHOOK_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "workstation-001",
    "alert_level": 10,
    "description": "Manual investigation trigger",
    "investigator": "analyst@example.com"
  }'
```

### Using Shuffle for Enrichment

Common enrichment workflows:

| Action | Input | Output |
|--------|-------|--------|
| VirusTotal File | SHA256 hash | Detection results, first seen |
| VirusTotal IP | IP address | Reputation, detections |
| AbuseIPDB | IP address | Abuse reports, confidence |
| URLScan | URL | Screenshot, request chain |
| GeoIP | IP address | Country, ISP, ASN |

---

## Quick Reference Card

### Severity Response Matrix

```
┌─────────┬─────────────┬────────────────┬─────────────────┐
│ Level   │ Response    │ Ticket         │ Escalation      │
├─────────┼─────────────┼────────────────┼─────────────────┤
│ 1-4     │ Log only    │ No             │ No              │
│ 5-7     │ 4 hours     │ Low priority   │ No              │
│ 8-10    │ 1 hour      │ Standard       │ If ongoing      │
│ 11-12   │ 15 min      │ High           │ Notify lead     │
│ 13+     │ Immediate   │ Critical       │ Full escalation │
└─────────┴─────────────┴────────────────┴─────────────────┘
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Quick search |
| `Ctrl+S` | Save search |
| `?` | Help panel |

### Useful Links

- [Wazuh Rules Reference](https://documentation.wazuh.com/current/user-manual/ruleset/ruleset-reference.html)
- [MITRE ATT&CK Mapping](https://documentation.wazuh.com/current/user-manual/ruleset/mitre.html)
- [Wazuh API Documentation](https://documentation.wazuh.com/current/api/reference.html)

---

*Last updated: 2026-01-15 | For Wazuh 4.7.x*
