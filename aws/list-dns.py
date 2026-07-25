#!/usr/bin/env python3
"""List Cloudflare DNS records for the MCaaS zone.

Usage:
    python list-dns.py --zone-id <ZONE_ID> --token <API_TOKEN>

Or set environment variables:
    export CLOUDFLARE_ZONE_ID=<ZONE_ID>
    export CLOUDFLARE_API_TOKEN=<API_TOKEN>
    python list-dns.py
"""

import argparse
import json
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="List Cloudflare DNS records for MCaaS"
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

    zone_id = args.zone_id
    token = args.token

    # Determine curl command based on platform
    curl_cmd = "curl.exe" if sys.platform == "win32" else "curl"

    result = subprocess.run(
        [
            curl_cmd,
            "-s",
            "-H",
            f"Authorization: Bearer {token}",
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?per_page=100",
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)

    for r in data["result"]:
        print(f'{r["name"]:50} {r["type"]:6} {r["content"]}')


if __name__ == "__main__":
    main()
