#!/usr/bin/env python3
"""
Threat Intelligence Integration Module for MCaaS Platform

This module provides unified threat intelligence enrichment for security alerts
by integrating VirusTotal, AbuseIPDB, and MISP APIs.

Author: MCaaS Research Agent
Date: 2026-07-27
"""

import os
import json
import time
import hashlib
import requests
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IOCType(Enum):
    """Supported IOC types"""
    IP = "ip"
    DOMAIN = "domain"
    URL = "url"
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"


class ThreatLevel(Enum):
    """Threat level classifications"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class EnrichmentResult:
    """Standardized enrichment result format"""
    ioc_type: str
    ioc_value: str
    source: str
    threat_level: str
    confidence_score: float
    malicious_count: int
    total_engines: int
    first_seen: Optional[str]
    last_seen: Optional[str]
    tags: List[str]
    raw_data: Dict
    enrichment_time: float


class BaseTIClient:
    """Base class for Threat Intelligence clients"""
    
    def __init__(self, api_key: str, base_url: str, rate_limit_per_min: int = 60):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.rate_limit_per_min = rate_limit_per_min
        self.session = self._create_session()
        self.last_request_time = 0
    
    def _create_session(self) -> requests.Session:
        """Create session with retry logic"""
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
    
    def _rate_limit(self):
        """Implement rate limiting"""
        min_interval = 60.0 / self.rate_limit_per_min
        elapsed = time.time() - self.last_request_time
        
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


class VirusTotalClient(BaseTIClient):
    """
    VirusTotal v3 API Client
    
    API Docs: https://developers.virustotal.com/v3.0/reference
    """
    
    def __init__(self, api_key: str):
        super().__init__(api_key, "https://www.virustotal.com/api/v3", rate_limit_per_min=4)
        self.headers = {
            "x-apikey": api_key,
            "Accept": "application/json"
        }
    
    def get_ip_report(self, ip_address: str) -> Dict:
        """Get reputation report for an IP address"""
        self._rate_limit()
        
        response = self.session.get(
            f"{self.base_url}/ip_addresses/{ip_address}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def get_domain_report(self, domain: str) -> Dict:
        """Get reputation report for a domain"""
        self._rate_limit()
        
        response = self.session.get(
            f"{self.base_url}/domains/{domain}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def get_file_report(self, file_hash: str) -> Dict:
        """Get report for file by hash (MD5, SHA1, SHA256)"""
        self._rate_limit()
        
        response = self.session.get(
            f"{self.base_url}/files/{file_hash}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def scan_url(self, url: str) -> Dict:
        """Submit URL for analysis"""
        self._rate_limit()
        
        data = {"url": url}
        response = self.session.post(
            f"{self.base_url}/urls",
            headers=self.headers,
            data=data,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def scan_file(self, file_path: str) -> Dict:
        """Upload file for analysis"""
        self._rate_limit()
        
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            response = self.session.post(
                f"{self.base_url}/files",
                headers={"x-apikey": self.api_key},
                files=files,
                timeout=120
            )
        response.raise_for_status()
        return response.json()
    
    def enrich(self, ioc_type: IOCType, ioc_value: str) -> EnrichmentResult:
        """
        Enrich an IOC and return standardized result
        
        Args:
            ioc_type: Type of IOC (IP, DOMAIN, etc.)
            ioc_value: The IOC value to check
            
        Returns:
            EnrichmentResult with standardized fields
        """
        start_time = time.time()
        
        try:
            if ioc_type == IOCType.IP:
                report = self.get_ip_report(ioc_value)
            elif ioc_type == IOCType.DOMAIN:
                report = self.get_domain_report(ioc_value)
            elif ioc_type in [IOCType.MD5, IOCType.SHA1, IOCType.SHA256]:
                report = self.get_file_report(ioc_value)
            else:
                raise ValueError(f"Unsupported IOC type: {ioc_type}")
            
            data = report.get("data", {})
            attributes = data.get("attributes", {})
            last_analysis = attributes.get("last_analysis_stats", {})
            
            malicious = last_analysis.get("malicious", 0)
            suspicious = last_analysis.get("suspicious", 0)
            total = sum(last_analysis.values()) if last_analysis else 0
            
            confidence = (malicious + suspicious) / total * 100 if total > 0 else 0
            
            # Determine threat level
            if confidence >= 75:
                threat_level = ThreatLevel.CRITICAL
            elif confidence >= 50:
                threat_level = ThreatLevel.HIGH
            elif confidence >= 25:
                threat_level = ThreatLevel.MEDIUM
            elif confidence > 0:
                threat_level = ThreatLevel.LOW
            else:
                threat_level = ThreatLevel.NONE
            
            return EnrichmentResult(
                ioc_type=ioc_type.value,
                ioc_value=ioc_value,
                source="virustotal",
                threat_level=threat_level.value,
                confidence_score=round(confidence, 2),
                malicious_count=malicious + suspicious,
                total_engines=total,
                first_seen=attributes.get("first_seen"),
                last_seen=attributes.get("last_seen"),
                tags=attributes.get("tags", []),
                raw_data=report,
                enrichment_time=round(time.time() - start_time, 3)
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"VirusTotal API error: {e}")
            return EnrichmentResult(
                ioc_type=ioc_type.value,
                ioc_value=ioc_value,
                source="virustotal",
                threat_level="error",
                confidence_score=0,
                malicious_count=0,
                total_engines=0,
                first_seen=None,
                last_seen=None,
                tags=[],
                raw_data={"error": str(e)},
                enrichment_time=round(time.time() - start_time, 3)
            )


class AbuseIPDBClient(BaseTIClient):
    """
    AbuseIPDB v2 API Client
    
    API Docs: https://docs.abuseipdb.com/
    Rate Limits: 1,000/day (free), 3,000/day (webmaster)
    """
    
    def __init__(self, api_key: str):
        super().__init__(api_key, "https://api.abuseipdb.com/api/v2", rate_limit_per_min=1)
        self.headers = {
            "Key": api_key,
            "Accept": "application/json"
        }
    
    def check_ip(self, ip_address: str, max_age_days: int = 90, verbose: bool = True) -> Dict:
        """Check IP reputation"""
        self._rate_limit()
        
        params = {
            "ipAddress": ip_address,
            "maxAgeInDays": max_age_days
        }
        if verbose:
            params["verbose"] = ""
        
        response = self.session.get(
            f"{self.base_url}/check",
            headers=self.headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def get_blacklist(self, confidence_minimum: int = 90, limit: int = 10000) -> Dict:
        """Download blacklist of abusive IPs"""
        self._rate_limit()
        
        params = {
            "confidenceMinimum": confidence_minimum,
            "limit": limit
        }
        
        response = self.session.get(
            f"{self.base_url}/blacklist",
            headers=self.headers,
            params=params,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    
    def enrich(self, ip_address: str) -> EnrichmentResult:
        """Enrich an IP address with AbuseIPDB data"""
        start_time = time.time()
        
        try:
            result = self.check_ip(ip_address)
            data = result.get("data", {})
            
            score = data.get("abuseConfidenceScore", 0)
            
            # Determine threat level
            if score >= 75:
                threat_level = ThreatLevel.HIGH
            elif score >= 50:
                threat_level = ThreatLevel.MEDIUM
            elif score >= 25:
                threat_level = ThreatLevel.LOW
            else:
                threat_level = ThreatLevel.NONE
            
            tags = []
            if data.get("isTor"):
                tags.append("tor")
            if data.get("isWhitelisted"):
                tags.append("whitelisted")
            if data.get("usageType"):
                tags.append(data["usageType"])
            
            return EnrichmentResult(
                ioc_type="ip",
                ioc_value=ip_address,
                source="abuseipdb",
                threat_level=threat_level.value,
                confidence_score=score,
                malicious_count=data.get("totalReports", 0),
                total_engines=100,  # AbuseIPDB uses confidence score
                first_seen=None,
                last_seen=data.get("lastReportedAt"),
                tags=tags,
                raw_data=result,
                enrichment_time=round(time.time() - start_time, 3)
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"AbuseIPDB API error: {e}")
            return EnrichmentResult(
                ioc_type="ip",
                ioc_value=ip_address,
                source="abuseipdb",
                threat_level="error",
                confidence_score=0,
                malicious_count=0,
                total_engines=0,
                first_seen=None,
                last_seen=None,
                tags=[],
                raw_data={"error": str(e)},
                enrichment_time=round(time.time() - start_time, 3)
            )


class MISPClient(BaseTIClient):
    """
    MISP API Client
    
    MISP is typically self-hosted, so base_url must be configured.
    """
    
    def __init__(self, base_url: str, api_key: str, ssl_verify: bool = True):
        super().__init__(api_key, base_url, rate_limit_per_min=60)
        self.ssl_verify = ssl_verify
        self.headers = {
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def search_ioc(self, value: str, ioc_type: str = "ip-dst") -> Dict:
        """Search for IOC in MISP"""
        self._rate_limit()
        
        endpoint = f"{self.base_url}/events/restSearch"
        
        data = {
            "returnFormat": "json",
            "type": ioc_type,
            "value": value,
            "to_ids": True
        }
        
        response = self.session.post(
            endpoint,
            headers=self.headers,
            json=data,
            verify=self.ssl_verify,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def enrich(self, ioc_type: IOCType, ioc_value: str) -> EnrichmentResult:
        """Enrich IOC with MISP data"""
        start_time = time.time()
        
        # Map IOC type to MISP type
        misp_type_map = {
            IOCType.IP: "ip-dst",
            IOCType.DOMAIN: "domain",
            IOCType.URL: "url",
            IOCType.MD5: "md5",
            IOCType.SHA1: "sha1",
            IOCType.SHA256: "sha256"
        }
        
        try:
            misp_type = misp_type_map.get(ioc_type, "ip-dst")
            result = self.search_ioc(ioc_value, misp_type)
            
            events = result.get("response", [])
            
            if events:
                # IOC found in MISP
                event_count = len(events)
                threat_level = ThreatLevel.MEDIUM  # Default if found
                
                # Aggregate tags from all events
                all_tags = []
                for event in events:
                    event_data = event.get("Event", {})
                    event_tags = event_data.get("Tag", [])
                    for tag in event_tags:
                        all_tags.append(tag.get("name", ""))
                
                return EnrichmentResult(
                    ioc_type=ioc_type.value,
                    ioc_value=ioc_value,
                    source="misp",
                    threat_level=threat_level.value,
                    confidence_score=50.0,  # Found in MISP
                    malicious_count=event_count,
                    total_engines=event_count,
                    first_seen=None,
                    last_seen=None,
                    tags=list(set(all_tags)),
                    raw_data=result,
                    enrichment_time=round(time.time() - start_time, 3)
                )
            else:
                # IOC not found
                return EnrichmentResult(
                    ioc_type=ioc_type.value,
                    ioc_value=ioc_value,
                    source="misp",
                    threat_level=ThreatLevel.NONE.value,
                    confidence_score=0,
                    malicious_count=0,
                    total_engines=0,
                    first_seen=None,
                    last_seen=None,
                    tags=[],
                    raw_data=result,
                    enrichment_time=round(time.time() - start_time, 3)
                )
                
        except requests.exceptions.RequestException as e:
            logger.error(f"MISP API error: {e}")
            return EnrichmentResult(
                ioc_type=ioc_type.value,
                ioc_value=ioc_value,
                source="misp",
                threat_level="error",
                confidence_score=0,
                malicious_count=0,
                total_engines=0,
                first_seen=None,
                last_seen=None,
                tags=[],
                raw_data={"error": str(e)},
                enrichment_time=round(time.time() - start_time, 3)
            )


class ThreatIntelOrchestrator:
    """
    Orchestrates multiple threat intelligence sources
    and aggregates results.
    """
    
    def __init__(self, vt_key: Optional[str] = None, 
                 abuseipdb_key: Optional[str] = None,
                 misp_url: Optional[str] = None,
                 misp_key: Optional[str] = None):
        
        self.clients = {}
        
        if vt_key:
            self.clients["virustotal"] = VirusTotalClient(vt_key)
        
        if abuseipdb_key:
            self.clients["abuseipdb"] = AbuseIPDBClient(abuseipdb_key)
        
        if misp_url and misp_key:
            self.clients["misp"] = MISPClient(misp_url, misp_key)
    
    def enrich_ioc(self, ioc_type: IOCType, ioc_value: str, 
                   sources: Optional[List[str]] = None) -> Dict:
        """
        Enrich IOC using all configured sources
        
        Args:
            ioc_type: Type of IOC
            ioc_value: The IOC value
            sources: Optional list of specific sources to use
            
        Returns:
            Dictionary with aggregated results
        """
        results = {}
        sources_to_use = sources or list(self.clients.keys())
        
        for source_name in sources_to_use:
            client = self.clients.get(source_name)
            if not client:
                continue
            
            try:
                if source_name == "abuseipdb" and ioc_type == IOCType.IP:
                    result = client.enrich(ioc_value)
                elif source_name == "misp":
                    result = client.enrich(ioc_type, ioc_value)
                else:
                    result = client.enrich(ioc_type, ioc_value)
                
                results[source_name] = asdict(result)
                
            except Exception as e:
                logger.error(f"Error enriching with {source_name}: {e}")
                results[source_name] = {
                    "error": str(e),
                    "ioc_type": ioc_type.value,
                    "ioc_value": ioc_value
                }
        
        # Calculate aggregate threat level
        aggregate = self._calculate_aggregate(results)
        
        return {
            "ioc_type": ioc_type.value,
            "ioc_value": ioc_value,
            "sources": results,
            "aggregate": aggregate,
            "enrichment_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
    
    def _calculate_aggregate(self, results: Dict) -> Dict:
        """Calculate aggregate threat level from multiple sources"""
        confidence_scores = []
        threat_levels = []
        all_tags = []
        sources_found = []
        
        level_priority = {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1,
            "none": 0,
            "error": -1
        }
        
        for source, result in results.items():
            if "error" in result:
                continue
            
            confidence_scores.append(result.get("confidence_score", 0))
            threat_levels.append(result.get("threat_level", "none"))
            all_tags.extend(result.get("tags", []))
            sources_found.append(source)
        
        # Determine aggregate threat level
        if threat_levels:
            highest_level = max(threat_levels, key=lambda x: level_priority.get(x, 0))
        else:
            highest_level = "unknown"
        
        # Calculate average confidence
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        return {
            "threat_level": highest_level,
            "confidence_score": round(avg_confidence, 2),
            "sources_consulted": len(results),
            "sources_found": sources_found,
            "tags": list(set(all_tags))
        }


# Example usage
if __name__ == "__main__":
    # Initialize orchestrator (use environment variables in production)
    orchestrator = ThreatIntelOrchestrator(
        vt_key=os.getenv("VIRUSTOTAL_API_KEY"),
        abuseipdb_key=os.getenv("ABUSEIPDB_API_KEY"),
        misp_url=os.getenv("MISP_URL"),
        misp_key=os.getenv("MISP_API_KEY")
    )
    
    # Example: Enrich an IP address
    result = orchestrator.enrich_ioc(
        IOCType.IP, 
        "8.8.8.8",
        sources=["virustotal", "abuseipdb"]  # Use specific sources
    )
    
    print(json.dumps(result, indent=2))
