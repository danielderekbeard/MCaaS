# Incident Response Runbook

> **Step-by-step procedures for common security incidents in MCaaS**

---

## Table of Contents

1. [Severity Classification](#severity-classification)
2. [Malware Detection Response](#malware-detection-response)
3. [Brute Force Attack Response](#brute-force-attack-response)
4. [Data Exfiltration Response](#data-exfiltration-response)
5. [Lateral Movement Detection](#lateral-movement-detection)
6. [Insider Threat Response](#insider-threat-response)
7. [Ransomware Response](#ransomware-response)
8. [Communication Templates](#communication-templates)

---

## Severity Classification

### Incident Severity Matrix

| Severity | Wazuh Level | Response Time | Notification | Actions |
|----------|-------------|---------------|--------------|---------|
| **Critical** | 13+ | Immediate | Security team + Management | Isolate, preserve evidence, full IR |
| **High** | 10-12 | 15 minutes | Security team lead | Investigate, may isolate |
| **Medium** | 7-9 | 1 hour | Ticket only | Investigate, document |
| **Low** | 5-6 | 4 hours | Ticket only | Review, document |
| **Informational** | 1-4 | Next business day | Log only | None |

### Escalation Matrix

```
Level 1: SOC Analyst
    ↓ (Level 10+)
Level 2: SOC Lead
    ↓ (Level 12+ or confirmed compromise)
Level 3: CISO
    ↓ (Business impact)
Level 4: Executive Team
```

---

## Malware Detection Response

### Detection Triggers

- Wazuh alert: `rule.id:100100` (Malware detected)
- Wazuh FIM: Suspicious file hash match
- Wazuh EDR: Known malicious signature
- User report: Antivirus notification

### Immediate Actions (First 5 Minutes)

**Step 1: Verify Alert**
```bash
# Get alert details from Wazuh
curl -k -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/security/alerts?rule.id=100100&time=1h"
```

**Step 2: Isolate Host via Shuffle**
```bash
# Trigger Shuffle workflow
curl -X POST \
  "http://shuffle-backend.security-ops:3008/api/v1/webhooks/ISOLATION_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "001",
    "action": "isolate",
    "reason": "Malware detection - auto isolate"
  }'
```

**Or manually via Wazuh:**
```bash
# Block all network traffic from host
curl -k -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "firewall-drop",
    "arguments": ["add", "0.0.0.0"]
  }' \
  "https://wazuh-manager.wazuh:55000/active-response?agents_list=001"
```

### Investigation Steps (5-30 Minutes)

**Step 3: Gather Evidence**

```bash
# Get file information
kubectl exec -n wazuh wazuh-manager-master-0 -- \
  /var/ossec/bin/agent_control -i 001

# Check file hashes
# Query syscheck for the file
```

**Step 4: Check Threat Intelligence**

```bash
# VirusTotal lookup (via Shuffle or manual)
curl -X GET \
  "https://www.virustotal.com/api/v3/files/FILE_HASH" \
  -H "x-apikey: YOUR_VT_API_KEY"

# AbuseIPDB (if C2 communication)
curl -X GET \
  "https://api.abuseipdb.com/api/v2/check?ipAddress=C2_IP" \
  -H "Key: YOUR_ABUSEIPDB_KEY"
```

**Step 5: Review Process Tree**

```bash
# Check running processes on affected host
# Query Wazuh for process events
```

### Containment (30-60 Minutes)

**Step 6: Prevent Lateral Movement**

1. **Identify network connections:**
   ```
   Query Wazuh: agent.id:001 AND data.dstip:*
   ```

2. **Block C2 IP at firewall:**
   ```bash
   # Add firewall rule (via your firewall admin)
   # Or use Wazuh active response on all agents
   ```

3. **Disable compromised user:**
   ```bash
   # Via Active Directory or local admin
   # Document in Zammad ticket
   ```

### Recovery (1-4 Hours)

**Step 7: Clean and Restore**

1. **Antivirus full scan**
2. **Remove malware files** (if identified)
3. **Restore from clean backup** (if needed)
4. **Verify system integrity:**
   ```
   - Run SFC /scannow (Windows)
   - Check file hashes vs. baseline
   - Verify no scheduled tasks/backdoors
   ```

5. **Re-enable network** (after verification):
   ```bash
   curl -k -X PUT \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "command": "firewall-drop",
       "arguments": ["delete", "0.0.0.0"]
     }' \
     "https://wazuh-manager.wazuh:55000/active-response?agents_list=001"
   ```

### Documentation

**Step 8: Create Incident Report**

Create Zammad ticket with:
- Timeline of events
- IOCs (file hashes, IPs, domains)
- Actions taken
- Lessons learned
- Link to CISO Assistant for compliance tracking

---

## Brute Force Attack Response

### Detection Triggers

- Wazuh alert: `rule.id:2502` (Multiple authentication failures)
- Wazuh alert: `rule.id:31533` (Web authentication brute force)
- Rate of login failures >10 per minute

### Response Steps

**Step 1: Identify Attack Source**

```bash
# Query Wazuh for source IPs
# Aggregate by data.srcip
```

**Step 2: Block Attacker**

```bash
# Add firewall rule to block source IP
# Or use Wazuh active response

curl -k -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "firewall-drop",
    "arguments": ["add", "ATTACKER_IP"]
  }' \
  "https://wazuh-manager.wazuh:55000/active-response?agents_list=all"
```

**Step 3: Check for Successful Compromise**

```bash
# Query for successful login from attacker IP
# Check if attacker IP had any successful authentication
```

**Step 4: Account Lockout Review**

1. **Check affected accounts:**
   ```bash
   # Query Windows Event ID 4740 (account locked)
   rule.id:2502 AND timestamp:["now-1h" TO "now"]
   ```

2. **Unlock legitimate accounts** (if applicable)

3. **Force password reset** for targeted accounts

**Step 5: Harden Defenses**

- Implement account lockout policy
- Enable MFA if not already
- Consider fail2ban or similar
- Review logs for other attack patterns

---

## Data Exfiltration Response

### Detection Triggers

- Wazuh alert: Large file transfers
- Unusual outbound network traffic
- Access to sensitive files outside normal hours
- USB/removable media usage

### Response Steps

**Step 1: Quantify the Exposure**

```bash
# Identify transferred files
# Query syscheck for recent large file modifications

# Check network connections
# Query for outbound connections to external IPs
```

**Step 2: Preserve Evidence**

```bash
# Create memory dump
# Save process list
# Export Wazuh logs

kubectl exec -n wazuh wazuh-manager-master-0 -- \
  tar czf /tmp/evidence-agent-001.tar.gz \
  /var/ossec/logs/archives/

kubectl cp n wazuh/wazuh-manager-master-0:/tmp/evidence-agent-001.tar.gz \
  ./evidence/
```

**Step 3: Block Ongoing Transfer**

```bash
# Identify destination IP
# Block at firewall
# Isolate source host

curl -k -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "command": "firewall-drop",
    "arguments": ["add", "EXFIL_IP"]
  }' \
  "https://wazuh-manager.wazuh:55000/active-response?agents_list=all"
```

**Step 4: Assess Data Sensitivity**

1. **Identify files accessed:**
   - Query Wazuh FIM logs
   - Review file paths
   - Cross-reference with data classification

2. **Determine classification:**
   - Public: Low impact
   - Internal: Medium impact
   - Confidential: High impact
   - Restricted: Critical impact

**Step 5: Notification**

- **Confidential/Restricted data:** Immediate CISO notification
- **Legal review:** May require breach notification
- **Customer notification:** Per SLA/contracts

---

## Lateral Movement Detection

### Detection Triggers

- Authentication from new source
- Service creation on multiple hosts
- Network connections to internal hosts
- Pass-the-hash indicators

### Response Steps

**Step 1: Map Compromise**

```bash
# Identify all affected hosts
# Query for common indicators across agents

# Check authentication patterns
# Look for same credentials across hosts
```

**Step 2: Contain Spread**

1. **Disable compromised accounts:**
   ```bash
   # Disable in AD
   # Force logoff
   ```

2. **Block C2 communication:**
   ```bash
   # Block C2 IPs
   # Isolate affected hosts
   ```

3. **Segment network** (if needed):
   - Enable additional firewall rules
   - Isolate network segments

**Step 3: Full Investigation**

- Review all hosts with same user login
- Check for persistence mechanisms
- Scan for malware on all potentially affected systems
- Review privileged access

---

## Insider Threat Response

### Detection Triggers

- Access to files outside normal job function
- Bulk download of files
- Off-hours access to sensitive data
- USB/removable media usage
- Failed access attempts to restricted areas

### Response Steps

**Step 1: Verify Threat**

- Check user role and permissions
- Review access patterns over time
- Compare with baseline activity

**Step 2: Discreet Monitoring**

- Do NOT alert the user
- Increase logging (if not already at max)
- Document all activity

**Step 3: Preserve Evidence**

- Export Wazuh logs
- Save file access audit trail
- Capture any artifacts

**Step 4: HR/Legal Coordination**

- Notify HR and Legal (not IT)
- Follow company policy
- Do not confront employee directly

**Step 5: Post-Investigation**

- Revoke access
- Forensic imaging (if needed)
- Recovery from backup (if sabotage)

---

## Ransomware Response

### Detection Triggers

- Mass file modifications (FIM alerts)
- Ransomware note files
- Shadow copy deletion
- Extension changes (.encrypted, .locked, etc.)

### Immediate Response

**Step 1: ISOLATE IMMEDIATELY**

```bash
# Disconnect all affected hosts NOW
# Do not wait for approval

curl -k -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "command": "firewall-drop",
    "arguments": ["add", "0.0.0.0"]
  }' \
  "https://wazuh-manager.wazuh:55000/active-response?agents_list=ID1,ID2,ID3"
```

**Step 2: IDENTIFY SCOPE**

- Which systems are affected?
- Which files are encrypted?
- Is backup available?

**Step 3: DO NOT PAY**

- Do not negotiate with attackers
- Do not pay ransom
- Restore from backup instead

**Step 4: PRESERVE EVIDENCE**

```bash
# Save ransom notes
# Export Wazuh logs
# Memory dump if possible

kubectl exec -n wazuh wazuh-manager-master-0 -- \
  cp /var/ossec/logs/alerts/alerts.json \
  /tmp/ransomware-evidence-$(date +%Y%m%d).json
```

**Step 5: RECOVERY**

1. **Verify backup integrity** (before restore)
2. **Restore from clean backup**
3. **Patch systems** (fix vulnerability)
4. **Verify no persistence** before reconnecting

**Step 6: POST-INCIDENT**

- Full security review
- Implement additional controls
- User training
- Update policies

---

## Communication Templates

### Template 1: Incident Notification (Internal)

```
Subject: [SECURITY] Incident #{TICKET_ID} - {BRIEF_DESCRIPTION}

Priority: {CRITICAL/HIGH/MEDIUM}
Affected Systems: {SYSTEM_LIST}
Time Detected: {TIMESTAMP}

SUMMARY:
{Brief description of incident}

ACTIONS TAKEN:
- {Action 1}
- {Action 2}

NEXT STEPS:
- {Next step}

For more details, see ticket: {ZAMMAD_URL}

SOC Team
```

### Template 2: Management Escalation

```
Subject: [URGENT] Security Incident Requires Attention

To: Security Manager, CISO

Summary:
A {SEVERITY} security incident has been detected affecting {SCOPE}.

Timeline:
- {Time}: Initial detection
- {Time}: Containment initiated
- {Time}: Current status

Business Impact:
- {List potential impacts}

Immediate Actions Required:
- {Approval for isolation}
- {Notification decisions}
- {Resource allocation}

Incident Command:
- Lead: {Analyst name}
- Ticket: {Zammad link}

Recommendations:
- {Suggested actions}
```

### Template 3: User Communication

```
Subject: Security Incident - Action Required

Dear {User},

We have detected suspicious activity on {system/resource}. 

Immediate Actions Required:
1. Change your password immediately
2. Log out of all sessions
3. Enable MFA if not already active

Do not:
- Attempt to investigate yourself
- Contact the suspected attacker
- Delete any files

The security team is investigating. You will receive updates via ticket #{ID}.

Questions? Contact security@mcaas.example.com

SOC Team
```

### Template 4: External Notification (If Required)

```
Subject: Security Incident Notification

To: Affected Customers/Partners

We are writing to inform you of a security incident that may have affected your data.

What Happened:
{Description of incident}

What Information Was Involved:
{Types of data affected}

What We Are Doing:
- {Containment measures}
- {Investigation status}
- {Remediation steps}

What You Can Do:
- {Recommended actions}

We sincerely apologize for any inconvenience this may cause.

Contact Information:
- Email: security@mcaas.example.com
- Phone: {Security hotline}

Sincerely,
{Security Team}
```

---

## Quick Reference

### Emergency Contacts

| Role | Contact | Purpose |
|------|---------|---------|
| SOC Lead | security-lead@mcaas.example.com | Escalation |
| CISO | ciso@mcaas.example.com | High severity |
| Legal | legal@mcaas.example.com | Breach notification |
| PR | pr@mcaas.example.com | External comms |
| IT Operations | ops@mcaas.example.com | Infrastructure |

### Important Commands

```bash
# Get Wazuh token
curl -k -u wazuh-wui:PASSWORD \
  -X POST "https://wazuh-manager.wazuh:55000/security/user/authenticate"

# Isolate host
curl -k -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"command":"firewall-drop","arguments":["add","0.0.0.0"]}' \
  "https://wazuh-manager.wazuh:55000/active-response?agents_list=ID"

# Get agent status
curl -k \
  -H "Authorization: Bearer $TOKEN" \
  "https://wazuh-manager.wazuh:55000/agents/ID"

# Create Zammad ticket
curl -X POST \
  "http://zammad-web.managed-it:80/api/v1/tickets" \
  -H "Authorization: Token token=$TOKEN" \
  -d '{"title":"Incident","group_id":1,"state_id":2}'
```

---

*Last updated: January 2026 | For MCaaS v1.0*
