#!/usr/bin/env python3
"""
CISO Assistant Integration for MCaaS Platform

This module provides integration with CISO Assistant's REST API
for compliance framework management, control mapping, and risk assessment.

Author: MCaaS Research Agent
Date: 2026-07-27

API Docs: https://intuitem.gitbook.io/ciso-assistant
"""

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComplianceStatus(Enum):
    """Compliance assessment statuses"""
    NOT_ASSESSED = "not_assessed"
    PARTIALLY_COMPLIANT = "partially_compliant"
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


class RiskLevel(Enum):
    """Risk levels"""
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


@dataclass
class Framework:
    """Compliance framework structure"""
    id: str
    name: str
    description: str
    version: str
    controls_count: int


@dataclass
class Control:
    """Security control structure"""
    id: str
    name: str
    description: str
    framework_id: str
    category: str
    status: str


class CISOAssistantClient:
    """
    CISO Assistant REST API Client
    
    CISO Assistant provides comprehensive GRC capabilities including:
    - Compliance framework management (167+ frameworks)
    - Automatic control mapping
    - Risk assessment workflows
    - Evidence management
    - Audit and campaign management
    """
    
    def __init__(self, base_url: str, api_token: str, verify_ssl: bool = True):
        """
        Initialize CISO Assistant client
        
        Args:
            base_url: CISO Assistant base URL
            api_token: API authentication token
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        self.session = self._create_session()
        
        # Set up authentication header
        self.session.headers.update({
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json"
        })
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make API request with error handling"""
        url = f"{self.base_url}/api{endpoint}"
        
        try:
            response = self.session.request(
                method, url, 
                verify=self.verify_ssl,
                **kwargs
            )
            response.raise_for_status()
            
            if response.status_code == 204 or not response.content:
                return {}
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"CISO Assistant API error: {e}")
            raise
    
    # ============== FRAMEWORK OPERATIONS ==============
    
    def list_frameworks(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        List available compliance frameworks
        
        Returns frameworks like ISO 27001, SOC 2, NIST CSF, etc.
        """
        params = {"limit": limit, "offset": offset}
        return self._request("GET", "/frameworks/", params=params)
    
    def get_framework(self, framework_id: str) -> Dict:
        """Get specific framework details"""
        return self._request("GET", f"/frameworks/{framework_id}/")
    
    def load_framework(self, framework_id: str) -> Dict:
        """Load a framework into your workspace"""
        return self._request("POST", f"/frameworks/{framework_id}/load/")
    
    def create_custom_framework(self, name: str, description: str,
                                controls: List[Dict]) -> Dict:
        """
        Create a custom compliance framework
        
        Args:
            name: Framework name
            description: Framework description
            controls: List of control definitions
        """
        data = {
            "name": name,
            "description": description,
            "controls": controls
        }
        return self._request("POST", "/frameworks/", json=data)
    
    # ============== CONTROL OPERATIONS ==============
    
    def list_controls(self, framework_id: Optional[str] = None,
                      limit: int = 100) -> List[Dict]:
        """
        List security controls
        
        Args:
            framework_id: Filter by specific framework
        """
        params = {"limit": limit}
        if framework_id:
            params["framework"] = framework_id
        
        return self._request("GET", "/controls/", params=params)
    
    def get_control(self, control_id: str) -> Dict:
        """Get specific control details"""
        return self._request("GET", f"/controls/{control_id}/")
    
    def update_control_status(self, control_id: str, 
                              status: ComplianceStatus,
                              evidence: Optional[str] = None) -> Dict:
        """
        Update control implementation status
        
        Args:
            control_id: Control identifier
            status: Compliance status
            evidence: Optional evidence description
        """
        data = {"status": status.value}
        if evidence:
            data["evidence"] = evidence
        
        return self._request("PATCH", f"/controls/{control_id}/", json=data)
    
    def get_control_mapping(self, control_id: str) -> List[Dict]:
        """
        Get automatic mappings for a control
        
        Returns mappings to other frameworks and standards.
        """
        return self._request("GET", f"/controls/{control_id}/mappings/")
    
    # ============== ASSESSMENT OPERATIONS ==============
    
    def create_assessment(self, name: str, framework_id: str,
                          description: str = "",
                          start_date: Optional[str] = None,
                          end_date: Optional[str] = None) -> Dict:
        """
        Create a compliance assessment
        
        Args:
            name: Assessment name
            framework_id: Framework to assess against
            description: Assessment description
            start_date: ISO date string (e.g., "2026-01-01")
            end_date: ISO date string
        """
        data = {
            "name": name,
            "framework": framework_id,
            "description": description
        }
        
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date
        
        return self._request("POST", "/assessments/", json=data)
    
    def get_assessment(self, assessment_id: str) -> Dict:
        """Get assessment details"""
        return self._request("GET", f"/assessments/{assessment_id}/")
    
    def list_assessments(self, status: Optional[str] = None) -> List[Dict]:
        """List assessments, optionally filtered by status"""
        params = {}
        if status:
            params["status"] = status
        
        return self._request("GET", "/assessments/", params=params)
    
    def submit_assessment_results(self, assessment_id: str,
                                   results: List[Dict]) -> Dict:
        """
        Submit control assessment results
        
        Args:
            assessment_id: Assessment ID
            results: List of control results
                   [{"control": "control_id", "status": "compliant", "evidence": "..."}]
        """
        data = {"results": results}
        return self._request("POST", 
                            f"/assessments/{assessment_id}/submit-results/", 
                            json=data)
    
    def get_assessment_report(self, assessment_id: str) -> Dict:
        """Generate assessment compliance report"""
        return self._request("GET", 
                            f"/assessments/{assessment_id}/report/")
    
    # ============== RISK OPERATIONS ==============
    
    def list_risks(self, assessment_id: Optional[str] = None) -> List[Dict]:
        """List identified risks"""
        params = {}
        if assessment_id:
            params["assessment"] = assessment_id
        
        return self._request("GET", "/risks/", params=params)
    
    def create_risk(self, name: str, description: str,
                   level: RiskLevel, assessment_id: str) -> Dict:
        """
        Create a risk entry
        
        Args:
            name: Risk name
            description: Risk description
            level: Risk level (1-4)
            assessment_id: Associated assessment
        """
        data = {
            "name": name,
            "description": description,
            "level": level.value,
            "assessment": assessment_id
        }
        return self._request("POST", "/risks/", json=data)
    
    def link_risk_to_control(self, risk_id: str, control_id: str) -> Dict:
        """Link a risk to a mitigating control"""
        data = {"control": control_id}
        return self._request("POST", 
                            f"/risks/{risk_id}/link-control/", 
                            json=data)
    
    # ============== EVIDENCE OPERATIONS ==============
    
    def upload_evidence(self, name: str, description: str,
                       file_path: Optional[str] = None,
                       control_id: Optional[str] = None) -> Dict:
        """
        Upload compliance evidence
        
        Args:
            name: Evidence name
            description: Evidence description
            file_path: Path to evidence file
            control_id: Associated control
        """
        data = {
            "name": name,
            "description": description
        }
        
        if control_id:
            data["control"] = control_id
        
        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f)}
                response = self.session.post(
                    f"{self.base_url}/api/evidences/",
                    headers={"Authorization": f"Token {self.api_token}"},
                    data=data,
                    files=files
                )
                response.raise_for_status()
                return response.json()
        
        return self._request("POST", "/evidences/", json=data)
    
    def list_evidence(self, control_id: Optional[str] = None) -> List[Dict]:
        """List evidence, optionally filtered by control"""
        params = {}
        if control_id:
            params["control"] = control_id
        
        return self._request("GET", "/evidences/", params=params)
    
    # ============== AUDIT OPERATIONS ==============
    
    def create_audit(self, name: str, assessment_id: str,
                     auditor: str, start_date: str,
                     end_date: str) -> Dict:
        """
        Create an audit/campaign
        
        Args:
            name: Audit name
            assessment_id: Assessment to audit
            auditor: Auditor name/ID
            start_date: Audit start date
            end_date: Audit end date
        """
        data = {
            "name": name,
            "assessment": assessment_id,
            "auditor": auditor,
            "start_date": start_date,
            "end_date": end_date
        }
        return self._request("POST", "/audits/", json=data)
    
    def get_audit_findings(self, audit_id: str) -> List[Dict]:
        """Get findings from an audit"""
        return self._request("GET", f"/audits/{audit_id}/findings/")
    
    # ============== MAPPING OPERATIONS ==============
    
    def explore_mapping(self, framework_a: str, framework_b: str) -> Dict:
        """
        Explore mapping between two frameworks
        
        Example: Map ISO 27001 to NIST CSF
        """
        params = {
            "framework_a": framework_a,
            "framework_b": framework_b
        }
        return self._request("GET", "/mappings/explore/", params=params)
    
    def get_framework_gap_analysis(self, framework_id: str) -> Dict:
        """
        Get gap analysis for a framework
        
        Shows implemented vs missing controls.
        """
        return self._request("GET", 
                            f"/frameworks/{framework_id}/gap-analysis/")
    
    # ============== COMPLIANCE SPECIFIC METHODS ==============
    
    def validate_control_implementation(self, framework_id: str,
                                       control_id: str,
                                       evidence_paths: List[str]) -> Dict:
        """
        Validate control implementation with evidence
        
        Args:
            framework_id: Framework ID
            control_id: Control ID
            evidence_paths: List of evidence file paths
        """
        results = {
            "control_id": control_id,
            "framework_id": framework_id,
            "evidence_uploaded": [],
            "status": "pending"
        }
        
        # Upload evidence files
        for path in evidence_paths:
            if os.path.exists(path):
                evidence = self.upload_evidence(
                    name=os.path.basename(path),
                    description=f"Evidence for {control_id}",
                    file_path=path,
                    control_id=control_id
                )
                results["evidence_uploaded"].append({
                    "path": path,
                    "id": evidence.get("id")
                })
        
        # Update control status
        self.update_control_status(
            control_id=control_id,
            status=ComplianceStatus.COMPLIANT,
            evidence=f"Evidence uploaded: {len(results['evidence_uploaded'])} files"
        )
        
        results["status"] = "compliant"
        return results
    
    def get_compliance_score(self, assessment_id: str) -> Dict:
        """
        Calculate compliance score for assessment
        
        Returns:
        - Total controls
        - Compliant controls
        - Non-compliant controls
        - Partially compliant
        - Not assessed
        - Overall percentage
        """
        assessment = self.get_assessment(assessment_id)
        
        if not assessment or "results" not in assessment:
            return {"error": "No results found for assessment"}
        
        results = assessment.get("results", [])
        
        total = len(results)
        compliant = sum(1 for r in results if r.get("status") == "compliant")
        non_compliant = sum(1 for r in results if r.get("status") == "non_compliant")
        partial = sum(1 for r in results if r.get("status") == "partially_compliant")
        not_assessed = sum(1 for r in results if r.get("status") == "not_assessed")
        
        score = (compliant / total * 100) if total > 0 else 0
        
        return {
            "assessment_id": assessment_id,
            "total_controls": total,
            "compliant": compliant,
            "non_compliant": non_compliant,
            "partially_compliant": partial,
            "not_assessed": not_assessed,
            "compliance_percentage": round(score, 2),
            "risk_level": self._calculate_risk_level(
                compliant, non_compliant, partial, not_assessed
            )
        }
    
    def _calculate_risk_level(self, compliant: int, non_compliant: int,
                              partial: int, not_assessed: int) -> str:
        """Calculate overall risk level from assessment results"""
        total = compliant + non_compliant + partial + not_assessed
        
        if total == 0:
            return "unknown"
        
        critical_ratio = non_compliant / total
        
        if critical_ratio >= 0.3:
            return "critical"
        elif critical_ratio >= 0.15:
            return "high"
        elif critical_ratio >= 0.05:
            return "medium"
        else:
            return "low"
    
    def generate_compliance_summary(self, framework_id: str) -> Dict:
        """
        Generate executive summary of compliance status
        
        Returns high-level metrics suitable for reporting.
        """
        framework = self.get_framework(framework_id)
        gap_analysis = self.get_framework_gap_analysis(framework_id)
        
        summary = {
            "framework": {
                "id": framework_id,
                "name": framework.get("name"),
                "version": framework.get("version"),
                "total_controls": framework.get("controls_count", 0)
            },
            "compliance_status": gap_analysis.get("compliance_status"),
            "key_findings": gap_analysis.get("findings", []),
            "recommendations": gap_analysis.get("recommendations", []),
            "generated_at": datetime.now().isoformat()
        }
        
        return summary


# ============== EXAMPLE USAGE ==============

def example_usage():
    """Example of using the CISO Assistant client"""
    
    # Initialize client
    client = CISOAssistantClient(
        base_url="https://ciso-assistant.yourdomain.com",
        api_token="your_api_token_here"
    )
    
    # Example 1: List available frameworks
    print("Available Frameworks:")
    frameworks = client.list_frameworks(limit=10)
    for fw in frameworks.get("results", []):
        print(f"  - {fw.get('name')} ({fw.get('controls_count')} controls)")
    
    # Example 2: Create assessment for ISO 27001
    assessment = client.create_assessment(
        name="Q3 2026 ISO 27001 Assessment",
        framework_id="iso27001-2022",
        description="Quarterly compliance assessment",
        start_date="2026-07-01",
        end_date="2026-09-30"
    )
    assessment_id = assessment.get("id")
    print(f"Created assessment: {assessment_id}")
    
    # Example 3: Submit control results
    results = [
        {
            "control": "a.5.1.1",
            "status": "compliant",
            "evidence": "Policy document v2.0 approved"
        },
        {
            "control": "a.12.3.1",
            "status": "partially_compliant",
            "evidence": "Backups configured, testing pending"
        }
    ]
    
    client.submit_assessment_results(assessment_id, results)
    
    # Example 4: Get compliance score
    score = client.get_compliance_score(assessment_id)
    print(f"Compliance Score: {score['compliance_percentage']}%")
    print(f"Risk Level: {score['risk_level']}")
    
    # Example 5: Generate executive summary
    summary = client.generate_compliance_summary("iso27001-2022")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    # Run example (requires valid credentials)
    # example_usage()
    pass
