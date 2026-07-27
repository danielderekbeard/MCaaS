#!/usr/bin/env python3
"""
Wazuh → CISO Assistant Compliance Mapper

Maps Wazuh security alerts to compliance frameworks (ISO 27001, NIST, SOC2)
and creates findings in CISO Assistant.

Environment Variables:
    CISO_ASSISTANT_URL: CISO Assistant API URL
    CISO_ASSISTANT_API_KEY: *** API authentication key
    DEFAULT_FRAMEWORK: Default compliance framework (iso27001, nist, soc2)
    AUTO_CREATE_FINDINGS: Automatically create findings (true/false)
    LOG_LEVEL: Logging level (default: INFO)

Usage:
    python compliance_mapper.py --alert-file alert.json --framework iso27001
    python compliance_mapper.py --alert-json '{...}' --dry-run
    cat alert.json | python compliance_mapper.py
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComplianceFramework(Enum):
    ISO27001 = "iso27001"
    NIST = "nist"
    SOC2 = "soc2"


@dataclass
class ControlMapping:
    """Maps Wazuh rule groups to compliance controls."""
    framework: str
    control_id: str
    control_name: str
    description: str
    wazuh_groups: Set[str]
    severity: str


class ComplianceMappings:
    """Compliance framework mappings for Wazuh alerts."""
    
    ISO27001_MAPPINGS = {
        "authentication": ControlMapping(
            framework="iso27001",
            control_id="A.9.4.2",
            control_name="Secure Log-on Procedures",
            description="Authentication failures and successful logins",
            wazuh_groups={"syslog", "authentication", "pam"},
            severity="medium"
        ),
        "access_control": ControlMapping(
            framework="iso27001",
            control_id="A.9.1.2",
            control_name="Access to Networks",
            description="SSH access and network connections",
            wazuh_groups={"syslog", "sshd"},
            severity="high"
        ),
        "malware": ControlMapping(
            framework="iso27001",
            control_id="A.12.2.1",
            control_name="Malware Protection",
            description="Malware detection and prevention",
            wazuh_groups={"syscheck", "malware", "rootcheck"},
            severity="high"
        ),
        "vulnerability": ControlMapping(
            framework="iso27001",
            control_id="A.12.6.1",
            control_name="Management of Technical Vulnerabilities",
            description="Vulnerability detection and assessment",
            wazuh_groups={"vulnerability-detection"},
            severity="high"
        ),
        "audit": ControlMapping(
            framework="iso27001",
            control_id="A.12.4.1",
            control_name="Event Logging",
            description="Audit and logging events",
            wazuh_groups={"syslog", "audit"},
            severity="medium"
        ),
    }
    
    NIST_MAPPINGS = {
        "authentication": ControlMapping(
            framework="nist",
            control_id="AC-2",
            control_name="Account Management",
            description="Account access and authentication events",
            wazuh_groups={"syslog", "authentication", "pam"},
            severity="high"
        ),
        "access_control": ControlMapping(
            framework="nist",
            control_id="AC-17",
            control_name="Remote Access",
            description="Remote access and SSH events",
            wazuh_groups={"syslog", "sshd"},
            severity="high"
        ),
        "malware": ControlMapping(
            framework="nist",
            control_id="SI-3",
            control_name="Malicious Code Protection",
            description="Malware detection and response",
            wazuh_groups={"syscheck", "malware", "rootcheck"},
            severity="high"
        ),
        "vulnerability": ControlMapping(
            framework="nist",
            control_id="RA-5",
            control_name="Vulnerability Scanning",
            description="Vulnerability assessment activities",
            wazuh_groups={"vulnerability-detection"},
            severity="high"
        ),
        "audit": ControlMapping(
            framework="nist",
            control_id="AU-6",
            control_name="Audit Review",
            description="Audit log analysis and review",
            wazuh_groups={"syslog", "audit"},
            severity="medium"
        ),
    }
    
    SOC2_MAPPINGS = {
        "authentication": ControlMapping(
            framework="soc2",
            control_id="CC6.1",
            control_name="Logical Access Security",
            description="Authentication and access controls",
            wazuh_groups={"syslog", "authentication", "pam"},
            severity="high"
        ),
        "access_control": ControlMapping(
            framework="soc2",
            control_id="CC6.2",
            control_name="Access Removal",
            description="Access management and removal",
            wazuh_groups={"syslog", "sshd"},
            severity="high"
        ),
        "malware": ControlMapping(
            framework="soc2",
            control_id="CC7.2",
            control_name="System Monitoring",
            description="System monitoring and malware detection",
            wazuh_groups={"syscheck", "malware", "rootcheck"},
            severity="high"
        ),
        "vulnerability": ControlMapping(
            framework="soc2",
            control_id="CC7.1",
            control_name="Vulnerability Detection",
            description="Vulnerability scanning and management",
            wazuh_groups={"vulnerability-detection"},
            severity="high"
        ),
        "audit": ControlMapping(
            framework="soc2",
            control_id="CC7.2",
            control_name="Monitoring Activities",
            description="System monitoring and logging",
            wazuh_groups={"syslog", "audit"},
            severity="medium"
        ),
    }
    
    @classmethod
    def get_mappings(cls, framework: str) -> Dict[str, ControlMapping]:
        """Get mappings for a specific framework."""
        framework = framework.lower()
        if framework == "iso27001":
            return cls.ISO27001_MAPPINGS
        elif framework == "nist":
            return cls.NIST_MAPPINGS
        elif framework == "soc2":
            return cls.SOC2_MAPPINGS
        else:
            raise ValueError(f"Unknown framework: {framework}")


class CISOAssistantClient:
    """Client for CISO Assistant API."""
    
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Authorization': f'***',
            'Content-Type': 'application/json'
        }
    
    def create_finding(self, title: str, description: str, severity: str,
                      control_id: str, framework: str, evidence: Dict = None) -> Optional[Dict]:
        """Create a compliance finding in CISO Assistant."""
        
        finding_data = {
            'title': title,
            'description': description,
            'severity': severity.lower(),
            'control': control_id,
            'framework': framework,
            'status': 'open',
            'source': 'wazuh',
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        if evidence:
            finding_data['evidence'] = evidence
        
        try:
            response = requests.post(
                f'{self.url}/api/v1/findings',
                headers=self.headers,
                json=finding_data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create finding: {e}")
            return None
    
    def get_frameworks(self) -> List[Dict]:
        """Get available compliance frameworks."""
        try:
            response = requests.get(
                f'{self.url}/api/v1/frameworks',
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get frameworks: {e}")
            return []


class ComplianceMapper:
    """Maps Wazuh alerts to compliance controls."""
    
    def __init__(self, default_framework: str = "iso27001"):
        self.default_framework = default_framework
        self.client = None
        if os.environ.get('CISO_ASSISTANT_URL') and os.environ.get('CISO_ASSISTANT_API_KEY'):
            self.client = CISOAssistantClient(
                os.environ['CISO_ASSISTANT_URL'],
                os.environ['CISO_ASSISTANT_API_KEY']
            )
    
    def map_alert_to_control(self, alert: Dict, framework: str = None) -> Optional[ControlMapping]:
        """Map a Wazuh alert to compliance control(s)."""
        framework = framework or self.default_framework
        mappings = ComplianceMappings.get_mappings(framework)
        
        rule_groups = set(alert.get('rule', {}).get('groups', []))
        rule_id = str(alert.get('rule', {}).get('id', ''))
        
        # Check for specific rule ID mappings
        rule_mappings = self._get_rule_mapping(rule_id, framework)
        if rule_mappings:
            return rule_mappings
        
        # Match based on rule groups
        for mapping_name, mapping in mappings.items():
            if rule_groups.intersection(mapping.wazuh_groups):
                return mapping
        
        return None
    
    def _get_rule_mapping(self, rule_id: str, framework: str) -> Optional[ControlMapping]:
        """Get control mapping for specific rule IDs."""
        # Add specific rule mappings here
        critical_rules = {
            '100001',  # Example critical rule
        }
        
        if rule_id in critical_rules:
            mappings = ComplianceMappings.get_mappings(framework)
            return mappings.get('malware')
        
        return None
    
    def create_finding_from_alert(self, alert: Dict, framework: str = None,
                                  dry_run: bool = False) -> Optional[Dict]:
        """Create a compliance finding from a Wazuh alert."""
        
        mapping = self.map_alert_to_control(alert, framework)
        if not mapping:
            logger.info("No compliance mapping found for alert")
            return None
        
        rule = alert.get('rule', {})
        agent = alert.get('agent', {})
        
        # Create finding data
        title = f"[{mapping.control_id}] {rule.get('description', 'Security Alert')}"
        
        description = f"""## Compliance Finding

**Framework:** {mapping.framework.upper()}
**Control:** {mapping.control_id} - {mapping.control_name}
**Severity:** {mapping.severity}

### Alert Details
- **Rule ID:** {rule.get('id', 'N/A')}
- **Rule Description:** {rule.get('description', 'N/A')}
- **Alert Level:** {rule.get('level', 'N/A')}

### Source Information
- **Agent:** {agent.get('name', 'Unknown')} ({agent.get('id', 'Unknown')})
- **Location:** {alert.get('location', 'N/A')}
- **Timestamp:** {alert.get('timestamp', 'N/A')}

### Evidence
```
{alert.get('full_log', 'N/A')}
```

### Mapping Rationale
This alert relates to {mapping.control_name} ({mapping.control_id}) under {mapping.framework.upper()} framework.
"""
        
        evidence = {
            'wazuh_alert': alert,
            'mapping_rationale': mapping.description,
            'auto_generated': True
        }
        
        if dry_run:
            logger.info(f"DRY RUN: Would create finding for {mapping.control_id}")
            return {
                'dry_run': True,
                'title': title,
                'control_id': mapping.control_id,
                'framework': mapping.framework
            }
        
        if not self.client:
            logger.error("CISO Assistant client not configured")
            return None
        
        result = self.client.create_finding(
            title=title,
            description=description,
            severity=mapping.severity,
            control_id=mapping.control_id,
            framework=mapping.framework,
            evidence=evidence
        )
        
        if result:
            logger.info(f"Created finding: {result.get('id')} for {mapping.control_id}")
        
        return result
    
    def process_alert(self, alert: Dict, frameworks: List[str] = None,
                     dry_run: bool = False) -> List[Dict]:
        """Process alert against multiple frameworks."""
        frameworks = frameworks or [self.default_framework]
        results = []
        
        for framework in frameworks:
            result = self.create_finding_from_alert(alert, framework, dry_run)
            if result:
                results.append(result)
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description='Map Wazuh alerts to compliance frameworks'
    )
    parser.add_argument('--alert-file', type=argparse.FileType('r'),
                        help='JSON file with Wazuh alert')
    parser.add_argument('--alert-json', type=str,
                        help='JSON string with Wazuh alert')
    parser.add_argument('--framework', type=str, default='iso27001',
                        choices=['iso27001', 'nist', 'soc2'],
                        help='Compliance framework')
    parser.add_argument('--all-frameworks', action='store_true',
                        help='Map to all supported frameworks')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done')
    parser.add_argument('--list-mappings', action='store_true',
                        help='List available mappings')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.list_mappings:
        for framework in ['iso27001', 'nist', 'soc2']:
            print(f"\n## {framework.upper()} Mappings")
            mappings = ComplianceMappings.get_mappings(framework)
            for name, mapping in mappings.items():
                print(f"  {mapping.control_id}: {mapping.control_name}")
        return
    
    # Get alert JSON
    if args.alert_file:
        alert_json = args.alert_file.read()
    elif args.alert_json:
        alert_json = args.alert_json
    else:
        alert_json = sys.stdin.read()
    
    if not alert_json.strip():
        logger.error("No alert data provided")
        sys.exit(1)
    
    try:
        alert = json.loads(alert_json)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        sys.exit(1)
    
    # Process alert
    frameworks = ['iso27001', 'nist', 'soc2'] if args.all_frameworks else [args.framework]
    mapper = ComplianceMapper(default_framework=args.framework)
    
    results = mapper.process_alert(alert, frameworks=frameworks, dry_run=args.dry_run)
    
    if results:
        print(json.dumps(results, indent=2))
        sys.exit(0)
    else:
        logger.info("No compliance findings created")
        sys.exit(0)


if __name__ == '__main__':
    main()
