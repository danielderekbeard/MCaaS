$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }

$parseActionId = "88da65c7-08c7-41cc-9f18-a5354534d260"
$httpActionId = "169f3fc4-97eb-487a-be93-1b0cb9cd7c6d"
$triggerId = "4ec040d0-2ba5-4135-bf69-050cad1d115b"
$workflowId = "8d264034-0040-48c6-86f2-aeb5294df90a"

# Python code for parsing Wazuh alert - will be injected as escaped string
$pythonCode = @"
import json

# Parse the incoming webhook data
try:
    data = json.loads(execution_data)
except:
    data = execution_data

# Extract alert information from Wazuh webhook format
alert = data if isinstance(data, dict) else {}
# Wazuh alerts come nested under different keys
if 'alert' in alert:
    alert = alert['alert']

# Build ticket title
rule_description = alert.get('rule', {}).get('description', 'Wazuh Alert')
alert_level = alert.get('rule', {}).get('level', 0)
agent_name = alert.get('agent', {}).get('name', 'unknown')
title = f"[Wazuh L{alert_level}] {rule_description} (Agent: {agent_name})"

# Build ticket body
body_lines = []
body_lines.append(f"Alert Level: {alert_level}")
body_lines.append(f"Rule: {alert.get('rule', {}).get('id', 'N/A')} - {rule_description}")
body_lines.append(f"Agent: {agent_name} ({alert.get('agent', {}).get('id', 'N/A')})")
body_lines.append(f"Timestamp: {alert.get('timestamp', 'N/A')}")

if 'full_log' in alert:
    body_lines.append(f"\nFull Log:\n{alert['full_log'][:2000]}")

# Return structured result for the next action
result = {
    "title": title,
    "body": "\n".join(body_lines)
}
print(json.dumps(result))
"@

# Escape for JSON embedding
$pythonCodeEscaped = $pythonCode -replace '\\', '\\\\' -replace '"', '\\"' -replace "`n", '\\n' -replace "`r", '' -replace "`t", '\\t'

# Build the workflow body
$body = @{
    id = $workflowId
    name = "Wazuh Alert Handler"
    description = "Receives Wazuh alerts via webhook, parses them, and creates Zammad tickets"
    owner = "23e49a8d-34b4-4dfb-b839-25196fc9a027"
    org = "2dab79be-d87a-43dd-99ad-232a3d7161fc"
    sharing = "private"
    status = "test"
    start = $triggerId
    is_valid = $true
    previously_saved = $true
    configuration = @{
        exit_on_error = $false
        start_from_top = $false
        skip_notifications = $false
    }
    triggers = @(
        @{
            id = $triggerId
            app_name = "Webhook"
            app_version = "1.0.0"
            trigger_type = "WEBHOOK"
            label = "Webhook Trigger"
            description = "Receives Wazuh alerts via webhook"
            status = "running"
            position = @{ x = 250; y = 446 }
            parameters = @(
                @{
                    name = "url"
                    value = "http://kydoimos.mcaas.example.com/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b"
                }
                @{
                    name = "tmp"
                    value = "webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b"
                }
            )
        }
    )
    actions = @(
        @{
            id = $parseActionId
            app_name = "Shuffle Tools"
            app_version = "1.2.0"
            app_id = "bdfea97e-6cb0-42c6-85f2-bd88c06e5a3e"
            label = "Parse Wazuh Alert"
            name = "execute_python"
            description = "Parses Wazuh alert JSON and extracts title and body for ticket creation"
            position = @{ x = 450; y = 340 }
            parameters = @(
                @{
                    name = "call"
                    value = "1"
                    is_secret = $false
                }
                @{
                    name = "code"
                    value = $pythonCode
                    is_secret = $false
                }
            )
            execution_variable = @()
            environment = "Shuffle Tools"
            errors = @()
            conditions = @()
        }
        @{
            id = $httpActionId
            app_name = "http"
            app_version = "1.4.0"
            app_id = "bd465bba-c3d3-416d-943b-fd9e283e00cd"
            label = "Create Zammad Ticket"
            name = "POST"
            description = "Creates a ticket in Zammad via API"
            position = @{ x = 700; y = 446 }
            parameters = @(
                @{
                    name = "call"
                    value = "2"
                    is_secret = $false
                }
                @{
                    name = "url"
                    value = "http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080/api/v1/tickets"
                    is_secret = $false
                }
                @{
                    name = "headers"
                    value = "Authorization: Token token=Phit7X-yMTQyn8hnTZBwGBzi_rJp5_wefGvrcgLmlgj9mVekK8aRryUPvYPiba7_`nContent-Type: application/json"
                    is_secret = $false
                }
                @{
                    name = "body"
                    value = '{"title":"{{parse_wazuh_alert.title}}","group_id":1,"customer_id":2,"article":{"subject":"Wazuh Alert","body":"{{parse_wazuh_alert.body}}"}}'
                    is_secret = $false
                }
                @{
                    name = "verify"
                    value = "false"
                    is_secret = $false
                }
            )
            execution_variable = @()
            environment = "http"
            errors = @()
            conditions = @()
        }
    )
    branches = @()
    visual_branches = @()
    comments = @()
    workflow_variables = $null
    categories = @{
        siem = @()
        communication = @()
        assets = @()
        cases = @()
        network = @()
        intel = @()
        edr = @()
        iam = @()
        ai = @()
        email = @()
        other = @()
    }
}

# Send the PUT request
$bodyJson = $body | ConvertTo-Json -Depth 15
Write-Host "Sending workflow update..."
Write-Host "Body length: $($bodyJson.Length)"

try {
    $response = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method PUT -Headers $headers -Body $bodyJson
    Write-Host "SUCCESS! Workflow updated."
    Write-Host "Response:"
    $response | ConvertTo-Json -Depth 5 | Write-Host
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    Write-Host "Status: $($_.Exception.Response.StatusCode)"
    $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
    Write-Host "Response body: $($reader.ReadToEnd())"
}