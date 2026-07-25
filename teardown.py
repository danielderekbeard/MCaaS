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
import yaml

# --- Configuration ---
SCRIPT_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_ROOT  # The script is in the project root
LOG_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / ".tmp"

# Detect platform
PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == "Windows"
IS_POSIX = PLATFORM in ("Linux", "Darwin")

# --- Default Configuration ---
# When --client is not specified, these defaults preserve the original
# hardcoded behaviour of the script.
DEFAULT_CONFIG = {
    "prefix": "mcaas",
    "namespaces": {
        "managed-it": "managed-it",
        "security-ops": "security-ops",
        "grc": "grc",
        "wazuh": "wazuh",
    },
    "domain": "mcaas.local",
    "database_name": "mcaas",
    "wazuh_version": "4.14.6",
    "ingress": {
        "zammad_host": "zammad.mcaas.local",
        "ciso_host": "ciso.mcaas.local",
    },
    "client_name": None,
    "env_prefix": "MCAAS",
    "client_dir": None,
    "values_dir": PROJECT_ROOT / "deploy" / "values",
}


def load_client_config(client_name):
    """Load a client-specific configuration from clients/<name>/config.yaml.

    When *client_name* is ``None``, returns :data:`DEFAULT_CONFIG` so that
    calling the script without ``--client`` behaves exactly as before.

    The returned dict contains:
      - prefix: resource name prefix (e.g. "mcaas" or "acme")
      - namespaces: dict mapping logical names to actual K8s namespace names
      - domain: base domain for ingress hosts
      - database_name: PostgreSQL database name
      - wazuh_version: Wazuh version tag for kustomize/git checkout
      - ingress: dict with zammad_host and ciso_host
      - client_name: the client name (or None for default)
      - env_prefix: uppercase prefix for environment variables
      - client_dir: Path to the client directory (or None for default)
      - values_dir: Path to the Helm values directory for this client
    """
    if client_name is None:
        return DEFAULT_CONFIG

    client_dir = PROJECT_ROOT / "clients" / client_name
    config_path = client_dir / "config.yaml"

    if not config_path.exists():
        logging.error(f"Client configuration not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    # Support both nested (client.key) and flat (key) config formats.
    # The standard client config files use a top-level "client" key:
    #   client:
    #     name: aws
    #     prefix: mcaas
    #     ...
    # Older or simpler configs may use flat top-level keys.
    if raw and "client" in raw:
        c = raw["client"]
    else:
        c = raw

    if not c:
        logging.error(f"Client config is empty: {config_path}")
        sys.exit(1)

    # Validate required fields
    for field in ("name", "prefix", "domain", "database_name"):
        if field not in c:
            logging.error(f"Client config missing required field: {field}")
            sys.exit(1)

    prefix = c["prefix"]

    # Build namespace mapping — auto-generate from prefix if not specified
    namespaces = c.get("namespaces", {}) or {}
    ns = {}
    for key in ("managed-it", "security-ops", "grc", "wazuh"):
        ns[key] = namespaces.get(key, f"{prefix}-{key}")

    # Build ingress host mapping
    ingress_raw = c.get("ingress", {}) or {}
    ingress = {
        "zammad_host": ingress_raw.get("zammad_host", f"zammad.{c['domain']}"),
        "ciso_host": ingress_raw.get("ciso_host", f"ciso.{c['domain']}"),
        "shuffle_host": ingress_raw.get("shuffle_host", f"shuffle.{c['domain']}"),
        "wazuh_host": ingress_raw.get("wazuh_host", f"wazuh.{c['domain']}"),
    }

    # Environment variable prefix: MCAAS, ACME, etc. (uppercased, dashes→underscores)
    env_prefix = prefix.upper().replace("-", "_")

    return {
        "prefix": prefix,
        "namespaces": ns,
        "domain": c["domain"],
        "database_name": c["database_name"],
        "wazuh_version": c.get("wazuh_version", DEFAULT_CONFIG["wazuh_version"]),
        "ingress": ingress,
        "client_name": client_name,
        "env_prefix": env_prefix,
        "client_dir": client_dir,
        "values_dir": client_dir / "values",
    }


# --- Logging Setup ---
LOG_DIR.mkdir(exist_ok=True)
log_file = (
    LOG_DIR / f"teardown-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)


def _add_tls_skip(command):
    """Add --insecure-skip-tls-verify to kubectl commands for self-signed clusters.

    This is a safety net alongside kubeconfig patching.  The CI workflows replace
    certificate-authority-data with insecure-skip-tls-verify: true in the kubeconfig,
    but some environments or tool versions may not fully honour that setting.  Passing
    the flag explicitly ensures we can always reach the local k3s / Rancher Desktop
    cluster whose API server uses a self-signed certificate.

    Note: ``--insecure-skip-tls-verify`` is a kubectl flag only — Helm does not
    support it (Helm reads TLS settings from the kubeconfig instead).
    """
    if (
        isinstance(command, list)
        and len(command) >= 1
        and command[0] == "kubectl"
    ):
        # Don't add the flag twice.
        if "--insecure-skip-tls-verify" not in command:
            command = command + ["--insecure-skip-tls-verify"]
    return command


def run_command(command, check=True, shell=False, cwd=None):
    """Run a command and log its output.

    For kubectl/helm commands the ``--insecure-skip-tls-verify`` flag is injected
    automatically so that self-signed clusters are always reachable, even when the
    kubeconfig patching is incomplete or ignored by the tool.

    Args:
        command: List of command arguments (preferred) or string if shell=True.
        check: Raise exception if command fails.
        shell: Run command through shell.
        cwd: Working directory for the command.
    """
    command = _add_tls_skip(command)
    cmd_str = " ".join(command) if isinstance(command, list) else command
    logging.info(f"Running: {cmd_str}")

    try:
        result = subprocess.run(
            command, check=check, text=True, capture_output=True, shell=shell, cwd=cwd
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


def verify_cluster_connectivity():
    """Verify that kubectl can reach the cluster before proceeding with teardown.

    Exits with an error if the cluster is unreachable, which avoids cascading
    failures from helm/kubectl commands that all fail for the same reason.
    """
    logging.info("Verifying cluster connectivity...")
    result = run_command(["kubectl", "cluster-info"], check=False)
    if result.returncode != 0:
        logging.error("Cluster is unreachable. Please verify your kubeconfig.")
        logging.error("STDOUT: %s", result.stdout)
        logging.error("STDERR: %s", result.stderr)
        sys.exit(1)
    logging.info("Cluster connectivity verified.")


def helm_release_exists(release_name, namespace):
    """Check if a Helm release exists in the given namespace."""
    result = run_command(
        ["helm", "status", release_name, "--namespace", namespace], check=False
    )
    return result.returncode == 0


def uninstall_helm_releases(cfg):
    """Uninstall all Helm releases in reverse deployment order.

    Each release is checked first with ``helm status``; if the release does not
    exist it is skipped.  Failures to uninstall an existing release are logged
    but do **not** abort the teardown so that remaining resources can still be
    cleaned up.
    """
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    # Releases listed in reverse deployment order
    releases = [
        (f"{prefix}-ciso", ns["grc"]),
        (f"{prefix}-zammad", ns["managed-it"]),
        (f"{prefix}-shuffle", ns["security-ops"]),
        (f"{prefix}-opensearch", ns["security-ops"]),
        (f"{prefix}-postgresql", ns["managed-it"]),
    ]

    errors = []
    for release_name, namespace in releases:
        logging.info(
            f"Uninstalling Helm release '{release_name}' from namespace '{namespace}'..."
        )
        if helm_release_exists(release_name, namespace):
            result = run_command(
                ["helm", "uninstall", release_name, "--namespace", namespace],
                check=False,
            )
            if result.returncode == 0:
                logging.info(f"Helm release '{release_name}' uninstalled.")
            else:
                logging.warning(
                    f"Failed to uninstall Helm release '{release_name}' "
                    f"(exit code {result.returncode}). Continuing..."
                )
                errors.append(f"helm uninstall {release_name}")
        else:
            logging.info(
                f"Helm release '{release_name}' not found in namespace '{namespace}', skipping."
            )

    if errors:
        logging.warning(
            f"The following Helm releases could not be uninstalled: {', '.join(errors)}"
        )


def delete_wazuh_resources(cfg):
    """Delete Wazuh kustomize resources and namespace."""
    logging.info("Deleting Wazuh resources...")
    wazuh_ns = cfg["namespaces"]["wazuh"]

    wazuh_env_dir = TMP_DIR / "wazuh-kubernetes" / "envs" / "local-env"
    if wazuh_env_dir.exists():
        logging.info(f"Deleting Wazuh kustomize resources from {wazuh_env_dir}...")
        run_command(
            ["kubectl", "delete", "-k", str(wazuh_env_dir), "--ignore-not-found=true"],
            check=False,
        )
    else:
        logging.warning(
            f"Wazuh kustomize directory not found at {wazuh_env_dir}. "
            "Cannot delete Wazuh resources via kustomize. "
            "The namespace deletion will clean up remaining resources."
        )

    logging.info("Deleting Wazuh namespace...")
    run_command(
        ["kubectl", "delete", "namespace", wazuh_ns, "--ignore-not-found=true"],
        check=False,
    )


def delete_secrets(cfg):
    """Delete Kubernetes secrets created by the deployment (5 secrets across 3 namespaces)."""
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    secrets = [
        (f"{prefix}-postgresql-secret", ns["managed-it"]),
        (f"{prefix}-postgresql-secret", ns["grc"]),
        (f"{prefix}-opensearch-secret", ns["security-ops"]),
        (f"{prefix}-zammad-redis-pass", ns["managed-it"]),
        (f"{prefix}-ciso-secret", ns["grc"]),
    ]

    for secret_name, namespace in secrets:
        logging.info(f"Deleting secret '{secret_name}' from namespace '{namespace}'...")
        run_command(
            [
                "kubectl",
                "delete",
                "secret",
                secret_name,
                "--namespace",
                namespace,
                "--ignore-not-found=true",
            ],
            check=False,
        )


def delete_pvcs(cfg):
    """Delete persistent volume claims created by the stack."""
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    pvc_labels = [
        (ns["security-ops"], f"app.kubernetes.io/instance={prefix}-opensearch"),
        (ns["managed-it"], f"app.kubernetes.io/instance={prefix}-postgresql"),
        (ns["managed-it"], f"app.kubernetes.io/instance={prefix}-zammad"),
        (ns["security-ops"], f"app.kubernetes.io/instance={prefix}-shuffle"),
    ]

    # Wazuh PVCs use different labels (app=wazuh-indexer / app=wazuh-manager)
    wazuh_pvc_labels = [
        (ns["wazuh"], "app=wazuh-indexer"),
        (ns["wazuh"], "app=wazuh-manager"),
    ]

    for namespace, label in pvc_labels:
        logging.info(
            f"Deleting PVCs in namespace '{namespace}' with label '{label}'..."
        )
        run_command(
            [
                "kubectl",
                "delete",
                "pvc",
                "-n",
                namespace,
                "-l",
                label,
                "--ignore-not-found=true",
            ],
            check=False,
        )

    for namespace, label in wazuh_pvc_labels:
        logging.info(
            f"Deleting Wazuh PVCs in namespace '{namespace}' with label '{label}'..."
        )
        run_command(
            [
                "kubectl",
                "delete",
                "pvc",
                "-n",
                namespace,
                "-l",
                label,
                "--ignore-not-found=true",
            ],
            check=False,
        )


def delete_base_manifests(cfg):
    """Delete base kustomize manifests (namespaces, etc.)."""
    logging.info("Deleting base manifests...")
    if cfg["client_name"] is not None:
        # Client-specific: delete the client's namespaces.yaml directly
        namespaces_file = cfg["client_dir"] / "namespaces.yaml"
        if namespaces_file.exists():
            run_command(
                [
                    "kubectl",
                    "delete",
                    "-f",
                    str(namespaces_file),
                    "--ignore-not-found=true",
                ],
                check=False,
            )
        else:
            logging.warning(f"Client namespaces file not found: {namespaces_file}")
    else:
        # Default: use the deploy/ kustomize directory
        run_command(
            [
                "kubectl",
                "delete",
                "-k",
                str(PROJECT_ROOT / "deploy"),
                "--ignore-not-found=true",
            ],
            check=False,
        )


def cleanup_tmp():
    """Remove cloned repositories from .tmp directory and .env file."""
    logging.info("Cleaning up cloned repositories...")
    wazuh_dir = TMP_DIR / "wazuh-kubernetes"
    if wazuh_dir.exists():
        shutil.rmtree(str(wazuh_dir), ignore_errors=True)
        logging.info(f"Removed {wazuh_dir}")
    else:
        logging.info("No Wazuh clone directory found, nothing to clean up.")

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        env_file.unlink()
        logging.info(f"Removed {env_file}")
    else:
        logging.info("No .env file found, nothing to clean up.")


def main():
    """Main teardown logic."""
    parser = argparse.ArgumentParser(description="Tear down MCaaS stack")
    parser.add_argument(
        "--client",
        help="Client name to tear down (loads clients/<name>/config.yaml). "
        "If omitted, uses default mcaas configuration.",
    )
    parser.add_argument(
        "--skip-namespaces",
        action="store_true",
        help="Skip deletion of namespaces (useful if other workloads share them)",
    )
    parser.add_argument(
        "--skip-pvcs",
        action="store_true",
        help="Skip deletion of persistent volume claims (preserve data)",
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip cleanup of cloned repositories in .tmp directory",
    )
    args = parser.parse_args()

    # Load configuration (default or client-specific)
    cfg = load_client_config(args.client)
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]

    try:
        logging.info(
            f"Starting MCaaS teardown on {PLATFORM} (client={cfg['client_name'] or 'default'}, prefix={prefix})"
        )

        # 0. Verify cluster connectivity before doing anything else
        verify_cluster_connectivity()

        # 1. Uninstall Helm releases (reverse deployment order)
        logging.info("=== Uninstalling Helm releases ===")
        uninstall_helm_releases(cfg)

        # 2. Delete Wazuh kustomize resources
        logging.info("=== Deleting Wazuh resources ===")
        delete_wazuh_resources(cfg)

        # 3. Delete secrets
        logging.info("=== Deleting Kubernetes secrets ===")
        delete_secrets(cfg)

        # 4. Delete PVCs (unless --skip-pvcs)
        if args.skip_pvcs:
            logging.info("Skipping PVC deletion (--skip-pvcs flag set).")
        else:
            logging.info("=== Deleting persistent volume claims ===")
            delete_pvcs(cfg)

        # 5. Delete base manifests / namespaces (unless --skip-namespaces)
        if args.skip_namespaces:
            logging.info("Skipping namespace deletion (--skip-namespaces flag set).")
        else:
            logging.info("=== Deleting base manifests and namespaces ===")
            delete_base_manifests(cfg)

        # 6. Cleanup cloned repos (unless --skip-cleanup)
        if args.skip_cleanup:
            logging.info("Skipping .tmp cleanup (--skip-cleanup flag set).")
        else:
            cleanup_tmp()

        logging.info("Teardown complete!")

    except SystemExit:
        raise  # Re-raise SystemExit (e.g. from verify_cluster_connectivity)
    except Exception as e:
        logging.error(f"An error occurred during teardown: {e}")
        logging.error(
            "Some resources may not have been fully cleaned up. "
            "Re-run the teardown script to retry, or manually inspect the cluster."
        )
        sys.exit(1)
    finally:
        logging.info(f"Logs written to {log_file}")


if __name__ == "__main__":
    main()
