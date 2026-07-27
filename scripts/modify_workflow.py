import json
import sys

# Read the full current workflow from file
with open('workflow-current.json', 'r', encoding='utf-8-sig') as f:
    content = f.read()

# Try to parse it
wf = json.loads(content)

print('Current start:', wf.get('start'))
print('Current actions count:', len(wf.get('actions', [])))
print('Current triggers count:', len(wf.get('triggers', [])))
if wf.get('actions'):
    for a in wf['actions']:
        print(f'  Action: {a["name"]} ({a["label"]}), id={a["id"]}')
if wf.get('triggers'):
    for t in wf['triggers']:
        print(f'  Trigger: {t["name"]} ({t["label"]}), id={t["id"]}')

# Now modify the workflow:
# 1. Fix start field to point to the trigger
# Start should point to the trigger, not an action
# But Shuffle seems to set start to the first action after save
# Let's try with the trigger ID first
wf['start'] = '4ec040d0-2ba5-4135-bf69-050cad1d115b'

# 2. Replace the single "Change Me" action with our new actions
# Parse action (Shuffle Tools execute_python)
parse_action = {
    "app_name": "Shuffle Tools",
    "app_version": "1.2.0",
    "description": "Parses Wazuh alert JSON and extracts title and body for ticket creation",
    "app_id": "bdfea97e-6cb0-42c6-85f2-bd88c06e5a3e",
    "errors": [],
    "id": "88da65c7-08c7-41cc-9f18-a5354534d260",
    "is_valid": True,
    "isStartNode": False,
    "sharing": True,
    "label": "Parse Wazuh Alert",
    "public": True,
    "generated": False,
    "large_image": "",
    "small_image": "",
    "environment": "Shuffle Tools",
    "name": "execute_python",
    "parameters": [
        {
            "description": "",
            "id": "",
            "name": "call",
            "example": "1",
            "value": "1",
            "multiline": False,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": False,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        },
        {
            "description": "The code to run. Can be a file ID from within Shuffle.",
            "id": "",
            "name": "code",
            "example": "print(\"hello world\")",
            "value": """import json

try:
    data = json.loads(execution_data)
except:
    data = execution_data

alert = data if isinstance(data, dict) else {}
if "alert" in alert:
    alert = alert["alert"]

rule_description = alert.get("rule", {}).get("description", "Wazuh Alert")
alert_level = alert.get("rule", {}).get("level", 0)
agent_name = alert.get("agent", {}).get("name", "unknown")
title = f"[Wazuh L{alert_level}] {rule_description} (Agent: {agent_name})"

body_lines = []
body_lines.append(f"Alert Level: {alert_level}")
body_lines.append(f"Rule: {alert.get('rule', {}).get('id', 'N/A')} - {rule_description}")
body_lines.append(f"Agent: {agent_name} ({alert.get('agent', {}).get('id', 'N/A')})")
body_lines.append(f"Timestamp: {alert.get('timestamp', 'N/A')}")

if "full_log" in alert:
    body_lines.append(f"\\nFull Log:\\n{alert['full_log'][:2000]}")

result = {"title": title, "body": "\\n".join(body_lines)}
print(json.dumps(result))""",
            "multiline": True,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": True,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        }
    ],
    "execution_variable": {
        "description": "",
        "id": "",
        "name": "",
        "value": ""
    },
    "position": {
        "x": 450,
        "y": 340
    },
    "authentication_id": "",
    "category": "",
    "reference_url": "",
    "sub_action": False,
    "run_magic_output": False,
    "run_magic_input": False,
    "execution_delay": 0,
    "category_label": None,
    "suggestion": False,
    "parent_controlled": False,
    "source_workflow": "",
    "source_execution": ""
}

# HTTP POST action (create Zammad ticket)
http_action = {
    "app_name": "http",
    "app_version": "1.4.0",
    "description": "Creates a ticket in Zammad via API",
    "app_id": "bd465bba-c3d3-416d-943b-fd9e283e00cd",
    "errors": [],
    "id": "169f3fc4-97eb-487a-be93-1b0cb9cd7c6d",
    "is_valid": True,
    "isStartNode": False,
    "sharing": True,
    "label": "Create Zammad Ticket",
    "public": True,
    "generated": False,
    "large_image": "",
    "small_image": "",
    "environment": "http",
    "name": "POST",
    "parameters": [
        {
            "description": "",
            "id": "",
            "name": "call",
            "example": "2",
            "value": "2",
            "multiline": False,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": False,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        },
        {
            "description": "",
            "id": "",
            "name": "url",
            "example": "",
            "value": "http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080/api/v1/tickets",
            "multiline": False,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": True,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        },
        {
            "description": "",
            "id": "",
            "name": "headers",
            "example": "",
            "value": "Authorization: Token token=Phit7X-yMTQyn8hnTZBwGBzi_rJp5_wefGvrcgLmlgj9mVekK8aRryUPvYPiba7_\nContent-Type: application/json",
            "multiline": True,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": False,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        },
        {
            "description": "",
            "id": "",
            "name": "body",
            "example": "",
            "value": '{"title":"{{parse_wazuh_alert.title}}","group_id":1,"customer_id":2,"article":{"subject":"Wazuh Alert","body":"{{parse_wazuh_alert.body}}"}}',
            "multiline": True,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": False,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        },
        {
            "description": "",
            "id": "",
            "name": "verify",
            "example": "",
            "value": "false",
            "multiline": False,
            "multiselect": False,
            "options": None,
            "action_field": "",
            "variant": "",
            "required": False,
            "configuration": False,
            "tags": None,
            "schema": {"type": ""},
            "skip_multicheck": False,
            "custom_value": False,
            "value_replace": None,
            "unique_toggled": False,
            "error": "",
            "hidden": False
        }
    ],
    "execution_variable": {
        "description": "",
        "id": "",
        "name": "",
        "value": ""
    },
    "position": {
        "x": 700,
        "y": 446
    },
    "authentication_id": "",
    "category": "",
    "reference_url": "",
    "sub_action": False,
    "run_magic_output": False,
    "run_magic_input": False,
    "execution_delay": 0,
    "category_label": None,
    "suggestion": False,
    "parent_controlled": False,
    "source_workflow": "",
    "source_execution": ""
}

wf['actions'] = [parse_action, http_action]

# Make sure trigger isStartNode is True and actions isStartNode is False
for trigger in wf['triggers']:
    if trigger['id'] == '4ec040d0-2ba5-4135-bf69-050cad1d115b':
        trigger['isStartNode'] = True

# Ensure parse action has isStartNode = False
parse_action['isStartNode'] = False
http_action['isStartNode'] = False

# Save the modified workflow
with open('workflow-updated.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, indent=2)

print('\nModified workflow saved to workflow-updated.json')
print('New start:', wf['start'])
print('Actions:', len(wf['actions']))
for a in wf['actions']:
    print(f'  {a["name"]} ({a["label"]}), id={a["id"]}')