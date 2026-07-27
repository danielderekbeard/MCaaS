#!/usr/bin/env python3
"""
Multi-Channel Alert Distribution Webhook

Receives security alerts and distributes them to multiple channels:
- Microsoft Teams (via webhook connector)
- Slack (via webhook)
- PagerDuty (via Events API v2)
- Email (via SMTP)

Environment Variables:
    TEAMS_WEBHOOK_URL: Microsoft Teams webhook URL
    SLACK_WEBHOOK_URL: Slack webhook URL
    PAGERDUTY_ROUTING_KEY: PagerDuty Events API routing key
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS: Email configuration
    SOC_EMAIL: SOC team email for critical alerts
    LISTEN_PORT: HTTP server port (default: 8081)

Usage:
    python webhook_handler.py
    curl -X POST http://localhost:8081/webhook/alert -H "Content-Type: application/json" -d '{...}'
"""

import argparse
import hashlib
import json
import logging
import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AlertSeverity:
    """Alert severity levels and routing rules."""
    level: int
    name: str
    teams: bool
    slack: bool
    pagerduty: bool
    email: bool


class SeverityConfig:
    """Severity-based routing configuration."""
    
    # Level: (name, teams, slack, pagerduty, email)
    SEVERITIES = {
        1: AlertSeverity(1, "info", False, False, False, False),
        3: AlertSeverity(3, "low", False, True, False, False),
        5: AlertSeverity(5, "medium", True, True, False, True),
        7: AlertSeverity(7, "high", True, True, True, True),
        10: AlertSeverity(10, "critical", True, True, True, True),
    }
    
    @classmethod
    def get_severity(cls, level: int) -> AlertSeverity:
        """Get severity config for alert level."""
        for threshold in sorted(cls.SEVERITIES.keys(), reverse=True):
            if level >= threshold:
                return cls.SEVERITIES[threshold]
        return cls.SEVERITIES[1]


class TeamsNotifier:
    """Send notifications to Microsoft Teams."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send(self, alert: Dict) -> bool:
        """Send alert to Teams channel."""
        rule = alert.get('rule', {})
        agent = alert.get('agent', {})
        level = rule.get('level', 0)
        
        # Determine color based on severity
        color = "green" if level < 5 else "yellow" if level < 7 else "red"
        
        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": color,
            "summary": f"Security Alert: {rule.get('description', 'Unknown')}",
            "sections": [
                {
                    "activityTitle": f"🚨 {rule.get('description', 'Security Alert')}",
                    "activitySubtitle": f"Agent: {agent.get('name', 'Unknown')}",
                    "facts": [
                        {"name": "Rule ID:", "value": str(rule.get('id', 'N/A'))},
                        {"name": "Severity:", "value": f"Level {level}"},
                        {"name": "Agent ID:", "value": agent.get('id', 'N/A')},
                        {"name": "Timestamp:", "value": alert.get('timestamp', 'N/A')}
                    ],
                    "markdown": True
                }
            ]
        }
        
        if level >= 7:
            card["potentialAction"] = [
                {
                    "@type": "OpenUri",
                    "name": "View in Wazuh",
                    "targets": [{"os": "default", "uri": "https://deimos.mcaas.example.com"}]
                }
            ]
        
        try:
            response = requests.post(
                self.webhook_url,
                json=card,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Teams notification sent for rule {rule.get('id')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Teams notification: {e}")
            return False


class SlackNotifier:
    """Send notifications to Slack."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send(self, alert: Dict) -> bool:
        """Send alert to Slack channel."""
        rule = alert.get('rule', {})
        agent = alert.get('agent', {})
        level = rule.get('level', 0)
        
        # Determine emoji based on severity
        emoji = "🟢" if level < 5 else "🟡" if level < 7 else "🔴"
        
        payload = {
            "text": f"{emoji} *Security Alert*",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} Security Alert"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Rule:*\n{rule.get('description', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Level:*\n{level}"},
                        {"type": "mrkdwn", "text": f"*Agent:*\n{agent.get('name', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Time:*\n{alert.get('timestamp', 'N/A')}"}
                    ]
                }
            ]
        }
        
        if level >= 7:
            payload["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Raw Log:*\n```" + alert.get('full_log', 'N/A')[:500] + "```"
                }
            })
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Slack notification sent for rule {rule.get('id')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False


class PagerDutyNotifier:
    """Send alerts to PagerDuty."""
    
    def __init__(self, routing_key: str):
        self.routing_key = routing_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"
    
    def send(self, alert: Dict) -> bool:
        """Trigger PagerDuty incident."""
        rule = alert.get('rule', {})
        agent = alert.get('agent', {})
        level = rule.get('level', 0)
        
        severity = "critical" if level >= 10 else "error" if level >= 7 else "warning"
        
        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": f"wazuh-{rule.get('id')}-{agent.get('id')}",
            "payload": {
                "summary": f"Wazuh Alert: {rule.get('description', 'Security Alert')}",
                "severity": severity,
                "source": agent.get('name', 'Unknown'),
                "component": "Wazuh SIEM",
                "group": "Security Alerts",
                "class": rule.get('groups', ['unknown'])[0] if rule.get('groups') else 'unknown',
                "custom_details": {
                    "rule_id": rule.get('id'),
                    "rule_level": level,
                    "agent_id": agent.get('id'),
                    "agent_name": agent.get('name'),
                    "location": alert.get('location'),
                    "full_log": alert.get('full_log', 'N/A')[:1000]
                }
            }
        }
        
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"PagerDuty incident triggered for rule {rule.get('id')}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to trigger PagerDuty: {e}")
            return False


class EmailNotifier:
    """Send email notifications."""
    
    def __init__(self, smtp_host: str, smtp_port: int, smtp_user: str,
                 smtp_pass: str, from_addr: str, to_addr: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.from_addr = from_addr
        self.to_addr = to_addr
    
    def send(self, alert: Dict) -> bool:
        """Send email alert."""
        rule = alert.get('rule', {})
        agent = alert.get('agent', {})
        level = rule.get('level', 0)
        
        subject = f"[Wazuh Alert Level {level}] {rule.get('description', 'Security Alert')}"
        
        body = f"""
Security Alert from Wazuh SIEM

Alert Details:
- Rule ID: {rule.get('id', 'N/A')}
- Description: {rule.get('description', 'N/A')}
- Level: {level}

Source Information:
- Agent: {agent.get('name', 'Unknown')} ({agent.get('id', 'Unknown')})
- Location: {alert.get('location', 'N/A')}
- Timestamp: {alert.get('timestamp', 'N/A')}

Raw Log:
{alert.get('full_log', 'N/A')}

---
This alert was generated automatically by MCaaS.
"""
        
        msg = MIMEMultipart()
        msg['From'] = self.from_addr
        msg['To'] = self.to_addr
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)
            server.quit()
            logger.info(f"Email sent for rule {rule.get('id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class AlertDistributor:
    """Distribute alerts to multiple channels based on severity."""
    
    def __init__(self):
        self.teams = None
        self.slack = None
        self.pagerduty = None
        self.email = None
        
        # Initialize notifiers from environment
        if os.environ.get('TEAMS_WEBHOOK_URL'):
            self.teams = TeamsNotifier(os.environ['TEAMS_WEBHOOK_URL'])
        
        if os.environ.get('SLACK_WEBHOOK_URL'):
            self.slack = SlackNotifier(os.environ['SLACK_WEBHOOK_URL'])
        
        if os.environ.get('PAGERDUTY_ROUTING_KEY'):
            self.pagerduty = PagerDutyNotifier(os.environ['PAGERDUTY_ROUTING_KEY'])
        
        if all(os.environ.get(k) for k in ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASS', 'SOC_EMAIL']):
            self.email = EmailNotifier(
                smtp_host=os.environ['SMTP_HOST'],
                smtp_port=int(os.environ.get('SMTP_PORT', '587')),
                smtp_user=os.environ['SMTP_USER'],
                smtp_pass=os.environ['SMTP_PASS'],
                from_addr=os.environ.get('SMTP_FROM', os.environ['SMTP_USER']),
                to_addr=os.environ['SOC_EMAIL']
            )
    
    def distribute(self, alert: Dict) -> Dict[str, bool]:
        """Distribute alert to configured channels."""
        rule = alert.get('rule', {})
        level = rule.get('level', 0)
        
        severity = SeverityConfig.get_severity(level)
        results = {}
        
        if severity.teams and self.teams:
            results['teams'] = self.teams.send(alert)
        
        if severity.slack and self.slack:
            results['slack'] = self.slack.send(alert)
        
        if severity.pagerduty and self.pagerduty:
            results['pagerduty'] = self.pagerduty.send(alert)
        
        if severity.email and self.email:
            results['email'] = self.email.send(alert)
        
        return results


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for alert webhook."""
    
    distributor = AlertDistributor()
    
    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")
    
    def _send_response(self, status_code: int, data: Dict = None):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if data:
            self.wfile.write(json.dumps(data).encode())
    
    def do_GET(self):
        if self.path == '/health':
            self._send_response(200, {'status': 'healthy', 'service': 'multi-channel-alert-distributor'})
        else:
            self._send_response(404, {'error': 'Not found'})
    
    def do_POST(self):
        if self.path == '/webhook/alert':
            self._handle_alert()
        else:
            self._send_response(404, {'error': 'Not found'})
    
    def _handle_alert(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_response(400, {'error': 'Empty request body'})
            return
        
        try:
            body = self.rfile.read(content_length).decode('utf-8')
            alert = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse request: {e}")
            self._send_response(400, {'error': f'Invalid JSON: {e}'})
            return
        
        logger.info(f"Processing alert: {alert.get('rule', {}).get('description', 'Unknown')}")
        
        results = self.distributor.distribute(alert)
        
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        
        self._send_response(200, {
            'status': 'processed',
            'channels_notified': success_count,
            'total_channels': total_count,
            'results': results
        })


def run_server(port: int = 8081):
    server = HTTPServer(('', port), WebhookHandler)
    logger.info(f"Starting multi-channel alert distributor on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description='Multi-channel alert distributor')
    parser.add_argument('--port', type=int, default=8081, help='Server port')
    parser.add_argument('--test', action='store_true', help='Test with sample alert')
    args = parser.parse_args()
    
    if args.test:
        test_alert = {
            "rule": {"id": "100001", "description": "Test Critical Alert", "level": 10},
            "agent": {"name": "test-server", "id": "001"},
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "full_log": "Test alert for verification"
        }
        distributor = AlertDistributor()
        results = distributor.distribute(test_alert)
        print(json.dumps(results, indent=2))
        return
    
    run_server(args.port)


if __name__ == '__main__':
    main()
