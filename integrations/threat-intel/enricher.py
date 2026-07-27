#!/usr/bin/env python3
"""
Threat Intelligence Enrichment Service

Enriches Wazuh alerts with external threat intelligence:
- VirusTotal: File hash reputation
- AbuseIPDB: IP reputation and abuse reports
- MISP: Threat sharing platform indicators

Environment Variables:
    VIRUSTOTAL_API_KEY: *** API key for hash lookups
    ABUSEIPDB_API_KEY: *** API key for IP reputation
    MISP_URL: MISP instance URL
    MISP_API_KEY: *** API key for MISP
    ENRICHMENT_CACHE_TTL: Cache TTL in seconds (default: 3600)
    LOG_LEVEL: Logging level (default: INFO)

Usage:
    python enricher.py --alert-file alert.json
    python enricher.py --ip 1.2.3.4 --hash abc123...
    cat alert.json | python enricher.py --stdout
"""

import argparse
import hashlib
import ipaddress
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Result of threat intel enrichment."""
    source: str
    indicator: str
    indicator_type: str
    malicious: Optional[bool]
    confidence: int  # 0-100
    details: Dict
    timestamp: str


class Cache:
    """Simple in-memory cache for enrichment results."""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._cache = {}
    
    def _make_key(self, source: str, indicator: str) -> str:
        return hashlib.md5(f"{source}:{indicator}".encode()).hexdigest()
    
    def get(self, source: str, indicator: str) -> Optional[EnrichmentResult]:
        key = self._make_key(source, indicator)
        if key in self._cache:
            result, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return result
            del self._cache[key]
        return None
    
    def set(self, source: str, indicator: str, result: EnrichmentResult):
        key = self._make_key(source, indicator)
        self._cache[key] = (result, datetime.now())


class VirusTotalClient:
    """VirusTotal API client for file hash lookups."""
    
    BASE_URL = "https://www.virustotal.com/api/v3"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-apikey": api_key,
            "Accept": "application/json"
        }
    
    def lookup_hash(self, file_hash: str) -> Optional[EnrichmentResult]:
        """Look up file hash reputation."""
        url = f"{self.BASE_URL}/files/{file_hash}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 404:
                return EnrichmentResult(
                    source="virustotal",
                    indicator=file_hash,
                    indicator_type="hash",
                    malicious=False,
                    confidence=0,
                    details={"error": "Hash not found in VirusTotal"},
                    timestamp=datetime.utcnow().isoformat()
                )
            response.raise_for_status()
            data = response.json()
            
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})
            
            malicious_count = stats.get("malicious", 0)
            suspicious_count = stats.get("suspicious", 0)
            total = stats.get("harmless", 0) + malicious_count + suspicious_count + stats.get("undetected", 0)
            
            is_malicious = malicious_count > 0 or suspicious_count > 0
            confidence = min(100, int((malicious_count + suspicious_count) / total * 100)) if total > 0 else 0
            
            return EnrichmentResult(
                source="virustotal",
                indicator=file_hash,
                indicator_type="hash",
                malicious=is_malicious,
                confidence=confidence,
                details={
                    "malicious": malicious_count,
                    "suspicious": suspicious_count,
                    "harmless": stats.get("harmless", 0),
                    "undetected": stats.get("undetected", 0),
                    "total_engines": total,
                    "threat_label": attributes.get("popular_threat_classification", {}).get("suggested_threat_label", "unknown")
                },
                timestamp=datetime.utcnow().isoformat()
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"VirusTotal API error: {e}")
            return None
    
    def lookup_ip(self, ip: str) -> Optional[EnrichmentResult]:
        """Look up IP address reputation."""
        url = f"{self.BASE_URL}/ip_addresses/{ip}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})
            
            malicious_count = stats.get("malicious", 0)
            suspicious_count = stats.get("suspicious", 0)
            total = sum(stats.values())
            
            is_malicious = malicious_count > 0 or suspicious_count > 0
            confidence = min(100, int((malicious_count + suspicious_count) / total * 100)) if total > 0 else 0
            
            return EnrichmentResult(
                source="virustotal",
                indicator=ip,
                indicator_type="ip",
                malicious=is_malicious,
                confidence=confidence,
                details={
                    "malicious": malicious_count,
                    "suspicious": suspicious_count,
                    "harmless": stats.get("harmless", 0),
                    "as_owner": attributes.get("as_owner", "unknown"),
                    "country": attributes.get("country", "unknown")
                },
                timestamp=datetime.utcnow().isoformat()
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"VirusTotal API error: {e}")
            return None


class AbuseIPDBClient:
    """AbuseIPDB API client for IP reputation."""
    
    BASE_URL = "https://api.abuseipdb.com/api/v2"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Key": api_key,
            "Accept": "application/json"
        }
    
    def check_ip(self, ip: str) -> Optional[EnrichmentResult]:
        """Check IP reputation in AbuseIPDB."""
        url = f"{self.BASE_URL}/check"
        params = {
            "ipAddress": ip,
            "maxAgeInDays": 90,
            "verbose": ""
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            ip_data = data.get("data", {})
            abuse_score = ip_data.get("abuseConfidencePercentage", 0)
            
            return EnrichmentResult(
                source="abuseipdb",
                indicator=ip,
                indicator_type="ip",
                malicious=abuse_score >= 50,
                confidence=abuse_score,
                details={
                    "abuse_score": abuse_score,
                    "total_reports": ip_data.get("totalReports", 0),
                    "last_reported": ip_data.get("lastReportedAt"),
                    "isp": ip_data.get("isp", "unknown"),
                    "country": ip_data.get("countryCode", "unknown"),
                    "usage_type": ip_data.get("usageType", "unknown")
                },
                timestamp=datetime.utcnow().isoformat()
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"AbuseIPDB API error: {e}")
            return None


class MISPClient:
    """MISP API client for threat intelligence."""
    
    def __init__(self, url: str, api_key: str):
        self.base_url = url.rstrip('/')
        self.headers = {
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def search_ioc(self, value: str) -> Optional[EnrichmentResult]:
        """Search for IOC in MISP."""
        url = f"{self.base_url}/attributes/restSearch/json"
        
        data = {
            "returnFormat": "json",
            "value": value,
            "type": ["ip-dst", "ip-src", "md5", "sha256"]
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data, timeout=30)
            response.raise_for_status()
            result_data = response.json()
            
            attributes = result_data.get("response", {}).get("Attribute", [])
            
            if not attributes:
                return None
            
            # Get the most recent attribute
            latest = attributes[0]
            threat_level = int(latest.get("event_info", {}).get("threat_level_id", 3))
            
            confidence_map = {1: 100, 2: 75, 3: 50, 4: 25}
            confidence = confidence_map.get(threat_level, 50)
            
            return EnrichmentResult(
                source="misp",
                indicator=value,
                indicator_type=latest.get("type", "unknown"),
                malicious=True,
                confidence=confidence,
                details={
                    "event_id": latest.get("event_id"),
                    "event_info": latest.get("event_info", {}).get("info", "unknown"),
                    "threat_level": threat_level,
                    "tags": [tag.get("name") for tag in latest.get("Tag", [])]
                },
                timestamp=datetime.utcnow().isoformat()
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"MISP API error: {e}")
            return None


class ThreatIntelEnricher:
    """Main enrichment service."""
    
    HASH_PATTERN = re.compile(r'^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$')
    IP_PATTERN = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    
    def __init__(self):
        self.cache = Cache(int(os.environ.get('ENRICHMENT_CACHE_TTL', '3600')))
        self.clients = {}
        
        # Initialize clients from environment
        if os.environ.get('VIRUSTOTAL_API_KEY'):
            self.clients['virustotal'] = VirusTotalClient(os.environ['VIRUSTOTAL_API_KEY'])
        
        if os.environ.get('ABUSEIPDB_API_KEY'):
            self.clients['abuseipdb'] = AbuseIPDBClient(os.environ['ABUSEIPDB_API_KEY'])
        
        if os.environ.get('MISP_URL') and os.environ.get('MISP_API_KEY'):
            self.clients['misp'] = MISPClient(os.environ['MISP_URL'], os.environ['MISP_API_KEY'])
    
    def extract_iocs(self, alert: Dict) -> Dict[str, List[str]]:
        """Extract IOCs from Wazuh alert."""
        iocs = {
            'ips': [],
            'hashes': [],
            'urls': []
        }
        
        # Check various fields
        full_log = alert.get('full_log', '')
        srcip = alert.get('srcip', '')
        dstip = alert.get('dstip', '')
        
        # Extract IPs
        if srcip and self.IP_PATTERN.match(srcip):
            try:
                ipaddress.ip_address(srcip)
                iocs['ips'].append(srcip)
            except ValueError:
                pass
        
        if dstip and self.IP_PATTERN.match(dstip):
            try:
                ipaddress.ip_address(dstip)
                iocs['ips'].append(dstip)
            except ValueError:
                pass
        
        # Extract hashes from full_log
        for match in self.HASH_PATTERN.findall(full_log):
            if match not in iocs['hashes']:
                iocs['hashes'].append(match)
        
        return iocs
    
    def enrich_ioc(self, ioc_type: str, value: str) -> List[EnrichmentResult]:
        """Enrich a single IOC across all configured sources."""
        results = []
        
        for source_name, client in self.clients.items():
            # Check cache first
            cached = self.cache.get(source_name, value)
            if cached:
                results.append(cached)
                continue
            
            result = None
            if ioc_type == 'ip':
                if source_name == 'virustotal':
                    result = client.lookup_ip(value)
                elif source_name == 'abuseipdb':
                    result = client.check_ip(value)
                elif source_name == 'misp':
                    result = client.search_ioc(value)
            
            elif ioc_type == 'hash':
                if source_name == 'virustotal':
                    result = client.lookup_hash(value)
                elif source_name == 'misp':
                    result = client.search_ioc(value)
            
            if result:
                self.cache.set(source_name, value, result)
                results.append(result)
        
        return results
    
    def enrich_alert(self, alert: Dict) -> Dict:
        """Enrich a Wazuh alert with threat intelligence."""
        iocs = self.extract_iocs(alert)
        enrichment = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'iocs_found': iocs,
            'results': {}
        }
        
        for ip in iocs['ips']:
            enrichment['results'][f"ip:{ip}"] = [
                asdict(r) for r in self.enrich_ioc('ip', ip)
            ]
        
        for file_hash in iocs['hashes']:
            enrichment['results'][f"hash:{file_hash}"] = [
                asdict(r) for r in self.enrich_ioc('hash', file_hash)
            ]
        
        # Add enrichment to alert
        alert['_enrichment'] = enrichment
        return alert
    
    def get_threat_score(self, alert: Dict) -> int:
        """Calculate overall threat score based on enrichment."""
        score = 0
        enrichment = alert.get('_enrichment', {})
        
        for ioc_key, results in enrichment.get('results', {}).items():
            for result in results:
                if result.get('malicious'):
                    score += result.get('confidence', 0) / len(results)
        
        return min(100, int(score))


def main():
    parser = argparse.ArgumentParser(description='Threat intelligence enrichment')
    parser.add_argument('--alert-file', type=argparse.FileType('r'),
                        help='JSON file with Wazuh alert')
    parser.add_argument('--alert-json', type=str,
                        help='JSON string with Wazuh alert')
    parser.add_argument('--ip', type=str,
                        help='Enrich specific IP')
    parser.add_argument('--hash', type=str,
                        help='Enrich specific hash')
    parser.add_argument('--stdout', action='store_true',
                        help='Output enriched alert to stdout')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    enricher = ThreatIntelEnricher()
    
    # Handle specific IOC lookup
    if args.ip:
        results = enricher.enrich_ioc('ip', args.ip)
        print(json.dumps([asdict(r) for r in results], indent=2))
        return
    
    if args.hash:
        results = enricher.enrich_ioc('hash', args.hash)
        print(json.dumps([asdict(r) for r in results], indent=2))
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
    
    # Enrich alert
    enriched = enricher.enrich_alert(alert)
    threat_score = enricher.get_threat_score(enriched)
    enriched['_enrichment']['threat_score'] = threat_score
    
    if args.stdout:
        print(json.dumps(enriched, indent=2))
    else:
        print(f"Enrichment complete. Threat score: {threat_score}")
        print(f"IOCs found: {enriched['_enrichment']['iocs_found']}")


if __name__ == '__main__':
    main()
