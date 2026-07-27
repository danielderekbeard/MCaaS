# MCaaS Platform - Integration Research Report

**Research Date:** 2026-07-27  
**Researcher:** MCaaS Research Agent  
**Scope:** Integration architecture for Managed Compliance as a Service platform

---

## Executive Summary

This report provides comprehensive research findings on four key integration areas for the MCaaS platform:

1. **Shuffle SOAR** - Workflow automation and security orchestration
2. **Zammad** - Ticket management and incident tracking
3. **CISO Assistant** - Compliance mapping and GRC automation
4. **Threat Intelligence APIs** - Alert enrichment (VirusTotal, AbuseIPDB, MISP)

---

## 1. Shuffle SOAR Integration

### Overview
Shuffle is an open-source SOAR (Security Orchestration, Automation and Response) platform that provides workflow automation for security operations. It enables integration with various security tools through a visual workflow builder.

### Key Integration Capabilities

#### Available Actions Categories:
- **Communication**: Email (Gmail, Outlook, Exchange), Slack, Discord, Microsoft Teams
- **SIEM/Log Management**: Splunk, Elastic, Datadog, Chronicle
- **Ticketing**: ServiceNow, Jira, Zendesk, Zammad
- **Threat Intelligence**: VirusTotal, AbuseIPDB, MISP, AlienVault OTX
- **Cloud Security**: AWS, Azure, GCP security operations
- **Identity & Access**: Active Directory, Okta, Azure AD
- **Network Security**: Firewalls, EDR platforms, vulnerability scanners
- **Data Enrichment**: URLScan, Shodan, IPinfo

#### Enhancement Options for MCaaS:

| Action Category | Recommended Actions | Use Case |
|----------------|---------------------|----------|
| **Compliance Checks** | Custom Python scripts | Validate controls against frameworks |
| **Evidence Collection** | File operations, API calls | Gather compliance evidence |
| **Notification** | Email, Slack, Teams | Alert stakeholders |
| **Ticketing** | Create/Update tickets | Track compliance tasks |
| **Reporting** | Generate PDF/HTML reports | Compliance dashboards |

### Authentication Methods
- **API Keys**: Most integrations use API key authentication
- **OAuth 2.0**: For Microsoft, Google, and cloud platforms
- **Basic Auth**: Legacy systems support
- **Bearer Tokens**: Modern REST APIs

### Integration Architecture Recommendation

```
MCaaS Platform → Shuffle SOAR → Integrated Security Tools
                     ↓
              Workflow Triggers
                     ↓
    ┌──────────┬──────────┬──────────┐
    │ SIEM     │ Ticketing│ Threat   │
    │ Tools    │ Systems  │ Intel    │
    └──────────┴──────────┴──────────┘
```

### Code Example - Shuffle Workflow Trigger

```python
import requests
import json

def trigger_shuffle_workflow(webhook_url, workflow_data):
    """
    Trigger a Shuffle workflow via webhook
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {shuffle_api_key}"
    }
    
    payload = {
        "action": "compliance_check",
        "framework": workflow_data.get("framework"),
        "control_id": workflow_data.get("control_id"),
        "severity": workflow_data.get("severity", "medium"),
        "metadata": workflow_data.get("metadata", {})
    }
    
    response = requests.post(
        webhook_url,
        headers=headers,
        json=payload,
        timeout=30
    )
    
    return response.json()
```

---

## 2. Zammad API for Ticket Automation

### Overview
Zammad provides a comprehensive REST API that allows all UI operations to be performed programmatically. It's particularly well-suited for incident management and compliance ticketing workflows.

### API Documentation Summary

**Base URL:** `https://{your-zammad-instance}/api/v1`

#### Authentication Methods

| Method | Header Format | Security Level |
|--------|--------------|----------------|
| **Access Token** | `Authorization: Token token={token}` | Recommended |
| **OAuth 2.0** | `Authorization: Bearer {token}` | Best for apps |
| **Basic Auth** | `-u {username}:{password}` | Legacy only |

#### Key Endpoints for MCaaS

##### Tickets
- `GET /api/v1/tickets` - List all tickets
- `GET /api/v1/tickets/{id}` - Get specific ticket
- `POST /api/v1/tickets` - Create ticket
- `PUT /api/v1/tickets/{id}` - Update ticket
- `GET /api/v1/tickets/search?query={search}` - Search tickets

##### Ticket Articles (Comments/Updates)
- `GET /api/v1/ticket_articles/by_ticket/{ticket_id}` - List articles
- `POST /api/v1/ticket_articles` - Add article/comment
- `GET /api/v1/ticket_attachment/{ticket_id}/{article_id}/{attachment_id}` - Download attachments

##### Tags
- `GET /api/v1/tags?object=Ticket&o_id={ticket_id}` - List tags
- `POST /api/v1/tags/add` - Add tag to ticket
- `DELETE /api/v1/tags/remove` - Remove tag from ticket

##### Users
- `GET /api/v1/users` - List users
- `POST /api/v1/users` - Create user
- `GET /api/v1/users/search?query={email}` - Search users

### Rate Limits
- **Pagination**: Use `page` and `per_page` parameters
- **Max Results**: Hard limits apply; use `with_total_count` for totals
- **Expand**: Add `?expand=true` for resolved relation names

### Code Examples

#### Create Compliance Ticket

```python
import requests
import json

class ZammadClient:
    def __init__(self, base_url, api_token):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Token token={api_token}",
            "Content-Type": "application/json"
        }
    
    def create_compliance_ticket(self, title, customer_email, 
                                  priority_id=2, group_id=1,
                                  custom_fields=None):
        """
        Create a compliance-related ticket
        
        Priority IDs: 1=low, 2=normal, 3=high
        Group IDs: Depends on your Zammad setup
        """
        ticket_data = {
            "title": title,
            "group_id": group_id,
            "priority_id": priority_id,
            "state_id": 1,  # new
            "customer_id": "guess:" + customer_email,
            "article": {
                "subject": title,
                "body": f"Compliance ticket created for {title}",
                "type": "note",
                "internal": False,
                "sender": "Agent"
            }
        }
        
        if custom_fields:
            ticket_data.update(custom_fields)
        
        response = requests.post(
            f"{self.base_url}/api/v1/tickets",
            headers=self.headers,
            json=ticket_data
        )
        
        return response.json()
    
    def add_article(self, ticket_id, body, article_type="note", 
                    internal=False, attachments=None):
        """Add an article/comment to a ticket"""
        article_data = {
            "ticket_id": ticket_id,
            "body": body,
            "content_type": "text/html",
            "type": article_type,
            "internal": internal,
            "sender": "Agent"
        }
        
        if attachments:
            article_data["attachments"] = attachments
        
        response = requests.post(
            f"{self.base_url}/api/v1/ticket_articles",
            headers=self.headers,
            json=article_data
        )
        
        return response.json()
    
    def add_tag(self, ticket_id, tag_name):
        """Add a tag to a ticket"""
        tag_data = {
            "item": tag_name,
            "object": "Ticket",
            "o_id": ticket_id
        }
        
        response = requests.post(
            f"{self.base_url}/api/v1/tags/add",
            headers=self.headers,
            json=tag_data
        )
        
        return response.json()
    
    def search_tickets(self, query, expand=True):
        """Search tickets by query string"""
        params = {"query": query}
        if expand:
            params["expand"] = "true"
        
        response = requests.get(
            f"{self.base_url}/api/v1/tickets/search",
            headers=self.headers,
            params=params
        )
        
        return response.json()

# Usage example
zammad = ZammadClient("https://tickets.yourdomain.com", "your_api_token")

# Create compliance ticket
ticket = zammad.create_compliance_ticket(
    title="ISO 27001 - A.12.3.1 Control Review Required",
    customer_email="security@company.com",
    priority_id=3,  # high
    group_id=2      # Security team
)

# Add compliance evidence as article
zammad.add_article(
    ticket_id=ticket["id"],
    body="Evidence reviewed: Backup logs confirm daily backups executed",
    article_type="note",
    internal=True
)

# Tag with compliance framework
zammad.add_tag(ticket["id"], "ISO27001")
zammad.add_tag(ticket["id"], "A.12.3.1")
```

#### Ticket States Reference

| State ID | State | Description |
|----------|-------|-------------|
| 1 | new | New ticket |
| 2 | open | Open/assigned |
| 3 | pending reminder | Waiting for response |
| 4 | closed | Closed ticket |
| 5 | merged | Merged with another |

---

## 3. CISO Assistant API for Compliance Mapping

### Overview
CISO Assistant is an open-source GRC platform supporting 150+ compliance frameworks with automatic control mapping. It provides a comprehensive REST API for automation.

### Key Capabilities

#### Supported Frameworks (167+)
- **International**: ISO 27001:2022, ISO 22301, ISO 42001 (AI)
- **US**: NIST CSF v2.0, SOC 2, PCI DSS 4.0, CMMC v2, HIPAA
- **EU**: NIS2, DORA, GDPR, Cyber Resilience Act, EU AI Act
- **Industry-Specific**: TISAX (automotive), HDS (healthcare), FedRAMP
- **Technical**: CIS Controls v8, CSA CCM, OWASP ASVS/MASVS

#### Core API Features
- **REST API**: Full CRUD operations
- **CLI**: Command-line interface for automation
- **Kafka Integration**: Event streaming
- **MCP Support**: Model Context Protocol
- **Outgoing Webhooks**: Real-time notifications

### API Authentication
- **Token-based**: API tokens per user
- **SSO**: SAML/OIDC integration
- **MFA**: TOTP and security keys
- **RBAC**: Granular permissions

### Architecture Recommendations

```
MCaaS Compliance Engine
        ↓
CISO Assistant API
        ↓
┌─────────────┬─────────────┬─────────────┐
│ Frameworks  │ Controls    │ Risk        │
│ Library     │ Mapping     │ Assessment  │
└─────────────┴─────────────┴─────────────┘
```

### Integration Points

#### 1. Automatic Framework Loading
```python
# Upload custom framework from Excel/ YAML
# CISO Assistant supports custom DSL for framework definition
```

#### 2. Compliance Assessment Workflow
```python
# Create compliance assessment
# Map controls to assets
# Track evidence collection
# Generate compliance reports
```

#### 3. Risk Management Integration
```python
# Import risk assessments
# Link risks to controls
# Track risk treatment
# Calculate residual risk
```

### Example: Compliance Mapping Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    MCaaS Platform                          │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              CISO Assistant API                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Framework│  │ Controls │  │ Evidence │                  │
│  │ Library  │  │ Mapping  │  │ Mgmt     │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Output: Compliance Reports                  │
│  - Framework gap analysis                                  │
│  - Control implementation status                           │
│  - Evidence collection status                              │
│  - Risk-based compliance scoring                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Threat Intelligence APIs for Alert Enrichment

### Overview
Integrating threat intelligence APIs enables MCaaS to enrich security alerts with reputation data, context, and actionable intelligence.

### API Comparison Matrix

| Feature | VirusTotal v3 | AbuseIPDB v2 | MISP |
|---------|---------------|--------------|------|
| **API Type** | REST JSON | REST JSON | REST JSON |
| **Auth** | API Key (header) | API Key (header) | API Key + cert |
| **Rate Limit (Free)** | 4 req/min | 1,000/day | Self-hosted |
| **Coverage** | Files, URLs, IPs, Domains | IPs | IOCs, Events |
| **Response Format** | JSON:API | JSON | STIX/MISP JSON |
| **Real-time** | Yes | Yes | Yes |
| **Commercial Tier** | Enterprise available | Premium available | Open source |

### VirusTotal v3 API

#### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v3/files/{hash}` | GET | Get file report by hash |
| `/api/v3/files` | POST | Upload file for scanning |
| `/api/v3/urls/{id}` | GET | Get URL analysis report |
| `/api/v3/urls` | POST | Submit URL for scanning |
| `/api/v3/domains/{domain}` | GET | Get domain report |
| `/api/v3/ip_addresses/{ip}` | GET | Get IP address report |

#### Authentication
```
Header: x-apikey: {your_api_key}
```

#### Code Example

```python
import requests
import json
import hashlib

class VirusTotalClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://www.virustotal.com/api/v3"
        self.headers = {
            "x-apikey": api_key,
            "Accept": "application/json"
        }
    
    def get_ip_report(self, ip_address):
        """Get reputation report for an IP address"""
        response = requests.get(
            f"{self.base_url}/ip_addresses/{ip_address}",
            headers=self.headers,
            timeout=30
        )
        return response.json()
    
    def get_domain_report(self, domain):
        """Get reputation report for a domain"""
        response = requests.get(
            f"{self.base_url}/domains/{domain}",
            headers=self.headers,
            timeout=30
        )
        return response.json()
    
    def get_file_report(self, file_hash):
        """Get report for file by hash (MD5, SHA1, SHA256)"""
        response = requests.get(
            f"{self.base_url}/files/{file_hash}",
            headers=self.headers,
            timeout=30
        )
        return response.json()
    
    def scan_url(self, url):
        """Submit URL for analysis"""
        data = {"url": url}
        response = requests.post(
            f"{self.base_url}/urls",
            headers=self.headers,
            data=data,
            timeout=30
        )
        return response.json()
    
    def scan_file(self, file_path):
        """Upload file for analysis"""
        with open(file_path, 'rb') as f:
            files = {'file': (file_path, f)}
            response = requests.post(
                f"{self.base_url}/files",
                headers=self.headers,
                files=files,
                timeout=120
            )
        return response.json()
    
    def analyze_alert(self, ioc_type, ioc_value):
        """
        Analyze an IOC and return enrichment data
        
        Returns dict with:
        - malicious_count: Number of detections
        - total_engines: Total scanners
        - reputation_score: Calculated score
        - last_analysis_date: When scanned
        - tags: Associated tags
        """
        try:
            if ioc_type == "ip":
                report = self.get_ip_report(ioc_value)
            elif ioc_type == "domain":
                report = self.get_domain_report(ioc_value)
            elif ioc_type in ["md5", "sha1", "sha256"]:
                report = self.get_file_report(ioc_value)
            else:
                return {"error": "Unsupported IOC type"}
            
            data = report.get("data", {})
            attributes = data.get("attributes", {})
            last_analysis = attributes.get("last_analysis_stats", {})
            
            malicious = last_analysis.get("malicious", 0)
            suspicious = last_analysis.get("suspicious", 0)
            total = sum(last_analysis.values()) if last_analysis else 0
            
            return {
                "malicious_count": malicious + suspicious,
                "total_engines": total,
                "reputation_score": (malicious + suspicious) / total * 100 if total > 0 else 0,
                "last_analysis_date": attributes.get("last_analysis_date"),
                "tags": attributes.get("tags", []),
                "raw_data": report
            }
            
        except Exception as e:
            return {"error": str(e)}

# Usage example
vt = VirusTotalClient("your_api_key_here")

# Enrich an IP alert
enrichment = vt.analyze_alert("ip", "8.8.8.8")
print(f"Reputation Score: {enrichment.get('reputation_score', 0):.2f}%")
```

### AbuseIPDB v2 API

#### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/check` | GET | Check IP reputation |
| `/api/v2/reports` | GET | Get detailed reports for IP |
| `/api/v2/blacklist` | GET | Download blacklist |
| `/api/v2/report` | POST | Report abusive IP |

#### Authentication
```
Header: Key: {your_api_key}
Header: Accept: application/json
```

#### Rate Limits
- **Free accounts**: 1,000 checks/reports per day
- **Webmaster accounts**: 3,000 requests/day
- **Report duplicates**: Same IP once per 15 minutes

#### Code Example

```python
import requests

class AbuseIPDBClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.abuseipdb.com/api/v2"
        self.headers = {
            "Key": api_key,
            "Accept": "application/json"
        }
    
    def check_ip(self, ip_address, max_age_days=90, verbose=True):
        """
        Check IP reputation
        
        Returns:
        - abuseConfidenceScore: 0-100 (higher = more abusive)
        - isWhitelisted: Whether IP is whitelisted
        - totalReports: Number of abuse reports
        - countryCode: Origin country
        - usageType: ISP/Hosting/etc
        - reports: Detailed reports (if verbose)
        """
        params = {
            "ipAddress": ip_address,
            "maxAgeInDays": max_age_days
        }
        if verbose:
            params["verbose"] = ""
        
        response = requests.get(
            f"{self.base_url}/check",
            headers=self.headers,
            params=params,
            timeout=30
        )
        
        return response.json()
    
    def get_blacklist(self, confidence_minimum=90, limit=10000):
        """Download blacklist of abusive IPs"""
        params = {
            "confidenceMinimum": confidence_minimum,
            "limit": limit
        }
        
        response = requests.get(
            f"{self.base_url}/blacklist",
            headers=self.headers,
            params=params,
            timeout=60
        )
        
        return response.json()
    
    def enrich_alert(self, ip_address):
        """
        Enrich an alert with AbuseIPDB data
        
        Returns standardized enrichment object
        """
        try:
            result = self.check_ip(ip_address)
            data = result.get("data", {})
            
            return {
                "ip": ip_address,
                "reputation_score": data.get("abuseConfidenceScore", 0),
                "is_whitelisted": data.get("isWhitelisted", False),
                "total_reports": data.get("totalReports", 0),
                "country": data.get("countryCode"),
                "country_name": data.get("countryName"),
                "isp": data.get("isp"),
                "usage_type": data.get("usageType"),
                "is_tor": data.get("isTor", False),
                "last_reported": data.get("lastReportedAt"),
                "reports": data.get("reports", []) if data.get("totalReports", 0) > 0 else [],
                "threat_level": self._calculate_threat_level(data)
            }
            
        except Exception as e:
            return {"error": str(e), "ip": ip_address}
    
    def _calculate_threat_level(self, data):
        """Calculate threat level from AbuseIPDB data"""
        score = data.get("abuseConfidenceScore", 0)
        
        if score >= 75:
            return "HIGH"
        elif score >= 50:
            return "MEDIUM"
        elif score >= 25:
            return "LOW"
        else:
            return "NONE"

# Usage example
abuseipdb = AbuseIPDBClient("your_api_key_here")

# Enrich alert
enrichment = abuseipdb.enrich_alert("118.25.6.39")
print(f"IP: {enrichment['ip']}")
print(f"Threat Level: {enrichment['threat_level']}")
print(f"Confidence Score: {enrichment['reputation_score']}%")
```

### MISP API

#### Overview
MISP (Malware Information Sharing Platform) is an open-source threat intelligence platform for sharing and storing information about malware, indicators of compromise, and security incidents.

#### Key Capabilities
- **Event Management**: Create/manage threat intelligence events
- **IOC Sharing**: Distribute indicators across organizations
- **Automated Correlation**: Link related IOCs
- **STIX/TAXII Support**: Industry-standard formats

#### Integration Approach
```python
import requests
import json

class MISPClient:
    def __init__(self, base_url, api_key, ssl_verify=True):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.ssl_verify = ssl_verify
    
    def search_ioc(self, ioc_value, ioc_type="ip-dst"):
        """
        Search for IOC in MISP
        
        ioc_types: ip-dst, ip-src, domain, md5, sha1, sha256, url, etc.
        """
        endpoint = f"{self.base_url}/events/restSearch"
        
        data = {
            "returnFormat": "json",
            "type": ioc_type,
            "value": ioc_value,
            "to_ids": True
        }
        
        response = requests.post(
            endpoint,
            headers=self.headers,
            json=data,
            verify=self.ssl_verify,
            timeout=30
        )
        
        return response.json()
    
    def get_event(self, event_id):
        """Get specific event details"""
        endpoint = f"{self.base_url}/events/view/{event_id}"
        
        response = requests.get(
            endpoint,
            headers=self.headers,
            verify=self.ssl_verify,
            timeout=30
        )
        
        return response.json()
    
    def create_event(self, info, distribution=0, threat_level_id=3):
        """
        Create new MISP event
        
        distribution: 0=your org only, 1=this community, 2=connected communities
        threat_level_id: 1=high, 2=medium, 3=low, 4=undefined
        """
        endpoint = f"{self.base_url}/events/add"
        
        data = {
            "Event": {
                "info": info,
                "distribution": distribution,
                "threat_level_id": threat_level_id,
                "analysis": 0,  # Initial
                "date": ""
            }
        }
        
        response = requests.post(
            endpoint,
            headers=self.headers,
            json=data,
            verify=self.ssl_verify,
            timeout=30
        )
        
        return response.json()
```

---

## Integration Architecture Recommendations

### Recommended Architecture

```
                    ┌─────────────────────────────────────┐
                    │         MCaaS Platform             │
                    │  ┌─────────┬─────────┬─────────┐  │
                    │  │ Alert   │ Comply  │ Report  │  │
                    │  │ Engine  │ Engine  │ Engine  │  │
                    │  └────┬────┴────┬────┴────┬────┘  │
                    └───────┼─────────┼─────────┼─────────┘
                            │         │         │
            ┌───────────────┘         │         └───────────────┐
            │                         │                         │
            ▼                         ▼                         ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  Shuffle SOAR     │    │  CISO Assistant   │    │  Threat Intel     │
│  ─────────────    │    │  ───────────────  │    │  ─────────────    │
│                   │    │                   │    │                   │
│ • Workflow Auto   │    │ • Framework Mgmt  │    │ • VirusTotal      │
│ • Incident Resp   │◄──►│ • Control Mapping │◄──►│ • AbuseIPDB       │
│ • Custom Actions  │    │ • Risk Assessment │    │ • MISP            │
│ • Integration Hub │    │ • Evidence Track  │    │ • Custom Feeds    │
└─────────┬─────────┘    └─────────┬─────────┘    └─────────┬─────────┘
          │                        │                        │
          ▼                        ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Zammad Ticketing                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │ Compliance│  │ Incident│  │ Evidence│  │ Review  │  │ Audit   │  │
│  │ Tickets   │  │ Tickets │  │ Tickets │  │ Tickets │  │ Tickets │  │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Alert Ingestion**: Security alerts enter MCaaS
2. **Threat Enrichment**: IPs/Hashes/URLs enriched via threat intel APIs
3. **Compliance Check**: CISO Assistant validates against frameworks
4. **Workflow Trigger**: Shuffle executes remediation workflows
5. **Ticket Creation**: Zammad tracks all activities

### Implementation Priority

| Priority | Integration | Effort | Value |
|----------|-------------|--------|-------|
| **P1** | Zammad Ticketing | Low | Critical for audit trail |
| **P1** | VirusTotal API | Low | Essential enrichment |
| **P2** | AbuseIPDB API | Low | Free IP intelligence |
| **P2** | CISO Assistant | Medium | Compliance automation |
| **P3** | Shuffle SOAR | Medium | Workflow orchestration |
| **P3** | MISP | High | Community intelligence |

### Security Considerations

1. **API Key Management**: Use secure vault (HashiCorp Vault, AWS Secrets Manager)
2. **Rate Limiting**: Implement exponential backoff
3. **Data Privacy**: Sanitize data before external API calls
4. **TLS**: All communications must use TLS 1.2+
5. **Authentication**: Prefer OAuth 2.0 over API keys when available

---

## Appendix: Quick Reference

### API Response Time Expectations

| Service | Typical Response Time |
|---------|----------------------|
| VirusTotal | 500ms - 2s |
| AbuseIPDB | 200ms - 1s |
| Zammad | 100ms - 500ms |
| MISP | 200ms - 1s |
| CISO Assistant | 200ms - 1s |
| Shuffle | 1s - 5s (depends on workflow) |

### Error Handling Best Practices

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session_with_retries():
    """Create requests session with retry logic"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session
```

---

*Report generated by MCaaS Research Agent*  
*For questions or updates, consult the main agent session*
