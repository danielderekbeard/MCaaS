#!/usr/bin/env python3
"""
Zammad Ticketing Integration for MCaaS Platform

This module provides comprehensive integration with Zammad's REST API
for compliance ticketing, incident tracking, and evidence management.

Author: MCaaS Research Agent
Date: 2026-07-27

API Docs: https://docs.zammad.org/en/latest/api/intro.html
"""

import os
import json
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TicketState(Enum):
    """Zammad ticket states"""
    NEW = 1
    OPEN = 2
    PENDING_REMINDER = 3
    CLOSED = 4
    MERGED = 5


class TicketPriority(Enum):
    """Zammad ticket priorities"""
    LOW = 1
    NORMAL = 2
    HIGH = 3


class ArticleType(Enum):
    """Zammad article types"""
    EMAIL = "email"
    PHONE = "phone"
    WEB = "web"
    NOTE = "note"
    SMS = "sms"
    CHAT = "chat"


class SenderType(Enum):
    """Zammad sender types"""
    AGENT = "Agent"
    CUSTOMER = "Customer"
    SYSTEM = "System"


@dataclass
class Ticket:
    """Zammad ticket data structure"""
    id: int
    title: str
    state_id: int
    priority_id: int
    group_id: int
    customer_id: int
    owner_id: Optional[int]
    number: str
    created_at: str
    updated_at: str


class ZammadClient:
    """
    Zammad REST API Client
    
    Supports authentication via:
    - Access Token (recommended)
    - OAuth 2.0
    - Basic Auth (legacy)
    """
    
    def __init__(self, base_url: str, api_token: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Zammad client
        
        Args:
            base_url: Zammad instance URL (e.g., https://tickets.example.com)
            api_token: API access token (preferred auth method)
            username: Username for basic auth
            password: Password for basic auth
        """
        self.base_url = base_url.rstrip('/')
        self.session = self._create_session()
        
        # Set up authentication
        if api_token:
            self.session.headers.update({
                "Authorization": f"Token token={api_token}",
                "Content-Type": "application/json"
            })
        elif username and password:
            self.session.auth = (username, password)
            self.session.headers.update({"Content-Type": "application/json"})
        else:
            raise ValueError("Must provide either api_token or username/password")
    
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
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make API request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            if response.status_code == 204:
                return {}
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Zammad API error: {e}")
            raise
    
    # ============== TICKET OPERATIONS ==============
    
    def create_ticket(self, title: str, customer_email: str,
                      group_id: int = 1, priority_id: int = 2,
                      state_id: int = 1, owner_id: Optional[int] = None,
                      article_body: str = "", article_subject: str = "",
                      article_type: str = "note", internal: bool = False,
                      custom_fields: Optional[Dict] = None) -> Dict:
        """
        Create a new ticket
        
        Args:
            title: Ticket title
            customer_email: Customer email (creates user if not exists)
            group_id: Group ID (default: 1)
            priority_id: Priority ID 1=low, 2=normal, 3=high
            state_id: State ID (1=new, 2=open, etc.)
            owner_id: Owner user ID (optional)
            article_body: Initial article body
            article_subject: Initial article subject
            article_type: Article type (note, email, phone, etc.)
            internal: Whether article is internal only
            custom_fields: Custom field values
        """
        ticket_data = {
            "title": title,
            "group_id": group_id,
            "priority_id": priority_id,
            "state_id": state_id,
            "customer_id": f"guess:{customer_email}",  # Auto-create user
            "article": {
                "subject": article_subject or title,
                "body": article_body or title,
                "content_type": "text/html",
                "type": article_type,
                "internal": internal,
                "sender": "Agent"
            }
        }
        
        if owner_id:
            ticket_data["owner_id"] = owner_id
        
        if custom_fields:
            ticket_data.update(custom_fields)
        
        return self._request("POST", "/tickets", json=ticket_data)
    
    def get_ticket(self, ticket_id: int, expand: bool = True) -> Dict:
        """Get ticket by ID"""
        params = {"expand": "true"} if expand else {}
        return self._request("GET", f"/tickets/{ticket_id}", params=params)
    
    def update_ticket(self, ticket_id: int, **updates) -> Dict:
        """Update ticket fields"""
        return self._request("PUT", f"/tickets/{ticket_id}", json=updates)
    
    def search_tickets(self, query: str, expand: bool = True) -> List[Dict]:
        """
        Search tickets using Zammad query syntax
        
        Query examples:
        - "state:new" - All new tickets
        - "priority:high" - High priority tickets
        - "tag:compliance" - Tickets with compliance tag
        - "owner_id:1" - Tickets owned by user ID 1
        """
        params = {"query": query}
        if expand:
            params["expand"] = "true"
        
        return self._request("GET", "/tickets/search", params=params)
    
    def list_tickets(self, page: int = 1, per_page: int = 50) -> List[Dict]:
        """List tickets with pagination"""
        params = {"page": page, "per_page": per_page}
        return self._request("GET", "/tickets", params=params)
    
    def close_ticket(self, ticket_id: int) -> Dict:
        """Close a ticket"""
        return self.update_ticket(ticket_id, state_id=TicketState.CLOSED.value)
    
    # ============== ARTICLE OPERATIONS ==============
    
    def add_article(self, ticket_id: int, body: str,
                    subject: str = "", article_type: str = "note",
                    internal: bool = False, sender: str = "Agent",
                    time_unit: Optional[str] = None,
                    attachments: Optional[List[Dict]] = None) -> Dict:
        """
        Add an article/comment to a ticket
        
        Args:
            ticket_id: Ticket ID
            body: Article body (HTML supported)
            subject: Article subject
            article_type: Type (note, email, phone, etc.)
            internal: Whether article is internal only
            sender: Sender type (Agent, Customer, System)
            time_unit: Time spent (e.g., "15" for 15 minutes)
            attachments: List of attachment dicts with filename, data, mime-type
        """
        article_data = {
            "ticket_id": ticket_id,
            "body": body,
            "content_type": "text/html",
            "type": article_type,
            "internal": internal,
            "sender": sender
        }
        
        if subject:
            article_data["subject"] = subject
        
        if time_unit:
            article_data["time_unit"] = time_unit
        
        if attachments:
            article_data["attachments"] = attachments
        
        return self._request("POST", "/ticket_articles", json=article_data)
    
    def get_articles(self, ticket_id: int) -> List[Dict]:
        """Get all articles for a ticket"""
        return self._request("GET", f"/ticket_articles/by_ticket/{ticket_id}")
    
    def get_article(self, article_id: int) -> Dict:
        """Get specific article"""
        return self._request("GET", f"/ticket_articles/{article_id}")
    
    def download_attachment(self, ticket_id: int, article_id: int, 
                          attachment_id: int) -> bytes:
        """Download attachment binary data"""
        endpoint = f"/ticket_attachment/{ticket_id}/{article_id}/{attachment_id}"
        url = f"{self.base_url}/api/v1{endpoint}"
        
        response = self.session.get(url)
        response.raise_for_status()
        return response.content
    
    # ============== TAG OPERATIONS ==============
    
    def get_ticket_tags(self, ticket_id: int) -> List[str]:
        """Get tags for a ticket"""
        params = {"object": "Ticket", "o_id": ticket_id}
        result = self._request("GET", "/tags", params=params)
        return result.get("tags", [])
    
    def add_tag(self, ticket_id: int, tag_name: str) -> bool:
        """Add tag to ticket"""
        data = {
            "item": tag_name,
            "object": "Ticket",
            "o_id": ticket_id
        }
        result = self._request("POST", "/tags/add", json=data)
        return result is True
    
    def remove_tag(self, ticket_id: int, tag_name: str) -> bool:
        """Remove tag from ticket"""
        data = {
            "item": tag_name,
            "object": "Ticket",
            "o_id": ticket_id
        }
        result = self._request("DELETE", "/tags/remove", json=data)
        return result is True
    
    # ============== USER OPERATIONS ==============
    
    def get_user(self, user_id: int) -> Dict:
        """Get user by ID"""
        return self._request("GET", f"/users/{user_id}")
    
    def search_users(self, query: str) -> List[Dict]:
        """Search users"""
        params = {"query": query}
        return self._request("GET", "/users/search", params=params)
    
    def create_user(self, email: str, firstname: str, lastname: str,
                   organization_id: Optional[int] = None,
                   roles: Optional[List[str]] = None) -> Dict:
        """Create a new user"""
        user_data = {
            "email": email,
            "firstname": firstname,
            "lastname": lastname
        }
        
        if organization_id:
            user_data["organization_id"] = organization_id
        
        if roles:
            user_data["role_ids"] = roles
        
        return self._request("POST", "/users", json=user_data)
    
    # ============== GROUP OPERATIONS ==============
    
    def list_groups(self) -> List[Dict]:
        """List all groups"""
        return self._request("GET", "/groups")
    
    def get_group(self, group_id: int) -> Dict:
        """Get group by ID"""
        return self._request("GET", f"/groups/{group_id}")
    
    # ============== COMPLIANCE SPECIFIC METHODS ==============
    
    def create_compliance_ticket(self, framework: str, control_id: str,
                                  title: str, description: str,
                                  customer_email: str = "compliance@company.com",
                                  priority: str = "normal",
                                  evidence_required: bool = True) -> Dict:
        """
        Create a compliance-specific ticket
        
        Args:
            framework: Compliance framework (e.g., "ISO27001", "SOC2")
            control_id: Control identifier (e.g., "A.12.3.1")
            title: Ticket title
            description: Detailed description
            customer_email: Contact email
            priority: Ticket priority (low, normal, high)
            evidence_required: Whether evidence collection is needed
        """
        priority_map = {
            "low": TicketPriority.LOW.value,
            "normal": TicketPriority.NORMAL.value,
            "high": TicketPriority.HIGH.value
        }
        
        full_title = f"[{framework}] {control_id}: {title}"
        
        ticket = self.create_ticket(
            title=full_title,
            customer_email=customer_email,
            priority_id=priority_map.get(priority, 2),
            article_body=description,
            article_subject=f"Compliance Control Review: {control_id}"
        )
        
        # Add framework and control tags
        ticket_id = ticket.get("id")
        if ticket_id:
            self.add_tag(ticket_id, framework)
            self.add_tag(ticket_id, f"control-{control_id}")
            self.add_tag(ticket_id, "compliance")
            
            if evidence_required:
                self.add_tag(ticket_id, "evidence-required")
        
        return ticket
    
    def add_evidence(self, ticket_id: int, evidence_description: str,
                     evidence_data: Optional[str] = None,
                     evidence_file_path: Optional[str] = None,
                     collector: str = "system") -> Dict:
        """
        Add evidence to a compliance ticket
        
        Args:
            ticket_id: Ticket ID
            evidence_description: Description of evidence
            evidence_data: Base64 encoded evidence data
            evidence_file_path: Path to evidence file
            collector: Who/what collected the evidence
        """
        attachments = []
        
        # Handle file attachment
        if evidence_file_path and os.path.exists(evidence_file_path):
            with open(evidence_file_path, 'rb') as f:
                file_data = f.read()
                encoded = base64.b64encode(file_data).decode('utf-8')
                
                attachments.append({
                    "filename": os.path.basename(evidence_file_path),
                    "data": encoded,
                    "mime-type": "application/octet-stream"
                })
        
        # Handle base64 data
        elif evidence_data:
            attachments.append({
                "filename": "evidence.dat",
                "data": evidence_data,
                "mime-type": "application/octet-stream"
            })
        
        body = f"<b>Evidence collected by:</b> {collector}<br><br>"
        body += f"<b>Description:</b> {evidence_description}<br><br>"
        
        return self.add_article(
            ticket_id=ticket_id,
            body=body,
            subject="Evidence Submitted",
            article_type="note",
            internal=True,
            attachments=attachments if attachments else None
        )
    
    def get_compliance_tickets(self, framework: Optional[str] = None,
                                status: str = "open") -> List[Dict]:
        """
        Get compliance tickets
        
        Args:
            framework: Filter by framework (optional)
            status: Ticket status (open, closed, pending)
        """
        if framework:
            query = f"tag:compliance tag:{framework}"
        else:
            query = "tag:compliance"
        
        if status == "open":
            query += " state:new OR state:open OR state:pending"
        elif status == "closed":
            query += " state:closed"
        
        return self.search_tickets(query)
    
    def link_tickets(self, ticket_id: int, linked_ticket_id: int,
                     link_type: str = "Parent") -> Dict:
        """Link two tickets together"""
        link_data = {
            "link_type": link_type,
            "link_object_source": "Ticket",
            "link_object_target": "Ticket",
            "link_object_source_number": ticket_id,
            "link_object_target_number": linked_ticket_id
        }
        return self._request("POST", "/ticket_links", json=link_data)


# ============== EXAMPLE USAGE ==============

def example_usage():
    """Example of using the Zammad client for compliance workflows"""
    
    # Initialize client
    client = ZammadClient(
        base_url="https://tickets.yourdomain.com",
        api_token="your_api_token_here"
    )
    
    # Example 1: Create ISO 27001 compliance ticket
    ticket = client.create_compliance_ticket(
        framework="ISO27001",
        control_id="A.12.3.1",
        title="Information Backup - Review Required",
        description="""
        <h3>Control Review Required</h3>
        <p><b>Framework:</b> ISO 27001:2022</p>
        <p><b>Control:</b> A.12.3.1 - Information backup</p>
        <p><b>Requirement:</b> Backup copies of information, software and system images shall be maintained and regularly tested.</p>
        
        <h4>Action Required:</h4>
        <ul>
            <li>Verify backup schedules are configured</li>
            <li>Check backup restoration logs</li>
            <li>Validate backup integrity</li>
            <li>Update backup policy if needed</li>
        </ul>
        """,
        customer_email="security@company.com",
        priority="high",
        evidence_required=True
    )
    
    ticket_id = ticket.get("id")
    print(f"Created compliance ticket: {ticket.get('number')} (ID: {ticket_id})")
    
    # Example 2: Add evidence
    client.add_evidence(
        ticket_id=ticket_id,
        evidence_description="Backup logs from last 30 days showing successful daily backups",
        collector="Backup Monitoring System",
        evidence_file_path="/path/to/backup_logs.zip"
    )
    
    # Example 3: Add compliance review note
    client.add_article(
        ticket_id=ticket_id,
        body="""
        <h4>Compliance Review Completed</h4>
        <p>Reviewed backup configuration and logs:</p>
        <ul>
            <li>✓ Daily backups configured (02:00 UTC)</li>
            <li>✓ Last 7 restoration tests successful</li>
            <li>✓ Backup policy updated (v2.3)</li>
        </ul>
        <p><b>Status:</b> COMPLIANT</p>
        """,
        article_type="note",
        internal=True
    )
    
    # Example 4: Search for compliance tickets
    tickets = client.get_compliance_tickets(framework="ISO27001")
    print(f"Found {len(tickets)} ISO27001 tickets")
    
    # Example 5: Close ticket
    client.close_ticket(ticket_id)
    print("Ticket closed")


if __name__ == "__main__":
    # Run example (won't work without valid credentials)
    # example_usage()
    pass
