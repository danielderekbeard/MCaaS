#!/usr/bin/env python3
"""
MCaaS AWS/EKS Full Infrastructure-as-Code Deployment Script

This script provides a complete end-to-end deployment of the MCaaS stack on
AWS Elastic Kubernetes Service (EKS). It handles:

1. AWS infrastructure provisioning (EKS cluster via eksctl)
2. AWS-specific add-ons (EBS CSI driver, AWS Load Balancer Controller,
   cert-manager for TLS)
3. AWS-specific Kubernetes resources (StorageClasses, namespaces)
4. Application deployment (reuses the same Helm charts and values as deploy.py)

This is a FULL IaC approach — no existing files are modified. All AWS-specific
configuration lives in:
  - aws/eksctl-cluster.yaml       — EKS cluster definition
  - aws/storage-classes.yaml      — EBS-backed StorageClasses
  - aws/aws-load-balancer-controller.yaml — ALB Controller manifest
  - clients/aws/config.yaml       — AWS client configuration
  - clients/aws/values/            — AWS-optimized Helm values

Usage:
  python deploy-aws.py                           # Full deployment
  python deploy-aws.py --dry-run                 # Dry-run (no changes)
  python deploy-aws.py --client aws              # Use AWS client config
  python deploy-aws.py --skip-cluster            # Skip cluster creation
  python deploy-aws.py --skip-infrastructure     # Skip AWS infra setup
  python deploy-aws.py --tear-down               # Destroy the EKS cluster
  python deploy-aws.py --cloudflare-token TOKEN   # Enable Cloudflare DNS01
"""

import os
import subprocess
import sys
import logging
import platform
import shutil
import secrets
import string
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import argparse

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install it with: pip install pyyaml")
    sys.exit(1)

# --- Configuration ---
SCRIPT_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_ROOT
LOG_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / ".tmp"
AWS_DIR = PROJECT_ROOT / "aws"

# Detect platform
PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == "Windows"
IS_POSIX = PLATFORM in ("Linux", "Darwin")

# Default EKS cluster configuration
DEFAULT_EKS_CLUSTER = "mcaas-eks"
DEFAULT_EKS_REGION = "eu-west-1"
EKSCTL_CLUSTER_CONFIG = AWS_DIR / "eksctl-cluster.yaml"


# --- AWS Client Configuration (mirrors deploy.py DEFAULT_CONFIG) ---
AWS_CONFIG = {
    "prefix": "mcaas",
    "namespaces": {
        "managed-it": "managed-it",
        "security-ops": "security-ops",
        "grc": "grc",
        "wazuh": "wazuh",
    },
    "domain": "app.skyddex.com",
    "database_name": "mcaas_db",
    "wazuh_version": "4.14.6",
    "ingress": {
        "zammad_host": "zammad.app.skyddex.com",
        "ciso_host": "ciso.app.skyddex.com",
    },
}


def load_aws_client_config(client_name: str | None) -> dict:
    """Load client configuration, mirroring deploy.py's load_client_config().

    When client_name is None, returns the AWS_CONFIG defaults.
    When a client name is provided, loads from clients/<name>/config.yaml.
    """
    if client_name is None:
        cfg = dict(AWS_CONFIG)
        cfg["client_name"] = None
        cfg["env_prefix"] = "MCAAS"
        cfg["client_dir"] = None
        cfg["values_dir"] = AWS_DIR / "values"
        # For AWS deployment, also look for client-specific values
        aws_client_dir = PROJECT_ROOT / "clients" / "aws"
        if aws_client_dir.exists():
            cfg["values_dir"] = aws_client_dir / "values"
        return cfg

    client_dir = PROJECT_ROOT / "clients" / client_name
    config_file = client_dir / "config.yaml"

    if not config_file.exists():
        logging.error(f"Client config not found: {config_file}")
        logging.error(
            f"Create the directory clients/{client_name}/ with a config.yaml file."
        )
        sys.exit(1)

    logging.info(f"Loading client configuration from {config_file}")
    with open(config_file, "r") as f:
        raw = yaml.safe_load(f)

    if not raw or "client" not in raw:
        logging.error(
            f"Invalid config file: missing top-level 'client' key in {config_file}"
        )
        sys.exit(1)

    c = raw["client"]

    for field in ("name", "prefix", "domain", "database_name"):
        if not c.get(field):
            logging.error(f"Client config missing required field: client.{field}")
            sys.exit(1)

    ns = c.get("namespaces", {}) or {}
    namespaces = {
        "managed-it": ns.get("managed-it") or f"{c['prefix']}-managed-it",
        "security-ops": ns.get("security-ops") or f"{c['prefix']}-security-ops",
        "grc": ns.get("grc") or f"{c['prefix']}-grc",
        "wazuh": ns.get("wazuh") or f"{c['prefix']}-wazuh",
    }

    ingress = c.get("ingress", {}) or {}
    zammad_host = ingress.get("zammad_host") or f"zammad.{c['domain']}"
    ciso_host = ingress.get("ciso_host") or f"ciso.{c['domain']}"

    cfg = {
        "prefix": c["prefix"],
        "namespaces": namespaces,
        "domain": c["domain"],
        "database_name": c["database_name"],
        "wazuh_version": c.get("wazuh_version", "4.14.6"),
        "ingress": {
            "zammad_host": zammad_host,
            "ciso_host": ciso_host,
        },
        "client_name": client_name,
        "env_prefix": c["prefix"].upper().replace("-", "_"),
        "client_dir": client_dir,
        "values_dir": client_dir / "values",
    }
    return cfg


# --- Logging Setup ---
LOG_DIR.mkdir(exist_ok=True)
log_file = (
    LOG_DIR / f"deploy-aws-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)


# ============================================================
# Utility functions (mirrors deploy.py patterns)
# ============================================================


def run_command(command, check=True, shell=False, cwd=None, input_data=None):
    """Run a command and log its output.

    In dry-run mode, adds --dry-run=client to helm/kubectl commands.
    """
    if isinstance(command, list) and globals().get("DRY_RUN", False):
        if command[0] == "helm" and ("upgrade" in command or "install" in command):
            command = [c for c in command if c != "--wait"]
            if "--dry-run=client" not in command:
                command = command + ["--dry-run=client"]
        elif command[0] == "kubectl":
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
            cwd=cwd,
            input=input_data,
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


def wait_for_resource(namespace, resource_name, timeout="5m"):
    """Wait for a Kubernetes Deployment or StatefulSet to become ready."""
    if globals().get("DRY_RUN", False):
        logging.info(
            f"Dry-run: skipping wait for resource '{resource_name}' in namespace '{namespace}'."
        )
        return

    logging.info(
        f"Waiting for resource '{resource_name}' in namespace '{namespace}' to be ready..."
    )

    # Try Deployment first
    deploy_cmd = [
        "kubectl",
        "wait",
        "--for=condition=available",
        "--namespace",
        namespace,
        f"deployment/{resource_name}",
        f"--timeout={timeout}",
    ]
    result = run_command(deploy_cmd, check=False)
    if result is not None and result.returncode == 0:
        logging.info(f"Deployment '{resource_name}' is ready.")
        return

    # Fall back to StatefulSet pod wait
    logging.info(f"Deployment '{resource_name}' not found, trying StatefulSet...")
    for label_key in ("app.kubernetes.io/instance", "app.kubernetes.io/name", "app"):
        label_selector = f"{label_key}={resource_name}"
        pod_cmd = [
            "kubectl",
            "wait",
            "--for=condition=ready",
            "--namespace",
            namespace,
            "pod",
            "-l",
            label_selector,
            f"--timeout={timeout}",
        ]
        result = run_command(pod_cmd, check=False)
        if result is not None and result.returncode == 0:
            logging.info(
                f"StatefulSet '{resource_name}' pods are ready (label {label_selector})."
            )
            return

    logging.warning(
        f"Could not confirm readiness for '{resource_name}' in namespace '{namespace}'."
    )


def generate_password(length=24):
    """Generate a random password with letters, digits, and symbols."""
    charset = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(charset) for _ in range(length))


def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        logging.info(f"Loading environment from {env_file}")
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, sep, value = line.partition("=")
                    if sep:
                        os.environ[key.strip()] = value.strip()


def find_openssl() -> str | None:
    """Locate the openssl executable (Windows-aware)."""
    found = shutil.which("openssl")
    if found:
        return found
    if IS_WINDOWS:
        git_path = shutil.which("git")
        if git_path:
            git_dir = Path(git_path).parent
            git_root = git_dir.parent
            for candidate in [
                git_root / "mingw64" / "bin" / "openssl.exe",
                git_root / "usr" / "bin" / "openssl.exe",
            ]:
                if candidate.exists():
                    logging.info(f"Found OpenSSL bundled with Git: {candidate}")
                    return str(candidate)
    return None


def ensure_openssl_on_path() -> None:
    """Ensure openssl is reachable on PATH (Windows-aware)."""
    if shutil.which("openssl"):
        return
    openssl_path = find_openssl()
    if openssl_path:
        openssl_dir = str(Path(openssl_path).parent)
        os.environ["PATH"] = openssl_dir + os.pathsep + os.environ.get("PATH", "")
        logging.info(f"Added OpenSSL directory to PATH: {openssl_dir}")
    else:
        logging.error(
            "OpenSSL not found. Install OpenSSL or Git for Windows and try again."
        )
        sys.exit(1)


# ============================================================
# AWS Infrastructure Provisioning
# ============================================================


def check_aws_prerequisites():
    """Verify that AWS-specific tools are installed."""
    if globals().get("DRY_RUN", False):
        logging.info("Dry-run mode: skipping AWS prerequisite tool checks.")
        return

    if IS_WINDOWS:
        ensure_openssl_on_path()

    required_tools = ["kubectl", "helm", "git", "openssl", "aws", "eksctl"]
    missing = []

    for tool in required_tools:
        if shutil.which(tool) is None:
            missing.append(tool)

    if missing:
        logging.error(f"Missing required tools: {', '.join(missing)}")
        logging.error("Please install the missing tools before continuing:")
        logging.error("  - kubectl:   https://kubernetes.io/docs/tasks/tools/")
        logging.error("  - helm:       https://helm.sh/docs/intro/install/")
        logging.error("  - git:        https://git-scm.com/downloads")
        logging.error("  - openssl:    https://www.openssl.org/")
        logging.error(
            "  - aws CLI:    https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2/"
        )
        logging.error("  - eksctl:     https://eksctl.io/installation/")
        if IS_WINDOWS:
            logging.error("On Windows, ensure all tools are in your PATH.")
        sys.exit(1)

    logging.info("All prerequisites (including AWS tools) are available.")

    # Verify AWS credentials
    result = run_command(["aws", "sts", "get-caller-identity"], check=False)
    if result.returncode != 0:
        logging.error(
            "AWS credentials not configured. Run 'aws configure' or set AWS environment variables."
        )
        sys.exit(1)
    logging.info("AWS credentials verified.")


def create_eks_cluster(cluster_config: Path | None = None):
    """Create an EKS cluster using eksctl.

    Args:
        cluster_config: Path to the eksctl cluster config file.
                       Defaults to aws/eksctl-cluster.yaml
    """
    dry_run = globals().get("DRY_RUN", False)

    if cluster_config is None:
        cluster_config = EKSCTL_CLUSTER_CONFIG

    if not cluster_config.exists():
        logging.error(f"EKS cluster config not found: {cluster_config}")
        sys.exit(1)

    logging.info("=" * 60)
    logging.info("STEP 1: Creating EKS cluster (this may take 20-30 minutes)...")
    logging.info("=" * 60)

    if dry_run:
        logging.info("Dry-run: would run 'eksctl create cluster -f <config>'")
        return

    run_command(
        ["eksctl", "create", "cluster", "-f", str(cluster_config)],
        check=True,
    )
    logging.info("EKS cluster created successfully.")


def update_kubeconfig(cluster_name: str | None = None, region: str | None = None):
    """Update kubeconfig to connect to the EKS cluster.

    Args:
        cluster_name: EKS cluster name. Defaults to DEFAULT_EKS_CLUSTER.
        region: AWS region. Defaults to DEFAULT_EKS_REGION.
    """
    dry_run = globals().get("DRY_RUN", False)

    cluster = cluster_name or DEFAULT_EKS_CLUSTER
    r = region or DEFAULT_EKS_REGION

    logging.info(f"Updating kubeconfig for cluster '{cluster}' in region '{r}'...")

    if dry_run:
        logging.info("Dry-run: would update kubeconfig")
        return

    run_command(
        ["aws", "eks", "update-kubeconfig", "--name", cluster, "--region", r],
        check=True,
    )
    logging.info("Kubeconfig updated successfully.")


def install_ebs_csi_driver(cluster_name: str | None = None, region: str | None = None):
    """Verify EBS CSI driver addon is installed on the EKS cluster.

    The EBS CSI driver is typically installed as part of the eksctl cluster config
    (addons section), but we verify it's running and install manually if needed.
    """
    dry_run = globals().get("DRY_RUN", False)

    logging.info("Verifying EBS CSI driver addon...")

    if dry_run:
        logging.info("Dry-run: would verify EBS CSI driver")
        return

    # Check if the addon is already installed
    result = run_command(
        [
            "eksctl",
            "get",
            "addon",
            "--cluster",
            cluster_name or DEFAULT_EKS_CLUSTER,
            "--region",
            region or DEFAULT_EKS_REGION,
            "--name",
            "aws-ebs-csi-driver",
        ],
        check=False,
    )

    if result.returncode != 0:
        logging.info("EBS CSI driver addon not found, installing...")
        run_command(
            [
                "eksctl",
                "create",
                "addon",
                "--cluster",
                cluster_name or DEFAULT_EKS_CLUSTER,
                "--region",
                region or DEFAULT_EKS_REGION,
                "--name",
                "aws-ebs-csi-driver",
                "--force",
            ],
            check=True,
        )
    else:
        logging.info("EBS CSI driver addon is already installed.")

    # Wait for the addon to be active
    logging.info("Waiting for EBS CSI driver pods to be ready...")
    time.sleep(5)  # Brief pause for pods to start scheduling
    run_command(
        [
            "kubectl",
            "wait",
            "--for=condition=ready",
            "pod",
            "-l",
            "app.kubernetes.io/name=aws-ebs-csi-driver",
            "-n",
            "kube-system",
            "--timeout=120s",
        ],
        check=False,
    )


def install_aws_load_balancer_controller(
    cluster_name: str | None = None, region: str | None = None
):
    """Install the AWS Load Balancer Controller using Helm.

    This controller is required for creating AWS Application Load Balancers
    and Network Load Balancers for Kubernetes Ingress and LoadBalancer services.
    """
    dry_run = globals().get("DRY_RUN", False)
    cluster = cluster_name or DEFAULT_EKS_CLUSTER
    r = region or DEFAULT_EKS_REGION

    logging.info("Installing AWS Load Balancer Controller...")

    # Create the kube-system namespace for the controller if it doesn't exist
    # (it should already exist, but be explicit)
    if not dry_run:
        run_command(
            [
                "kubectl",
                "create",
                "namespace",
                "kube-system",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            check=False,
        )

    # Add the EKS Helm repo
    run_command(
        [
            "helm",
            "repo",
            "add",
            "aws-ebs-csi-driver",
            "https://kubernetes-sigs.github.io/aws-ebs-csi-driver",
        ],
        check=False,
    )
    run_command(
        ["helm", "repo", "add", "eks-charts", "https://aws.github.io/eks-charts"],
        check=False,
    )
    run_command(["helm", "repo", "update"])

    if dry_run:
        logging.info("Dry-run: would install AWS Load Balancer Controller via Helm")
        return

    # Get VPC ID for the cluster
    vpc_result = run_command(
        [
            "aws",
            "eks",
            "describe-cluster",
            "--name",
            cluster,
            "--region",
            r,
            "--query",
            "cluster.resourcesVpcConfig.vpcId",
            "--output",
            "text",
        ],
        check=True,
    )
    vpc_id = vpc_result.stdout.strip()
    logging.info(f"Cluster VPC ID: {vpc_id}")

    # Install the AWS Load Balancer Controller
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            "aws-load-balancer-controller",
            "eks-charts/aws-load-balancer-controller",
            "--namespace",
            "kube-system",
            "--set",
            f"clusterName={cluster}",
            "--set",
            "serviceAccount.create=true",
            "--set",
            "serviceAccount.name=aws-load-balancer-controller",
            "--set",
            f"region={r}",
            "--set",
            f"vpcId={vpc_id}",
            "--wait",
            "--timeout",
            "5m",
        ],
        check=True,
    )
    logging.info("AWS Load Balancer Controller installed.")


def install_cert_manager():
    """Install cert-manager for TLS certificate management.

    On AWS EKS, cert-manager can be used with Let's Encrypt via HTTP01
    or DNS01 challenges (Cloudflare) to automatically provision TLS certs.
    """
    dry_run = globals().get("DRY_RUN", False)

    logging.info("Installing cert-manager...")

    run_command(
        ["helm", "repo", "add", "jetstack", "https://charts.jetstack.io"],
        check=False,
    )
    run_command(["helm", "repo", "update"])

    if dry_run:
        logging.info("Dry-run: would install cert-manager via Helm")
        return

    # Create the cert-manager namespace
    run_command(
        [
            "kubectl",
            "create",
            "namespace",
            "cert-manager",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        check=False,
    )

    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            "cert-manager",
            "jetstack/cert-manager",
            "--namespace",
            "cert-manager",
            "--set",
            "installCRDs=true",
            "--set",
            "replicaCount=2",
            "--wait",
            "--timeout",
            "5m",
        ],
        check=True,
    )
    logging.info("cert-manager installed.")
    logging.info("NOTE: For Cloudflare DNS01 challenges, create the API token secret:")
    logging.info(
        "  kubectl create secret generic cloudflare-api-token-secret"
        " --namespace cert-manager"
        " --from-literal=api-token=<YOUR_CLOUDFLARE_API_TOKEN>"
    )
    logging.info(
        "Then uncomment the letsencrypt-cloudflare ClusterIssuer in"
        " aws/ingress-and-cert.yaml and apply it."
    )


def setup_cloudflare_dns01(api_token: str):
    """Set up Cloudflare DNS01 challenge support for cert-manager.

    Creates a Kubernetes Secret with the Cloudflare API token in the
    cert-manager namespace, then applies the letsencrypt-cloudflare
    ClusterIssuer from aws/ingress-and-cert.yaml.

    This enables automatic wildcard certificate provisioning for
    *.app.skyddex.com via Let's Encrypt DNS01 challenges.
    """
    dry_run = globals().get("DRY_RUN", False)

    if dry_run:
        logging.info(
            "Dry-run: would create Cloudflare API token secret and ClusterIssuer"
        )
        return

    logging.info("Setting up Cloudflare DNS01 challenge support...")

    # Create the Cloudflare API token Secret
    secret_cmd = [
        "kubectl",
        "create",
        "secret",
        "generic",
        "cloudflare-api-token-secret",
        "--namespace",
        "cert-manager",
        f"--from-literal=api-token={api_token}",
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    result = run_command(secret_cmd, check=False)
    if result is not None and result.returncode == 0:
        apply_cmd = [
            "kubectl",
            "apply",
            "-f",
            "-",
        ]
        run_command(
            apply_cmd,
            check=True,
            input_data=result.stdout,
        )
        logging.info("Cloudflare API token secret created in cert-manager namespace.")
    else:
        logging.warning(
            "Failed to create Cloudflare API token secret. "
            "You may need to create it manually."
        )
        return

    # Wait briefly for cert-manager to be ready before applying ClusterIssuer
    logging.info("Waiting for cert-manager webhook to be ready...")
    run_command(
        [
            "kubectl",
            "wait",
            "--for=condition=available",
            "--namespace",
            "cert-manager",
            "deployment/cert-manager-webhook",
            "--timeout=120s",
        ],
        check=False,
    )

    # Read and uncomment the Cloudflare ClusterIssuer from ingress-and-cert.yaml
    ingress_file = AWS_DIR / "ingress-and-cert.yaml"
    if not ingress_file.exists():
        logging.error(f"Ingress/cert file not found: {ingress_file}")
        return

    content = ingress_file.read_text(encoding="utf-8")

    # Check if the Cloudflare ClusterIssuer is already uncommented
    if "name: letsencrypt-cloudflare" in content and not content.strip().startswith(
        "#"
    ):
        # Check if it's an active (uncommented) resource
        lines = content.split("\n")
        in_cloudflare_block = False
        uncommented = False
        for line in lines:
            if "name: letsencrypt-cloudflare" in line and not line.strip().startswith(
                "#"
            ):
                uncommented = True
                break

        if uncommented:
            logging.info("Cloudflare ClusterIssuer already active, applying...")
            run_command(
                ["kubectl", "apply", "-f", str(ingress_file)],
                check=True,
            )
            logging.info("Cloudflare ClusterIssuer applied.")
            return

    # Uncomment the Cloudflare ClusterIssuer block
    # Lines starting with "# " within the block need the "# " prefix removed
    uncommented_lines = []
    in_cloudflare_block = False
    block_indent = None

    for line in content.split("\n"):
        stripped = line.strip()

        # Detect start of the commented Cloudflare block
        if (
            stripped.startswith("# apiVersion: cert-manager.io/v1")
            and "letsencrypt-cloudflare" in content
        ):
            # Look ahead to see if this is the cloudflare block
            pass

        if stripped == "# ---":
            # Check if next non-empty line starts cloudflare block
            # We'll handle this differently
            pass

        # Simple approach: uncomment lines that are part of the cloudflare block
        # The block is delimited by "# ---" and contains "letsencrypt-cloudflare"
        if "# name: letsencrypt-cloudflare" in stripped:
            in_cloudflare_block = True

        if in_cloudflare_block:
            if stripped.startswith("#"):
                # Remove the "# " prefix (or just "#" if no space)
                if stripped.startswith("# "):
                    uncommented_lines.append(line.replace("# ", "", 1))
                elif stripped.startswith("#"):
                    uncommented_lines.append(line.replace("#", "", 1).rstrip())
            else:
                uncommented_lines.append(line)

            # End of block: blank line or next "---" after content
            if stripped and not stripped.startswith("#") and stripped != "---":
                pass  # still in block
        else:
            uncommented_lines.append(line)

        if in_cloudflare_block and stripped == "---" and line.strip() == "---":
            in_cloudflare_block = False

    # Write a temporary file with the uncommented content
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("\n".join(uncommented_lines))
        tmp_path = tmp.name

    try:
        logging.info("Applying Cloudflare ClusterIssuer...")
        run_command(
            ["kubectl", "apply", "-f", tmp_path],
            check=True,
        )
        logging.info("Cloudflare ClusterIssuer applied successfully.")
        logging.info(
            "You can now use 'cert-manager.io/cluster-issuer: letsencrypt-cloudflare' "
            "in your Ingress annotations for wildcard certificates on *.app.skyddex.com."
        )
    finally:
        import os

        os.unlink(tmp_path)


def apply_aws_storage_classes():
    """Apply AWS-specific StorageClasses for EBS volumes.

    Creates:
      - gp3: General-purpose SSD (default for most workloads)
      - io1: High-performance SSD (for databases and latency-sensitive workloads)
    """
    dry_run = globals().get("DRY_RUN", False)

    storage_classes_file = AWS_DIR / "storage-classes.yaml"
    if not storage_classes_file.exists():
        logging.error(f"StorageClasses file not found: {storage_classes_file}")
        sys.exit(1)

    logging.info("Applying AWS StorageClasses...")

    if dry_run:
        logging.info("Dry-run: would apply AWS StorageClasses")
        return

    run_command(["kubectl", "apply", "-f", str(storage_classes_file)])
    logging.info("AWS StorageClasses applied.")


def apply_aws_namespaces(cfg: dict):
    """Apply namespace definitions for the MCaaS stack on AWS.

    Uses the client-specific namespaces.yaml if available, otherwise
    falls back to the AWS directory namespaces, or generates them.
    """
    dry_run = globals().get("DRY_RUN", False)

    # Check for client-specific namespaces first
    if cfg.get("client_dir"):
        client_ns = cfg["client_dir"] / "namespaces.yaml"
        if client_ns.exists():
            logging.info(f"Applying client-specific namespaces from {client_ns}...")
            if not dry_run:
                run_command(["kubectl", "apply", "-f", str(client_ns)])
            else:
                logging.info("Dry-run: would apply client namespaces")
            return

    # Check AWS directory namespaces
    aws_ns = AWS_DIR / "namespaces.yaml"
    if aws_ns.exists():
        logging.info(f"Applying AWS namespaces from {aws_ns}...")
        if not dry_run:
            run_command(["kubectl", "apply", "-f", str(aws_ns)])
        else:
            logging.info("Dry-run: would apply AWS namespaces")
        return

    # Generate namespace manifests on the fly
    logging.info("Generating and applying namespace manifests...")
    ns_manifests = []
    for ns_name in cfg["namespaces"].values():
        ns_manifests.append(
            f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {ns_name}\n"
        )
    ns_yaml = "---\n".join(ns_manifests)

    if dry_run:
        logging.info(f"Dry-run: would apply namespaces:\n{ns_yaml}")
    else:
        run_command(["kubectl", "apply", "-f", "-"], input_data=ns_yaml)
    logging.info("Namespaces applied.")


def ensure_wazuh_certs(wazuh_dir: Path) -> None:
    """Generate self-signed TLS certificates required by the Wazuh kustomization.

    Mirrors the function in deploy.py. On AWS/EKS we still use the same
    self-signed cert generation approach for Wazuh internal TLS.
    """
    indexer_cluster = wazuh_dir / "wazuh" / "certs" / "indexer_cluster"
    dashboard_http = wazuh_dir / "wazuh" / "certs" / "dashboard_http"

    for directory in (indexer_cluster, dashboard_http):
        directory.mkdir(parents=True, exist_ok=True)

    root_ca_key = indexer_cluster / "root-ca-key.pem"
    root_ca_cert = indexer_cluster / "root-ca.pem"

    if not root_ca_cert.exists() or not root_ca_key.exists():
        logging.info("Generating self-signed root CA for Wazuh TLS...")
        run_command(
            [
                "openssl",
                "req",
                "-x509",
                "-new",
                "-nodes",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(root_ca_key),
                "-out",
                str(root_ca_cert),
                "-days",
                "3650",
                "-subj",
                "/CN=WazuhRootCA/O=Wazuh/L=California/C=US",
            ],
        )
    else:
        logging.info("Root CA already exists – reusing it.")

    def _sign_cert(name, cn, key_path, csr_path, cert_path):
        if cert_path.exists() and key_path.exists():
            logging.debug(f"Certificate {name} already present – skipping.")
            return
        logging.info(f"Generating certificate for {name}…")
        run_command(["openssl", "genrsa", "-out", str(key_path), "2048"])
        run_command(
            [
                "openssl",
                "req",
                "-new",
                "-key",
                str(key_path),
                "-out",
                str(csr_path),
                "-subj",
                f"/CN={cn}/OU=Wazuh/O=Wazuh/L=California/C=US",
            ],
        )
        run_command(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(csr_path),
                "-CA",
                str(root_ca_cert),
                "-CAkey",
                str(root_ca_key),
                "-CAcreateserial",
                "-out",
                str(cert_path),
                "-days",
                "3650",
            ],
        )

    _sign_cert(
        "indexer",
        "indexer",
        indexer_cluster / "node-key.pem",
        indexer_cluster / "node.csr",
        indexer_cluster / "node.pem",
    )
    _sign_cert(
        "admin",
        "admin",
        indexer_cluster / "admin-key.pem",
        indexer_cluster / "admin.csr",
        indexer_cluster / "admin.pem",
    )
    _sign_cert(
        "dashboard",
        "dashboard",
        indexer_cluster / "dashboard-key.pem",
        indexer_cluster / "dashboard.csr",
        indexer_cluster / "dashboard.pem",
    )
    _sign_cert(
        "filebeat",
        "filebeat",
        indexer_cluster / "filebeat-key.pem",
        indexer_cluster / "filebeat.csr",
        indexer_cluster / "filebeat.pem",
    )
    _sign_cert(
        "dashboard_http",
        "dashboard",
        dashboard_http / "key.pem",
        dashboard_http / "dashboard_http.csr",
        dashboard_http / "cert.pem",
    )
    shutil.copy2(str(root_ca_cert), str(dashboard_http / "root-ca.pem"))
    logging.info("Wazuh TLS certificates generated successfully.")


def clone_or_use_wazuh_repo(wazuh_dir):
    """Clone Wazuh repo or use existing. Mirrors deploy.py."""
    if wazuh_dir.exists() and (wazuh_dir / "envs" / "local-env").exists():
        logging.info(f"Wazuh repo already exists at {wazuh_dir}")
        return wazuh_dir

    if wazuh_dir.exists():
        logging.warning(f"Removing incomplete Wazuh clone at {wazuh_dir}")
        import stat

        def _remove_readonly(func, path, _exc_info):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(wazuh_dir, onerror=_remove_readonly)

    logging.info("Cloning Wazuh repository...")
    wazuh_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        if IS_WINDOWS:
            run_command(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--no-checkout",
                    "--branch",
                    "v4.14.6",
                    "https://github.com/wazuh/wazuh-kubernetes.git",
                    str(wazuh_dir),
                ],
            )
            run_command(
                ["git", "checkout", "HEAD", "--", "envs/local-env", "wazuh"],
                cwd=str(wazuh_dir),
            )
            if not (wazuh_dir / "envs" / "local-env").exists():
                logging.error(
                    "Wazuh clone checkout incomplete — envs/local-env missing"
                )
                shutil.rmtree(wazuh_dir, ignore_errors=True)
                return None
        else:
            run_command(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    "v4.14.6",
                    "https://github.com/wazuh/wazuh-kubernetes.git",
                    str(wazuh_dir),
                ],
            )
    except subprocess.CalledProcessError:
        logging.warning(
            "Failed to clone Wazuh repo locally, will use remote URL with kubectl"
        )
        if wazuh_dir.exists():
            import stat as _stat

            def _ro_handler(func, path, _exc):
                os.chmod(path, _stat.S_IWRITE)
                func(path)

            shutil.rmtree(wazuh_dir, onerror=_ro_handler)
        return None

    return wazuh_dir


def deploy_wazuh_aws(wazuh_dir, cfg):
    """Deploy Wazuh on AWS/EKS.

    Similar to deploy.py's deploy_wazuh(), but replaces the Wazuh StorageClass
    with an EBS-backed gp3 StorageClass instead of the k3s local-path provisioner.
    """
    wazuh_ns = cfg["namespaces"]["wazuh"]
    wazuh_version = cfg["wazuh_version"]

    logging.info("Deploying Wazuh from manifests (AWS/EKS)...")

    remote_kustomize = f"https://github.com/wazuh/wazuh-kubernetes//envs/local-env?ref=v{wazuh_version}"
    dry_run = globals().get("DRY_RUN", False)

    if dry_run:
        if wazuh_dir and wazuh_dir.exists():
            ensure_wazuh_certs(wazuh_dir)
            kustomize_path = str(wazuh_dir / "envs" / "local-env")
            logging.info("Dry-run: using local Wazuh clone with placeholder TLS files.")
        else:
            kustomize_path = remote_kustomize
            logging.warning(
                "Dry-run: local Wazuh clone missing; falling back to remote."
            )
    else:
        if IS_WINDOWS:
            if (
                wazuh_dir
                and wazuh_dir.exists()
                and (wazuh_dir / "envs" / "local-env").exists()
            ):
                ensure_wazuh_certs(wazuh_dir)
                kustomize_path = str(wazuh_dir / "envs" / "local-env")
                logging.info(
                    "Windows – using local Wazuh clone with generated TLS certificates."
                )
            else:
                kustomize_path = remote_kustomize
                logging.warning(
                    "Windows – local clone unavailable; falling back to remote manifests."
                )
        else:
            local_kustomize = wazuh_dir and (wazuh_dir / "envs" / "local-env")
            if local_kustomize and local_kustomize.exists():
                required_cert = (
                    wazuh_dir / "wazuh" / "certs" / "indexer_cluster" / "root-ca.pem"
                )
                if not required_cert.exists():
                    logging.info(
                        "Wazuh TLS certificates not found – generating them now."
                    )
                    ensure_wazuh_certs(wazuh_dir)
                kustomize_path = str(local_kustomize)
            else:
                logging.warning(
                    "Local Wazuh clone incomplete; falling back to remote manifests"
                )
                kustomize_path = remote_kustomize

    # Delete the wazuh-storage StorageClass BEFORE applying kustomize.
    logging.info("Pre-deleting wazuh-storage StorageClass (immutable fields)...")
    run_command(
        ["kubectl", "delete", "storageclass", "wazuh-storage", "--ignore-not-found"],
        check=False,
    )

    # Execute the apply command
    run_command(["kubectl", "apply", "-k", kustomize_path])

    # Replace the Wazuh StorageClass with EBS gp3 for EKS compatibility.
    # On k3s, this used rancher.io/local-path; on EKS we use ebs.csi.aws.com with gp3.
    logging.info("Replacing wazuh-storage StorageClass with EBS gp3 for EKS...")
    run_command(
        ["kubectl", "delete", "storageclass", "wazuh-storage", "--ignore-not-found"],
        check=False,
    )
    run_command(
        ["kubectl", "apply", "-f", "-"],
        input_data=(
            "apiVersion: storage.k8s.io/v1\n"
            "kind: StorageClass\n"
            "metadata:\n"
            "  name: wazuh-storage\n"
            "provisioner: ebs.csi.aws.com\n"
            "parameters:\n"
            "  type: gp3\n"
            "  iopsPerGB: '50'\n"
            "  fsType: ext4\n"
            "reclaimPolicy: Delete\n"
            "volumeBindingMode: WaitForFirstConsumer\n"
            "allowVolumeExpansion: true\n"
        ),
    )


def create_secrets(cfg: dict):
    """Create Kubernetes secrets required by the MCaaS stack.

    Mirrors deploy.py's create_secrets() but uses AWS-specific namespace names
    from the config.
    """
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    env_prefix = cfg["env_prefix"]
    env_file = PROJECT_ROOT / ".env"

    env_postgres = f"{env_prefix}_POSTGRES_PASSWORD"
    env_opensearch = f"{env_prefix}_OPENSEARCH_PASSWORD"
    env_redis = f"{env_prefix}_REDIS_PASSWORD"
    env_django = f"{env_prefix}_DJANGO_SECRET_KEY"

    postgres_pw = os.environ.get(env_postgres)
    opensearch_pw = os.environ.get(env_opensearch)

    if not postgres_pw or not opensearch_pw:
        if not env_file.exists():
            logging.info(
                "No .env file found. Generating passwords and creating .env file..."
            )
            postgres_pw = postgres_pw or generate_password()
            opensearch_pw = opensearch_pw or generate_password()
            env_file.write_text(
                f"{env_postgres}={postgres_pw}\n{env_opensearch}={opensearch_pw}\n"
            )
            logging.info(
                f"Created {env_file} with generated passwords. Back this file up for redeployments."
            )
        else:
            if not postgres_pw:
                logging.error(
                    f"{env_postgres} is not set. Set it in your .env file or environment."
                )
                sys.exit(1)
            if not opensearch_pw:
                logging.error(
                    f"{env_opensearch} is not set. Set it in your .env file or environment."
                )
                sys.exit(1)

    logging.info("Creating/updating Kubernetes secrets...")
    dry_run = globals().get("DRY_RUN", False)

    def _create_and_apply(namespace, secret_name, literals):
        """Helper: create a secret from literals and apply it."""
        cmd = ["kubectl", "-n", namespace, "create", "secret", "generic", secret_name]
        for key, value in literals:
            cmd.append(f"--from-literal={key}={value}")
        cmd.extend(["--dry-run=client", "-o", "yaml"])

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logging.error(
                f"Failed to generate secret manifest for '{secret_name}': {proc.stderr}"
            )
            raise RuntimeError(f"Failed to create secret '{secret_name}'")

        if dry_run:
            logging.info(
                f"Dry-run: would apply secret '{secret_name}' in namespace '{namespace}'."
            )
        else:
            apply_proc = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=proc.stdout,
                text=True,
            )
            if apply_proc.returncode != 0:
                logging.error(f"Failed to apply secret '{secret_name}'")
                raise RuntimeError(f"Failed to apply secret '{secret_name}'")
            logging.info(
                f"Secret '{secret_name}' created/updated in {namespace} namespace."
            )

    # 1. PostgreSQL secret (managed-it namespace)
    _create_and_apply(
        ns["managed-it"],
        f"{prefix}-postgresql-secret",
        [
            ("postgres-password", postgres_pw),
            ("password", postgres_pw),
        ],
    )

    # 2. OpenSearch secret (security-ops namespace)
    _create_and_apply(
        ns["security-ops"],
        f"{prefix}-opensearch-secret",
        [
            ("opensearch-password", opensearch_pw),
            ("SHUFFLE_OPENSEARCH_PASSWORD", opensearch_pw),
        ],
    )

    # 3. Redis secret (managed-it namespace)
    redis_pw = os.environ.get(env_redis, "zammad")
    _create_and_apply(
        ns["managed-it"],
        f"{prefix}-zammad-redis-pass",
        [
            ("redis-password", redis_pw),
        ],
    )

    # 4. Cross-namespace PostgreSQL secret (grc namespace)
    _create_and_apply(
        ns["grc"],
        f"{prefix}-postgresql-secret",
        [
            ("postgres-password", postgres_pw),
            ("password", postgres_pw),
        ],
    )

    # 5. Django secret for CISO Assistant (grc namespace)
    django_secret = os.environ.get(env_django)
    if not django_secret:
        django_secret = generate_password(length=50)
        with open(env_file, "a") as f:
            f.write(f"\n{env_django}={django_secret}\n")
        logging.info(f"Generated {env_django} and appended to {env_file}")

    _create_and_apply(
        ns["grc"],
        f"{prefix}-ciso-secret",
        [
            ("django-secret-key", django_secret),
        ],
    )


def _create_database(pod_name, namespace, db_name, secret_name, secret_key):
    """Create a database in the PostgreSQL instance (mirrors deploy.py)."""
    dry_run = globals().get("DRY_RUN", False)
    if dry_run:
        logging.info(f"Dry-run: would create database '{db_name}' in PostgreSQL.")
        return

    logging.info(f"Ensuring database '{db_name}' exists in PostgreSQL...")
    pw_result = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            secret_name,
            "-n",
            namespace,
            "-o",
            f"jsonpath={{.data.{secret_key}}}",
        ],
        capture_output=True,
        text=True,
    )
    if pw_result.returncode != 0:
        logging.error(
            f"Failed to retrieve password from secret '{secret_name}': {pw_result.stderr}"
        )
        raise RuntimeError(f"Failed to retrieve password from secret '{secret_name}'")

    import base64

    db_password = base64.b64decode(pw_result.stdout.strip()).decode()

    sql = f'CREATE DATABASE "{db_name}";\n'
    result = subprocess.run(
        [
            "kubectl",
            "exec",
            "-i",
            pod_name,
            "-n",
            namespace,
            "--",
            "env",
            f"PGPASSWORD={db_password}",
            "psql",
            "-U",
            "postgres",
        ],
        input=sql,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if "already exists" in result.stderr:
            logging.info(f"Database '{db_name}' already exists.")
        else:
            logging.warning(f"Could not create database '{db_name}': {result.stderr}")
    else:
        logging.info(f"Database '{db_name}' created successfully.")


def check_kubectl_connectivity():
    """Verify kubectl can authenticate to the cluster."""
    logging.info("Verifying kubectl connectivity...")
    result = run_command(
        ["kubectl", "auth", "can-i", "create", "namespaces"],
        check=False,
    )
    if result.returncode != 0:
        logging.error("kubectl cannot authenticate to the cluster.")
        logging.error(
            "Check that your kubeconfig is valid and credentials are not expired."
        )
        logging.error(f"STDERR: {result.stderr.strip()}")
        sys.exit(1)
    if "yes" not in (result.stdout or "").lower():
        logging.error(
            "kubectl authenticated but lacks permission to create namespaces."
        )
        logging.error(
            "Ensure the service account has cluster-admin or equivalent RBAC."
        )
        sys.exit(1)
    logging.info("kubectl connectivity verified.")


# ============================================================
# Main Deployment Logic
# ============================================================


def deploy_infrastructure(cfg: dict, cluster_name: str | None, region: str | None):
    """Deploy AWS infrastructure: EKS cluster, add-ons, StorageClasses, cert-manager."""
    logging.info("=" * 60)
    logging.info("PHASE 1: AWS Infrastructure Provisioning")
    logging.info("=" * 60)

    # Step 1: Create EKS cluster
    create_eks_cluster(EKSCTL_CLUSTER_CONFIG)

    # Step 2: Update kubeconfig
    update_kubeconfig(cluster_name, region)

    # Step 3: Verify kubectl connectivity
    check_kubectl_connectivity()

    # Step 4: Install EBS CSI driver
    install_ebs_csi_driver(cluster_name, region)

    # Step 5: Install AWS Load Balancer Controller
    install_aws_load_balancer_controller(cluster_name, region)

    # Step 6: Install cert-manager
    install_cert_manager()

    # Step 6b: Set up Cloudflare DNS01 (if token provided)
    if args.cloudflare_token:
        setup_cloudflare_dns01(args.cloudflare_token)
    else:
        logging.info(
            "Cloudflare DNS01 not configured. Pass --cloudflare-token to enable "
            "wildcard certificates for *.app.skyddex.com."
        )

    # Step 7: Apply AWS StorageClasses
    apply_aws_storage_classes()

    # Step 8: Apply namespaces
    apply_aws_namespaces(cfg)

    logging.info("AWS infrastructure provisioning complete.")


def deploy_applications(cfg: dict):
    """Deploy the MCaaS application stack (PostgreSQL, OpenSearch, Wazuh, etc.)."""
    logging.info("=" * 60)
    logging.info("PHASE 2: MCaaS Application Deployment")
    logging.info("=" * 60)

    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    values_dir = cfg["values_dir"]

    # Create secrets
    logging.info("Creating required Kubernetes secrets...")
    create_secrets(cfg)

    # Add Helm repositories
    logging.info("Adding and updating Helm repositories...")
    run_command(
        ["helm", "repo", "add", "bitnami", "https://charts.bitnami.com/bitnami"],
        check=False,
    )
    run_command(
        [
            "helm",
            "repo",
            "add",
            "opensearch",
            "https://opensearch-project.github.io/helm-charts",
        ],
        check=False,
    )
    run_command(["helm", "repo", "update"])

    # Deploy PostgreSQL
    logging.info("Deploying PostgreSQL...")
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            f"{prefix}-postgresql",
            "bitnami/postgresql",
            "--namespace",
            ns["managed-it"],
            "--values",
            str(values_dir / "postgresql.yaml"),
            "--wait",
            "--timeout",
            "5m",
        ]
    )
    wait_for_resource(ns["managed-it"], f"{prefix}-postgresql")

    # Deploy OpenSearch
    logging.info("Deploying OpenSearch...")
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            f"{prefix}-opensearch",
            "opensearch/opensearch",
            "--namespace",
            ns["security-ops"],
            "--values",
            str(values_dir / "opensearch.yaml"),
            "--wait",
            "--timeout",
            "10m",
        ]
    )
    wait_for_resource(ns["security-ops"], f"{prefix}-opensearch")

    # Clone and deploy Wazuh
    wazuh_dir = TMP_DIR / "wazuh-kubernetes"
    wazuh_clone_result = clone_or_use_wazuh_repo(wazuh_dir)
    effective_wazuh_dir = (
        wazuh_clone_result if wazuh_clone_result is not None else wazuh_dir
    )

    deploy_wazuh_aws(effective_wazuh_dir, cfg)

    logging.info("Waiting for Wazuh components to be ready...")
    run_command(
        [
            "kubectl",
            "wait",
            "--for=condition=ready",
            "pod",
            "-l",
            "app=wazuh-manager",
            "-n",
            ns["wazuh"],
            "--timeout=10m",
        ],
        check=False,
    )
    run_command(
        [
            "kubectl",
            "wait",
            "--for=condition=ready",
            "pod",
            "-l",
            "app=wazuh-indexer",
            "-n",
            ns["wazuh"],
            "--timeout=10m",
        ],
        check=False,
    )
    run_command(
        [
            "kubectl",
            "wait",
            "--for=condition=ready",
            "pod",
            "-l",
            "app=wazuh-dashboard",
            "-n",
            ns["wazuh"],
            "--timeout=10m",
        ],
        check=False,
    )

    # Deploy Shuffle
    logging.info("Deploying Shuffle (OCI chart)...")
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            f"{prefix}-shuffle",
            "oci://ghcr.io/shuffle/charts/shuffle",
            "--namespace",
            ns["security-ops"],
            "--values",
            str(values_dir / "shuffle.yaml"),
            "--wait",
            "--timeout",
            "10m",
        ]
    )
    wait_for_resource(ns["security-ops"], f"{prefix}-shuffle")

    # Create zammad database
    logging.info("Creating zammad database in PostgreSQL...")
    _create_database(
        f"{prefix}-postgresql-0",
        ns["managed-it"],
        "zammad",
        f"{prefix}-postgresql-secret",
        "postgres-password",
    )

    # Deploy Zammad
    logging.info("Deploying Zammad (OCI chart)...")
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            f"{prefix}-zammad",
            "oci://ghcr.io/zammad/charts/zammad",
            "--namespace",
            ns["managed-it"],
            "--values",
            str(values_dir / "zammad.yaml"),
            "--wait",
            "--timeout",
            "15m",
        ]
    )
    wait_for_resource(ns["managed-it"], f"{prefix}-zammad-railsserver")

    # Create ciso-assistant database
    logging.info("Creating ciso-assistant database in PostgreSQL...")
    _create_database(
        f"{prefix}-postgresql-0",
        ns["managed-it"],
        "ciso-assistant",
        f"{prefix}-postgresql-secret",
        "postgres-password",
    )

    # Deploy CISO Assistant
    logging.info("Deploying CISO Assistant (OCI chart)...")
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            f"{prefix}-ciso",
            "oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant",
            "--version",
            "0.11.4",
            "--namespace",
            ns["grc"],
            "--values",
            str(values_dir / "ciso-assistant.yaml"),
            "--wait",
            "--timeout",
            "10m",
        ]
    )
    wait_for_resource(ns["grc"], f"{prefix}-ciso")

    logging.info("Application deployment complete!")


def generate_environment_summary(cfg: dict):
    """Generate a deployment summary file with AWS-specific information."""
    import base64

    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    env_prefix = cfg["env_prefix"]
    domain = cfg.get("domain", "app.skyddex.com")
    ingress = cfg.get("ingress", {})
    client_name = cfg.get("client_name") or "default"
    dry_run = globals().get("DRY_RUN", False)

    def _get_secret_value(secret_name, namespace, key):
        if dry_run:
            return f"<{key} (dry-run: not retrieved)>"
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "secret",
                    secret_name,
                    "-n",
                    namespace,
                    "-o",
                    f"jsonpath={{.data.{key}}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return base64.b64decode(result.stdout.strip()).decode()
            return f"<{key} (not found)>"
        except Exception:
            return f"<{key} (error retrieving)>"

    postgres_pw = os.environ.get(
        f"{env_prefix}_POSTGRES_PASSWORD"
    ) or _get_secret_value(
        f"{prefix}-postgresql-secret", ns["managed-it"], "postgres-password"
    )
    opensearch_pw = os.environ.get(
        f"{env_prefix}_OPENSEARCH_PASSWORD"
    ) or _get_secret_value(
        f"{prefix}-opensearch-secret", ns["security-ops"], "opensearch-password"
    )
    redis_pw = os.environ.get(f"{env_prefix}_REDIS_PASSWORD") or _get_secret_value(
        f"{prefix}-zammad-redis-pass", ns["managed-it"], "redis-password"
    )
    django_secret = os.environ.get(
        f"{env_prefix}_DJANGO_SECRET_KEY"
    ) or _get_secret_value(f"{prefix}-ciso-secret", ns["grc"], "django-secret-key")

    zammad_host = ingress.get("zammad_host", f"zammad.{domain}")
    ciso_host = ingress.get("ciso_host", f"ciso.{domain}")
    zammad_url = f"https://{zammad_host}"
    ciso_url = f"https://{ciso_host}"

    pg_host = f"{prefix}-postgresql.{ns['managed-it']}.svc.cluster.local"
    os_host = f"{prefix}-opensearch.{ns['security-ops']}.svc.cluster.local"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# MCaaS AWS/EKS Deployment Summary",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Client** | `{client_name}` |",
        f"| **Prefix** | `{prefix}` |",
        f"| **Domain** | `{domain}` |",
        f"| **Platform** | AWS EKS |",
        f"| **Cluster** | `{DEFAULT_EKS_CLUSTER}` |",
        f"| **Region** | `{DEFAULT_EKS_REGION}` |",
        f"| **Generated** | {now} |",
        f"| **Mode** | {'Dry-run (no changes applied)' if dry_run else 'Live deployment'} |",
        "",
        "---",
        "",
        "## AWS Infrastructure",
        "",
        "| Component | Details |",
        "|-----------|---------|",
        "| **EKS Cluster** | mcaas-eks (v1.29) |",
        "| **Node Group: Workers** | m5.xlarge, 3-8 nodes |",
        "| **Node Group: Monitoring** | m5.2xlarge, 1-4 nodes |",
        "| **EBS CSI Driver** | aws-ebs-csi-driver addon |",
        "| **Load Balancer** | AWS Load Balancer Controller |",
        "| **TLS** | cert-manager (Let's Encrypt / ACM) |",
        "| **StorageClass: gp3** | General-purpose EBS SSD (default) |",
        "| **StorageClass: io1** | High-performance EBS SSD |",
        "",
        "---",
        "",
        "## Web Interfaces (Ingress / ALB)",
        "",
        "| Service | URL | Default Credentials |",
        "|---------|-----|---------------------|",
        f"| **Zammad** (Ticketing) | [{zammad_url}]({zammad_url}) | `admin` / set on first login |",
        f"| **CISO Assistant** (GRC) | [{ciso_url}]({ciso_url}) | `admin` / set on first login |",
        "",
        "## Web Interfaces (Port-Forward Required)",
        "",
        "### Wazuh Dashboard",
        "```bash",
        f"kubectl port-forward svc/wazuh-dashboard -n {ns['wazuh']} 8443:5601",
        "```",
        "- **URL:** <https://localhost:8443>",
        "- **Username:** `admin`",
        "- **Password:** Change from default `MYPASSWORD_`",
        "",
        "### Shuffle (SOAR)",
        "```bash",
        f"kubectl port-forward svc/shuffle -n {ns['security-ops']} 3000:80",
        "```",
        "",
        "---",
        "",
        "## Internal Services (Cluster-Only)",
        "",
        "| Service | Host | Port |",
        "|---------|------|------|",
        f"| **PostgreSQL** | `{pg_host}` | 5432 |",
        f"| **OpenSearch** | `{os_host}` | 9200 |",
        f"| **Zammad Redis** | `{prefix}-zammad-redis.{ns['managed-it']}.svc.cluster.local` | 6379 |",
        "",
        "---",
        "",
        "## Kubernetes Secrets",
        "",
        f"| Secret | Namespace | Keys |",
        f"|--------|-----------|------|",
        f"| `{prefix}-postgresql-secret` | `{ns['managed-it']}` | `postgres-password`, `password` |",
        f"| `{prefix}-opensearch-secret` | `{ns['security-ops']}` | `opensearch-password`, `SHUFFLE_OPENSEARCH_PASSWORD` |",
        f"| `{prefix}-zammad-redis-pass` | `{ns['managed-it']}` | `redis-password` |",
        f"| `{prefix}-postgresql-secret` | `{ns['grc']}` | `postgres-password`, `password` |",
        f"| `{prefix}-ciso-secret` | `{ns['grc']}` | `django-secret-key` |",
        "",
        "---",
        "",
        "## Credentials",
        "",
        "### PostgreSQL",
        f"- **Host:** `{pg_host}:5432`",
        f"- **Username:** `postgres`",
        f"- **Password:** `{postgres_pw}`",
        f"- **Databases:** `mcaas_db`, `zammad`, `ciso-assistant`",
        "",
        "### OpenSearch",
        f"- **Host:** `{os_host}:9200`",
        f"- **Username:** `admin`",
        f"- **Password:** `{opensearch_pw}`",
        "",
        "### Zammad Redis",
        f"- **Password:** `{redis_pw}`",
        "",
        "### CISO Assistant",
        f"- **Django Secret Key:** `{django_secret}`",
        "",
        "---",
        "",
        "## Helm Releases",
        "",
        f"| Release | Chart | Namespace |",
        f"|---------|-------|-----------|",
        f"| `{prefix}-postgresql` | `bitnami/postgresql` | `{ns['managed-it']}` |",
        f"| `{prefix}-opensearch` | `opensearch/opensearch` | `{ns['security-ops']}` |",
        f"| `{prefix}-shuffle` | `oci://ghcr.io/shuffle/charts/shuffle` | `{ns['security-ops']}` |",
        f"| `{prefix}-zammad` | `oci://ghcr.io/zammad/charts/zammad` | `{ns['managed-it']}` |",
        f"| `{prefix}-ciso` | `oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant` | `{ns['grc']}` |",
        "",
        "---",
        "",
        "## AWS-Specific Notes",
        "",
        "- **Ingress**: Uses AWS Application Load Balancer (ALB) via the AWS Load Balancer Controller.",
        "- **Storage**: All persistent volumes use EBS gp3 StorageClass (or io1 for databases).",
        "- **TLS**: cert-manager is installed for automatic TLS certificate provisioning.",
        "  Configure a ClusterIssuer for Let's Encrypt or use AWS Certificate Manager.",
        "- **Wazuh Storage**: Uses EBS gp3 via `ebs.csi.aws.com` provisioner instead of `rancher.io/local-path`.",
        "",
        "---",
        "",
        f"_This file was auto-generated by `deploy-aws.py` on {now}._",
        "",
    ]

    summary_text = "\n".join(lines)
    summary_file = PROJECT_ROOT / f"deploy-aws-summary-{prefix}.md"
    summary_file.write_text(summary_text, encoding="utf-8")
    logging.info(f"Deployment summary written to {summary_file}")

    print("\n" + "=" * 72)
    print("  MCaaS AWS/EKS DEPLOYMENT SUMMARY")
    print("=" * 72)
    print()
    print(f"  Client:      {client_name}")
    print(f"  Prefix:      {prefix}")
    print(f"  Domain:      {domain}")
    print(f"  Platform:    AWS EKS ({DEFAULT_EKS_CLUSTER})")
    print()
    print("  Web Interfaces:")
    print(f"    Zammad:          {zammad_url}")
    print(f"    CISO Assistant:  {ciso_url}")
    print(
        f"    Wazuh Dashboard: kubectl port-forward svc/wazuh-dashboard -n {ns['wazuh']} 8443:5601"
    )
    print(
        f"    Shuffle:         kubectl port-forward svc/shuffle -n {ns['security-ops']} 3000:80"
    )
    print()
    print("  Credentials:")
    print(f"    PostgreSQL password: {postgres_pw}")
    print(f"    OpenSearch password: {opensearch_pw}")
    print(f"    Redis password:      {redis_pw}")
    print(f"    Django secret key:   {django_secret}")
    print()
    print(f"  Full summary saved to: {summary_file}")
    print("=" * 72 + "\n")


def tear_down(cluster_name: str | None = None, region: str | None = None):
    """Delete the EKS cluster and all associated resources."""
    cluster = cluster_name or DEFAULT_EKS_CLUSTER
    r = region or DEFAULT_EKS_REGION

    logging.warning(
        f"This will delete the EKS cluster '{cluster}' and all associated resources!"
    )
    logging.warning("This action cannot be undone.")

    # Safety confirmation
    try:
        confirm = input(f"Type 'yes' to confirm deletion of cluster '{cluster}': ")
        if confirm.lower() != "yes":
            logging.info("Teardown cancelled.")
            return
    except (EOFError, KeyboardInterrupt):
        logging.info("Teardown cancelled.")
        return

    logging.info(f"Deleting EKS cluster '{cluster}'...")
    run_command(
        ["eksctl", "delete", "cluster", "--name", cluster, "--region", r],
        check=True,
    )
    logging.info("EKS cluster deleted successfully.")


def main():
    """Main entry point for AWS/EKS deployment."""
    parser = argparse.ArgumentParser(
        description="Deploy MCaaS stack on AWS EKS (Full Infrastructure-as-Code)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deploy-aws.py                           # Full deployment
  python deploy-aws.py --dry-run                  # Dry-run (no changes)
  python deploy-aws.py --client aws               # Use AWS client config
  python deploy-aws.py --skip-cluster             # Skip EKS cluster creation
  python deploy-aws.py --skip-infrastructure      # Skip AWS infra setup (just apps)
  python deploy-aws.py --tear-down                # Delete the EKS cluster
  python deploy-aws.py --cloudflare-token TOKEN   # Enable Cloudflare DNS01
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run deployment in dry-run mode (no changes applied)",
    )
    parser.add_argument(
        "--client",
        metavar="NAME",
        default=None,
        help="Deploy a specific client configuration from clients/<NAME>/config.yaml",
    )
    parser.add_argument(
        "--skip-cluster",
        action="store_true",
        help="Skip EKS cluster creation (cluster already exists)",
    )
    parser.add_argument(
        "--skip-infrastructure",
        action="store_true",
        help="Skip AWS infrastructure setup (cluster + add-ons already exist)",
    )
    parser.add_argument(
        "--tear-down",
        action="store_true",
        help="Delete the EKS cluster and all associated resources",
    )
    parser.add_argument(
        "--cloudflare-token",
        metavar="TOKEN",
        default=None,
        help="Cloudflare API token for DNS01 challenges (enables letsencrypt-cloudflare issuer)",
    )
    parser.add_argument(
        "--cluster-name",
        metavar="NAME",
        default=DEFAULT_EKS_CLUSTER,
        help=f"EKS cluster name (default: {DEFAULT_EKS_CLUSTER})",
    )
    parser.add_argument(
        "--region",
        metavar="REGION",
        default=DEFAULT_EKS_REGION,
        help=f"AWS region (default: {DEFAULT_EKS_REGION})",
    )
    args = parser.parse_args()

    # Set global flag for dry-run mode
    globals()["DRY_RUN"] = args.dry_run

    # Load client configuration
    cfg = load_aws_client_config(args.client)
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]

    if cfg["client_name"]:
        logging.info(
            f"Deploying client '{cfg['client_name']}' with prefix '{prefix}' on AWS EKS"
        )
    else:
        logging.info("Deploying default MCaaS configuration on AWS EKS")

    # Handle teardown
    if args.tear_down:
        tear_down(args.cluster_name, args.region)
        return

    try:
        logging.info(f"Starting MCaaS AWS/EKS deployment on {PLATFORM}")

        # Load environment variables
        load_env_file()

        # Verify AWS prerequisites
        check_aws_prerequisites()

        # Phase 1: AWS Infrastructure Provisioning
        if not args.skip_infrastructure:
            if args.skip_cluster:
                logging.info("Skipping EKS cluster creation (--skip-cluster)")
                # Still update kubeconfig and verify connectivity
                update_kubeconfig(args.cluster_name, args.region)
                check_kubectl_connectivity()
            else:
                deploy_infrastructure(cfg, args.cluster_name, args.region)
        else:
            logging.info("Skipping AWS infrastructure setup (--skip-infrastructure)")
            check_kubectl_connectivity()

        # Phase 2: Application Deployment
        deploy_applications(cfg)

        # Generate summary
        generate_environment_summary(cfg)

        logging.info("=" * 60)
        logging.info("MCaaS AWS/EKS deployment complete!")
        logging.info("=" * 60)

    except Exception as e:
        logging.error(f"An error occurred during deployment: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Logs written to {log_file}")


if __name__ == "__main__":
    main()
