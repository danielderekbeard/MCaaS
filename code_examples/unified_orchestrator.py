#!/usr/bin/env python3
"""
Unified MCaaS Orchestrator

This module provides unified orchestration across all integrated platforms:
- Shuffle SOAR (workflow automation)
- Zammad (ticketing)
- CISO Assistant (compliance)
- Threat Intelligence (VirusTotal, AbuseIPDB, MISP)

Author: MCaaS Research Agent
Date: 2026-07-27
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

from threat_intel_integration import (
    ThreatIntelOrchestrator, IOCType, EnrichmentResult
)
from zammad_integration import ZammadClient, TicketState
from ciso_assistant_integration import CISOAssistantClient, ComplianceStatus
from shuffle_integration import ShuffleClient, WorkflowResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class MCaaSAlert:
    """Standardized alert structure for MCaaS"""
    alert_id: str
    title: str
    description: str
    severity: str
    source: str
    ioc_type: Optional[str] = None
    ioc_value: Optional[str] = None
    framework: Optional[str] = None
    control_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


@dataclass
class ProcessingResult:
    """Unified processing result"""
    alert_id: str
    success: bool
    ticket_id: Optional[str]
    workflow_execution_id: Optional[str]
    enrichment_data: Optional[Dict]
    compliance_status: Optional[str]
    errors: List[str] = field(default_factory=list)
    processing_time: float = 0.0


class MCaaSOrchestrator:
    """
    Unified orchestrator for MCaaS platform integrations
    
    Coordinates actions across:
    - Threat Intelligence enrichment
    - Compliance validation
    - Ticket creation/management
    - Workflow automation
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize orchestrator with configuration
        
        Config structure:
        {
            "virustotal": {"api_key": "..."},
            "abuseipdb": {"api_key": "..."},
            "misp": {"url": "...", "api_key": "..."},
            "zammad": {"base_url": "...", "api_token": "..."},
            "ciso_assistant": {"base_url": "...", "api_token": "..."},
            "shuffle": {"base_url": "...", "api_key": "..."}
        }
        """
        self.config = config
        
        # Initialize clients
        self.ti_orchestrator = ThreatIntelOrchestrator(
            vt_key=config.get("virustotal", {}).get("api_key"),
            abuseipdb_key=config.get("abuseipdb", {}).get("api_key"),
            misp_url=config.get("misp", {}).get("url"),
            misp_key=config.get("misp", {}).get("api_key")
        )
        
        self.zammad = ZammadClient(
            base_url=config["zammad"]["base_url"],
            api_token=config["zammad"]["api_token"]
        )
        
        self.ciso = CISOAssistantClient(
            base_url=config["ciso_assistant"]["base_url"],
            api_token=config["ciso_assistant"]["api_token"]
        )
        
        self.shuffle = ShuffleClient(
            base_url=config["shuffle"]["base_url"],
            api_key=config["shuffle"]["api_key"]
        )
    
    def process_security_alert(self, alert: MCaaSAlert) -> ProcessingResult:
        """
        Process a security alert through the full MCaaS pipeline
        
        Pipeline:
        1. Enrich IOCs with threat intelligence
        2. Check compliance relevance
        3. Create/Update ticket
        4. Trigger remediation workflows
        5. Update compliance status
        
        Args:
            alert: Security alert to process
            
        Returns:
            ProcessingResult with all actions taken
        """
        import time
        start_time = time.time()
        
        result = ProcessingResult(
            alert_id=alert.alert_id,
            success=True,
            ticket_id=None,
            workflow_execution_id=None,
            enrichment_data=None,
            compliance_status=None
        )
        
        try:
            # Step 1: Threat Intelligence Enrichment
            if alert.ioc_type and alert.ioc_value:
                logger.info(f"Enriching {alert.ioc_type}: {alert.ioc_value}")
                enrichment = self.ti_orchestrator.enrich_ioc(
                    IOCType(alert.ioc_type),
                    alert.ioc_value
                )
                result.enrichment_data = enrichment
                
                # Adjust severity based on TI results
                aggregate = enrichment.get("aggregate", {})
                threat_level = aggregate.get("threat_level", "none")
                
                if threat_level == "critical":
                    alert.severity = AlertSeverity.CRITICAL.value
                elif threat_level == "high":
                    alert.severity = AlertSeverity.HIGH.value
            
            # Step 2: Create Compliance Ticket
            logger.info(f"Creating ticket for alert: {alert.alert_id}")
            
            ticket_priority = self._map_severity_to_priority(alert.severity)
            
            ticket = self.zammad.create_ticket(
                title=f"[Security Alert] {alert.title}",
                customer_email="security@company.com",
                priority_id=ticket_priority,
                article_body=self._format_alert_description(alert, enrichment),
                article_subject=f"Alert {alert.alert_id} - {alert.severity.upper()}"
            )
            
            result.ticket_id = str(ticket.get("id"))
            
            # Add tags
            self.zammad.add_tag(result.ticket_id, "security-alert")
            self.zammad.add_tag(result.ticket_id, alert.severity)
            
            if alert.framework:
                self.zammad.add_tag(result.ticket_id, alert.framework)
            
            if alert.control_id:
                self.zammad.add_tag(result.ticket_id, f"control-{alert.control_id}")
            
            # Step 3: Check Compliance Relevance
            if alert.framework and alert.control_id:
                logger.info(f"Checking compliance: {alert.framework} {alert.control_id}")
                
                # Map severity to control status
                if alert.severity in [AlertSeverity.CRITICAL.value, AlertSeverity.HIGH.value]:
                    control_status = ComplianceStatus.NON_COMPLIANT
                elif alert.severity == AlertSeverity.MEDIUM.value:
                    control_status = ComplianceStatus.PARTIALLY_COMPLIANT
                else:
                    control_status = ComplianceStatus.COMPLIANT
                
                # Update control status
                self.ciso.update_control_status(
                    control_id=alert.control_id,
                    status=control_status,
                    evidence=f"Security alert {alert.alert_id}: {alert.title}"
                )
                
                result.compliance_status = control_status.value
            
            # Step 4: Execute Remediation Workflows
            if alert.severity in [AlertSeverity.CRITICAL.value, AlertSeverity.HIGH.value]:
                logger.info(f"Triggering remediation workflow for {alert.alert_id}")
                
                try:
                    wf_result = self.shuffle.execute_incident_response(
                        alert_id=alert.alert_id,
                        alert_data={
                            "title": alert.title,
                            "severity": alert.severity,
                            "ioc": {
                                "type": alert.ioc_type,
                                "value": alert.ioc_value
                            },
                            "ticket_id": result.ticket_id
                        },
                        playbook="default"
                    )
                    
                    result.workflow_execution_id = wf_result.execution_id
                    
                    # Add workflow results to ticket
                    self.zammad.add_article(
                        ticket_id=result.ticket_id,
                        body=f"Workflow executed: {wf_result.status}",
                        article_type="note",
                        internal=True
                    )
                    
                except Exception as e:
                    logger.error(f"Workflow execution failed: {e}")
                    result.errors.append(f"Workflow error: {str(e)}")
            
            # Step 5: Send Notifications for Critical Alerts
            if alert.severity == AlertSeverity.CRITICAL.value:
                try:
                    self.shuffle.execute_notification_workflow(
                        channels=["slack", "email"],
                        message=f"🚨 CRITICAL SECURITY ALERT: {alert.title} - Ticket {result.ticket_id}",
                        priority="critical"
                    )
                except Exception as e:
                    logger.error(f"Notification failed: {e}")
            
        except Exception as e:
            logger.error(f"Error processing alert {alert.alert_id}: {e}")
            result.success = False
            result.errors.append(str(e))
        
        result.processing_time = time.time() - start_time
        return result
    
    def process_compliance_findings(self, framework: str,
                                     control_id: str,
                                     finding: str,
                                     severity: str = "medium") -> ProcessingResult:
        """
        Process compliance findings and create remediation workflow
        
        Args:
            framework: Compliance framework
            control_id: Control identifier
            finding: Finding description
            severity: Finding severity
        """
        import time
        start_time = time.time()
        
        alert = MCaaSAlert(
            alert_id=f"COMP-{framework}-{control_id}-{int(time.time())}",
            title=f"Compliance Finding: {framework} {control_id}",
            description=finding,
            severity=severity,
            source="ciso_assistant",
            framework=framework,
            control_id=control_id
        )
        
        return self.process_security_alert(alert)
    
    def validate_control_evidence(self, framework: str,
                                  control_id: str,
                                  evidence_paths: List[str]) -> Dict:
        """
        Validate control evidence across all platforms
        
        Args:
            framework: Compliance framework
            control_id: Control ID
            evidence_paths: List of evidence file paths
        """
        results = {
            "framework": framework,
            "control_id": control_id,
            "validations": []
        }
        
        # Validate in CISO Assistant
        try:
            ciso_result = self.ciso.validate_control_implementation(
                framework_id=framework.lower(),
                control_id=control_id,
                evidence_paths=evidence_paths
            )
            results["validations"].append({
                "platform": "ciso_assistant",
                "status": "success",
                "evidence_uploaded": len(ciso_result["evidence_uploaded"])
            })
        except Exception as e:
            results["validations"].append({
                "platform": "ciso_assistant",
                "status": "error",
                "error": str(e)
            })
        
        # Create/update ticket with evidence
        try:
            tickets = self.zammad.search_tickets(
                f"tag:{framework} tag:control-{control_id}"
            )
            
            if tickets:
                ticket_id = tickets[0]["id"]
                
                # Add evidence to existing ticket
                for path in evidence_paths:
                    self.zammad.add_evidence(
                        ticket_id=ticket_id,
                        evidence_description=f"Evidence for {control_id}",
                        evidence_file_path=path
                    )
                
                results["validations"].append({
                    "platform": "zammad",
                    "status": "success",
                    "ticket_id": ticket_id,
                    "evidence_added": len(evidence_paths)
                })
            else:
                results["validations"].append({
                    "platform": "zammad",
                    "status": "no_ticket",
                    "message": "No existing ticket found"
                })
                
        except Exception as e:
            results["validations"].append({
                "platform": "zammad",
                "status": "error",
                "error": str(e)
            })
        
        return results
    
    def generate_compliance_dashboard(self, framework: Optional[str] = None) -> Dict:
        """
        Generate unified compliance dashboard
        
        Args:
            framework: Optional framework filter
            
        Returns:
            Dashboard data from all platforms
        """
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "framework": framework,
            "sources": {}
        }
        
        # Get CISO Assistant data
        try:
            if framework:
                summary = self.ciso.generate_compliance_summary(framework.lower())
                dashboard["sources"]["ciso_assistant"] = summary
        except Exception as e:
            dashboard["sources"]["ciso_assistant"] = {"error": str(e)}
        
        # Get Zammad ticket data
        try:
            if framework:
                tickets = self.zammad.get_compliance_tickets(framework)
            else:
                tickets = self.zammad.get_compliance_tickets()
            
            dashboard["sources"]["zammad"] = {
                "total_tickets": len(tickets),
                "by_priority": self._aggregate_by_priority(tickets),
                "by_state": self._aggregate_by_state(tickets)
            }
        except Exception as e:
            dashboard["sources"]["zammad"] = {"error": str(e)}
        
        # Get threat intel summary
        try:
            dashboard["sources"]["threat_intel"] = {
                "status": "active",
                "sources": list(self.ti_orchestrator.clients.keys())
            }
        except Exception as e:
            dashboard["sources"]["threat_intel"] = {"error": str(e)}
        
        return dashboard
    
    def _map_severity_to_priority(self, severity: str) -> int:
        """Map alert severity to Zammad priority"""
        mapping = {
            AlertSeverity.CRITICAL.value: 3,  # high
            AlertSeverity.HIGH.value: 3,
            AlertSeverity.MEDIUM.value: 2,    # normal
            AlertSeverity.LOW.value: 1,       # low
            AlertSeverity.INFO.value: 1
        }
        return mapping.get(severity, 2)
    
    def _format_alert_description(self, alert: MCaaSAlert, 
                                   enrichment: Optional[Dict]) -> str:
        """Format alert description for ticket"""
        html = f"""
        <h3>{alert.title}</h3>
        
        <p><b>Alert ID:</b> {alert.alert_id}</p>
        <p><b>Severity:</b> {alert.severity.upper()}</p>
        <p><b>Source:</b> {alert.source}</p>
        """
        
        if alert.ioc_type and alert.ioc_value:
            html += f"""
            <p><b>IOC:</b> {alert.ioc_type} - {alert.ioc_value}</p>
            """
        
        html += f"""
        <h4>Description</h4>
        <p>{alert.description}</p>
        """
        
        if enrichment:
            aggregate = enrichment.get("aggregate", {})
            html += f"""
            <h4>Threat Intelligence</h4>
            <ul>
                <li>Threat Level: {aggregate.get('threat_level', 'unknown')}</li>
                <li>Confidence: {aggregate.get('confidence_score', 0)}%</li>
                <li>Sources Consulted: {', '.join(aggregate.get('sources_consulted', []))}</li>
            </ul>
            """
        
        if alert.framework:
            html += f"""
            <h4>Compliance Context</h4>
            <ul>
                <li>Framework: {alert.framework}</li>
                <li>Control: {alert.control_id}</li>
            </ul>
            """
        
        return html
    
    def _aggregate_by_priority(self, tickets: List[Dict]) -> Dict:
        """Aggregate tickets by priority"""
        counts = {}
        for t in tickets:
            priority = t.get("priority", "unknown")
            counts[priority] = counts.get(priority, 0) + 1
        return counts
    
    def _aggregate_by_state(self, tickets: List[Dict]) -> Dict:
        """Aggregate tickets by state"""
        counts = {}
        for t in tickets:
            state = t.get("state", "unknown")
            counts[state] = counts.get(state, 0) + 1
        return counts


# ============== EXAMPLE USAGE ==============

def example_configuration():
    """Example configuration structure"""
    return {
        "virustotal": {
            "api_key": os.getenv("VIRUSTOTAL_API_KEY", "your_vt_key")
        },
        "abuseipdb": {
            "api_key": os.getenv("ABUSEIPDB_API_KEY", "your_abuseipdb_key")
        },
        "misp": {
            "url": os.getenv("MISP_URL", "https://misp.yourdomain.com"),
            "api_key": os.getenv("MISP_API_KEY", "your_misp_key")
        },
        "zammad": {
            "base_url": os.getenv("ZAMMAD_URL", "https://tickets.yourdomain.com"),
            "api_token": os.getenv("ZAMMAD_TOKEN", "your_zammad_token")
        },
        "ciso_assistant": {
            "base_url": os.getenv("CISO_URL", "https://ciso.yourdomain.com"),
            "api_token": os.getenv("CISO_TOKEN", "your_ciso_token")
        },
        "shuffle": {
            "base_url": os.getenv("SHUFFLE_URL", "https://shuffle.yourdomain.com"),
            "api_key": os.getenv("SHUFFLE_KEY", "your_shuffle_key")
        }
    }


def example_usage():
    """Example usage of the unified orchestrator"""
    
    config = example_configuration()
    orchestrator = MCaaSOrchestrator(config)
    
    # Example 1: Process security alert with IOC
    alert = MCaaSAlert(
        alert_id="ALT-2026-001",
        title="Suspicious IP Connection Detected",
        description="Connection to known malicious IP detected by firewall",
        severity="high",
        source="firewall",
        ioc_type="ip",
        ioc_value="192.168.1.100",  # Example IP
        framework="ISO27001",
        control_id="A.12.6.1"
    )
    
    result = orchestrator.process_security_alert(alert)
    
    print(f"Processing Result:")
    print(f"  Success: {result.success}")
    print(f"  Ticket ID: {result.ticket_id}")
    print(f"  Workflow: {result.workflow_execution_id}")
    print(f"  Compliance: {result.compliance_status}")
    print(f"  Processing Time: {result.processing_time:.2f}s")
    
    if result.errors:
        print(f"  Errors: {result.errors}")
    
    # Example 2: Process compliance finding
    result2 = orchestrator.process_compliance_findings(
        framework="ISO27001",
        control_id="A.18.1.2",
        finding="Intellectual property rights not properly documented",
        severity="medium"
    )
    
    print(f"\nCompliance Finding Result:")
    print(f"  Ticket ID: {result2.ticket_id}")
    
    # Example 3: Generate dashboard
    dashboard = orchestrator.generate_compliance_dashboard("ISO27001")
    print(f"\nDashboard Data:")
    print(json.dumps(dashboard, indent=2))


if __name__ == "__main__":
    # example_usage()
    pass
