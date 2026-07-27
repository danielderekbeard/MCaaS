#!/usr/bin/env python3
"""
Wazuh → Zammad Ticket Creator

Creates tickets in Zammad from Wazuh security alerts.
Can be called directly or deployed as a webhook receiver.

Environment Variables:
    ZAMMAD_URL: Zammad instance URL (e.g., http://alala.mcaas.example.com)
    ZAMMAD_API_TOKEN: Zammad API token for authentication
    ZAMMAD_GROUP: Target ticket group (default: SOC)
    DEDUP_WINDOW_HOURS: Deduplication window in hours (default: 24)

Example:
    python ticket_creator.py --alert-file /path/to/alert.json
    python ticket_creator.py --alert-json '{"rule": {"description": "Test"}}'
    cat alert.json | python ticket_creator.py
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ZammadClient:
    """Client for Zammad API interactions."""
    
    def __init__(self, url: str, api_token: str):
        self.url = url.rstrip('/')
        self.api_token = api_token
        self.headers = {
            'Authorization': f'Token token={api_token}',
            'Content-Type': 'application/json'
        }
    
    def create_ticket(self, title: str, body: str, customer: str = None,
                      group: str = 'SOC', priority: str = '2 normal',
                      tags: List[str] = None, article_type: str = 'web') -> Dict:
        """Create a new ticket in Zammad."""
        
        # Prepare ticket data
        ticket_data = {
            'title': title,
            'group': group,
            'priority': priority,
            'state': 'new',
            'article': {
                'subject': title,
                'body': body,
                'type': article_type,
                'internal': False
            }
        }
        
        if customer:
            ticket_data['customer'] = customer
        
        if tags:
            ticket_data['tags'] = tags
        
        try:
            response = requests.post(
                f'{self.url}/api/v1/tickets',
                headers=self.headers,
                json=ticket_data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create ticket: {e}")
            raise
    
    def search_tickets(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for existing tickets."""
        try:
            response = requests.get(
                f'{self.url}/api/v1/tickets/search',
                headers=self.headers,
                params={'query': query, 'limit': limit},
                timeout=30
            )
            response.raise_for_status()
            return response.json().get('assets', {}).get('Ticket', {}).values()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search tickets: {e}")
            return []


class TicketDeduplicator:
    """Prevents duplicate tickets for the same alert condition."""
    
    def __init__(self, window_hours: int = 24):
        self.window = timedelta(hours=window_hours)
        self.cache = {}
    
    def _generate_fingerprint(self, alert: Dict) -> str:
        """Generate unique fingerprint for an alert."""
        rule_id = alert.get('rule', {}).get('id', 'unknown')
        agent_id = alert.get('agent', {}).get('id', 'unknown')
        srcip = alert.get('srcip', 'unknown')
        
        # Create deterministic hash
        data = f"{rule_id}:{agent_id}:{srcip}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def is_duplicate(self, alert: Dict) -> bool:
        """Check if this alert already has a recent ticket."""
        fingerprint = self._generate_fingerprint(alert)
        now = datetime.now()
        
        if fingerprint in self.cache:
            created_at = self.cache[fingerprint]
            if now - created_at < self.window:
                logger.info(f"Duplicate alert detected (fingerprint: {fingerprint[:8]}...)")
                return True
        
        self.cache[fingerprint] = now
        return False


def map_severity_to_priority(level: int) -> str:
    """Map Wazuh alert level to Zammad priority."""
    if level >= 10:
        return '3 high'
    elif level >= 7:
        return '2 normal'
    elif level >= 4:
        return '2 normal'
    else:
        return '1 low'


def format_ticket_body(alert: Dict) -> str:
    """Format Wazuh alert as Zammad ticket body."""
    rule = alert.get('rule', {})
    agent = alert.get('agent', {})
    
    body = f"""## Wazuh Security Alert

### Alert Details
- **Rule ID:** {rule.get('id', 'N/A')}
- **Rule Description:** {rule.get('description', 'N/A')}
- **Alert Level:** {rule.get('level', 'N/A')}
- **Timestamp:** {alert.get('timestamp', 'N/A')}

### Source Information
- **Agent Name:** {agent.get('name', 'N/A')}
- **Agent ID:** {agent.get('id', 'N/A')}
- **Agent IP:** {agent.get('ip', 'N/A')}
- **Source IP:** {alert.get('srcip', 'N/A')}
- **Location:** {alert.get('location', 'N/A')}

### Raw Log
```
{alert.get('full_log', 'N/A')}
```

### Full Alert JSON
<details>
<summary>Click to expand</summary>

```json
{json.dumps(alert, indent=2)}
```

</details>

---
*This ticket was automatically created by the Wazuh→Zammad integration.*
"""
    return body


def process_alert(alert_json: str, dry_run: bool = False) -> Optional[Dict]:
    """Process a Wazuh alert and create Zammad ticket."""
    
    # Parse alert
    try:
        alert = json.loads(alert_json)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return None
    
    # Get configuration from environment
    zammad_url = os.environ.get('ZAMMAD_URL')
    zammad_token = os.environ.get('ZAMMAD_API_TOKEN')
    zammad_group = os.environ.get('ZAMMAD_GROUP', 'SOC')
    dedup_hours = int(os.environ.get('DEDUP_WINDOW_HOURS', '24'))
    
    if not zammad_url or not zammad_token:
        logger.error("ZAMMAD_URL and ZAMMAD_API_TOKEN must be set")
        return None
    
    # Initialize components
    client = ZammadClient(zammad_url, zammad_token)
    deduplicator = TicketDeduplicator(dedup_hours)
    
    # Check for duplicates
    if deduplicator.is_duplicate(alert):
        logger.info("Skipping duplicate alert")
        return {'skipped': True, 'reason': 'duplicate'}
    
    # Extract alert info
    rule = alert.get('rule', {})
    rule_desc = rule.get('description', 'Wazuh Security Alert')
    level = rule.get('level', 3)
    agent_name = alert.get('agent', {}).get('name', 'Unknown')
    
    # Prepare ticket data
    title = f"[Wazuh] {rule_desc} - {agent_name}"
    body = format_ticket_body(alert)
    priority = map_severity_to_priority(level)
    tags = ['wazuh', 'security', f"level-{level}", 'auto-generated']
    
    if dry_run:
        logger.info("DRY RUN: Would create ticket:")
        logger.info(f"  Title: {title}")
        logger.info(f"  Priority: {priority}")
        logger.info(f"  Group: {zammad_group}")
        return {'dry_run': True, 'title': title}
    
    # Create ticket
    try:
        result = client.create_ticket(
            title=title,
            body=body,
            group=zammad_group,
            priority=priority,
            tags=tags
        )
        logger.info(f"Created ticket #{result.get('number')} (ID: {result.get('id')})")
        return result
    except Exception as e:
        logger.error(f"Failed to create ticket: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Create Zammad tickets from Wazuh alerts'
    )
    parser.add_argument(
        '--alert-file',
        type=argparse.FileType('r'),
        help='JSON file containing Wazuh alert'
    )
    parser.add_argument(
        '--alert-json',
        type=str,
        help='JSON string containing Wazuh alert'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without creating ticket'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get alert JSON from file, string, or stdin
    if args.alert_file:
        alert_json = args.alert_file.read()
    elif args.alert_json:
        alert_json = args.alert_json
    else:
        # Read from stdin
        alert_json = sys.stdin.read()
    
    if not alert_json.strip():
        logger.error("No alert data provided")
        sys.exit(1)
    
    # Process alert
    result = process_alert(alert_json, dry_run=args.dry_run)
    
    if result:
        if result.get('skipped'):
            logger.info("Alert skipped (duplicate)")
            sys.exit(0)
        elif result.get('dry_run'):
            print(json.dumps(result, indent=2))
            sys.exit(0)
        else:
            print(json.dumps(result, indent=2))
            sys.exit(0)
    else:
        logger.error("Failed to process alert")
        sys.exit(1)


if __name__ == '__main__':
    main()
