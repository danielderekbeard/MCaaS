# Wazuh → Shuffle SOAR Integration

## Overview

Wazuh SIEM sends security alerts to Shuffle SOAR for automated incident response workflow execution.

## Integration Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Wazuh Manager  │────▶│  Shuffle Webhook  │────▶│  Shuffle Workflow│
│  (alerts level  │     │  /api/v1/hooks/   │     │  (automated     │
│   >= 3)         │     │  webhook_*        │     │   response)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
      Namespace: wazuh         Namespace: security-ops
```

## Configuration

### Wazuh Side (ConfigMap: `wazuh-conf-2t66md6694`)

```xml
<integration>
  <name>slack</name>
  <hook_url>http://shuffle-backend.security-ops.svc.cluster.local:5001/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b</hook_url>
  <level>3</level>
  <alert_format>json</alert_format>
</integration>
```

**Key Settings:**
- **Name**: `slack` (Wazuh uses this as the integration type - webhook-based)
- **Hook URL**: Shuffle webhook endpoint
- **Level**: `3` (sends alerts with severity >= 3)
- **Format**: JSON

### Shuffle Side

- **Webhook ID**: `4ec040d0-2ba5-4135-bf69-050cad1d115b`
- **Workflow ID**: `8d264034-0040-48c6-86f2-aeb5294df90a`
- **Endpoint**: `shuffle-backend.security-ops.svc.cluster.local:5001`

## Verification

### Test Webhook Connectivity

```bash
kubectl run test-webhook --rm -i --restart=Never --image=curlimages/curl \
  -- curl -s http://shuffle-backend.security-ops.svc.cluster.local:5001/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b \
  -X POST -H "Content-Type: application/json" -d '{"test":"alert"}'
```

**Expected Response:**
```json
{"success": true, "execution_id": "..."}
```

### Check Recent Executions

```bash
kubectl logs -n security-ops deployment/shuffle-backend --tail 50 | grep webhook
```

**Expected Output:**
```
[INFO] Running webhook for workflow 8d264034-0040-48c6-86f2-aeb5294df90a
[INFO][...] Execution: should execute onprem with execution environment "Shuffle"
[INFO][...] Set workflowexecution... Status: FINISHED
```

## Alert Flow

1. **Wazuh detects security event** (e.g., failed login, malware detection, file integrity change)
2. **Alert severity checked** - Only levels >= 3 trigger the integration
3. **Wazuh sends JSON payload** to Shuffle webhook URL
4. **Shuffle triggers workflow** execution with the alert data
5. **Workflow executes** automated response actions

## Alert Payload Format

Wazuh sends alerts in JSON format:

```json
{
  "timestamp": "2026-07-27T00:37:34.123Z",
  "rule": {
    "id": "5710",
    "level": 5,
    "description": "sshd: Attempt to login using a non-existent user"
  },
  "agent": {
    "id": "001",
    "name": "web-server",
    "ip": "10.0.0.5"
  },
  "srcip": "192.168.1.100",
  "location": "/var/log/auth.log",
  "full_log": "Failed password for invalid user test from 192.168.1.100 port 12345 ssh2"
}
```

## Troubleshooting

### Integration Not Working

1. **Check Wazuh ConfigMap**:
   ```bash
   kubectl get configmap wazuh-conf-2t66md6694 -n wazuh -o jsonpath="{.data.master.conf}" | grep -A5 "Shuffle SOAR"
   ```

2. **Restart Wazuh Manager** (after ConfigMap changes):
   ```bash
   kubectl rollout restart statefulset/wazuh-manager-master -n wazuh
   ```

3. **Check Shuffle Backend Logs**:
   ```bash
   kubectl logs -n security-ops deployment/shuffle-backend --tail 100 | grep -i webhook
   ```

4. **Test Webhook Manually**:
   ```bash
   kubectl run test-webhook --rm -i --restart=Never --image=curlimages/curl \
     -- curl -s http://shuffle-backend.security-ops.svc.cluster.local:5001/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b \
     -X POST -H "Content-Type: application/json" \
     -d '{"rule":{"description":"Test Alert","level":5},"timestamp":"2026-01-01T00:00:00Z"}'
   ```

### No Alerts Being Sent

- Check alert level threshold (currently set to 3)
- Verify alerts are being generated: `kubectl exec -n wazuh wazuh-manager-master-0 -- cat /var/ossec/logs/alerts/alerts.json | tail -20`
- Check Wazuh manager logs: `kubectl logs -n wazuh statefulset/wazuh-manager-master -c wazuh-manager`

## Enhancement Ideas

1. **Custom Integration Name**: Change from `<name>slack</name>` to `<name>custom-shuffle</name>` for semantic clarity
2. **Add API Key Authentication**: If Shuffle webhook requires auth
3. **Filter by Rule Groups**: Add `<group>` filters to only send specific alert types
4. **Multiple Shuffle Workflows**: Configure different webhooks for different alert severities

## Files

- `patch-wazuh-configmap.py` - Script to add/update Shuffle integration
- Workflow stored in Shuffle database (ID: `8d264034-0040-48c6-86f2-aeb5294df90a`)

## References

- [Wazuh Integrations Documentation](https://documentation.wazuh.com/current/user-manual/manager/alert-management/integrations.html)
- [Shuffle Webhooks Documentation](https://shuffler.io/docs/webhooks)
- ConfigMap: `wazuh-conf-2t66md6694` in `wazuh` namespace
