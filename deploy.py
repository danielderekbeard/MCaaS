#!/usr/bin/env python3
"""
MCaaS Deployment Script - Cross-platform (Windows, Linux, macOS)

This script handles deployment of the MCaaS stack including:
- PostgreSQL, OpenSearch, Wazuh, Shuffle, Zammad, and CISO Assistant
- Works on Windows, Linux, and macOS
- Handles platform-specific path and command issues
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
log_file = LOG_DIR / f"deploy-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

def check_prerequisites():
    """Verify that required tools are installed.

    In dry‑run mode we only need to log the check – the actual tools are not
    required because no commands will be executed.
    """
    if globals().get("DRY_RUN", False):
        logging.info("Dry‑run mode: skipping prerequisite tool checks.")
        return

    required_tools = ["kubectl", "helm", "git"]
    missing = []
    
    for tool in required_tools:
        if shutil.which(tool) is None:
            missing.append(tool)
    
    if missing:
        logging.error(f"Missing required tools: {', '.join(missing)}")
        logging.error("Please install the missing tools and try again.")
        if IS_WINDOWS:
            logging.error("On Windows, ensure kubectl, helm, and git are in your PATH.")
        sys.exit(1)
    
    logging.info("All prerequisites are available.")

def run_command(command, check=True, shell=False, cwd=None):
    """Runs a command and logs its output.

    When ``DRY_RUN`` is enabled we add ``--dry-run=client`` to ``helm`` and
    ``kubectl`` invocations so that no resources are actually created or
    modified. The flag is appended only to list‑type commands to avoid breaking
    string commands that may already contain their own options.
    
    Args:
        command: List of command arguments (preferred) or string if shell=True
        check: Raise exception if command fails
        shell: Run command through shell (generally not recommended)
        cwd: Working directory for the command
    """
    # Inject dry‑run flag for helm/kubectl when appropriate
    if isinstance(command, list) and globals().get("DRY_RUN", False):
        if command[0] in ("helm", "kubectl"):
            # Avoid duplicate flags if the user already supplied one
            if "--dry-run=client" not in command:
                command = command + ["--dry-run=client"]

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

def wait_for_deployment(namespace, deployment_name, timeout="5m"):
    """Waits for a Kubernetes deployment to become available.

    In dry‑run mode the resources are not actually created, so we skip the
    wait entirely.
    """
    if globals().get("DRY_RUN", False):
        logging.info(f"Dry‑run: skipping wait for deployment '{deployment_name}' in namespace '{namespace}'.")
        return

    logging.info(f"Waiting for deployment '{deployment_name}' in namespace '{namespace}' to be ready...")
    cmd = [
        "kubectl", "wait", 
        f"--for=condition=available",
        "--namespace", namespace,
        f"deployment/{deployment_name}",
        f"--timeout={timeout}"
    ]
    run_command(cmd)
    logging.info(f"Deployment '{deployment_name}' is ready.")

def clone_or_use_wazuh_repo(wazuh_dir):
    """Clone Wazuh repo or use existing.
    
    On Windows, we handle symlinks by cloning with --no-checkout and then
    checking out individual files. On POSIX systems, normal clone works.
    """
    if wazuh_dir.exists():
        logging.info(f"Wazuh repo already exists at {wazuh_dir}")
        return
    
    logging.info("Cloning Wazuh repository...")
    wazuh_dir.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if IS_WINDOWS:
            # On Windows, clone with --depth 1 to minimize symlink issues
            run_command([
                "git", "clone",
                "--depth", "1",
                "--no-checkout",
                "https://github.com/wazuh/wazuh-kubernetes.git",
                str(wazuh_dir)
            ])
            # Now checkout the specific directory we need
            run_command([
                "git", "checkout", "HEAD", "envs/local-env"
            ], cwd=str(wazuh_dir))
        else:
            # On POSIX, normal clone works fine
            run_command([
                "git", "clone",
                "--depth", "1",
                "https://github.com/wazuh/wazuh-kubernetes.git",
                str(wazuh_dir)
            ])
    except subprocess.CalledProcessError:
        logging.warning("Failed to clone Wazuh repo locally, will use remote URL with kubectl")
        return None
    
    return wazuh_dir

def deploy_wazuh(wazuh_dir):
    """Deploy Wazuh using kubectl apply.
    
    On Windows the local clone often lacks the required certificate files and can contain broken symlinks. To guarantee a reliable deployment we now always use the remote kustomize URL when running on Windows. On POSIX systems we still attempt a local clone first and fall back to the remote URL if needed.
    """
    logging.info("Deploying Wazuh from manifests...")

    remote_kustomize = "https://github.com/wazuh/wazuh-kubernetes//envs/local-env?ref=v4.14.6"

    if IS_WINDOWS:
        # On Windows always use the remote URL to avoid symlink and cert issues.
        kustomize_path = remote_kustomize
        logging.info("Running on Windows – using remote Wazuh manifests to avoid filesystem issues.")
    else:
        # Prefer a local clone, but verify it contains the expected certificate.
        local_kustomize = wazuh_dir and (wazuh_dir / "envs" / "local-env")
        required_cert = wazuh_dir and (wazuh_dir / "wazuh" / "config" / "indexer" / "certs" / "admin-key.pem")

        if local_kustomize and local_kustomize.exists() and required_cert and required_cert.exists():
            kustomize_path = str(local_kustomize)
        else:
            logging.warning("Local Wazuh clone is incomplete or missing; falling back to remote manifests")
            kustomize_path = remote_kustomize

    run_command(["kubectl", "apply", "-k", kustomize_path])

def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        logging.info(f"Loading environment from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, sep, value = line.partition('=')
                    if sep:
                        os.environ[key.strip()] = value.strip()

def main():
    """Main deployment logic."""
    try:
        logging.info(f"Starting MCaaS deployment on {PLATFORM}")
        
        # Load environment variables
        load_env_file()
        
        # Verify prerequisites
        check_prerequisites()
        
        logging.info("Adding and updating Helm repositories...")
        run_command(["helm", "repo", "add", "bitnami", "https://charts.bitnami.com/bitnami"], check=False)
        run_command(["helm", "repo", "add", "opensearch", "https://opensearch-project.github.io/helm-charts"], check=False)
        run_command(["helm", "repo", "add", "zammad", "https://zammad.github.io/zammad-helm"], check=False)
        run_command(["helm", "repo", "update"])

        logging.info("Applying namespaces and base manifests...")
        run_command(["kubectl", "apply", "-k", str(PROJECT_ROOT / "deploy")])

        logging.info("Deploying PostgreSQL...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-postgresql", "bitnami/postgresql",
            "--namespace", "managed-it",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "postgresql.yaml"),
            "--wait", "--timeout", "5m"
        ])

        logging.info("Deploying OpenSearch...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-opensearch", "opensearch/opensearch",
            "--namespace", "security-ops",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "opensearch.yaml"),
            "--wait", "--timeout", "5m"
        ])

        # Clone or prepare Wazuh repo
        wazuh_dir = TMP_DIR / "wazuh-kubernetes"
        clone_or_use_wazuh_repo(wazuh_dir)
        
        # Deploy Wazuh
        deploy_wazuh(wazuh_dir)

        logging.info("Waiting for Wazuh components to be ready...")
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-manager", "-n", "security-ops", "--timeout=5m"], check=False)
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-indexer", "-n", "security-ops", "--timeout=5m"], check=False)
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-dashboard", "-n", "security-ops", "--timeout=5m"], check=False)

        logging.info("Deploying Shuffle (OCI chart)...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-shuffle", "oci://ghcr.io/shuffle/charts/shuffle",
            "--namespace", "security-ops",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "shuffle.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_deployment("security-ops", "mcaas-shuffle")

        logging.info("Deploying Zammad...")
        run_command([
            "helm", "upgrade", "--install", "zammad", "zammad/zammad",
            "--namespace", "managed-it",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "zammad.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_deployment("managed-it", "zammad-zammad-scheduler")
        wait_for_deployment("managed-it", "zammad-zammad-websocket")
        wait_for_deployment("managed-it", "zammad-zammad-web")

        logging.info("Deploying CISO Assistant...")
        run_command([
            "helm", "upgrade", "--install", "ciso-assistant", "oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant",
            "--version", "0.11.4",
            "--namespace", "grc",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "ciso-assistant.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_deployment("grc", "ciso-assistant-frontend")
        wait_for_deployment("grc", "ciso-assistant-backend")

        logging.info("Deployment complete!")

    except Exception as e:
        logging.error(f"An error occurred during deployment: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Logs written to {log_file}")

if __name__ == "__main__":
    main()