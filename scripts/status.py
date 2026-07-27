#!/usr/bin/env python3
"""Run service health checks using the existing shell/PowerShell scripts.

This provides a simple Python entrypoint so workflows or users can run
`python scripts/status.py` and get consistent logging like other scripts.
"""

import logging
import subprocess
import sys
import platform
import shutil
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_ROOT = Path(__file__).parent.resolve()
LOG_DIR = SCRIPT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = (
    LOG_DIR / f"status-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)


def run_command(cmd):
    logging.info(f"Running command: {' '.join(map(str, cmd))}")
    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if result.stdout:
        logging.info(result.stdout.strip())
    if result.stderr:
        logging.info(result.stderr.strip())
    return result.returncode


def main():
    system = platform.system()
    if system == "Windows":
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            logging.error("No PowerShell executable found (pwsh or powershell)")
            sys.exit(1)
        script = SCRIPT_ROOT / "scripts" / "test-services.ps1"
        cmd = [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        script = SCRIPT_ROOT / "scripts" / "test-services.sh"
        cmd = ["bash", str(script)]

    rc = run_command(cmd)
    if rc != 0:
        logging.error(f"Health checks failed with exit code {rc}")
        sys.exit(rc)
    logging.info("All health checks passed.")


if __name__ == "__main__":
    main()
