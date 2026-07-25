#!/usr/bin/env python3
"""Set up Cloudflare DNS CNAME records for MCaaS services.

Reads ALB hostnames from Kubernetes ingress resources and creates
CNAME records in Cloudflare.

Usage:
    python setup-dns.py --zone-id <ZONE_ID> --token <API_TOKEN> --domain <customer.socom.co.il>

Or set environment variables:
    export CLOUDFLARE_ZONE_ID=<ZONE_ID>
    export CLOUDFLARE_API_TOKEN=<API_TOKEN>
    export MCAAS_DOMAIN=<customer.socom.co.il>
    python setup-dns.py
"""

import argparse
import json
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Create Cloudflare DNS CNAME records for MCaaS services"
    )
    parser.add_argument(
        "--zone-id",
        default=os.environ.get("CLOUDFLARE_ZONE_ID", ""),
        help="Cloudflare Zone ID (or set CLOUDFLARE_ZONE_ID env var)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        help="Cloudflare API Token (or set CLOUDFLARE_API_TOKEN env var)",
    )
    parser.add_argument(
        "--domain",
        default=os.environ.get("MCAAS_DOMAIN", ""),
        help="Customer domain, e.g. 'testcustomer.socom.co.il' (or set MCAAS_DOMAIN env var)",
    )
    args = parser.parse_args()

    if not args.zone_id:
        print(
            "ERROR: Cloudflare Zone ID required. Use --zone-id or set CLOUDFLARE_ZONE_ID env var."
        )
        sys.exit(1)
    if not args.token:
        print(
            "ERROR: Cloudflare API Token required. Use --token or set CLOUDFLARE_API_TOKEN env var."
        )
        sys.exit(1)
    if not args.domain:
        print("ERROR: Domain required. Use --domain or set MCAAS_DOMAIN env var.")
        sys.exit(1)

    zone_id = args.zone_id
    token = args.token
    domain = args.domain
    headers = [
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Content-Type: application/json",
    ]

    # Determine curl command based on platform
    curl_cmd = "curl.exe" if sys.platform == "win32" else "curl"

    # Get ALB hostnames from ingresses
    result = subprocess.run(
        ["kubectl", "get", "ingress", "-A", "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to get ingresses: {result.stderr}")
        sys.exit(1)

    data = json.loads(result.stdout)

    dns_records = {}
    for i in data["items"]:
        name = i["metadata"]["name"]
        host = i["spec"]["rules"][0]["host"]
        alb = None
        if i["status"]["loadBalancer"].get("ingress"):
            alb = i["status"]["loadBalancer"]["ingress"][0]["hostname"]

        # Map to customer domain
        service = host.split(".")[0]
        new_domain = f"{service}.{domain}"
        if alb:
            dns_records[new_domain] = alb

    print("DNS records to create:")
    for d, target in dns_records.items():
        print(f"  {d} -> {target}")

    # Create or update CNAME records
    for d, target in dns_records.items():
        payload = json.dumps(
            {"type": "CNAME", "name": d, "content": target, "proxied": False, "ttl": 1}
        )

        # Check if record already exists
        check = subprocess.run(
            [
                curl_cmd,
                "-s",
                "-H",
                f"Authorization: Bearer {token}",
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?name={d}",
            ],
            capture_output=True,
            text=True,
        )
        check_data = json.loads(check.stdout)

        if check_data.get("result") and len(check_data["result"]) > 0:
            record_id = check_data["result"][0]["id"]
            # Update existing record
            result = subprocess.run(
                [curl_cmd, "-s", "-X", "PUT"]
                + headers
                + [
                    "--data",
                    payload,
                    f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                ],
                capture_output=True,
                text=True,
            )
            print(f"  Updated {d}: {result.stdout[:200]}")
        else:
            # Create new record
            result = subprocess.run(
                [curl_cmd, "-s", "-X", "POST"]
                + headers
                + [
                    "--data",
                    payload,
                    f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                ],
                capture_output=True,
                text=True,
            )
            print(f"  Created {d}: {result.stdout[:200]}")

    print("\nDone!")


if __name__ == "__main__":
    main()
