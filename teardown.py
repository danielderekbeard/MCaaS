#!/usr/bin/env python3
import subprocess
import sys
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---
SCRIPT_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_ROOT.parent
LOG_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / ".tmp"

# --- Logging Setup ---
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"teardown-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_command(command, check=True):
    """Runs a command, logs its output, and returns the result."""
    logging.info(f"Running command: {' '.join(map(str, command))}")
    try:
        result = subprocess.run(command, check=check, text=True, capture_output=True)
        if result.stdout:
            logging.info(f"STDOUT: {result.stdout.strip()}")
        if result.stderr:
            # Log stderr as info for non-failing commands, as some tools write to it
            level = logging.ERROR if check and result.returncode != 0 else logging.INFO
            logging.log(level, f"STDERR: {result.stderr.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}")
        if e.stdout:
            logging.error(f"STDOUT: {e.stdout.strip()}")
        if e.stderr:
            logging.error(f"STDERR: {e.stderr.strip()}")
        raise

def main():
    """Main teardown logic."""
    try:
        releases = {
            'ciso-assistant': 'grc',
            'zammad': 'managed-it',
            'mcaas-shuffle': 'security-ops',
            'wazuh': 'security-ops', # For manifest-based, this won't exist, but good to have
            'mcaas-opensearch': 'security-ops',
            'mcaas-postgresql': 'managed-it'
        }

        for release, namespace in releases.items():
            logging.info(f"Checking for Helm release '{release}' in namespace '{namespace}'...")
            # Check if the release exists before trying to uninstall
            status_cmd = ["helm", "status", release, "--namespace", namespace]
            result = run_command(status_cmd, check=False)

            if result.returncode == 0:
                logging.info(f"Uninstalling Helm release '{release}'...")
                run_command(["helm", "uninstall", release, "--namespace", namespace])
            else:
                logging.info(f"Helm release '{release}' not found, skipping.")

        logging.info("Cleaning up cloned repositories...")
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR)
            logging.info(f"Removed directory: {TMP_DIR}")

        logging.info("Deleting persistent volume claims...")
        # Using labels to target PVCs, ignoring if not found
        pvc_commands = [
            ["kubectl", "delete", "pvc", "-n", "security-ops", "-l", "app.kubernetes.io/instance=mcaas-opensearch", "--ignore-not-found=true"],
            ["kubectl", "delete", "pvc", "-n", "security-ops", "-l", "app=wazuh-indexer", "--ignore-not-found=true"],
            ["kubectl", "delete", "pvc", "-n", "managed-it", "-l", "app.kubernetes.io/instance=mcaas-postgresql", "--ignore-not-found=true"]
        ]
        for cmd in pvc_commands:
            run_command(cmd)

        logging.info("Deleting resources from kustomization (including namespaces)...")
        run_command(["kubectl", "delete", "-k", str(PROJECT_ROOT / "deploy"), "--ignore-not-found=true"])

    except Exception as e:
        logging.error(f"An error occurred during teardown: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Teardown script finished. Logs written to {log_file}")

if __name__ == "__main__":
    main()