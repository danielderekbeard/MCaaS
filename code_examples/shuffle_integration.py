#!/usr/bin/env python3
"""
Shuffle SOAR Integration for MCaaS Platform

This module provides integration with Shuffle workflows
for security orchestration and automated compliance actions.

Author: MCaaS Research Agent
Date: 2026-07-27

Docs: https://shuffler.io/docs
"""

import os
import json
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """Shuffle workflow execution statuses"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowResult:
    """Shuffle workflow execution result"""
    execution_id: str
    status: str
    start_time: str
    end_time: Optional[str]
    results: Dict[str, Any]
    error: Optional[str]


class ShuffleClient:
    """
    Shuffle SOAR API Client
    
    Shuffle is an open-source SOAR platform for workflow automation.
    This client supports:
    - Triggering workflows via webhooks
    - Checking execution status
    - Retrieving results
    - Managing workflow configurations
    """
    
    def __init__(self, base_url: str, api_key: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Shuffle client
        
        Args:
            base_url: Shuffle instance URL
            api_key: API key for authentication
            username: Username for basic auth
            password: Password for basic auth
        """
        self.base_url = base_url.rstrip('/')
        self.session = self._create_session()
        
        # Set up authentication
        if api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            })
        elif username and password:
            # Get auth token
            self._authenticate(username, password)
        else:
            raise ValueError("Must provide api_key or username/password")
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def _authenticate(self, username: str, password: str):
        """Authenticate and get token"""
        auth_url = f"{self.base_url}/api/v1/login"
        response = self.session.post(auth_url, json={
            "username": username,
            "password": password
        })
        response.raise_for_status()
        
        token = response.json().get("token")
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make API request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            if response.status_code == 204 or not response.content:
                return {}
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Shuffle API error: {e}")
            raise
    
    # ============== WORKFLOW OPERATIONS ==============
    
    def list_workflows(self, limit: int = 50) -> List[Dict]:
        """List available workflows"""
        params = {"limit": limit}
        return self._request("GET", "/workflows", params=params)
    
    def get_workflow(self, workflow_id: str) -> Dict:
        """Get workflow details"""
        return self._request("GET", f"/workflows/{workflow_id}")
    
    def get_workflow_by_name(self, name: str) -> Optional[Dict]:
        """Find workflow by name"""
        workflows = self.list_workflows()
        for wf in workflows:
            if wf.get("name") == name:
                return wf
        return None
    
    # ============== WEBHOOK OPERATIONS ==============
    
    def trigger_webhook(self, webhook_url: str, data: Dict) -> Dict:
        """
        Trigger a workflow via webhook URL
        
        Args:
            webhook_url: Full webhook URL
            data: Data to send to webhook
        """
        response = self.session.post(
            webhook_url,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def trigger_workflow(self, workflow_id: str, 
                        execution_argument: str = "",
                        start_node: str = "",
                        parameters: Optional[Dict] = None) -> Dict:
        """
        Execute a workflow
        
        Args:
            workflow_id: Workflow ID
            execution_argument: Starting argument
            start_node: Starting node ID
            parameters: Additional parameters
        """
        data = {
            "execution_argument": execution_argument,
            "start": start_node
        }
        
        if parameters:
            data.update(parameters)
        
        return self._request("POST", f"/workflows/{workflow_id}/execute", json=data)
    
    # ============== EXECUTION OPERATIONS ==============
    
    def get_execution(self, execution_id: str) -> Dict:
        """Get execution details and results"""
        return self._request("GET", f"/ executions/{execution_id}")
    
    def get_execution_results(self, execution_id: str) -> Dict:
        """Get execution results"""
        return self._request("GET", f"/ executions/{execution_id}/results")
    
    def list_executions(self, workflow_id: Optional[str] = None,
                       status: Optional[str] = None,
                       limit: int = 50) -> List[Dict]:
        """List workflow executions"""
        params = {"limit": limit}
        if workflow_id:
            params["workflow_id"] = workflow_id
        if status:
            params["status"] = status
        
        return self._request("GET", "/ executions", params=params)
    
    def wait_for_execution(self, execution_id: str, 
                          timeout: int = 300,
                          poll_interval: int = 5) -> WorkflowResult:
        """
        Wait for workflow execution to complete
        
        Args:
            execution_id: Execution ID
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between polls
            
        Returns:
            WorkflowResult with execution details
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            execution = self.get_execution(execution_id)
            status = execution.get("status", "pending")
            
            if status in ["completed", "failed", "cancelled"]:
                results = self.get_execution_results(execution_id)
                
                return WorkflowResult(
                    execution_id=execution_id,
                    status=status,
                    start_time=execution.get("start_time", ""),
                    end_time=execution.get("end_time"),
                    results=results,
                    error=execution.get("error")
                )
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Execution {execution_id} did not complete within {timeout}s")
    
    # ============== MCaaS SPECIFIC METHODS ==============
    
    def execute_compliance_workflow(self, workflow_name: str,
                                     framework: str,
                                     control_id: str,
                                     severity: str = "medium",
                                     metadata: Optional[Dict] = None) -> WorkflowResult:
        """
        Execute a compliance-specific workflow
        
        Args:
            workflow_name: Name of workflow to execute
            framework: Compliance framework
            control_id: Control ID
            severity: Alert severity
            metadata: Additional metadata
            
        Returns:
            WorkflowResult with execution results
        """
        # Find workflow by name
        workflow = self.get_workflow_by_name(workflow_name)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_name}' not found")
        
        workflow_id = workflow.get("id")
        
        # Prepare execution arguments
        execution_data = {
            "action": "compliance_check",
            "framework": framework,
            "control_id": control_id,
            "severity": severity,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metadata": metadata or {}
        }
        
        # Trigger workflow
        result = self.trigger_workflow(
            workflow_id=workflow_id,
            execution_argument=json.dumps(execution_data)
        )
        
        execution_id = result.get("execution_id")
        
        # Wait for completion
        return self.wait_for_execution(execution_id)
    
    def execute_enrichment_workflow(self, ioc_type: str,
                                   ioc_value: str,
                                   ticket_id: Optional[str] = None) -> WorkflowResult:
        """
        Execute threat enrichment workflow
        
        Args:
            ioc_type: Type of IOC (ip, domain, hash, etc.)
            ioc_value: IOC value
            ticket_id: Optional ticket ID to update
        """
        workflow = self.get_workflow_by_name("Threat Enrichment")
        if not workflow:
            raise ValueError("Threat enrichment workflow not found")
        
        data = {
            "action": "enrich_ioc",
            "ioc_type": ioc_type,
            "ioc_value": ioc_value,
            "ticket_id": ticket_id
        }
        
        result = self.trigger_workflow(
            workflow_id=workflow.get("id"),
            execution_argument=json.dumps(data)
        )
        
        return self.wait_for_execution(result.get("execution_id"))
    
    def execute_incident_response(self, alert_id: str,
                                   alert_data: Dict,
                                   playbook: str = "default") -> WorkflowResult:
        """
        Execute incident response workflow
        
        Args:
            alert_id: Alert identifier
            alert_data: Alert data
            playbook: Response playbook name
        """
        workflow = self.get_workflow_by_name(f"IR Playbook - {playbook}")
        if not workflow:
            workflow = self.get_workflow_by_name("Incident Response")
        
        if not workflow:
            raise ValueError(f"Incident response workflow not found")
        
        data = {
            "action": "incident_response",
            "alert_id": alert_id,
            "playbook": playbook,
            "alert_data": alert_data
        }
        
        result = self.trigger_workflow(
            workflow_id=workflow.get("id"),
            execution_argument=json.dumps(data)
        )
        
        return self.wait_for_execution(result.get("execution_id"))
    
    def execute_notification_workflow(self, channels: List[str],
                                     message: str,
                                     priority: str = "normal") -> WorkflowResult:
        """
        Execute notification workflow
        
        Args:
            channels: List of channels (email, slack, teams)
            message: Message content
            priority: Message priority
        """
        workflow = self.get_workflow_by_name("Send Notifications")
        if not workflow:
            raise ValueError("Notification workflow not found")
        
        data = {
            "action": "notify",
            "channels": channels,
            "message": message,
            "priority": priority
        }
        
        result = self.trigger_workflow(
            workflow_id=workflow.get("id"),
            execution_argument=json.dumps(data)
        )
        
        return self.wait_for_execution(result.get("execution_id"))
    
    def execute_evidence_collection(self, control_id: str,
                                    evidence_types: List[str]) -> WorkflowResult:
        """
        Execute evidence collection workflow
        
        Args:
            control_id: Control requiring evidence
            evidence_types: Types of evidence to collect
        """
        workflow = self.get_workflow_by_name("Evidence Collection")
        if not workflow:
            raise ValueError("Evidence collection workflow not found")
        
        data = {
            "action": "collect_evidence",
            "control_id": control_id,
            "evidence_types": evidence_types
        }
        
        result = self.trigger_workflow(
            workflow_id=workflow.get("id"),
            execution_argument=json.dumps(data)
        )
        
        return self.wait_for_execution(result.get("execution_id"))
    
    # ============== WORKFLOW BUILDER METHODS ==============
    
    def create_compliance_workflow_template(self, name: str,
                                             description: str = "") -> Dict:
        """
        Create a workflow template for compliance checks
        
        This creates a basic workflow structure that can be customized
        with Shuffle's visual workflow builder.
        """
        template = {
            "name": name,
            "description": description or f"Compliance workflow: {name}",
            "tags": ["compliance", "mcaaas"],
            "actions": [
                {
                    "id": "trigger",
                    "name": "Webhook Trigger",
                    "type": "trigger",
                    "parameters": {
                        "webhook": True
                    }
                },
                {
                    "id": "parse_input",
                    "name": "Parse Input",
                    "type": "shuffle_tools",
                    "parameters": {
                        "action": "parse_json"
                    },
                    "depends_on": ["trigger"]
                },
                {
                    "id": "check_framework",
                    "name": "Check Framework",
                    "type": "condition",
                    "parameters": {
                        "conditions": [
                            {
                                "field": "framework",
                                "operator": "equals",
                                "value": "ISO27001"
                            }
                        ]
                    },
                    "depends_on": ["parse_input"]
                },
                {
                    "id": "create_ticket",
                    "name": "Create Compliance Ticket",
                    "type": "zammad",
                    "parameters": {
                        "action": "create_ticket"
                    },
                    "depends_on": ["check_framework"]
                },
                {
                    "id": "notify_team",
                    "name": "Notify Security Team",
                    "type": "email",
                    "parameters": {
                        "to": "security@company.com"
                    },
                    "depends_on": ["create_ticket"]
                }
            ]
        }
        
        return self._request("POST", "/workflows", json=template)


# ============== WEBHOOK HANDLER ==============

class ShuffleWebhookHandler:
    """
    Handler for incoming Shuffle webhook calls
    
    Use this to process Shuffle workflow results
    back in your MCaaS application.
    """
    
    def __init__(self, secret_token: Optional[str] = None):
        self.secret_token = secret_token
        self.handlers: Dict[str, Callable] = {}
    
    def register_handler(self, action: str, handler: Callable):
        """Register handler for specific action type"""
        self.handlers[action] = handler
    
    def handle_webhook(self, request_data: Dict, 
                       signature: Optional[str] = None) -> Dict:
        """
        Process incoming webhook
        
        Args:
            request_data: Webhook payload
            signature: Optional signature for verification
            
        Returns:
            Response data
        """
        # Verify signature if configured
        if self.secret_token and signature:
            if not self._verify_signature(request_data, signature):
                raise ValueError("Invalid webhook signature")
        
        # Extract action and data
        action = request_data.get("action")
        data = request_data.get("data", {})
        
        # Call appropriate handler
        handler = self.handlers.get(action)
        if handler:
            try:
                result = handler(data)
                return {
                    "status": "success",
                    "action": action,
                    "result": result
                }
            except Exception as e:
                logger.error(f"Handler error for {action}: {e}")
                return {
                    "status": "error",
                    "action": action,
                    "error": str(e)
                }
        
        return {
            "status": "no_handler",
            "action": action
        }
    
    def _verify_signature(self, data: Dict, signature: str) -> bool:
        """Verify webhook signature"""
        import hmac
        import hashlib
        
        payload = json.dumps(data, sort_keys=True)
        expected = hmac.new(
            self.secret_token.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)


# ============== EXAMPLE USAGE ==============

def example_usage():
    """Example of using the Shuffle client"""
    
    # Initialize client
    client = ShuffleClient(
        base_url="https://shuffle.yourdomain.com",
        api_key="your_api_key"
    )
    
    # Example 1: List workflows
    print("Available Workflows:")
    workflows = client.list_workflows()
    for wf in workflows:
        print(f"  - {wf.get('name')} (ID: {wf.get('id')})")
    
    # Example 2: Execute compliance workflow
    try:
        result = client.execute_compliance_workflow(
            workflow_name="ISO 27001 Compliance Check",
            framework="ISO27001",
            control_id="A.12.3.1",
            severity="high",
            metadata={"assessment_id": "Q3-2026"}
        )
        
        print(f"Workflow completed: {result.status}")
        print(f"Results: {json.dumps(result.results, indent=2)}")
        
    except Exception as e:
        print(f"Workflow failed: {e}")
    
    # Example 3: Execute enrichment workflow
    result = client.execute_enrichment_workflow(
        ioc_type="ip",
        ioc_value="8.8.8.8",
        ticket_id="12345"
    )
    
    print(f"Enrichment status: {result.status}")
    
    # Example 4: Execute notification
    result = client.execute_notification_workflow(
        channels=["slack", "email"],
        message="Compliance assessment completed for ISO 27001",
        priority="normal"
    )


def example_webhook_handler():
    """Example webhook handler setup"""
    
    handler = ShuffleWebhookHandler(secret_token="your_webhook_secret")
    
    # Register handlers
    def handle_compliance_result(data):
        print(f"Compliance check result: {data}")
        # Update MCaaS database, send notifications, etc.
        return {"processed": True}
    
    def handle_evidence_result(data):
        print(f"Evidence collected: {data}")
        # Store evidence references
        return {"stored": True}
    
    handler.register_handler("compliance_result", handle_compliance_result)
    handler.register_handler("evidence_result", handle_evidence_result)
    
    # In your webhook endpoint:
    # result = handler.handle_webhook(request.json)


if __name__ == "__main__":
    # example_usage()
    pass
