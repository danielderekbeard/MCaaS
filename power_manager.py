#!/usr/bin/env python3
"""
MCaaS Stack Power Manager

Gracefully shuts down (scales to 0) or powers on (restores replicas)
the Kubernetes stack deployed by the MCaaS deploy.py script.
"""

import os
import subprocess
import json
import argparse
import logging
from pathlib import Path

# --- Configuration ---
SCRIPT_ROOT = Path(__file__).parent.resolve()
STATE_FILE = SCRIPT_ROOT / ".tmp" / "power_state.json"

# Namespaces managed by the deployment script
NAMESPACES = ["managed-it", "security-ops", "grc", "wazuh"]

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def run_command(command):
    """Runs a shell command and returns the stdout."""
    try:
        result = subprocess.run(
            command, check=True, text=True, capture_output=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(command)}")
        logging.error(f"STDERR: {e.stderr}")
        raise

def shutdown():
    """Saves current replica counts and scales all resources to 0."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {}

    logging.info("Starting graceful shutdown of MCaaS stack...")

    for ns in NAMESPACES:
        logging.info(f"Scanning namespace: {ns}")
        state[ns] = {}
        
        # Get all Deployments and StatefulSets in JSON format
        cmd = ["kubectl", "get", "deployment,statefulset", "-n", ns, "-o", "json"]
        try:
            output = run_command(cmd)
            if not output:
                continue
                
            resources = json.loads(output).get("items", [])
            for res in resources:
                kind = res["kind"]
                name = res["metadata"]["name"]
                replicas = res["spec"].get("replicas", 1)
                
                # Only save state if it's currently running (not already 0)
                if replicas > 0:
                    state[ns][f"{kind}/{name}"] = replicas
                    
        except Exception as e:
            logging.warning(f"Could not read resources in {ns}: {e}")

    # Save state to file
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    logging.info(f"Saved cluster state to {STATE_FILE}")

    # Scale everything to 0
    for ns, resources in state.items():
        if not resources:
            continue
        for resource_name in resources.keys():
            logging.info(f"Scaling {resource_name} in {ns} to 0...")
            run_command(["kubectl", "scale", resource_name, "--replicas=0", "-n", ns])

    logging.info("Graceful shutdown complete. All MCaaS compute resources are suspended.")
    logging.info("Note: Storage (PVCs) and configurations remain safely intact.")

def poweron():
    """Reads saved replica counts and restores all resources."""
    if not STATE_FILE.exists():
        logging.error(f"State file {STATE_FILE} not found. Cannot power on.")
        logging.error("If you restarted your machine, you can also just re-run deploy.py.")
        return

    logging.info("Powering on MCaaS stack...")
    
    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    for ns, resources in state.items():
        for resource_name, original_replicas in resources.items():
            logging.info(f"Restoring {resource_name} in {ns} to {original_replicas} replicas...")
            try:
                run_command(["kubectl", "scale", resource_name, f"--replicas={original_replicas}", "-n", ns])
            except Exception as e:
                logging.warning(f"Failed to scale {resource_name}: {e}")

    logging.info("Power on initiated. Wait a few minutes for all pods to reach a 'Ready' state.")

def main():
    parser = argparse.ArgumentParser(description="Gracefully shutdown or power on the MCaaS stack.")
    parser.add_argument("action", choices=["shutdown", "poweron"], help="Action to perform")
    
    args = parser.parse_args()

    # Ensure kubectl connectivity before executing
    try:
        run_command(["kubectl", "auth", "can-i", "create", "deployments"])
    except Exception:
        logging.error("kubectl cannot authenticate to the cluster. Check your kubeconfig.")
        return

    if args.action == "shutdown":
        shutdown()
    elif args.action == "poweron":
        poweron()

if __name__ == "__main__":
    main()