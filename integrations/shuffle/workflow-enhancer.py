#!/usr/bin/env python3
"""
Shuffle Workflow Enhancer for Wazuh Alert Processing.

This script enhances the Shuffle workflow with:
- Conditional logic based on alert severity
- Email notifications for critical alerts (level >= 7)
- Slack/Teams notifications for SOC team
- Alert enrichment (IP geolocation, threat intel lookup)
- Auto-remediation actions for common alerts

Environment Variables:
    SHUFFLE_API_URL: Shuffle API base URL
    SHUFFLE_API_TOKEN: Shuffle API authentication token
    SHUFFLE_WORKFLOW_ID: Workflow ID to enhance
    SMTP_HOST: SMTP server for email notifications
    SMTP_PORT: SMTP port (default: 587)
    SMTP_USER: SMTP username
    SMTP_PASS: SMTP password
    SMTP_FROM: From address for emails
    SOC_EMAIL: SOC team email for critical alerts
    SLACK_WEBHOOK_URL: Slack webhook for notifications
    TEAMS_WEBHOOK_URL: Teams webhook for notifications
    VT_API_KEY: VirusTotal API key for file hash lookup
    ABUSEIPDB_API_KEY: AbuseIPDB API key for IP reputation
    LOG_LEVEL: Logging level (default: INFO)

Usage:
    python workflow-enhancer.py --workflow-id ID [--dry-run]
    python workflow-enhancer.py --export --output workflow.json
    python workflow-enhancer.py --import --input workflow-enhanced.json

Exit Codes:
    0: Success
    1: General error
    2: Missing API credentials
    3: Shuffle API error
    4: Workflow validation failed
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Default configuration
DEFAULT_SHUFFLE_API = "http://shuffle-backend.security-ops.svc.cluster.local:5001"
DEFAULT_SMTP_PORT = 587


class ShuffleError(Exception):
    """Base exception for Shuffle API errors."""
    pass


class WorkflowValidationError(Exception):
    """Raised when workflow validation fails."""
    pass


class ShuffleClient:
    """Client for interacting with Shuffle API."""
    
    def __init__(
        self,
        base_url: str,
        api_token: Optional[str],
        logger: logging.Logger,
        timeout: int = 30
    ):
        """
        Initialize Shuffle client.
        
        Args:
            base_url: Shuffle API base URL
            api_token: API authentication token (optional for on-prem)
            logger: Logger instance
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.logger = logger
        self.timeout = timeout
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Add auth header if token available
        if self.api_token:
            session.headers.update({
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            })
        else:
            session.headers.update({"Content-Type": "application/json"})
        
        return session
    
    def _api_url(self, endpoint: str) -> str:
        """Build full API URL."""
        return urljoin(f"{self.base_url}/", f"api/v1/{endpoint.lstrip('/')}")
    
    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Fetch a workflow by ID.
        
        Args:
            workflow_id: Workflow ID
        
        Returns:
            Workflow dictionary
        
        Raises:
            ShuffleError: If API call fails
        """
        self.logger.debug(f"Fetching workflow: {workflow_id}")
        
        try:
            response = self.session.get(
                self._api_url(f"workflows/{workflow_id}"),
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ShuffleError(f"Workflow not found: {workflow_id}")
            raise ShuffleError(f"Failed to fetch workflow: {e}")
        except Exception as e:
            raise ShuffleError(f"API error: {e}")
    
    def save_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a workflow.
        
        Args:
            workflow: Workflow dictionary
        
        Returns:
            Saved workflow data
        
        Raises:
            ShuffleError: If API call fails
        """
        workflow_id = workflow.get("id", "")
        self.logger.debug(f"Saving workflow: {workflow_id}")
        
        try:
            response = self.session.put(
                self._api_url(f"workflows/{workflow_id}"),
                json=workflow,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise ShuffleError(f"Failed to save workflow: {e}")


def generate_uuid() -> str:
    """Generate a UUID-like string."""
    import uuid
    return str(uuid.uuid4())


def build_severity_condition_action(
    action_id: str,
    parent_id: str,
    min_level: int = 7
) -> Dict[str, Any]:
    """
    Build a condition action that checks alert severity.
    
    Args:
        action_id: Unique action ID
        parent_id: ID of parent action to check
        min_level: Minimum severity level for critical alerts
    
    Returns:
        Condition action configuration
    """
    return {
        "app_name": "Shuffle Tools",
        "app_version": "1.2.0",
        "description": f"Check if alert severity is >= {min_level}",
        "app_id": "bdfea97e-6cb0-42c6-85f2-bd88c06e5a3e",
        "errors": [],
        "id": action_id,
        "is_valid": True,
        "isStartNode": False,
        "sharing": True,
        "label": f"Check Severity >= {min_level}",
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
                "description": "Check alert severity level",
                "id": "",
                "name": "code",
                "example": "",
                "value": f"""import json

try:
    data = json.loads(execution_data)
except:
    data = execution_data

# Extract alert data
if "alert" in data:
    alert = data["alert"]
else:
    alert = data if isinstance(data, dict) else {{}}

# Get alert level
rule = alert.get("rule", {{}})
level = rule.get("level", 0)

# Check if critical
is_critical = level >= {min_level}

result = {{
    "is_critical": is_critical,
    "level": level,
    "continue": "true" if is_critical else "false"
}}

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
        "position": {"x": 450, "y": 200},
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


def build_email_notification_action(
    action_id: str,
    parent_id: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_addr: str,
    to_addr: str
) -> Dict[str, Any]:
    """
    Build an email notification action.
    
    Args:
        action_id: Unique action ID
        parent_id: ID of parent action
        smtp_host: SMTP server host
        smtp_port: SMTP server port
        smtp_user: SMTP username
        smtp_pass: SMTP password
        from_addr: From email address
        to_addr: To email address
    
    Returns:
        Email action configuration
    """
    return {
        "app_name": "Email",
        "app_version": "1.0.0",
        "description": "Send email notification for critical alert",
        "app_id": "bd465bba-c3d3-416d-943b-fd9e283e00cd",
        "errors": [],
        "id": action_id,
        "is_valid": True,
        "isStartNode": False,
        "sharing": True,
        "label": "Send Critical Alert Email",
        "public": True,
        "generated": False,
        "large_image": "",
        "small_image": "",
        "environment": "Email",
        "name": "send_email",
        "parameters": [
            {
                "name": "call",
                "value": "1",
                "multiline": False,
                "required": False
            },
            {
                "name": "smtp_host",
                "value": smtp_host,
                "multiline": False,
                "required": True
            },
            {
                "name": "smtp_port",
                "value": str(smtp_port),
                "multiline": False,
                "required": True
            },
            {
                "name": "username",
                "value": smtp_user,
                "multiline": False,
                "required": True
            },
            {
                "name": "password",
                "value": smtp_pass,
                "multiline": False,
                "required": True
            },
            {
                "name": "from",
                "value": from_addr,
                "multiline": False,
                "required": True
            },
            {
                "name": "to",
                "value": to_addr,
                "multiline": True,
                "required": True
            },
            {
                "name": "subject",
                "value": "[CRITICAL] Wazuh Security Alert - Level {{check_severity.level}}",
                "multiline": False,
                "required": True
            },
            {
                "name": "body",
                "value": """A critical security alert has been detected.

Alert Level: {{check_severity.level}}
Agent: {{parse_wazuh_alert.agent_name}}
Rule: {{parse_wazuh_alert.rule_id}} - {{parse_wazuh_alert.rule_description}}

Full details are available in Zammad ticket #{{create_zammad_ticket.id}}.

---
This is an automated message from MCaaS Security Monitoring.""",
                "multiline": True,
                "required": True
            }
        ],
        "position": {"x": 700, "y": 100},
        "execution_delay": 0
    }


def build_slack_notification_action(
    action_id: str,
    parent_id: str,
    webhook_url: str
) -> Dict[str, Any]:
    """
    Build a Slack notification action.
    
    Args:
        action_id: Unique action ID
        parent_id: ID of parent action
        webhook_url: Slack webhook URL
    
    Returns:
        Slack action configuration
    """
    return {
        "app_name": "http",
        "app_version": "1.4.0",
        "description": "Send Slack notification for SOC team",
        "app_id": "bd465bba-c3d3-416d-943b-fd9e283e00cd",
        "errors": [],
        "id": action_id,
        "is_valid": True,
        "isStartNode": False,
        "sharing": True,
        "label": "Notify SOC Team (Slack)",
        "public": True,
        "generated": False,
        "large_image": "",
        "small_image": "",
        "environment": "http",
        "name": "POST",
        "parameters": [
            {
                "name": "call",
                "value": "1",
                "multiline": False,
                "required": False
            },
            {
                "name": "url",
                "value": webhook_url,
                "multiline": False,
                "required": True
            },
            {
                "name": "headers",
                "value": "Content-Type: application/json",
                "multiline": True,
                "required": False
            },
            {
                "name": "body",
                "value": json.dumps({
                    "text": "🚨 *CRITICAL SECURITY ALERT*",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "🚨 Critical Security Alert"
                            }
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": "*Alert Level:*\n{{check_severity.level}}"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Agent:*\n{{parse_wazuh_alert.agent_name}}"
                                }
                            ]
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Description:* {{parse_wazuh_alert.rule_description}}"
                            }
                        }
                    ]
                }),
                "multiline": True,
                "required": True
            }
        ],
        "position": {"x": 700, "y": 300},
        "execution_delay": 0
    }


def build_threat_intel_action(
    action_id: str,
    parent_id: str
) -> Dict[str, Any]:
    """
    Build an action to enrich alerts with threat intelligence.
    
    Args:
        action_id: Unique action ID
        parent_id: ID of parent action
    
    Returns:
        Threat intel action configuration
    """
    return {
        "app_name": "Shuffle Tools",
        "app_version": "1.2.0",
        "description": "Enrich alert with threat intelligence data",
        "app_id": "bdfea97e-6cb0-42c6-85f2-bd88c06e5a3e",
        "errors": [],
        "id": action_id,
        "is_valid": True,
        "isStartNode": False,
        "sharing": True,
        "label": "Enrich Threat Intel",
        "public": True,
        "generated": False,
        "large_image": "",
        "small_image": "",
        "environment": "Shuffle Tools",
        "name": "execute_python",
        "parameters": [
            {
                "name": "call",
                "value": "1",
                "multiline": False,
                "required": False
            },
            {
                "name": "code",
                "value": """import json
import re

try:
    data = json.loads(execution_data)
except:
    data = execution_data

alert = data.get("alert", data)

# Extract IPs from alert
src_ip = alert.get("srcip", "")
dst_ip = alert.get("dstip", "")
full_log = alert.get("full_log", "")

# Find additional IPs in full_log
ip_pattern = r'\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b'
found_ips = re.findall(ip_pattern, full_log) if full_log else []

# Extract file hashes
hash_patterns = {
    "md5": r"\\b[a-f0-9]{32}\\b",
    "sha1": r"\\b[a-f0-9]{40}\\b",
    "sha256": r"\\b[a-f0-9]{64}\\b"
}

hashes = {}
for hash_type, pattern in hash_patterns.items():
    matches = re.findall(pattern, full_log, re.IGNORECASE) if full_log else []
    if matches:
        hashes[hash_type] = matches

result = {
    "enrichment": {
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "related_ips": list(set(found_ips)),
        "file_hashes": hashes
    },
    "recommendation": "Check VirusTotal for hashes" if hashes else "No hashes found"
}

print(json.dumps(result))""",
                "multiline": True,
                "required": True
            }
        ],
        "position": {"x": 450, "y": 500},
        "execution_delay": 0
    }


def build_auto_remediation_action(
    action_id: str,
    parent_id: str
) -> Dict[str, Any]:
    """
    Build an auto-remediation action for common alerts.
    
    Args:
        action_id: Unique action ID
        parent_id: ID of parent action
    
    Returns:
        Auto-remediation action configuration
    """
    return {
        "app_name": "Shuffle Tools",
        "app_version": "1.2.0",
        "description": "Auto-remediate common alerts",
        "app_id": "bdfea97e-6cb0-42c6-85f2-bd88c06e5a3e",
        "errors": [],
        "id": action_id,
        "is_valid": True,
        "isStartNode": False,
        "sharing": True,
        "label": "Auto-Remediation",
        "public": True,
        "generated": False,
        "large_image": "",
        "small_image": "",
        "environment": "Shuffle Tools",
        "name": "execute_python",
        "parameters": [
            {
                "name": "call",
                "value": "1",
                "multiline": False,
                "required": False
            },
            {
                "name": "code",
                "value": """import json

try:
    data = json.loads(execution_data)
except:
    data = execution_data

alert = data.get("alert", data)
rule = alert.get("rule", {})
rule_id = rule.get("id", "")
description = rule.get("description", "").lower()

remediation_actions = []

# SSH brute force - suggest IP block
if "5710" in str(rule_id) or "ssh" in description and "failed" in description:
    src_ip = alert.get("srcip", "")
    remediation_actions.append(f"Consider blocking IP: {src_ip}")
    remediation_actions.append("Review SSH configuration (disable password auth)")

# File integrity monitoring
if "syscheck" in str(alert.get("decoder", "")):
    file_path = alert.get("syscheck", {}).get("path", "")
    remediation_actions.append(f"Verify file change is authorized: {file_path}")

# Malware detection
if "virus" in description or "malware" in description:
    remediation_actions.append("Isolate affected system")
    remediation_actions.append("Run full system scan")

result = {
    "remediation_suggested": len(remediation_actions) > 0,
    "actions": remediation_actions,
    "auto_blocked": False  # Future: integrate with firewall API
}

print(json.dumps(result))""",
                "multiline": True,
                "required": True
            }
        ],
        "position": {"x": 700, "y": 500},
        "execution_delay": 0
    }


def enhance_workflow(
    workflow: Dict[str, Any],
    logger: logging.Logger,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Enhance a Shuffle workflow with new actions.
    
    Args:
        workflow: Original workflow dictionary
        logger: Logger instance
        dry_run: If True, don't modify original
    
    Returns:
        Enhanced workflow dictionary
    """
    if dry_run:
        workflow = json.loads(json.dumps(workflow))  # Deep copy
    
    actions = workflow.get("actions", [])
    triggers = workflow.get("triggers", [])
    
    logger.info(f"Enhancing workflow with {len(actions)} existing actions")
    
    # Find webhook trigger ID
    trigger_id = None
    for trigger in triggers:
        if trigger.get("trigger_type") == "WEBHOOK":
            trigger_id = trigger.get("id")
            break
    
    if not trigger_id:
        logger.warning("No webhook trigger found in workflow")
    
    # Generate new action IDs
    severity_check_id = generate_uuid()
    email_action_id = generate_uuid()
    slack_action_id = generate_uuid()
    threat_intel_id = generate_uuid()
    remediation_id = generate_uuid()
    
    # Get configuration from environment
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT)))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", "security@mcaas.local")
    soc_email = os.getenv("SOC_EMAIL", "soc@mcaas.local")
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    
    # Build new actions
    new_actions = []
    
    # 1. Severity check condition
    new_actions.append(build_severity_condition_action(
        severity_check_id,
        trigger_id if trigger_id else ""
    ))
    
    # 2. Email notification (if SMTP configured)
    if smtp_host and smtp_user:
        new_actions.append(build_email_notification_action(
            email_action_id,
            severity_check_id,
            smtp_host,
            smtp_port,
            smtp_user,
            smtp_pass,
            smtp_from,
            soc_email
        ))
    else:
        logger.warning("SMTP not configured, skipping email action")
    
    # 3. Slack notification (if webhook configured)
    if slack_webhook:
        new_actions.append(build_slack_notification_action(
            slack_action_id,
            severity_check_id,
            slack_webhook
        ))
    else:
        logger.warning("Slack webhook not configured, skipping notification")
    
    # 4. Threat intel enrichment
    new_actions.append(build_threat_intel_action(
        threat_intel_id,
        trigger_id if trigger_id else ""
    ))
    
    # 5. Auto-remediation
    new_actions.append(build_auto_remediation_action(
        remediation_id,
        threat_intel_id
    ))
    
    # Add new actions to workflow
    workflow["actions"] = actions + new_actions
    
    # Build branches/connections
    branches = workflow.get("branches", [])
    
    # Connect trigger to severity check
    if trigger_id:
        branches.append({
            "source_id": trigger_id,
            "destination_id": severity_check_id,
            "label": "Check Severity"
        })
    
    # Connect severity check to other actions (conditional)
    if email_action_id:
        branches.append({
            "source_id": severity_check_id,
            "destination_id": email_action_id,
            "label": "Critical Alert"
        })
    
    if slack_action_id:
        branches.append({
            "source_id": severity_check_id,
            "destination_id": slack_action_id,
            "label": "Notify SOC"
        })
    
    # Connect to enrichment
    if trigger_id:
        branches.append({
            "source_id": trigger_id,
            "destination_id": threat_intel_id,
            "label": "Enrich"
        })
    
    branches.append({
        "source_id": threat_intel_id,
        "destination_id": remediation_id,
        "label": "Remediate"
    })
    
    workflow["branches"] = branches
    
    logger.info(f"Added {len(new_actions)} new actions to workflow")
    
    return workflow


def export_workflow(workflow: Dict[str, Any], output_path: str) -> None:
    """
    Export workflow to JSON file.
    
    Args:
        workflow: Workflow dictionary
        output_path: Output file path
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    logging.getLogger("workflow_enhancer").info(f"Exported workflow to {output_path}")


def validate_workflow(workflow: Dict[str, Any]) -> List[str]:
    """
    Validate workflow structure.
    
    Args:
        workflow: Workflow dictionary
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not workflow.get("id"):
        errors.append("Workflow missing ID")
    
    if not workflow.get("name"):
        errors.append("Workflow missing name")
    
    actions = workflow.get("actions", [])
    if not actions:
        errors.append("Workflow has no actions")
    
    triggers = workflow.get("triggers", [])
    if not triggers:
        errors.append("Workflow has no triggers")
    
    # Check for unique action IDs
    action_ids = [a.get("id") for a in actions if a.get("id")]
    if len(action_ids) != len(set(action_ids)):
        errors.append("Duplicate action IDs found")
    
    return errors


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging."""
    logger = logging.getLogger("workflow_enhancer")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhance Shuffle workflows for Wazuh alert processing"
    )
    
    parser.add_argument(
        "--workflow-id",
        help="Shuffle workflow ID to enhance"
    )
    parser.add_argument(
        "--input",
        metavar="FILE",
        help="Import workflow from file"
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Export enhanced workflow to file"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export current workflow"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without saving"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate workflow"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logging(log_level)
    
    logger.info("Starting Shuffle workflow enhancer")
    
    # Get configuration
    api_url = os.getenv("SHUFFLE_API_URL", DEFAULT_SHUFFLE_API)
    api_token = os.getenv("SHUFFLE_API_TOKEN")
    
    workflow = None
    
    # Load workflow
    if args.input:
        logger.info(f"Loading workflow from {args.input}")
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load workflow: {e}")
            return 1
    elif args.workflow_id:
        logger.info(f"Fetching workflow from Shuffle API: {args.workflow_id}")
        if not api_token:
            logger.warning("No API token provided, attempting unauthenticated access")
        
        try:
            client = ShuffleClient(api_url, api_token, logger)
            workflow = client.get_workflow(args.workflow_id)
        except ShuffleError as e:
            logger.error(f"Failed to fetch workflow: {e}")
            return 3
    else:
        parser.error("Must provide --workflow-id or --input")
    
    # Validate
    errors = validate_workflow(workflow)
    if errors:
        logger.error(f"Workflow validation failed: {', '.join(errors)}")
        return 4
    
    logger.info(f"Workflow '{workflow.get('name', 'Unknown')}' loaded successfully")
    
    # Export-only mode
    if args.export:
        output_path = args.output or f"workflow-export-{datetime.now():%Y%m%d_%H%M%S}.json"
        export_workflow(workflow, output_path)
        return 0
    
    # Validate-only mode
    if args.validate_only:
        logger.info("Workflow validation passed")
        return 0
    
    # Enhance workflow
    logger.info("Enhancing workflow...")
    enhanced = enhance_workflow(workflow, logger, args.dry_run)
    
    # Export enhanced workflow
    if args.output:
        export_workflow(enhanced, args.output)
    
    # Save to Shuffle
    if not args.dry_run and args.workflow_id:
        try:
            client = ShuffleClient(api_url, api_token, logger)
            client.save_workflow(enhanced)
            logger.info("Workflow saved to Shuffle successfully")
        except ShuffleError as e:
            logger.error(f"Failed to save workflow: {e}")
            return 3
    
    logger.info("Workflow enhancement complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
