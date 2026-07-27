#!/usr/bin/env python3
"""
Wazuh to Zammad Ticket Creator.

This script receives Wazuh alerts (via webhook or file) and creates tickets
in Zammad with deduplication logic to prevent duplicate tickets for the same issue.

Environment Variables:
    ZAMMAD_URL: Zammad instance URL (default: http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080)
    ZAMMAD_API_TOKEN: Zammad API token for authentication
    ZAMMAD_GROUP_ID: Default ticket group ID (default: 1)
    ZAMMAD_CUSTOMER_ID: Default customer ID for tickets (default: 2)
    TICKET_DEDUPLICATION_WINDOW: Hours to consider for deduplication (default: 24)
    LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR) (default: INFO)
    STATE_FILE: Path to deduplication state file (default: /tmp/wazuh-zammad-state.json)

Usage:
    python ticket-creator.py --alert-file alerts.json
    python ticket-creator.py --webhook --port 5000
    echo '{"alert": {...}}' | python ticket-creator.py --stdin

Exit Codes:
    0: Success
    1: General error
    2: Missing API token
    3: Zammad API error
    4: Duplicate alert (skipped)
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Default configuration
DEFAULT_ZAMMAD_URL = "http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080"
DEFAULT_GROUP_ID = 1
DEFAULT_CUSTOMER_ID = 2
DEFAULT_DEDUPLICATION_WINDOW = 24  # hours
DEFAULT_STATE_FILE = "/tmp/wazuh-zammad-state.json"
DEFAULT_REQUEST_TIMEOUT = 30


class ZammadError(Exception):
    """Base exception for Zammad API errors."""
    pass


class AuthenticationError(ZammadError):
    """Raised when authentication fails."""
    pass


class DuplicateAlertError(Exception):
    """Raised when a duplicate alert is detected."""
    pass


class TicketCreatorError(Exception):
    """Base exception for ticket creator errors."""
    pass


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure logging with structured output.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("wazuh_zammad")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def create_session() -> requests.Session:
    """
    Create a requests session with retry logic.
    
    Returns:
        Configured requests Session
    """
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


class DeduplicationStore:
    """
    Manages deduplication state for Wazuh alerts.
    
    Tracks alert signatures and their timestamps to prevent duplicate tickets.
    """
    
    def __init__(self, state_file: str, window_hours: int, logger: logging.Logger):
        """
        Initialize the deduplication store.
        
        Args:
            state_file: Path to state file
            window_hours: Hours to keep alert signatures
            logger: Logger instance
        """
        self.state_file = Path(state_file)
        self.window_hours = window_hours
        self.logger = logger
        self.signatures: Dict[str, datetime] = {}
        self._load()
    
    def _load(self) -> None:
        """Load state from file."""
        if not self.state_file.exists():
            self.logger.debug("No existing state file found")
            return
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cutoff = datetime.now() - timedelta(hours=self.window_hours)
            
            for sig, timestamp_str in data.get("signatures", {}).items():
                timestamp = datetime.fromisoformat(timestamp_str)
                if timestamp > cutoff:
                    self.signatures[sig] = timestamp
            
            self.logger.debug(f"Loaded {len(self.signatures)} valid signatures from state")
        except Exception as e:
            self.logger.warning(f"Failed to load state file: {e}")
            self.signatures = {}
    
    def _save(self) -> None:
        """Save state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "last_updated": datetime.now().isoformat(),
                "signatures": {
                    sig: ts.isoformat() for sig, ts in self.signatures.items()
                }
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"Saved {len(self.signatures)} signatures to state")
        except Exception as e:
            self.logger.error(f"Failed to save state file: {e}")
    
    def is_duplicate(self, signature: str) -> bool:
        """
        Check if an alert is a duplicate.
        
        Args:
            signature: Alert signature
        
        Returns:
            True if duplicate, False otherwise
        """
        cutoff = datetime.now() - timedelta(hours=self.window_hours)
        
        if signature in self.signatures:
            timestamp = self.signatures[signature]
            if timestamp > cutoff:
                self.logger.info(f"Duplicate detected (last seen: {timestamp})")
                return True
            else:
                # Expired entry, remove it
                del self.signatures[signature]
        
        return False
    
    def add(self, signature: str) -> None:
        """
        Add a signature to the store.
        
        Args:
            signature: Alert signature
        """
        self.signatures[signature] = datetime.now()
        self._save()
    
    def cleanup(self) -> int:
        """
        Remove expired signatures.
        
        Returns:
            Number of signatures removed
        """
        cutoff = datetime.now() - timedelta(hours=self.window_hours)
        expired = [
            sig for sig, ts in self.signatures.items()
            if ts <= cutoff
        ]
        
        for sig in expired:
            del self.signatures[sig]
        
        if expired:
            self._save()
        
        self.logger.debug(f"Cleaned up {len(expired)} expired signatures")
        return len(expired)


def generate_alert_signature(alert: Dict[str, Any]) -> str:
    """
    Generate a unique signature for an alert.
    
    The signature is based on alert fields that identify the same underlying issue.
    
    Args:
        alert: Wazuh alert dictionary
    
    Returns:
        MD5 hash signature
    """
    rule = alert.get("rule", {})
    agent = alert.get("agent", {})
    
    # Fields that identify the same issue
    signature_parts = [
        str(rule.get("id", "")),
        str(rule.get("description", "")),
        str(agent.get("id", "")),
        str(agent.get("name", "")),
        str(alert.get("srcip", "")),
        str(alert.get("dstip", "")),
        str(alert.get("location", ""))
    ]
    
    signature_string = "|".join(signature_parts)
    return hashlib.md5(signature_string.encode()).hexdigest()


def map_severity_to_priority(level: int) -> str:
    """
    Map Wazuh alert severity level to Zammad ticket priority.
    
    Wazuh levels:
        0-3: Low (informational)
        4-6: Normal (notice/warning)
        7-10: High (error/critical)
        11+: Critical (alert/emergency)
    
    Args:
        level: Wazuh alert level
    
    Returns:
        Zammad priority string
    """
    if level >= 11:
        return "4 critical"
    elif level >= 7:
        return "3 high"
    elif level >= 4:
        return "2 normal"
    else:
        return "1 low"


def map_severity_to_state(level: int) -> str:
    """
    Map Wazuh alert severity level to Zammad ticket state.
    
    Args:
        level: Wazuh alert level
    
    Returns:
        Zammad state string
    """
    if level >= 7:
        return "new"  # High severity alerts start as new
    else:
        return "open"  # Lower severity can be processed normally


def extract_alert_data(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and format relevant data from a Wazuh alert.
    
    Args:
        alert: Raw Wazuh alert
    
    Returns:
        Formatted alert data dictionary
    """
    rule = alert.get("rule", {})
    agent = alert.get("agent", {})
    
    return {
        "rule_id": rule.get("id", "N/A"),
        "rule_description": rule.get("description", "Unknown Alert"),
        "rule_level": rule.get("level", 0),
        "agent_id": agent.get("id", "N/A"),
        "agent_name": agent.get("name", "Unknown"),
        "agent_ip": agent.get("ip", "N/A"),
        "timestamp": alert.get("timestamp", datetime.now().isoformat()),
        "src_ip": alert.get("srcip", "N/A"),
        "dst_ip": alert.get("dstip", "N/A"),
        "location": alert.get("location", "N/A"),
        "full_log": alert.get("full_log", ""),
        "mitre": alert.get("mitre", {}),
        "decoder": alert.get("decoder", "")
    }


def build_ticket_title(data: Dict[str, Any]) -> str:
    """
    Build a descriptive ticket title from alert data.
    
    Args:
        data: Extracted alert data
    
    Returns:
        Ticket title string
    """
    level = data["rule_level"]
    description = data["rule_description"]
    agent = data["agent_name"]
    
    return f"[Wazuh L{level}] {description} (Agent: {agent})"


def build_ticket_body(data: Dict[str, Any]) -> str:
    """
    Build a detailed ticket body from alert data.
    
    Args:
        data: Extracted alert data
    
    Returns:
        Ticket body string (Markdown formatted)
    """
    lines = [
        "## Wazuh Security Alert",
        "",
        f"**Alert Level:** {data['rule_level']}",
        f"**Rule ID:** {data['rule_id']}",
        f"**Description:** {data['rule_description']}",
        "",
        "### Affected System",
        f"- **Agent:** {data['agent_name']} ({data['agent_id']})",
        f"- **Agent IP:** {data['agent_ip']}",
        f"- **Location:** {data['location']}",
        "",
        "### Alert Details",
        f"- **Timestamp:** {data['timestamp']}",
        f"- **Source IP:** {data['src_ip']}",
        f"- **Destination IP:** {data['dst_ip']}",
    ]
    
    # Add MITRE ATT&CK info if available
    mitre = data.get("mitre", {})
    if mitre:
        lines.extend([
            "",
            "### MITRE ATT&CK",
        ])
        if "id" in mitre:
            lines.append(f"- **Technique ID:** {mitre['id']}")
        if "tactic" in mitre:
            lines.append(f"- **Tactic:** {mitre['tactic']}")
    
    # Add full log if available
    if data["full_log"]:
        log_preview = data["full_log"][:2000]
        if len(data["full_log"]) > 2000:
            log_preview += "\n\n... (truncated)"
        lines.extend([
            "",
            "### Full Log",
            "```",
            log_preview,
            "```"
        ])
    
    lines.extend([
        "",
        "---",
        "*This ticket was automatically created by MCaaS Wazuh integration.*"
    ])
    
    return "\n".join(lines)


class ZammadClient:
    """
    Client for interacting with Zammad API.
    """
    
    def __init__(
        self,
        base_url: str,
        api_token: str,
        logger: logging.Logger,
        timeout: int = DEFAULT_REQUEST_TIMEOUT
    ):
        """
        Initialize Zammad client.
        
        Args:
            base_url: Zammad instance URL
            api_token: API authentication token
            logger: Logger instance
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.logger = logger
        self.timeout = timeout
        self.session = create_session()
        
        # Set up authentication header
        self.session.headers.update({
            "Authorization": f"Token token={api_token}",
            "Content-Type": "application/json"
        })
        
        self.logger.debug(f"Initialized Zammad client for {base_url}")
    
    def _api_url(self, endpoint: str) -> str:
        """Build full API URL."""
        return urljoin(f"{self.base_url}/", f"api/v1/{endpoint.lstrip('/')}")
    
    def test_connection(self) -> bool:
        """
        Test API connectivity and authentication.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.session.get(
                self._api_url("users/me"),
                timeout=self.timeout
            )
            response.raise_for_status()
            self.logger.debug("Zammad API connection successful")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API token")
            raise ZammadError(f"API error: {e}")
        except Exception as e:
            raise ZammadError(f"Connection failed: {e}")
    
    def create_ticket(
        self,
        title: str,
        body: str,
        group_id: int,
        customer_id: int,
        priority: str,
        state: str
    ) -> Dict[str, Any]:
        """
        Create a ticket in Zammad.
        
        Args:
            title: Ticket title
            body: Ticket body (article content)
            group_id: Group ID for the ticket
            customer_id: Customer ID for the ticket
            priority: Ticket priority
            state: Ticket state
        
        Returns:
            Created ticket data
        
        Raises:
            ZammadError: If ticket creation fails
        """
        payload = {
            "title": title,
            "group_id": group_id,
            "customer_id": customer_id,
            "priority": priority,
            "state": state,
            "article": {
                "subject": f"Alert: {title[:100]}",
                "body": body,
                "type": "note",
                "internal": False
            }
        }
        
        self.logger.debug(f"Creating ticket: {title[:80]}...")
        
        try:
            response = self.session.post(
                self._api_url("tickets"),
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            ticket = response.json()
            self.logger.info(f"Ticket created: #{ticket.get('number', 'N/A')} (ID: {ticket.get('id', 'N/A')})")
            return ticket
        
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
            raise ZammadError(f"Failed to create ticket: {e} - {error_detail}")
        except Exception as e:
            raise ZammadError(f"Failed to create ticket: {e}")


def process_alert(
    alert: Dict[str, Any],
    zammad: ZammadClient,
    dedup_store: DeduplicationStore,
    group_id: int,
    customer_id: int,
    logger: logging.Logger
) -> Optional[Dict[str, Any]]:
    """
    Process a single Wazuh alert and create a ticket.
    
    Args:
        alert: Wazuh alert dictionary
        zammad: Zammad client instance
        dedup_store: Deduplication store
        group_id: Ticket group ID
        customer_id: Ticket customer ID
        logger: Logger instance
    
    Returns:
        Created ticket data or None if skipped
    
    Raises:
        DuplicateAlertError: If alert is a duplicate
        ZammadError: If ticket creation fails
    """
    # Handle nested alert structure
    if "alert" in alert:
        alert = alert["alert"]
    
    # Extract alert data
    data = extract_alert_data(alert)
    
    # Generate signature for deduplication
    signature = generate_alert_signature(alert)
    
    # Check for duplicates
    if dedup_store.is_duplicate(signature):
        logger.info(f"Skipping duplicate alert: {data['rule_description']}")
        raise DuplicateAlertError(f"Duplicate alert detected: {signature}")
    
    # Map severity to priority and state
    priority = map_severity_to_priority(data["rule_level"])
    state = map_severity_to_state(data["rule_level"])
    
    # Build ticket content
    title = build_ticket_title(data)
    body = build_ticket_body(data)
    
    logger.info(f"Creating ticket for: {title}")
    
    # Create ticket in Zammad
    ticket = zammad.create_ticket(
        title=title,
        body=body,
        group_id=group_id,
        customer_id=customer_id,
        priority=priority,
        state=state
    )
    
    # Record this alert to prevent duplicates
    dedup_store.add(signature)
    
    return ticket


def load_alerts_from_file(filepath: str, logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Load alerts from a JSON file.
    
    Args:
        filepath: Path to JSON file
        logger: Logger instance
    
    Returns:
        List of alert dictionaries
    """
    path = Path(filepath)
    
    if not path.exists():
        raise TicketCreatorError(f"File not found: {filepath}")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise TicketCreatorError(f"Invalid JSON in file: {e}")
    
    # Handle various JSON structures
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    else:
        raise TicketCreatorError(f"Unexpected JSON structure: {type(data)}")


def load_alerts_from_stdin(logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Load alerts from stdin.
    
    Args:
        logger: Logger instance
    
    Returns:
        List of alert dictionaries
    """
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        raise TicketCreatorError(f"Invalid JSON from stdin: {e}")
    
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    else:
        raise TicketCreatorError(f"Unexpected JSON structure: {type(data)}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create Zammad tickets from Wazuh alerts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --alert-file alerts.json
    %(prog)s --alert-file alerts.json --dry-run
    echo '{"alert": {...}}' | %(prog)s --stdin
    %(prog)s --cleanup-state
        """
    )
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--alert-file",
        metavar="FILE",
        help="Path to JSON file containing Wazuh alerts"
    )
    input_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read alerts from stdin"
    )
    input_group.add_argument(
        "--cleanup-state",
        action="store_true",
        help="Clean up expired deduplication entries"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview tickets without creating"
    )
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        default=True,
        help="Skip duplicate alerts (default: True)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create tickets even for duplicates"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logging(log_level)
    
    logger.info("Starting Wazuh to Zammad ticket creator")
    
    # Get configuration from environment
    zammad_url = os.getenv("ZAMMAD_URL", DEFAULT_ZAMMAD_URL)
    api_token = os.getenv("ZAMMAD_API_TOKEN")
    group_id = int(os.getenv("ZAMMAD_GROUP_ID", DEFAULT_GROUP_ID))
    customer_id = int(os.getenv("ZAMMAD_CUSTOMER_ID", DEFAULT_CUSTOMER_ID))
    dedup_window = int(os.getenv("TICKET_DEDUPLICATION_WINDOW", DEFAULT_DEDUPLICATION_WINDOW))
    state_file = os.getenv("STATE_FILE", DEFAULT_STATE_FILE)
    
    if not api_token:
        logger.error("ZAMMAD_API_TOKEN environment variable is required")
        return 2
    
    # Initialize deduplication store
    dedup_store = DeduplicationStore(state_file, dedup_window, logger)
    
    # Cleanup mode
    if args.cleanup_state:
        removed = dedup_store.cleanup()
        logger.info(f"Cleaned up {removed} expired entries")
        return 0
    
    # Initialize Zammad client
    try:
        zammad = ZammadClient(zammad_url, api_token, logger)
        zammad.test_connection()
    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        return 2
    except ZammadError as e:
        logger.error(f"Zammad connection failed: {e}")
        return 3
    
    # Load alerts
    try:
        if args.alert_file:
            alerts = load_alerts_from_file(args.alert_file, logger)
        else:  # stdin
            alerts = load_alerts_from_stdin(logger)
    except TicketCreatorError as e:
        logger.error(f"Failed to load alerts: {e}")
        return 1
    
    logger.info(f"Processing {len(alerts)} alert(s)")
    
    # Process alerts
    created = 0
    skipped = 0
    failed = 0
    
    for i, alert in enumerate(alerts, 1):
        logger.debug(f"Processing alert {i}/{len(alerts)}")
        
        try:
            if args.dry_run:
                # Preview mode
                if "alert" in alert:
                    alert = alert["alert"]
                data = extract_alert_data(alert)
                title = build_ticket_title(data)
                priority = map_severity_to_priority(data["rule_level"])
                signature = generate_alert_signature(alert)
                is_dup = dedup_store.is_duplicate(signature)
                
                print(f"\n[DRY-RUN] Would create ticket:")
                print(f"  Title: {title}")
                print(f"  Priority: {priority}")
                print(f"  Duplicate: {is_dup and not args.force}")
                continue
            
            ticket = process_alert(
                alert,
                zammad,
                dedup_store,
                group_id,
                customer_id,
                logger
            )
            created += 1
            
        except DuplicateAlertError:
            skipped += 1
            if not args.skip_duplicates or args.force:
                logger.warning("Creating ticket anyway (--force specified)")
                try:
                    if "alert" in alert:
                        alert = alert["alert"]
                    data = extract_alert_data(alert)
                    priority = map_severity_to_priority(data["rule_level"])
                    state = map_severity_to_state(data["rule_level"])
                    ticket = zammad.create_ticket(
                        title=build_ticket_title(data),
                        body=build_ticket_body(data),
                        group_id=group_id,
                        customer_id=customer_id,
                        priority=priority,
                        state=state
                    )
                    created += 1
                except Exception as e:
                    logger.error(f"Failed to create ticket: {e}")
                    failed += 1
        except Exception as e:
            logger.error(f"Failed to process alert: {e}")
            failed += 1
    
    # Summary
    logger.info(
        f"Processing complete: {created} created, {skipped} skipped (duplicates), "
        f"{failed} failed"
    )
    
    if failed > 0:
        return 3
    elif created == 0 and skipped > 0:
        return 4  # All were duplicates
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
