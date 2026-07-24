#!/usr/bin/env python3
"""
MCaaS Teardown Script - Cross-platform (Windows, Linux, macOS)

This script handles teardown (uninstall) of the MCaaS stack including:
- Uninstalling all Helm releases
- Deleting Wazuh kustomize resources
- Deleting Kubernetes secrets
- Removing persistent volume claims
- Cleaning up cloned repositories
- Optionally removing namespaces

Works on Windows, Linux, and macOS.
"""

import os
import subprocess
import sys
import logging
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
import argparse

# --- Configuration ---
SCRIPT_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_ROOT  # The script is in the project root
LOG_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / ".tmp"

# Detect platform
PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == "Windows"
IS_POSIX = PLATFORM in ("Linux", "Darwin")

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


def run_command(command, check=True, shell=False, cwd=None):
    """Run a command and log its output.

    Args:
        command: List of command arguments (preferred) or string if shell=True.
        check: Raise exception if command fails.
        shell: Run command through shell.
        cwd: Working directory for the command.
    """
    cmd_str = " ".join(command) if isinstance(command, list) else command
    logging.info(f"Running: {cmd_str}")

    try:
        result = subprocess.run(
            command,
            check=check,
            text=True,
            capture_output=True,
            shell=shell,
            cwd=cwd
        )
        if result.stdout:
            logging.debug(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            logging.debug(f"STDERR:\n{result.stderr}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}")
        logging.error(f"Command: {cmd_str}")
        if e.stdout:
            logging.error(f"STDOUT: {e.stdout}")
        if e.stderr:
            logging.error(f"STDERR: {e.stderr}")
        raise
    except FileNotFoundError as e:
        logging.error(f"Command not found: {cmd_str}")
        logging.error(f"Error: {e}")
        raise


def helm_release_exists(release_name, namespace):
    """Check if a Helm release exists in the given namespace."""
    result = run_command(
        ["helm", "status", release_name, "--namespace", namespace],
        check=False
    )
    return result.returncode == 0


def uninstall_helm_releases():
    """Uninstall all Helm releases in reverse deployment order."""
    # Releases listed in reverse deployment order
    releases = [
        ("mcaas-ciso", "grc"),
        ("mcaas-zammad", "managed-it"),
        ("mcaas-shuffle", "security-ops"),
        ("mcaas-opensearch", "security-ops"),
        ("mcaas-postgresql", "managed-it"),
    ]

    for release_name, namespace in releases:
        logging.info(f"Uninstalling Helm release '{release_name}' from namespace '{namespace}'...")
        if helm_release_exists(release_name, namespace):
            run_command(["helm", "uninstall", release_name, "--namespace", namespace])
            logging.info(f"Helm release '{release_name}' uninstalled.")
        else:
            logging.info(f"Helm release '{release_name}' not found in namespace '{namespace}', skipping.")


def delete_wazuh_resources():
    """Delete Wazuh kustomize resources and namespace."""
    logging.info("Deleting Wazuh resources...")

    wazuh_env_dir = TMP_DIR / "wazuh-kubernetes" / "envs" / "local-env"
    if wazuh_env_dir.exists():
        logging.info(f"Deleting Wazuh kustomize resources from {wazuh_env_dir}...")
        run_command(
            ["kubectl", "delete", "-k", str(wazuh_env_dir), "--ignore-not-found=true"],
            check=False
        )
    else:
        logging.warning(
            f"Wazuh kustomize directory not found at {wazuh_env_dir}. "
            "Cannot delete Wazuh resources via kustomize. "
            "The namespace deletion will clean up remaining resources."
        )

    logging.info("Deleting Wazuh namespace...")
    run_command(
        ["kubectl", "delete", "namespace", "wazuh", "--ignore-not-found=true"],
        check=False
    )


def delete_secrets():
    """Delete Kubernetes secrets created by the deployment (5 secrets across 3 namespaces)."""
    secrets = [
        ("mcaas-postgresql-secret", "managed-it"),
        ("mcaas-postgresql-secret", "grc"),
        ("mcaas-opensearch-secret", "security-ops"),
        ("mcaas-zammad-redis-pass", "managed-it"),
        ("mcaas-ciso-ciso-assistant-backend", "grc"),
    ]

    for secret_name, namespace in secrets:
        logging.info(f"Deleting secret '{secret_name}' from namespace '{namespace}'...")
        run_command(
            ["kubectl", "delete", "secret", secret_name, "--namespace", namespace, "--ignore-not-found=true"],
            check=False
        )


def delete_pvcs():
    """Delete persistent volume claims created by the stack."""
    pvc_labels = [
        ("security-ops", "app.kubernetes.io/instance=mcaas-opensearch"),
        ("managed-it", "app.kubernetes.io/instance=mcaas-postgresql"),
        ("managed-it", "app.kubernetes.io/instance=mcaas-zammad"),
        ("security-ops", "app.kubernetes.io/instance=mcaas-shuffle"),
    ]

    for namespace, label in pvc_labels:
        logging.info(f"Deleting PVCs in namespace '{namespace}' with label '{label}'...")
        run_command(
            ["kubectl", "delete", "pvc", "-n", namespace, "-l", label, "--ignore-not-found=true"],
            check=False
        )


def delete_base_manifests():
    """Delete base kustomize manifests (namespaces, etc.)."""
    logging.info("Deleting base kustomize manifests...")
    run_command(
        ["kubectl", "delete", "-k", str(PROJECT_ROOT / "deploy"), "--ignore-not-found=true"],
        check=False
    )


def cleanup_tmp():
    """Remove cloned repositories from .tmp directory."""
    logging.info("Cleaning up cloned repositories...")
    wazuh_dir = TMP_DIR / "wazuh-kubernetes"
    if wazuh_dir.exists():
        shutil.rmtree(str(wazuh_dir), ignore_errors=True)
        logging.info(f"Removed {wazuh_dir}")
    else:
        logging.info("No Wazuh clone directory found, nothing to clean up.")


def main():
    """Main teardown logic."""
    parser = argparse.ArgumentParser(description="Tear down MCaaS stack")
    parser.add_argument(
        "--skip-namespaces", action="store_true",
        help="Skip deletion of namespaces (useful if other workloads share them)"
    )
    parser.add_argument(
        "--skip-pvcs", action="store_true",
        help="Skip deletion of persistent volume claims (preserve data)"
    )
    parser.add_argument(
        "--skip-cleanup", action="store_true",
        help="Skip cleanup of cloned repositories in .tmp directory"
    )
    args = parser.parse_args()

    try:
        logging.info(f"Starting MCaaS teardown on {PLATFORM}")

        # 1. Uninstall Helm releases (reverse deployment order)
        logging.info("=== Uninstalling Helm releases ===")
        uninstall_helm_releases()

        # 2. Delete Wazuh kustomize resources
        logging.info("=== Deleting Wazuh resources ===")
        delete_wazuh_resources()

        # 3. Delete secrets
        logging.info("=== Deleting Kubernetes secrets ===")
        delete_secrets()

        # 4. Delete PVCs (unless --skip-pvcs)
        if args.skip_pvcs:
            logging.info("Skipping PVC deletion (--skip-pvcs flag set).")
        else:
            logging.info("=== Deleting persistent volume claims ===")
            delete_pvcs()

        # 5. Delete base manifests / namespaces (unless --skip-namespaces)
        if args.skip_namespaces:
            logging.info("Skipping namespace deletion (--skip-namespaces flag set).")
        else:
            logging.info("=== Deleting base manifests and namespaces ===")
            delete_base_manifests()

        # 6. Cleanup cloned repos (unless --skip-cleanup)
        if args.skip_cleanup:
            logging.info("Skipping .tmp cleanup (--skip-cleanup flag set).")
        else:
            cleanup_tmp()

        logging.info("Teardown complete!")

    except Exception as e:
        logging.error(f"An error occurred during teardown: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Logs written to {log_file}")


if __name__ == "__main__":
    main()