#!/usr/bin/env python3
import os
import subprocess
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---
SCRIPT_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_ROOT  # The script is in the project root
LOG_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / ".tmp"

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

def run_command(command, check=True):
    """Runs a command and logs its output."""
    logging.info(f"Running command: {' '.join(command)}")
    try:
        # Using list format for command is safer
        subprocess.run(command, check=check, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}")
        logging.error(f"STDOUT: {e.stdout}")
        logging.error(f"STDERR: {e.stderr}")
        raise

def wait_for_deployment(namespace, deployment_name, timeout="5m"):
    """Waits for a Kubernetes deployment to become available."""
    logging.info(f"Waiting for deployment '{deployment_name}' in namespace '{namespace}' to be ready...")
    cmd = [
        "kubectl", "wait", f"--for=condition=available",
        "--namespace", namespace,
        f"deployment/{deployment_name}",
        f"--timeout={timeout}"
    ]
    run_command(cmd)
    logging.info(f"Deployment '{deployment_name}' is ready.")

def main():
    """Main deployment logic."""
    try:
        logging.info("Adding and updating Helm repositories...")
        run_command(["helm", "repo", "add", "bitnami", "https://charts.bitnami.com/bitnami"])
        run_command(["helm", "repo", "add", "opensearch", "https://opensearch-project.github.io/helm-charts"])
        run_command(["helm", "repo", "add", "zammad", "https://zammad.github.io/zammad-helm"])
        run_command(["helm", "repo", "update"])

        logging.info("Applying namespaces and base manifests...")
        run_command(["kubectl", "apply", "-k", str(PROJECT_ROOT / "deploy")])

        logging.info("Deploying PostgreSQL...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-postgresql", "bitnami/postgresql",
            "--namespace", "managed-it",
            "--values", str(PROJECT_ROOT / "deploy/values/postgresql.yaml"),
            "--wait", "--timeout", "5m"
        ])

        logging.info("Deploying OpenSearch...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-opensearch", "opensearch/opensearch",
            "--namespace", "security-ops",
            "--values", str(PROJECT_ROOT / "deploy/values/opensearch.yaml"),
            "--wait", "--timeout", "5m"
        ])

        logging.info("Cloning Wazuh repository...")
        TMP_DIR.mkdir(exist_ok=True)
        wazuh_dir = TMP_DIR / "wazuh-kubernetes"
        if not wazuh_dir.exists():
            run_command(["git", "clone", "--depth", "1", "https://github.com/wazuh/wazuh-kubernetes.git", str(wazuh_dir)])

        logging.info("Deploying Wazuh from manifests...")
        run_command(["kubectl", "apply", "-k", str(wazuh_dir / "envs/local-env")])

        logging.info("Waiting for Wazuh components to be ready...")
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-manager", "-n", "security-ops", "--timeout=5m"])
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-indexer", "-n", "security-ops", "--timeout=5m"])
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-dashboard", "-n", "security-ops", "--timeout=5m"])

        logging.info("Deploying Shuffle (OCI chart)...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-shuffle", "oci://ghcr.io/shuffle/charts/shuffle",
            "--namespace", "security-ops",
            "--values", str(PROJECT_ROOT / "deploy/values/shuffle.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_deployment("security-ops", "mcaas-shuffle")

        logging.info("Deploying Zammad...")
        run_command([
            "helm", "upgrade", "--install", "zammad", "zammad/zammad",
            "--namespace", "managed-it",
            "--values", str(PROJECT_ROOT / "deploy/values/zammad.yaml"),
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
            "--values", str(PROJECT_ROOT / "deploy/values/ciso-assistant.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_deployment("grc", "ciso-assistant-frontend")
        wait_for_deployment("grc", "ciso-assistant-backend")

    except Exception as e:
        logging.error(f"An error occurred during deployment: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Deployment script finished. Logs written to {log_file}")

if __name__ == "__main__":
    main()