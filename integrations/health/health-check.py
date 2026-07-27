#!/usr/bin/env python3
"""
MCaaS Integration Health Check.

This script performs comprehensive health checks on MCaaS integrations:
- Wazuh → Shuffle connectivity
- Shuffle → Zammad connectivity (if implemented)
- Kubernetes ConfigMap accessibility
- API endpoint availability
- Alert flow validation

Environment Variables:
    WAZUH_NAMESPACE: Wazuh namespace (default: wazuh)
    WAZUH_CONFIGMAP_LABELS: ConfigMap label selector
    SHUFFLE_API_URL: Shuffle API URL
    SHUFFLE_WEBHOOK_URL: Shuffle webhook URL
    ZAMMAD_URL: Zammad URL
    ZAMMAD_API_TOKEN: Zammad API token
    LOG_LEVEL: Logging level (default: INFO)
    HEALTH_CHECK_TIMEOUT: Request timeout in seconds (default: 30)

Usage:
    python health-check.py [--verbose] [--integration NAME]
    python health-check.py --continuous --interval 300

Exit Codes:
    0: All checks passed
    1: One or more checks failed
    2: Configuration error
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Default configuration
DEFAULT_WAZUH_NS = "wazuh"
DEFAULT_SHUFFLE_API = "http://shuffle-backend.security-ops.svc.cluster.local:5001"
DEFAULT_SHUFFLE_WEBHOOK = (
    "http://shuffle-backend.security-ops.svc.cluster.local:5001"
    "/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b"
)
DEFAULT_ZAMMAD_URL = "http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080"
DEFAULT_TIMEOUT = 30
DEFAULT_INTERVAL = 300  # 5 minutes for continuous mode


class Status(Enum):
    """Check status enumeration."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    WARN = "WARN"


@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: Status
    message: str
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """MCaaS integration health checker."""
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize health checker.
        
        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.results: List[CheckResult] = []
        
        # Configuration from environment
        self.wazuh_ns = os.getenv("WAZUH_NAMESPACE", DEFAULT_WAZUH_NS)
        self.shuffle_api = os.getenv("SHUFFLE_API_URL", DEFAULT_SHUFFLE_API)
        self.shuffle_webhook = os.getenv("SHUFFLE_WEBHOOK_URL", DEFAULT_SHUFFLE_WEBHOOK)
        self.zammad_url = os.getenv("ZAMMAD_URL", DEFAULT_ZAMMAD_URL)
        self.zammad_token = os.getenv("ZAMMAD_API_TOKEN")
        self.timeout = int(os.getenv("HEALTH_CHECK_TIMEOUT", str(DEFAULT_TIMEOUT)))
        
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _record_result(
        self,
        name: str,
        status: Status,
        message: str,
        duration_ms: float = 0.0,
        details: Optional[Dict] = None
    ) -> CheckResult:
        """Record a check result."""
        result = CheckResult(
            name=name,
            status=status,
            message=message,
            duration_ms=duration_ms,
            details=details or {}
        )
        self.results.append(result)
        return result
    
    def check_kubectl_access(self) -> CheckResult:
        """Check if kubectl is available and configured."""
        self.logger.info("Checking kubectl access...")
        start = time.time()
        
        try:
            result = subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            duration = (time.time() - start) * 1000
            
            if result.returncode == 0:
                version = result.stdout.strip().split('\n')[0]
                return self._record_result(
                    "kubectl_access",
                    Status.PASS,
                    f"kubectl available: {version[:50]}...",
                    duration
                )
            else:
                return self._record_result(
                    "kubectl_access",
                    Status.FAIL,
                    f"kubectl error: {result.stderr}",
                    duration
                )
        except FileNotFoundError:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "kubectl_access",
                Status.FAIL,
                "kubectl not found in PATH",
                duration
            )
        except subprocess.TimeoutExpired:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "kubectl_access",
                Status.FAIL,
                "kubectl command timed out",
                duration
            )
    
    def check_wazuh_namespace(self) -> CheckResult:
        """Check if Wazuh namespace exists and is accessible."""
        self.logger.info("Checking Wazuh namespace...")
        start = time.time()
        
        try:
            result = subprocess.run(
                ["kubectl", "get", "namespace", self.wazuh_ns, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            duration = (time.time() - start) * 1000
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                phase = data.get("status", {}).get("phase", "Unknown")
                return self._record_result(
                    "wazuh_namespace",
                    Status.PASS,
                    f"Namespace '{self.wazuh_ns}' exists (status: {phase})",
                    duration
                )
            else:
                return self._record_result(
                    "wazuh_namespace",
                    Status.FAIL,
                    f"Cannot access namespace: {result.stderr.strip()}",
                    duration
                )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "wazuh_namespace",
                Status.FAIL,
                f"Error checking namespace: {e}",
                duration
            )
    
    def check_wazuh_configmap(self) -> CheckResult:
        """Check if Wazuh ConfigMap is accessible."""
        self.logger.info("Checking Wazuh ConfigMap...")
        start = time.time()
        
        try:
            result = subprocess.run(
                ["kubectl", "get", "configmap", "-n", self.wazuh_ns, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            duration = (time.time() - start) * 1000
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                configmaps = data.get("items", [])
                
                # Find ConfigMaps related to wazuh
                wazuh_cms = [
                    cm for cm in configmaps
                    if "wazuh" in cm.get("metadata", {}).get("name", "").lower()
                ]
                
                if wazuh_cms:
                    names = [cm["metadata"]["name"] for cm in wazuh_cms]
                    return self._record_result(
                        "wazuh_configmap",
                        Status.PASS,
                        f"Found {len(wazuh_cms)} Wazuh ConfigMap(s): {', '.join(names[:3])}",
                        duration
                    )
                else:
                    return self._record_result(
                        "wazuh_configmap",
                        Status.WARN,
                        "No Wazuh ConfigMaps found with 'wazuh' in name",
                        duration
                    )
            else:
                return self._record_result(
                    "wazuh_configmap",
                    Status.FAIL,
                    f"Cannot list ConfigMaps: {result.stderr.strip()}",
                    duration
                )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "wazuh_configmap",
                Status.FAIL,
                f"Error checking ConfigMap: {e}",
                duration
            )
    
    def check_wazuh_manager_running(self) -> CheckResult:
        """Check if Wazuh manager is running."""
        self.logger.info("Checking Wazuh manager status...")
        start = time.time()
        
        try:
            result = subprocess.run(
                ["kubectl", "get", "pods", "-n", self.wazuh_ns, "-l", "app=wazuh-manager-master", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            duration = (time.time() - start) * 1000
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                pods = data.get("items", [])
                
                if not pods:
                    return self._record_result(
                        "wazuh_manager_running",
                        Status.FAIL,
                        "No Wazuh manager pods found",
                        duration
                    )
                
                # Check pod status
                running = sum(
                    1 for p in pods
                    if p.get("status", {}).get("phase") == "Running"
                )
                
                if running == len(pods):
                    return self._record_result(
                        "wazuh_manager_running",
                        Status.PASS,
                        f"All {len(pods)} Wazuh manager pod(s) running",
                        duration
                    )
                else:
                    return self._record_result(
                        "wazuh_manager_running",
                        Status.WARN,
                        f"{running}/{len(pods)} Wazuh manager pods running",
                        duration
                    )
            else:
                return self._record_result(
                    "wazuh_manager_running",
                    Status.FAIL,
                    f"Cannot check pod status: {result.stderr.strip()}",
                    duration
                )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "wazuh_manager_running",
                Status.FAIL,
                f"Error checking manager: {e}",
                duration
            )
    
    def check_shuffle_api(self) -> CheckResult:
        """Check if Shuffle API is accessible."""
        self.logger.info("Checking Shuffle API...")
        start = time.time()
        
        try:
            response = self.session.get(
                f"{self.shuffle_api}/api/v1/health",
                timeout=self.timeout
            )
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return self._record_result(
                    "shuffle_api",
                    Status.PASS,
                    f"Shuffle API responding (HTTP {response.status_code})",
                    duration
                )
            else:
                return self._record_result(
                    "shuffle_api",
                    Status.WARN,
                    f"Shuffle API returned HTTP {response.status_code}",
                    duration
                )
        except requests.exceptions.ConnectionError:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "shuffle_api",
                Status.FAIL,
                "Cannot connect to Shuffle API",
                duration
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "shuffle_api",
                Status.FAIL,
                f"Shuffle API error: {e}",
                duration
            )
    
    def check_shuffle_webhook(self) -> CheckResult:
        """Check if Shuffle webhook is accessible."""
        self.logger.info("Checking Shuffle webhook...")
        start = time.time()
        
        try:
            # Send a test payload
            test_payload = {
                "test": True,
                "timestamp": datetime.now().isoformat(),
                "source": "health-check"
            }
            
            response = self.session.post(
                self.shuffle_webhook,
                json=test_payload,
                timeout=self.timeout
            )
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success"):
                        return self._record_result(
                            "shuffle_webhook",
                            Status.PASS,
                            f"Webhook accepting requests (execution: {data.get('execution_id', 'N/A')[:8]}...)",
                            duration
                        )
                    else:
                        return self._record_result(
                            "shuffle_webhook",
                            Status.WARN,
                            "Webhook returned success=false",
                            duration,
                            {"response": data}
                        )
                except json.JSONDecodeError:
                    return self._record_result(
                        "shuffle_webhook",
                        Status.PASS,
                        f"Webhook responding (HTTP {response.status_code})",
                        duration
                    )
            else:
                return self._record_result(
                    "shuffle_webhook",
                    Status.WARN,
                    f"Webhook returned HTTP {response.status_code}",
                    duration
                )
        except requests.exceptions.ConnectionError:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "shuffle_webhook",
                Status.FAIL,
                "Cannot connect to Shuffle webhook",
                duration
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "shuffle_webhook",
                Status.FAIL,
                f"Webhook error: {e}",
                duration
            )
    
    def check_zammad_api(self) -> CheckResult:
        """Check if Zammad API is accessible."""
        self.logger.info("Checking Zammad API...")
        start = time.time()
        
        if not self.zammad_token:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "zammad_api",
                Status.SKIP,
                "ZAMMAD_API_TOKEN not configured, skipping",
                duration
            )
        
        try:
            headers = {
                "Authorization": f"Token token={self.zammad_token}",
                "Content-Type": "application/json"
            }
            
            response = self.session.get(
                f"{self.zammad_url}/api/v1/users/me",
                headers=headers,
                timeout=self.timeout
            )
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                login = data.get("login", "unknown")
                return self._record_result(
                    "zammad_api",
                    Status.PASS,
                    f"Zammad API accessible (authenticated as {login})",
                    duration
                )
            elif response.status_code == 401:
                return self._record_result(
                    "zammad_api",
                    Status.FAIL,
                    "Zammad API authentication failed (401)",
                    duration
                )
            else:
                return self._record_result(
                    "zammad_api",
                    Status.WARN,
                    f"Zammad API returned HTTP {response.status_code}",
                    duration
                )
        except requests.exceptions.ConnectionError:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "zammad_api",
                Status.FAIL,
                "Cannot connect to Zammad API",
                duration
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "zammad_api",
                Status.FAIL,
                f"Zammad API error: {e}",
                duration
            )
    
    def check_integration_flow(self) -> CheckResult:
        """Validate the complete integration flow."""
        self.logger.info("Checking integration flow...")
        start = time.time()
        
        # Check if we can reach from Wazuh pod to Shuffle
        try:
            result = subprocess.run(
                [
                    "kubectl", "run", "health-check-test", "--rm", "-i",
                    "--restart=Never", "--image=curlimages/curl",
                    "-n", self.wazuh_ns,
                    "--", "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    self.shuffle_webhook, "-X", "POST",
                    "-H", "Content-Type: application/json",
                    "-d", '{"health_check": true}'
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            duration = (time.time() - start) * 1000
            
            if result.returncode == 0:
                status_code = result.stdout.strip()
                if status_code == "200":
                    return self._record_result(
                        "integration_flow",
                        Status.PASS,
                        "Full integration flow working (Wazuh → Shuffle)",
                        duration
                    )
                else:
                    return self._record_result(
                        "integration_flow",
                        Status.WARN,
                        f"Integration flow returned HTTP {status_code}",
                        duration
                    )
            else:
                return self._record_result(
                    "integration_flow",
                    Status.WARN,
                    f"Integration flow test failed: {result.stderr.strip()[:100]}",
                    duration
                )
        except subprocess.TimeoutExpired:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "integration_flow",
                Status.WARN,
                "Integration flow test timed out",
                duration
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return self._record_result(
                "integration_flow",
                Status.WARN,
                f"Integration flow check error: {e}",
                duration
            )
    
    def run_all_checks(self, integration_filter: Optional[str] = None) -> List[CheckResult]:
        """
        Run all health checks.
        
        Args:
            integration_filter: Optional filter to run only specific integration checks
        
        Returns:
            List of check results
        """
        self.results = []
        
        checks = [
            ("kubernetes", [
                self.check_kubectl_access,
                self.check_wazuh_namespace,
                self.check_wazuh_configmap,
                self.check_wazuh_manager_running,
            ]),
            ("shuffle", [
                self.check_shuffle_api,
                self.check_shuffle_webhook,
            ]),
            ("zammad", [
                self.check_zammad_api,
            ]),
            ("flow", [
                self.check_integration_flow,
            ])
        ]
        
        for name, check_funcs in checks:
            if integration_filter and name != integration_filter:
                continue
            
            for check_func in check_funcs:
                try:
                    check_func()
                except Exception as e:
                    self.logger.error(f"Unexpected error in {check_func.__name__}: {e}")
                    self._record_result(
                        check_func.__name__,
                        Status.FAIL,
                        f"Unexpected error: {e}"
                    )
        
        return self.results
    
    def print_results(self, format: str = "text") -> None:
        """
        Print results in specified format.
        
        Args:
            format: Output format (text, json)
        """
        if format == "json":
            output = {
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": len(self.results),
                    "passed": sum(1 for r in self.results if r.status == Status.PASS),
                    "failed": sum(1 for r in self.results if r.status == Status.FAIL),
                    "warnings": sum(1 for r in self.results if r.status == Status.WARN),
                    "skipped": sum(1 for r in self.results if r.status == Status.SKIP),
                },
                "checks": [
                    {
                        "name": r.name,
                        "status": r.status.value,
                        "message": r.message,
                        "duration_ms": r.duration_ms
                    }
                    for r in self.results
                ]
            }
            print(json.dumps(output, indent=2))
        else:
            # Text format
            print("\n" + "=" * 70)
            print("MCaaS INTEGRATION HEALTH CHECK RESULTS")
            print("=" * 70)
            
            for result in self.results:
                status_icon = {
                    Status.PASS: "✓",
                    Status.FAIL: "✗",
                    Status.WARN: "⚠",
                    Status.SKIP: "○"
                }.get(result.status, "?")
                
                print(f"\n{status_icon} {result.name}")
                print(f"  Status: {result.status.value}")
                print(f"  Message: {result.message}")
                if result.duration_ms > 0:
                    print(f"  Duration: {result.duration_ms:.2f}ms")
            
            # Summary
            passed = sum(1 for r in self.results if r.status == Status.PASS)
            failed = sum(1 for r in self.results if r.status == Status.FAIL)
            warnings = sum(1 for r in self.results if r.status == Status.WARN)
            skipped = sum(1 for r in self.results if r.status == Status.SKIP)
            
            print("\n" + "-" * 70)
            print(f"SUMMARY: {passed} passed, {failed} failed, {warnings} warnings, {skipped} skipped")
            print("=" * 70)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging."""
    logger = logging.getLogger("health_check")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCaaS Integration Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                          # Run all checks
    %(prog)s --integration shuffle    # Check Shuffle only
    %(prog)s --json                   # Output JSON format
    %(prog)s --continuous             # Run continuously
        """
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )
    parser.add_argument(
        "--integration",
        metavar="NAME",
        choices=["kubernetes", "shuffle", "zammad", "flow"],
        help="Check specific integration only"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run checks continuously"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Interval between checks in seconds (default: {DEFAULT_INTERVAL})"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logging(log_level)
    
    logger.info("Starting MCaaS Integration Health Check")
    
    checker = HealthChecker(logger)
    
    if args.continuous:
        logger.info(f"Running continuously with {args.interval}s interval")
        try:
            while True:
                checker.run_all_checks(args.integration)
                checker.print_results("text" if not args.json else "json")
                
                failed = sum(1 for r in checker.results if r.status == Status.FAIL)
                if failed > 0:
                    logger.warning(f"{failed} check(s) failed")
                
                logger.info(f"Sleeping for {args.interval}s...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            return 0
    else:
        checker.run_all_checks(args.integration)
        checker.print_results("json" if args.json else "text")
        
        # Exit with appropriate code
        failed = sum(1 for r in checker.results if r.status == Status.FAIL)
        return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
