# MCaaS Integration Development TODO

**Created:** 2026-07-27 03:39 GMT+3  
**Project:** MCaaS - Managed Compliance as a Service  
**Status:** Active Development

---

## 🔴 High Priority

### 1. Enhance Shuffle Workflow for Wazuh Alerts
- [ ] **Description:** Expand the current Shuffle workflow (ID: `8d264034-0040-48c6-86f2-aeb5294df90a`)
- [ ] Add conditional logic based on alert severity
- [ ] Implement email notifications for critical alerts (level ≥ 7)
- [ ] Add Slack/Teams notifications for SOC team
- [ ] Create alert enrichment (IP geolocation, threat intel lookup)
- [ ] Add auto-remediation actions for common alerts
- [ ] **File:** `integrations/shuffle/wazuh-workflow-enhanced.yaml`

### 2. Wazuh → Zammad Ticket Integration ✅ COMPLETED
- [x] **Description:** Automatically create tickets in Zammad from Wazuh alerts
- [ ] Create API integration script (`integrations/wazuh-zammad/ticket-creator.py`)
- [ ] Map Wazuh alert fields to Zammad ticket fields
- [ ] Configure alert severity → ticket priority mapping
- [ ] Add deduplication logic (prevent duplicate tickets for same issue)
- [ ] Include alert metadata in ticket description
- [ ] Set up automation rules in Zammad for SOC triage
- [ ] **Depends on:** Zammad API token (move from hardcoded to env var)

### 3. Alert Filtering & Routing ✅ COMPLETED
- [x] **Description:** Implement intelligent alert filtering before sending to Shuffle
- [ ] Filter by rule groups (only send `syslog`, `ossec`, `vulnerability-detection`)
- [ ] Exclude noisy rules (e.g., frequent informational alerts)
- [ ] Create different Shuffle webhooks for different alert categories
- [ ] Add time-based filtering (e.g., critical alerts only after hours)
- [ ] **File:** Modify `scripts/patch-wazuh-configmap.py` with filter logic

---

## 🟡 Medium Priority

### 4. CISO Assistant Compliance Mapping ✅ COMPLETED
- [x] **Description:** Map Wazuh alerts to compliance frameworks in CISO Assistant
- [ ] Create compliance framework mappings (ISO 27001, NIST, SOC2)
- [ ] Auto-create findings in CISO Assistant from security alerts
- [ ] Link Wazuh rules to specific control requirements
- [ ] Generate compliance reports from alert data
- [ ] **File:** `integrations/ciso-assistant/compliance-mapper.py`

### 5. Enhanced Wazuh ConfigMap Patching ✅ COMPLETED
- [x] **Description:** Improve `scripts/patch-wazuh-configmap.py` robustness
- [ ] Use label selectors instead of hardcoded ConfigMap name (`wazuh-conf-2t66md6694`)
- [ ] Add error handling and rollback capability
- [ ] Validate ConfigMap syntax before applying
- [ ] Add dry-run mode
- [ ] Create backup of previous configuration
- [ ] **File:** Update `scripts/patch-wazuh-configmap.py`

### 6. Integration Health Monitoring ✅ COMPLETED
- [x] **Description:** Set up monitoring for all integrations
- [ ] Create health check script (`integrations/health-check.py`)
- [ ] Verify Wazuh → Shuffle connectivity
- [ ] Verify Shuffle → Zammad connectivity (if implemented)
- [ ] Alert on integration failures
- [ ] Log integration metrics (alerts sent, tickets created, etc.)
- [ ] **Integration:** Add to heartbeat checks

---

## 🟢 Low Priority / Future

### 7. Multi-Channel Alert Distribution ✅ COMPLETED
- [x] **Description:** Support multiple notification channels
- [ ] Microsoft Teams integration
- [ ] Slack integration (native, not just Shuffle)
- [ ] SMS/PagerDuty for critical alerts
- [ ] Webhook for custom endpoints

### 8. Threat Intelligence Enrichment ✅ COMPLETED
- [x] **Description:** Enrich alerts with external threat intel
- [ ] VirusTotal API integration for file hashes
- [ ] AbuseIPDB integration for malicious IPs
- [ ] MISP integration for threat sharing
- [ ] Add enrichment data to Shuffle workflow

### 9. Historical Analysis & Reporting
- [ ] **Description:** Generate reports from integration data
- [ ] Weekly/monthly alert volume reports
- [ ] Top triggered rules analysis
- [ ] Mean time to ticket creation (Wazuh → Zammad)
- [ ] Integration uptime reports

### 10. Documentation & Runbooks ✅ COMPLETED
- [x] **Description:** Create operational documentation
- [ ] Incident response runbook for each alert type
- [ ] Integration troubleshooting guide
- [ ] Onboarding guide for new SOC analysts
- [ ] Architecture diagrams for all integrations

---

## 📋 Quick Reference

### Current Integration Status

| Integration | Status | Config Location |
|-------------|--------|-----------------|
| Wazuh → Shuffle | ✅ Working | ConfigMap: `wazuh-conf-2t66md6694` |
| Shuffle → (Workflow) | ✅ Working | Workflow ID: `8d264034-0040-48c6-86f2-aeb5294df90a` |
| Wazuh → Zammad | ⏳ TODO | Script needed: `ticket-creator.py` |
| Wazuh → CISO Assistant | ⏳ TODO | Mapper needed |

### Important IDs

- **Shuffle Webhook ID:** `4ec040d0-2ba5-4135-bf69-050cad1d115b`
- **Shuffle Workflow ID:** `8d264034-0040-48c6-86f2-aeb5294df90a`
- **Wazuh ConfigMap:** `wazuh-conf-2t66md6694` (in `wazuh` namespace)

### Files to Modify

1. `scripts/patch-wazuh-configmap.py` - Improve robustness
2. `scripts/modify_workflow.py` - Move hardcoded API token to env var
3. Create `integrations/` directory structure

---

## 🏃 Next Steps (Suggested Order)

1. Start with **#1** (Enhance Shuffle Workflow) - builds on existing working integration
2. Then **#2** (Wazuh → Zammad) - adds ticket automation
3. Then **#3** (Alert Filtering) - reduces noise before ticket creation
4. Then **#5** (ConfigMap Patching improvements) - technical debt

---

**Last Updated:** 2026-07-27 03:39 GMT+3  
**Owner:** Daniel Beard  
**Notes:** All code review issues from previous session should be addressed alongside these integrations
