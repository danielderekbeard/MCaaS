#!/usr/bin/env python3
"""
Wazuh Alert Filtering and Routing

Filters Wazuh alerts based on configurable rules before sending to downstream
integrations (Shuffle, Zammad, etc.).

Features:
- Filter by rule group
- Exclude specific rule IDs
- Filter by severity level
- Time-based filtering
- Route alerts to different destinations based on criteria

Usage:
    python alert_filter.py --alert-file alert.json --config filters.yaml
    cat alert.json | python alert_filter.py --stdout
"""

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Callable
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FilterAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ROUTE = "route"


@dataclass
class FilterRule:
    """Single filter rule configuration."""
    name: str
    condition: str  # Python expression evaluated against alert
    action: FilterAction
    destination: Optional[str] = None  # For ROUTE action
    priority: int = 0


class AlertFilter:
    """Filter and route Wazuh alerts."""
    
    # Default noisy rules to exclude
    DEFAULT_EXCLUDED_RULES = {
        '5710',  # SSH brute force (too noisy)
        '5712',  # SSH scan
        '100001',  # Example noisy rule
    }
    
    # Default groups to include
    DEFAULT_INCLUDED_GROUPS = {
        'syslog', 'ossec', 'windows', 'web', 'attack', 'vulnerability-detection'
    }
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.excluded_rules = set(self.config.get('excluded_rules', self.DEFAULT_EXCLUDED_RULES))
        self.included_groups = set(self.config.get('included_groups', self.DEFAULT_INCLUDED_GROUPS))
        self.min_level = self.config.get('min_level', 3)
        self.max_level = self.config.get('max_level', 15)
        self.after_hours_only = self.config.get('after_hours_only', [])
        self.custom_filters: List[FilterRule] = []
        
    def add_custom_filter(self, rule: FilterRule):
        """Add a custom filter rule."""
        self.custom_filters.append(rule)
        self.custom_filters.sort(key=lambda x: x.priority, reverse=True)
    
    def _is_business_hours(self) -> bool:
        """Check if current time is business hours (9-17, Mon-Fri)."""
        now = datetime.now()
        if now.weekday() >= 5:  # Weekend
            return False
        hour = now.hour
        return 9 <= hour < 17
    
    def _check_time_filter(self, alert: Dict) -> bool:
        """Check if alert passes time-based filtering."""
        rule_id = str(alert.get('rule', {}).get('id', ''))
        
        if rule_id in self.after_hours_only:
            return not self._is_business_hours()
        
        return True
    
    def _check_rule_filter(self, alert: Dict) -> bool:
        """Check if alert passes rule-based filtering."""
        rule = alert.get('rule', {})
        rule_id = str(rule.get('id', ''))
        level = rule.get('level', 0)
        groups = set(rule.get('groups', []))
        
        # Check excluded rules
        if rule_id in self.excluded_rules:
            logger.debug(f"Rule {rule_id} is excluded")
            return False
        
        # Check level range
        if not (self.min_level <= level <= self.max_level):
            logger.debug(f"Level {level} not in range [{self.min_level}, {self.max_level}]")
            return False
        
        # Check groups
        if not groups.intersection(self.included_groups):
            logger.debug(f"No matching groups in {groups}")
            return False
        
        return True
    
    def _apply_custom_filters(self, alert: Dict) -> tuple:
        """Apply custom filter rules. Returns (action, destination)."""
        for filter_rule in self.custom_filters:
            try:
                # Create evaluation context
                context = {
                    'alert': alert,
                    'rule': alert.get('rule', {}),
                    'agent': alert.get('agent', {}),
                    'level': alert.get('rule', {}).get('level', 0),
                    'srcip': alert.get('srcip', ''),
                    'timestamp': alert.get('timestamp', ''),
                }
                
                # Evaluate condition
                result = eval(filter_rule.condition, {"__builtins__": {}}, context)
                
                if result:
                    logger.debug(f"Custom filter '{filter_rule.name}' matched")
                    return filter_rule.action, filter_rule.destination
                    
            except Exception as e:
                logger.warning(f"Error evaluating filter '{filter_rule.name}': {e}")
        
        return FilterAction.ALLOW, None
    
    def filter_alert(self, alert: Dict) -> tuple:
        """
        Filter an alert.
        
        Returns:
            (should_process, destination) tuple
            - should_process: bool indicating if alert should be processed
            - destination: optional routing destination
        """
        # Apply basic filters
        if not self._check_rule_filter(alert):
            return False, None
        
        if not self._check_time_filter(alert):
            logger.debug("Alert filtered by time restriction")
            return False, None
        
        # Apply custom filters
        action, destination = self._apply_custom_filters(alert)
        
        if action == FilterAction.DENY:
            return False, None
        elif action == FilterAction.ROUTE:
            return True, destination
        else:
            return True, None
    
    def filter_alerts(self, alerts: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Filter multiple alerts and group by destination.
        
        Returns:
            Dictionary mapping destination to list of alerts
        """
        results = {'default': []}
        
        for alert in alerts:
            should_process, destination = self.filter_alert(alert)
            if should_process:
                dest = destination or 'default'
                if dest not in results:
                    results[dest] = []
                results[dest].append(alert)
        
        return results


def load_config(config_file: str) -> Dict:
    """Load filter configuration from YAML file."""
    with open(config_file) as f:
        return yaml.safe_load(f)


def create_sample_config() -> Dict:
    """Create sample filter configuration."""
    return {
        'min_level': 3,
        'max_level': 15,
        'excluded_rules': ['5710', '5712', '5720'],
        'included_groups': [
            'syslog',
            'ossec',
            'windows',
            'web',
            'attack',
            'vulnerability-detection',
            'security'
        ],
        'after_hours_only': ['550', '553', '554'],
        'custom_filters': [
            {
                'name': 'critical_to_pagerduty',
                'condition': 'level >= 10',
                'action': 'route',
                'destination': 'pagerduty',
                'priority': 100
            },
            {
                'name': 'exclude_test_agents',
                'condition': '"test" in agent.get("name", "")',
                'action': 'deny',
                'priority': 90
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description='Filter Wazuh alerts')
    parser.add_argument('--alert-file', type=argparse.FileType('r'),
                        help='JSON file with alert(s)')
    parser.add_argument('--config', type=str,
                        help='YAML configuration file')
    parser.add_argument('--generate-config', action='store_true',
                        help='Generate sample configuration')
    parser.add_argument('--stdout', action='store_true',
                        help='Output filtered alerts to stdout')
    parser.add_argument('--stats', action='store_true',
                        help='Show filtering statistics')
    
    args = parser.parse_args()
    
    if args.generate_config:
        config = create_sample_config()
        print(yaml.dump(config, default_flow_style=False))
        return
    
    # Load configuration
    config = {}
    if args.config:
        config = load_config(args.config)
    
    # Create filter
    alert_filter = AlertFilter(config)
    
    # Load alerts
    if args.alert_file:
        data = json.load(args.alert_file)
    else:
        data = json.load(sys.stdin)
    
    # Handle single alert or list
    if isinstance(data, dict):
        alerts = [data]
    else:
        alerts = data
    
    # Filter alerts
    total = len(alerts)
    results = alert_filter.filter_alerts(alerts)
    passed = sum(len(v) for v in results.values())
    
    # Output results
    if args.stdout:
        for dest, dest_alerts in results.items():
            for alert in dest_alerts:
                alert['_routing_destination'] = dest
                print(json.dumps(alert))
    
    # Show statistics
    if args.stats:
        print(f"Total alerts: {total}")
        print(f"Passed filters: {passed}")
        print(f"Filtered out: {total - passed}")
        print(f"\nBy destination:")
        for dest, dest_alerts in results.items():
            print(f"  {dest}: {len(dest_alerts)}")


if __name__ == '__main__':
    main()
