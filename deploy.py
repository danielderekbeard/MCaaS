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
import secrets
import string
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


# --- Default (mcaas) Configuration ---
# When --client is NOT specified, these values are used, preserving
# backward-compatible behaviour identical to the original hardcoded script.
DEFAULT_CONFIG = {
    "prefix": "mcaas",
    "namespaces": {
        "managed-it": "managed-it",
        "security-ops": "security-ops",
        "grc": "grc",
        "wazuh": "wazuh",
    },
    "domain": "mcaas.example.com",
    "database_name": "mcaas_db",
    "wazuh_version": "4.14.6",
    "ingress": {
        "zammad_host": "alala.mcaas.example.com",
        "ciso_host": "strategos.mcaas.example.com",
        "shuffle_host": "kydoimos.mcaas.example.com",
        "wazuh_host": "deimos.mcaas.example.com",
    },
}


def load_client_config(client_name: str | None) -> dict:
    """Load client configuration from ``clients/<name>/config.yaml``.

    When *client_name* is ``None`` (i.e. ``--client`` was not supplied) the
    function returns :data:`DEFAULT_CONFIG` so that every caller gets a
    consistent config dict regardless of whether multi-client mode is active.

    The returned dict always contains at least:
      - ``prefix``               – resource name prefix (e.g. ``"mcaas"`` or ``"acme"``)
      - ``namespaces``           – mapping of base→full namespace names
      - ``domain``               – domain suffix
      - ``database_name``        – PostgreSQL database name
      - ``wazuh_version``        – Wazuh version tag
      - ``ingress``              – dict with ``zammad_host``, ``ciso_host``, ``shuffle_host``, ``wazuh_host``
      - ``client_name``          – the client identifier (or ``None`` for default)
      - ``env_prefix``           – uppercase prefix for environment variables
      - ``client_dir``           – ``Path`` to ``clients/<name>/`` or ``None``
      - ``values_dir``           – ``Path`` to client values dir or base ``deploy/values/``

    Raises :class:`SystemExit` if the config file cannot be found or parsed.
    """
    if client_name is None:
        cfg = dict(DEFAULT_CONFIG)
        cfg["client_name"] = None
        cfg["env_prefix"] = "MCAAS"
        cfg["client_dir"] = None
        cfg["values_dir"] = PROJECT_ROOT / "deploy" / "values"
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

    # Validate required fields
    for field in ("name", "prefix", "domain", "database_name"):
        if not c.get(field):
            logging.error(f"Client config missing required field: client.{field}")
            sys.exit(1)

    # Build the namespaces mapping, falling back to prefix-based defaults
    ns = c.get("namespaces", {}) or {}
    namespaces = {
        "managed-it": ns.get("managed-it") or f"{c['prefix']}-managed-it",
        "security-ops": ns.get("security-ops") or f"{c['prefix']}-security-ops",
        "grc": ns.get("grc") or f"{c['prefix']}-grc",
        "wazuh": ns.get("wazuh") or f"{c['prefix']}-wazuh",
    }

    ingress = c.get("ingress", {}) or {}
    zammad_host = ingress.get("zammad_host") or f"alala.{c['domain']}"
    ciso_host = ingress.get("ciso_host") or f"strategos.{c['domain']}"
    shuffle_host = ingress.get("shuffle_host") or f"kydoimos.{c['domain']}"
    wazuh_host = ingress.get("wazuh_host") or f"deimos.{c['domain']}"

    cfg = {
        "prefix": c["prefix"],
        "namespaces": namespaces,
        "domain": c["domain"],
        "database_name": c["database_name"],
        "wazuh_version": c.get("wazuh_version", "4.14.6"),
        "ingress": {
            "zammad_host": zammad_host,
            "ciso_host": ciso_host,
            "shuffle_host": shuffle_host,
            "wazuh_host": wazuh_host,
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
    LOG_DIR / f"deploy-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)


def ensure_wazuh_certs(wazuh_dir: Path) -> None:
    """Generate self-signed TLS certificates required by the Wazuh kustomization.

    The upstream Wazuh kustomization uses ``secretGenerator`` entries in
    ``wazuh/kustomization.yml`` that reference PEM files under
    ``<repo>/wazuh/certs/``.  In a fresh clone those files are not present,
    causing ``kubectl apply -k`` to fail.

    This function generates a self-signed root CA and then signs leaf
    certificates for the indexer, dashboard, and manager components.  The
    certificates are written to the exact paths expected by the
    ``secretGenerator`` directives so that ``kubectl apply -k`` can embed
    them as secrets.

    The expected layout (derived from ``wazuh/kustomization.yml``) is:

    * ``wazuh/certs/indexer_cluster/`` — root-ca, node, admin, dashboard,
      filebeat PEMs
    * ``wazuh/certs/dashboard_http/`` — cert, key PEMs (plus root-ca symlink)

    Requires ``openssl`` to be available on ``$PATH``.
    """
    # --- Directory layout (must match kustomization.yml secretGenerator paths) ---
    indexer_cluster = wazuh_dir / "wazuh" / "certs" / "indexer_cluster"
    dashboard_http = wazuh_dir / "wazuh" / "certs" / "dashboard_http"

    for directory in (indexer_cluster, dashboard_http):
        directory.mkdir(parents=True, exist_ok=True)

    root_ca_key = indexer_cluster / "root-ca-key.pem"
    root_ca_cert = indexer_cluster / "root-ca.pem"

    # --- 1. Generate root CA (if not already present) ---
    if not root_ca_cert.exists() or not root_ca_key.exists():
        logging.info("Generating self-signed root CA for Wazuh TLS …")
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
            ]
        )
    else:
        logging.info("Root CA already exists – reusing it.")

    def _sign_cert(name: str, cn: str, key_path: Path, csr_path: Path, cert_path: Path):
        """Generate a leaf key, CSR, and certificate signed by the root CA."""
        if cert_path.exists() and key_path.exists():
            logging.debug(f"Certificate {name} already present – skipping.")
            return
        logging.info(f"Generating certificate for {name} …")
        # Key
        run_command(["openssl", "genrsa", "-out", str(key_path), "2048"])
        # CSR
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
            ]
        )
        # Sign
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
            ]
        )

    # --- 2. Indexer cluster certificates ---
    # Node cert (CN=indexer)
    _sign_cert(
        "indexer",
        "indexer",
        indexer_cluster / "node-key.pem",
        indexer_cluster / "node.csr",
        indexer_cluster / "node.pem",
    )
    # Admin client cert (used by the dashboard to authenticate to the indexer)
    _sign_cert(
        "admin",
        "admin",
        indexer_cluster / "admin-key.pem",
        indexer_cluster / "admin.csr",
        indexer_cluster / "admin.pem",
    )
    # Dashboard-to-indexer cert
    _sign_cert(
        "dashboard",
        "dashboard",
        indexer_cluster / "dashboard-key.pem",
        indexer_cluster / "dashboard.csr",
        indexer_cluster / "dashboard.pem",
    )
    # Filebeat cert
    _sign_cert(
        "filebeat",
        "filebeat",
        indexer_cluster / "filebeat-key.pem",
        indexer_cluster / "filebeat.csr",
        indexer_cluster / "filebeat.pem",
    )

    # --- 3. Dashboard HTTP certificate ---
    _sign_cert(
        "dashboard_http",
        "dashboard",
        dashboard_http / "key.pem",
        dashboard_http / "dashboard_http.csr",
        dashboard_http / "cert.pem",
    )
    # Copy root CA into dashboard_http (secretGenerator expects it here)
    shutil.copy2(str(root_ca_cert), str(dashboard_http / "root-ca.pem"))

    logging.info("Wazuh TLS certificates generated successfully.")


def find_openssl() -> str | None:
    """Locate the ``openssl`` executable.

    On Windows, ``openssl`` is typically not on PATH even when Git is
    installed.  Git for Windows ships OpenSSL under
    ``<Git\\mingw64\\bin\\openssl.exe`` and ``<Git\\usr\\bin\\openssl.exe``.
    This function searches those locations and returns the path when found.
    On POSIX systems the function simply delegates to :func:`shutil.which`.
    """
    # Try the standard PATH lookup first.
    found = shutil.which("openssl")
    if found:
        return found

    if IS_WINDOWS:
        # Git for Windows bundles openssl – locate it via the git executable.
        git_path = shutil.which("git")
        if git_path:
            git_dir = Path(git_path).parent
            # Typical layout: C:\Program Files\Git\cmd\git.exe → parent = …\Git\cmd
            # The openssl binary lives under …\Git\mingw64\bin or …\Git\usr\bin
            git_root = git_dir.parent  # …\Git
            for candidate in [
                git_root / "mingw64" / "bin" / "openssl.exe",
                git_root / "usr" / "bin" / "openssl.exe",
            ]:
                if candidate.exists():
                    logging.info(f"Found OpenSSL bundled with Git: {candidate}")
                    return str(candidate)
    return None


def ensure_openssl_on_path() -> None:
    """Ensure ``openssl`` is reachable on PATH.

    On Windows, if ``openssl`` is not already on PATH, this function loc the
    Git-bundled OpenSSL and adds its directory to ``PATH`` so subsequent
    calls to ``openssl`` (via :func:`run_command`) succeed.
    """
    if shutil.which("openssl"):
        return  # Already on PATH

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


def check_prerequisites():
    """Verify that required tools are installed.

    In dry-run mode we only need to log the check -- the actual tools are not
    required because no commands will be executed.
    """
    # On Windows, ensure openssl from the Git bundle is on PATH.
    if IS_WINDOWS:
        ensure_openssl_on_path()

    # In dry-run mode we still need kubectl for generating manifests
    # (e.g. ``kubectl create secret --dry-run=client -o yaml``), but we
    # skip the cluster connectivity check.
    required_tools = (
        ["kubectl"]
        if globals().get("DRY_RUN", False)
        else ["kubectl", "helm", "git", "openssl"]
    )
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


def select_local_context():
    """Switch kubectl to a local cluster context if available.

    On Windows (Rancher Desktop / Docker Desktop) we prefer the local
    development cluster over any remote EKS context that may be lingering
    in the kubeconfig.  The function tries contexts in priority order
    and switches if the current context isn't already a known local one.
    """
    local_contexts = ["rancher-desktop", "docker-desktop", "minikube"]

    # Check current context
    result = run_command(["kubectl", "config", "current-context"], check=False)
    current = (result.stdout or "").strip() if result.returncode == 0 else ""

    if current in local_contexts:
        logging.info(f"Already using local context: {current}")
        return

    # List available contexts
    result = run_command(
        ["kubectl", "config", "get-contexts", "-o", "name"], check=False
    )
    if result.returncode != 0:
        logging.warning("Could not list kubectl contexts — skipping context selection.")
        return

    available = [c.strip() for c in (result.stdout or "").splitlines() if c.strip()]

    for preferred in local_contexts:
        if preferred in available:
            logging.info(f"Switching kubectl context to local cluster: {preferred}")
            run_command(["kubectl", "config", "use-context", preferred], check=False)
            return

    logging.warning(
        "No local Kubernetes context found (rancher-desktop / docker-desktop / minikube)."
    )
    logging.warning("Current context: %s", current or "(unknown)")
    logging.warning(
        "If deploying to a local cluster, switch context manually before running."
    )


def check_kubectl_connectivity():
    """Verify that kubectl can authenticate to the cluster.

    Runs ``kubectl auth can-i create namespaces`` as a lightweight check.
    Exits early with a clear message if the kubeconfig is missing, malformed,
    or the credentials are rejected — preventing cryptic failures later.
    In dry-run mode this check is skipped because there may be no live cluster.
    """
    if globals().get("DRY_RUN", False):
        logging.info("Dry-run mode: skipping kubectl connectivity check.")
        return
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
        logging.error("STDERR: %s", result.stderr.strip())
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


def run_command(command, check=True, shell=False, cwd=None, input_data=None):
    """Runs a command and logs its output.

    When ``DRY_RUN`` is enabled we log kubectl mutating commands and helm
    install/upgrade commands without executing them, because ``kubectl apply
    --dry-run=client`` still contacts the API server for OpenAPI validation
    and resource discovery, and ``helm upgrade --install --dry-run=client``
    also contacts the API server.  In a local Windows deployment with no
    cluster, both of these fail.

    Non-mutating kubectl commands (``get``, ``wait``, ``auth``, ``kustomize``,
    ``logs``, ``exec``, etc.) are executed normally in dry-run mode.

    Args:
        command: List of command arguments (preferred) or string if shell=True
        check: Raise exception if command fails
        shell: Run command through shell (generally not recommended)
        cwd: Working directory for the command
        input_data: String data to pass to stdin (e.g. for kubectl apply -f -)
    """
    if isinstance(command, list) and globals().get("DRY_RUN", False):
        # Helm upgrade/install: skip entirely in dry-run (needs API server).
        if command[0] == "helm" and ("upgrade" in command or "install" in command):
            cmd_str = " ".join(command)
            logging.info(f"Dry-run: would run: {cmd_str}")
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="", stderr=""
            )
        # kubectl mutating verbs: skip entirely in dry-run because even
        # ``--dry-run=client`` contacts the API server for discovery.
        _kubectl_mutating_verbs = {
            "apply",
            "create",
            "delete",
            "replace",
            "patch",
            "expose",
            "rollout",
            "scale",
            "set",
            "wait",  # Nothing to wait for in dry-run; resources don't exist
        }
        if (
            command[0] == "kubectl"
            and len(command) > 1
            and command[1] in _kubectl_mutating_verbs
        ):
            cmd_str = " ".join(command)
            logging.info(f"Dry-run: would run: {cmd_str}")
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="", stderr=""
            )

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
    """Waits for a Kubernetes Deployment or StatefulSet to become ready.

    Helm charts may create either a Deployment or a StatefulSet depending on
    the chart.  This function first tries to wait on a Deployment; if that
    resource does not exist it falls back to waiting on a StatefulSet's pods.

    For StatefulSets, ``kubectl wait --for=condition=ready stateset/...`` does
    not work reliably because StatefulSets often lack the ``ready`` condition.
    Instead, we wait for the pods belonging to the StatefulSet.

    In dry-run mode the resources are not actually created, so we skip the
    wait entirely.
    """
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

    # Fall back to StatefulSet — wait for pods with app.kubernetes.io/name or
    # app label matching the resource name.
    logging.info(f"Deployment '{resource_name}' not found, trying StatefulSet...")

    # Determine the label selector.  Helm charts label pods with:
    #   app.kubernetes.io/instance=<release>  (always set by Helm)
    #   app.kubernetes.io/name=<chart>         (chart name, NOT release name)
    #   app=<release>                          (some charts)
    # Try instance label first (most reliable for release-name matching),
    # then chart name, then app.
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

    # If neither label worked, try StatefulSet polling.  The resource_name
    # might be the Helm release name, which may differ from the actual
    # StatefulSet name (e.g. release "mcaas-opensearch" creates StatefulSet
    # "opensearch-cluster-master").  Discover the actual StatefulSet names
    # using the app.kubernetes.io/instance label.
    logging.info(
        f"Label-based wait did not find pods for '{resource_name}', discovering StatefulSets..."
    )

    import time

    deadline = time.time() + _parse_timeout(timeout)

    # Discover actual StatefulSet names associated with this Helm release.
    discover_cmd = [
        "kubectl",
        "get",
        "statefulset",
        "--namespace",
        namespace,
        "-l",
        f"app.kubernetes.io/instance={resource_name}",
        "-o",
        "jsonpath={.items[*].metadata.name}",
    ]
    discover_result = subprocess.run(discover_cmd, capture_output=True, text=True)
    statefulset_names = []
    if discover_result.returncode == 0 and discover_result.stdout.strip():
        statefulset_names = discover_result.stdout.strip().split()
        logging.info(
            f"Discovered StatefulSets for release '{resource_name}': {statefulset_names}"
        )

    # Also try the resource_name directly in case it IS the StatefulSet name.
    if resource_name not in statefulset_names:
        check_cmd = [
            "kubectl",
            "get",
            "statefulset",
            resource_name,
            "--namespace",
            namespace,
            "-o",
            "jsonpath={.metadata.name}",
        ]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True)
        if check_result.returncode == 0 and check_result.stdout.strip():
            statefulset_names.append(resource_name)

    if not statefulset_names:
        logging.warning(
            f"No StatefulSets found for '{resource_name}' in namespace '{namespace}'"
        )

    # Poll each discovered StatefulSet until all are ready.
    while time.time() < deadline:
        all_ready = True
        for sts_name in statefulset_names:
            cmd = [
                "kubectl",
                "get",
                "statefulset",
                sts_name,
                "--namespace",
                namespace,
                "-o",
                "jsonpath={.status.readyReplicas}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            ready = (
                int(result.stdout.strip())
                if result.returncode == 0 and result.stdout.strip()
                else 0
            )
            cmd2 = [
                "kubectl",
                "get",
                "statefulset",
                sts_name,
                "--namespace",
                namespace,
                "-o",
                "jsonpath={.spec.replicas}",
            ]
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            desired = int(result2.stdout.strip()) if result2.stdout.strip() else 1
            if ready < desired:
                all_ready = False
                break
            else:
                logging.info(
                    f"StatefulSet '{sts_name}' is ready ({ready}/{desired} replicas)."
                )
        if all_ready and statefulset_names:
            logging.info(
                f"All StatefulSets for '{resource_name}' in namespace '{namespace}' are ready."
            )
            return
        time.sleep(5)
    raise RuntimeError(
        f"Timeout waiting for StatefulSets for '{resource_name}' in namespace '{namespace}'"
    )


def _parse_timeout(timeout):
    """Parse a Kubernetes-style timeout string (e.g. '5m', '300s') into seconds."""
    if isinstance(timeout, (int, float)):
        return int(timeout)
    timeout = str(timeout)
    if timeout.endswith("m"):
        return int(timeout[:-1]) * 60
    elif timeout.endswith("s"):
        return int(timeout[:-1])
    return int(timeout)


def clone_or_use_wazuh_repo(wazuh_dir):
    """Clone Wazuh repo or use existing.

    On Windows, we handle symlinks by cloning with --no-checkout and then
    checking out individual directories. On POSIX systems, normal clone works.

    We need both ``envs/local-env`` (the environment overlay) and ``wazuh/``
    (the base manifests) for kustomize to resolve the full resource tree.
    """
    # Validate that the existing clone is usable — the top-level directory may
    # exist from a failed or partial checkout, so we also verify that the
    # critical ``envs/local-env`` subtree is present.
    if wazuh_dir.exists() and (wazuh_dir / "envs" / "local-env").exists():
        logging.info(f"Wazuh repo already exists at {wazuh_dir}")
        return wazuh_dir

    # Remove a broken/incomplete clone so we can start fresh.
    # On Windows, shutil.rmtree can fail on read-only files or locked
    # directories.  Use a robust removal that handles permission errors.
    if wazuh_dir.exists():
        logging.warning(f"Removing incomplete Wazuh clone at {wazuh_dir}")
        import stat

        def _remove_readonly(func, path, _exc_info):
            """Error handler for rmtree that clears the read-only flag and retries."""
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(wazuh_dir, onerror=_remove_readonly)

    logging.info("Cloning Wazuh repository...")
    wazuh_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        if IS_WINDOWS:
            # On Windows, clone with --depth 1 --no-checkout to avoid symlink
            # issues, then selectively check out only the directories we need.
            # Use --branch v4.14.6 to match the remote kustomize ref.
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
                ]
            )
            # Check out the directories required by kustomize:
            #   envs/local-env  — the environment overlay
            #   wazuh           — the base manifests referenced by the overlay
            run_command(
                [
                    "git",
                    "checkout",
                    "HEAD",
                    "--",
                    "envs/local-env",
                    "wazuh",
                ],
                cwd=str(wazuh_dir),
            )
            # Validate the checkout — if the critical directory is missing the
            # clone is unusable and we should clean up and fall back.
            if not (wazuh_dir / "envs" / "local-env").exists():
                logging.error(
                    "Wazuh clone checkout incomplete — envs/local-env missing"
                )
                shutil.rmtree(wazuh_dir, ignore_errors=True)
                return None
        else:
            # On POSIX, normal clone works fine. Use --branch v4.14.6 to
            # match the remote kustomize ref.
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
                ]
            )
    except subprocess.CalledProcessError:
        logging.warning(
            "Failed to clone Wazuh repo locally, will use remote URL with kubectl"
        )
        # Clean up any partial clone so deploy_wazuh doesn't try to use it.
        if wazuh_dir.exists():
            import stat as _stat

            def _ro_handler(func, path, _exc):
                os.chmod(path, _stat.S_IWRITE)
                func(path)

            shutil.rmtree(wazuh_dir, onerror=_ro_handler)
        return None

    return wazuh_dir


def deploy_ingress_controller(cfg):
    """Deploy the NGINX Ingress Controller via Helm.

    Installs the ``ingress-nginx`` Helm chart which provides a single
    LoadBalancer entry point for all services. On local Kubernetes clusters
    (Docker Desktop, Rancher Desktop, Minikube) the LoadBalancer service
    will be assigned an external IP of ``127.0.0.1`` or ``localhost``,
    making all ingress hosts accessible locally.

    Args:
        cfg: Client configuration dict from :func:`load_client_config`.
    """
    prefix = cfg["prefix"]
    ns_ingress = "ingress-nginx"

    logging.info("Installing NGINX Ingress Controller...")

    # Create the ingress-nginx namespace (idempotent).
    run_command(
        ["kubectl", "create", "namespace", ns_ingress],
        check=False,
    )

    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            f"{prefix}-ingress-nginx",
            "ingress-nginx/ingress-nginx",
            "--namespace",
            ns_ingress,
            "--set",
            "controller.service.type=LoadBalancer",
            "--set",
            "controller.service.externalTrafficPolicy=Local",
            "--set",
            "controller.config.proxy-body-size=64m",
            "--wait",
            "--timeout",
            "5m",
        ]
    )

    logging.info("NGINX Ingress Controller installed successfully.")


def deploy_ingress_resources(cfg):
    """Create Ingress resources for services not managed by Helm.

    Zammad and CISO Assistant already have ``ingress.enabled: true`` in
    their Helm value files, so their Ingress resources are created
    automatically during the Helm upgrade/install step. This function
    creates Ingress resources for **Shuffle** and **Wazuh Dashboard**,
    which do not have Helm-managed ingress configuration.

    On local clusters (Docker Desktop, Rancher Desktop) the Ingress
    controller's LoadBalancer IP is typically ``127.0.0.1``. To access
    services by hostname, add entries to the hosts file (see the
    deployment summary for details).

    Args:
        cfg: Client configuration dict from :func:`load_client_config`.
    """
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    domain = cfg.get("domain", "mcaas.example.com")
    ingress = cfg.get("ingress", {})

    shuffle_host = ingress.get("shuffle_host", f"kydoimos.{domain}")
    wazuh_host = ingress.get("wazuh_host", f"deimos.{domain}")

    # --- Shuffle Ingress ---
    shuffle_ingress = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {prefix}-shuffle-ingress
  namespace: {ns["security-ops"]}
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "64m"
spec:
  ingressClassName: nginx
  rules:
    - host: {shuffle_host}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: shuffle
                port:
                  number: 80
"""
    shuffle_manifest = TMP_DIR / "shuffle-ingress.yaml"
    shuffle_manifest.write_text(shuffle_ingress, encoding="utf-8")
    logging.info(f"Applying Shuffle Ingress manifest ({shuffle_host})...")
    run_command(["kubectl", "apply", "-f", str(shuffle_manifest)])

    # --- Wazuh Dashboard Ingress ---
    wazuh_ingress = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {prefix}-wazuh-ingress
  namespace: {ns["wazuh"]}
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "64m"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
spec:
  ingressClassName: nginx
  rules:
    - host: {wazuh_host}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: wazuh-dashboard
                port:
                  number: 5601
"""
    wazuh_manifest = TMP_DIR / "wazuh-ingress.yaml"
    wazuh_manifest.write_text(wazuh_ingress, encoding="utf-8")
    logging.info(f"Applying Wazuh Dashboard Ingress manifest ({wazuh_host})...")
    run_command(["kubectl", "apply", "-f", str(wazuh_manifest)])

    logging.info("Ingress resources for Shuffle and Wazuh Dashboard applied.")


def deploy_wazuh(wazuh_dir, cfg):
    """Deploy Wazuh using ``kubectl apply``.

    The upstream Wazuh kustomization references TLS certificate files that are
    not present in a fresh clone. For production deployments on Windows we use
    a remote kustomize URL to avoid symlink and filesystem issues. However, when
    running in **dry-run** mode those remote manifests still attempt to load the
    missing files, causing ``kubectl apply`` to fail.

    To make dry-run reliable we fall back to the **local clone** (which we
    already create in ``.tmp/wazuh-kubernetes``) and generate empty placeholder
    certificate files via :func:`ensure_wazuh_certs`. This approach works on both
    Windows and POSIX platforms because the local path is under our control and
    the placeholders satisfy the kustomize ``secretGenerator`` without affecting a
    real deployment.

    Args:
        wazuh_dir: Path to the local Wazuh kubernetes repo clone (or None).
        cfg: Client configuration dict from :func:`load_client_config`.
    """
    wazuh_ns = cfg["namespaces"]["wazuh"]
    wazuh_version = cfg["wazuh_version"]

    logging.info("Deploying Wazuh from manifests...")

    remote_kustomize = f"https://github.com/wazuh/wazuh-kubernetes//envs/local-env?ref=v{wazuh_version}"

    # Determine whether we are in dry-run mode.
    dry_run = globals().get("DRY_RUN", False)

    if dry_run:
        # In dry-run we prefer the local clone because we can inject placeholder
        # certs. Ensure the clone exists – ``clone_or_use_wazuh_repo`` is called
        # earlier in ``main`` – and then generate the certs.
        if wazuh_dir and wazuh_dir.exists():
            ensure_wazuh_certs(wazuh_dir)
            kustomize_path = str(wazuh_dir / "envs" / "local-env")
            logging.info("Dry-run: using local Wazuh clone with placeholder TLS files.")
        else:
            # Fallback to remote if the clone is unavailable; this may still
            # error, but we log the situation for visibility.
            kustomize_path = remote_kustomize
            logging.warning(
                "Dry-run: local Wazuh clone missing; falling back to remote manifests (may fail)."
            )
    else:
        # Normal execution path.
        if IS_WINDOWS:
            # On Windows we prefer a local clone with self-signed certs to
            # avoid symlink and remote-fetch issues.
            if (
                wazuh_dir
                and wazuh_dir.exists()
                and (wazuh_dir / "envs" / "local-env").exists()
            ):
                ensure_wazuh_certs(wazuh_dir)
                kustomize_path = str(wazuh_dir / "envs" / "local-env")
                logging.info(
                    "Running on Windows – using local Wazuh clone with generated TLS certificates."
                )
            else:
                kustomize_path = remote_kustomize
                logging.warning(
                    "Running on Windows – local clone unavailable or incomplete; falling back to remote manifests."
                )
        else:
            # POSIX: Prefer a local clone; if certs are missing, generate them.
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
                    "Local Wazuh clone is incomplete or missing; falling back to remote manifests"
                )
                kustomize_path = remote_kustomize

    # Delete the wazuh-storage StorageClass BEFORE applying kustomize.
    # The upstream local-env overlay creates a StorageClass with the
    # microk8s.io/hostpath provisioner which does not exist on k3s, and
    # the provisioner field is immutable — kustomize apply will fail if an
    # existing StorageClass has a different (immutable) provisioner.
    # Pre-deleting ensures the apply succeeds and lets us replace it after.
    # In dry-run mode we skip this because there is no live cluster.
    if dry_run:
        logging.info("Dry-run: skipping pre-delete of wazuh-storage StorageClass.")
    else:
        logging.info("Pre-deleting wazuh-storage StorageClass (immutable fields)...")
        run_command(
            [
                "kubectl",
                "delete",
                "storageclass",
                "wazuh-storage",
                "--ignore-not-found",
            ],
            check=False,
        )

    # Execute the apply command.
    # In dry-run mode we cannot use ``kubectl apply -k`` because kustomize
    # contacts the API server for OpenAPI validation even with
    # ``--dry-run=client --validate=false``.  Instead, we build the manifests
    # locally with ``kubectl kustomize`` and apply them with ``-f -`` so the
    # entire operation stays client-side.  ``run_command`` will automatically
    # inject ``--dry-run=client --validate=false`` for the ``kubectl apply``.
    if dry_run:
        logging.info("Dry-run: building Wazuh manifests locally with kustomize...")
        kustomize_result = run_command(
            ["kubectl", "kustomize", kustomize_path],
            check=False,
        )
        if kustomize_result and kustomize_result.returncode == 0:
            run_command(
                ["kubectl", "apply", "-f", "-"],
                input_data=kustomize_result.stdout,
            )
        else:
            logging.warning(
                "Dry-run: could not build Wazuh kustomize manifests; skipping apply."
            )
    else:
        run_command(["kubectl", "apply", "-k", kustomize_path])

    # Replace the Wazuh StorageClass for k3s compatibility.
    # The upstream local-env overlay creates a StorageClass with
    # microk8s.io/hostpath provisioner which does not exist on k3s.
    # We must delete and recreate because the provisioner field is immutable.
    # We also set WaitForFirstConsumer so the local-path provisioner knows
    # which node to provision volumes on before binding PVCs.
    # In dry-run mode we skip this because there is no live cluster.
    if dry_run:
        logging.info("Dry-run: skipping wazuh-storage StorageClass replacement.")
    else:
        logging.info("Replacing wazuh-storage StorageClass for k3s compatibility...")
        run_command(
            [
                "kubectl",
                "delete",
                "storageclass",
                "wazuh-storage",
                "--ignore-not-found",
            ],
            check=False,
        )
        run_command(
            ["kubectl", "apply", "-f", "-"],
            input_data=(
                "apiVersion: storage.k8s.io/v1\n"
                "kind: StorageClass\n"
                "metadata:\n"
                "  name: wazuh-storage\n"
                "provisioner: rancher.io/local-path\n"
                "reclaimPolicy: Delete\n"
                "volumeBindingMode: WaitForFirstConsumer\n"
            ),
        )


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


def generate_password(length=24):
    """Generate a random password with letters, digits, and symbols."""
    charset = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(charset) for _ in range(length))


def _generate_secret_yaml(secret_name, namespace, data_dict):
    """Generate a Kubernetes Secret manifest as a YAML string.

    This is a pure-Python replacement for
    ``kubectl create secret generic <name> --from-literal=... --dry-run=client -o yaml``
    and avoids any cluster connectivity, which makes it suitable for offline
    dry-run mode on a local Windows machine.

    Args:
        secret_name: Name of the Secret object.
        namespace: Namespace for the Secret.
        data_dict: Mapping of key names to plaintext string values.

    Returns:
        A YAML string representing the Secret.
    """
    import base64
    import yaml as _yaml  # PyYAML – guaranteed available (deploy.py imports it at top)

    encoded = {k: base64.b64encode(v.encode()).decode() for k, v in data_dict.items()}
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
        },
        "type": "Opaque",
        "data": encoded,
    }
    return _yaml.dump(secret, default_flow_style=False)


def create_secrets(cfg: dict):
    """Create Kubernetes secrets required by the MCaaS stack.

    Creates five secrets (names prefixed with *cfg* prefix):
      - ``<prefix>-postgresql-secret`` in the ``managed-it`` namespace
        (keys: ``postgres-password`` for Bitnami PostgreSQL, ``password`` for
        CISO Assistant)
      - ``<prefix>-opensearch-secret`` in the ``security-ops`` namespace
        (keys: ``opensearch-password`` and ``SHUFFLE_OPENSEARCH_PASSWORD``)
      - ``<prefix>-zammad-redis-pass`` in the ``managed-it`` namespace
        (key: ``redis-password``)
      - ``<prefix>-postgresql-secret`` in the ``grc`` namespace (for cross-namespace
        access by CISO Assistant)
      - ``<prefix>-ciso-secret`` in the ``grc`` namespace
        (key: ``django-secret-key`` for CISO Assistant's Django secret)

    Password values are sourced from environment variables named
    ``<ENV_PREFIX>_POSTGRES_PASSWORD``, ``<ENV_PREFIX>_OPENSEARCH_PASSWORD``,
    and ``<ENV_PREFIX>_DJANGO_SECRET_KEY`` (e.g. ``MCAAS_POSTGRES_PASSWORD``
    for the default config or ``ACME_POSTGRES_PASSWORD`` for a client named
    "acme"). These can be set directly or loaded from a ``.env`` file via
    :func:`load_env_file`. If the variables are not set, random passwords are
    generated and persisted to the ``.env`` file for future use.
    """
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    env_prefix = cfg["env_prefix"]
    env_file = PROJECT_ROOT / ".env"

    # Environment variable names derived from the client prefix
    env_postgres = f"{env_prefix}_POSTGRES_PASSWORD"
    env_opensearch = f"{env_prefix}_OPENSEARCH_PASSWORD"
    env_redis = f"{env_prefix}_REDIS_PASSWORD"
    env_django = f"{env_prefix}_DJANGO_SECRET_KEY"

    # Ensure passwords exist — generate if missing
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
                f"{env_postgres}={postgres_pw}\n" f"{env_opensearch}={opensearch_pw}\n"
            )
            logging.info(
                f"Created {env_file} with generated passwords. Back this file up for redeployments."
            )
        else:
            # .env exists but variables may not have been loaded properly
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

    # PostgreSQL secret (in the managed-it namespace)
    pg_secret_name = f"{prefix}-postgresql-secret"
    if dry_run:
        pg_manifest = _generate_secret_yaml(
            pg_secret_name,
            ns["managed-it"],
            {"postgres-password": postgres_pw, "password": postgres_pw},
        )
        logging.info(
            f"Dry-run: would apply PostgreSQL secret '{pg_secret_name}'. Manifest:\n{pg_manifest}"
        )
    else:
        proc = subprocess.run(
            [
                "kubectl",
                "-n",
                ns["managed-it"],
                "create",
                "secret",
                "generic",
                pg_secret_name,
                f"--from-literal=postgres-password={postgres_pw}",
                f"--from-literal=password={postgres_pw}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logging.error(
                f"Failed to generate PostgreSQL secret manifest: {proc.stderr}"
            )
            raise RuntimeError("Failed to create PostgreSQL secret")
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"], input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error("Failed to apply PostgreSQL secret")
            raise RuntimeError("Failed to apply PostgreSQL secret")
        logging.info(
            f"PostgreSQL secret '{pg_secret_name}' created/updated in {ns['managed-it']} namespace."
        )

    # OpenSearch secret — includes both opensearch-password (for the OpenSearch
    # chart) and SHUFFLE_OPENSEARCH_PASSWORD (for Shuffle's extraEnvVarsSecret).
    # Shuffle mounts all keys from the referenced secret as environment variables;
    # the key name must be a valid env-var identifier (no dashes), hence the
    # separate SHUFFLE_OPENSEARCH_PASSWORD key.
    os_secret_name = f"{prefix}-opensearch-secret"
    if dry_run:
        os_manifest = _generate_secret_yaml(
            os_secret_name,
            ns["security-ops"],
            {
                "opensearch-password": opensearch_pw,
                "SHUFFLE_OPENSEARCH_PASSWORD": opensearch_pw,
            },
        )
        logging.info(
            f"Dry-run: would apply OpenSearch secret '{os_secret_name}'. Manifest:\n{os_manifest}"
        )
    else:
        proc = subprocess.run(
            [
                "kubectl",
                "-n",
                ns["security-ops"],
                "create",
                "secret",
                "generic",
                os_secret_name,
                f"--from-literal=opensearch-password={opensearch_pw}",
                f"--from-literal=SHUFFLE_OPENSEARCH_PASSWORD={opensearch_pw}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logging.error(
                f"Failed to generate OpenSearch secret manifest: {proc.stderr}"
            )
            raise RuntimeError("Failed to create OpenSearch secret")
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"], input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error("Failed to apply OpenSearch secret")
            raise RuntimeError("Failed to apply OpenSearch secret")
        logging.info(
            f"OpenSearch secret '{os_secret_name}' created/updated in {ns['security-ops']} namespace."
        )

    # Redis secret for Zammad (in the managed-it namespace).
    # The Zammad chart's Redis sub-chart requires a secret with the key
    # "redis-password" containing the Redis auth password.
    redis_pw = os.environ.get(env_redis, "zammad")
    redis_secret_name = f"{prefix}-zammad-redis-pass"
    if dry_run:
        redis_manifest = _generate_secret_yaml(
            redis_secret_name,
            ns["managed-it"],
            {"redis-password": redis_pw},
        )
        logging.info(
            f"Dry-run: would apply Redis secret '{redis_secret_name}'. Manifest:\n{redis_manifest}"
        )
    else:
        proc = subprocess.run(
            [
                "kubectl",
                "-n",
                ns["managed-it"],
                "create",
                "secret",
                "generic",
                redis_secret_name,
                f"--from-literal=redis-password={redis_pw}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logging.error(f"Failed to generate Redis secret manifest: {proc.stderr}")
            raise RuntimeError("Failed to create Redis secret")
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"], input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error("Failed to apply Redis secret")
            raise RuntimeError("Failed to apply Redis secret")
        logging.info(
            f"Redis secret '{redis_secret_name}' created/updated in {ns['managed-it']} namespace."
        )

    # Cross-namespace PostgreSQL secret for CISO Assistant.
    # CISO Assistant runs in the 'grc' namespace but needs to connect to
    # PostgreSQL in the 'managed-it' namespace.  Kubernetes secrets are
    # namespace-scoped, so we create the same PostgreSQL secret in the 'grc'
    # namespace as well.
    if dry_run:
        pg_grc_manifest = _generate_secret_yaml(
            pg_secret_name,
            ns["grc"],
            {"postgres-password": postgres_pw, "password": postgres_pw},
        )
        logging.info(
            f"Dry-run: would apply PostgreSQL secret in {ns['grc']} namespace. Manifest:\n{pg_grc_manifest}"
        )
    else:
        proc = subprocess.run(
            [
                "kubectl",
                "-n",
                ns["grc"],
                "create",
                "secret",
                "generic",
                pg_secret_name,
                f"--from-literal=postgres-password={postgres_pw}",
                f"--from-literal=password={postgres_pw}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logging.error(
                f"Failed to generate PostgreSQL secret for {ns['grc']} namespace: {proc.stderr}"
            )
            raise RuntimeError(
                f"Failed to create PostgreSQL secret for {ns['grc']} namespace"
            )
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"], input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error(f"Failed to apply PostgreSQL secret in {ns['grc']} namespace")
            raise RuntimeError(
                f"Failed to apply PostgreSQL secret in {ns['grc']} namespace"
            )
        logging.info(
            f"PostgreSQL secret '{pg_secret_name}' created/updated in {ns['grc']} namespace (for CISO Assistant)."
        )

    # Django secret key for CISO Assistant.
    # The CISO Assistant Helm chart reads the Django secret from a Kubernetes
    # secret whose name is specified in ``backend.config.djangoExistingSecretKey``.
    # The key within that secret must be ``django-secret-key`` (chart default).
    django_secret = os.environ.get(env_django)
    if not django_secret:
        django_secret = generate_password(length=50)
        with open(env_file, "a") as f:
            f.write(f"\n{env_django}={django_secret}\n")
        logging.info(f"Generated {env_django} and appended to {env_file}")

    ciso_secret_name = f"{prefix}-ciso-secret"
    if dry_run:
        ciso_manifest = _generate_secret_yaml(
            ciso_secret_name,
            ns["grc"],
            {"django-secret-key": django_secret},
        )
        logging.info(
            f"Dry-run: would apply CISO Assistant Django secret '{ciso_secret_name}'. Manifest:\n{ciso_manifest}"
        )
    else:
        proc = subprocess.run(
            [
                "kubectl",
                "-n",
                ns["grc"],
                "create",
                "secret",
                "generic",
                ciso_secret_name,
                f"--from-literal=django-secret-key={django_secret}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logging.error(
                f"Failed to generate CISO Assistant Django secret: {proc.stderr}"
            )
            raise RuntimeError("Failed to create CISO Assistant Django secret")
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"], input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error("Failed to apply CISO Assistant Django secret")
            raise RuntimeError("Failed to apply CISO Assistant Django secret")
        logging.info(
            f"CISO Assistant Django secret '{ciso_secret_name}' created/updated in {ns['grc']} namespace."
        )


def generate_environment_summary(cfg: dict):
    """Generate an environment-specific summary file with secrets, URLs, and credentials.

    After a successful deployment, this function collects all the deployed
    service information — Kubernetes secrets, ingress URLs, internal service
    addresses, default credentials, and port-forward commands — and writes a
    Markdown file that operators can use as a quick-reference for accessing
    the stack.

    The file is written to ``<PROJECT_ROOT>/deploy-summary-<prefix>.md`` and
    is also logged to the console for immediate visibility.

    In dry-run mode, the summary is still generated (using env-var values or
    placeholder markers) so operators can review what *would* be deployed.
    """
    import base64
    from datetime import datetime, timezone

    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    env_prefix = cfg["env_prefix"]
    domain = cfg.get("domain", "mcaas.example.com")
    ingress = cfg.get("ingress", {})
    client_name = cfg.get("client_name") or "default"
    dry_run = globals().get("DRY_RUN", False)

    # --- Collect secret values from the cluster (or env vars) ---
    def _get_secret_value(secret_name, namespace, key):
        """Retrieve a secret value from the cluster; return placeholder on failure."""
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

    # --- Build ingress URLs (HTTP for local deployments — no cert-manager) ---
    zammad_host = ingress.get("zammad_host", f"alala.{domain}")
    ciso_host = ingress.get("ciso_host", f"strategos.{domain}")
    shuffle_host = ingress.get("shuffle_host", f"kydoimos.{domain}")
    wazuh_host = ingress.get("wazuh_host", f"deimos.{domain}")
    zammad_url = f"http://{zammad_host}"
    ciso_url = f"http://{ciso_host}"
    shuffle_url = f"http://{shuffle_host}"
    wazuh_url = f"http://{wazuh_host}"

    # --- Internal service addresses ---
    pg_host = f"{prefix}-postgresql.{ns['managed-it']}.svc.cluster.local"
    os_host = f"{prefix}-opensearch.{ns['security-ops']}.svc.cluster.local"
    shuffle_backend = f"shuffle.{ns['security-ops']}.svc.cluster.local"
    zammad_redis = f"{prefix}-zammad-redis.{ns['managed-it']}.svc.cluster.local"

    # --- Timestamp ---
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # --- Build the Markdown summary ---
    lines = [
        f"# MCaaS Deployment Summary",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Client** | `{client_name}` |",
        f"| **Prefix** | `{prefix}` |",
        f"| **Domain** | `{domain}` |",
        f"| **Generated** | {now} |",
        f"| **Mode** | {'Dry-run (no changes applied)' if dry_run else 'Live deployment'} |",
        "",
        "---",
        "",
        "## Web Interfaces (Ingress)",
        "",
        "All services are exposed via the NGINX Ingress Controller.  Access them",
        "by adding the host entries to your hosts file (see Local Access Setup below).",
        "",
        "| Service | URL | Default Credentials |",
        "|---------|-----|---------------------|",
        f"| **Alala** (Zammad Ticketing) | [{zammad_url}]({zammad_url}) | `admin` / set on first login |",
        f"| **Strategos** (CISO Assistant GRC) | [{ciso_url}]({ciso_url}) | `admin` / set on first login |",
        f"| **Kydoimos** (Shuffle SOAR) | [{shuffle_url}]({shuffle_url}) | OpenID / configured at first setup |",
        f"| **Deimos** (Wazuh SIEM) | [{wazuh_url}]({wazuh_url}) | `admin` / `MYPASSWORD_` — change immediately |",
        "",
        "## Local Access Setup (Windows)",
        "",
        "Add the following entries to your Windows hosts file so that the",
        "ingress domains resolve to the LoadBalancer IP:",
        "",
        "1.  Get the LoadBalancer IP:",
        "    ```bash",
        "    kubectl get svc -n ingress-nginx",
        "    ```",
        "    For Docker Desktop / Rancher Desktop the EXTERNAL-IP is typically",
        "    `127.0.0.1` or `localhost`.",
        "",
        "2.  Edit `C:\\Windows\\System32\\drivers\\etc\\hosts` (run as Administrator):",
        f"    ```",
        f"    127.0.0.1 {zammad_host} {ciso_host} {shuffle_host} {wazuh_host}",
        f"    ```",
        "",
        "3.  Open any of the URLs listed above in your browser.",
        "",
        "---",
        "",
        "## Internal Services (Cluster-Only)",
        "",
        "| Service | Host | Port | Notes |",
        "|---------|------|------|-------|",
        f"| **PostgreSQL** | `{pg_host}` | 5432 | Primary database |",
        f"| **OpenSearch** | `{os_host}` | 9200 | REST API (HTTPS) |",
        f"| **Zammad Redis** | `{zammad_redis}` | 6379 | Session/cache store |",
        f"| **Shuffle Backend** | `{shuffle_backend}` | 80 | SOAR engine |",
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
        f"| `{prefix}-postgresql-secret` | `{ns['grc']}` | `postgres-password`, `password` (for CISO Assistant) |",
        f"| `{prefix}-ciso-secret` | `{ns['grc']}` | `django-secret-key` |",
        "",
        "---",
        "",
        "## Credentials",
        "",
        "### PostgreSQL",
        "",
        "- **Host:** `{pg_host}:5432`",
        "- **Username:** `postgres`",
        f"- **Password:** `{postgres_pw}`",
        f"- **Database names:** `mcaas_db` (default), `zammad`, `ciso-assistant`",
        "",
        "### OpenSearch",
        "",
        "- **Host:** `{os_host}:9200`",
        "- **Username:** `admin`",
        f"- **Password:** `{opensearch_pw}`",
        "",
        "### Zammad Redis",
        "",
        "- **Host:** `{zammad_redis}:6379`",
        f"- **Password:** `{redis_pw}`",
        "",
        "### Wazuh Dashboard",
        "",
        f"- **Username:** `admin`",
        "- **Default password:** `MYPASSWORD_` — **change this immediately** after first login",
        "- **Port-forward:** `kubectl port-forward svc/wazuh-dashboard -n "
        f"{ns['wazuh']} 8443:5601`",
        "",
        "### CISO Assistant",
        "",
        f"- **Django Secret Key:** `{django_secret}`",
        f"- **PostgreSQL connection:** uses `{prefix}-postgresql-secret` in `{ns['grc']}` namespace",
        "",
        "### Shuffle",
        "",
        f"- **OpenSearch connection:** uses `{prefix}-opensearch-secret` (key `SHUFFLE_OPENSEARCH_PASSWORD`)",
        f"- **OpenSearch URL:** `{os_host}:9200`",
        "",
        "---",
        "",
        "## Namespaces",
        "",
        f"| Purpose | Namespace |",
        f"|---------|-----------|",
        f"| Managed IT / Zammad / PostgreSQL / Redis | `{ns['managed-it']}` |",
        f"| Security Ops / OpenSearch / Shuffle | `{ns['security-ops']}` |",
        f"| GRC / CISO Assistant | `{ns['grc']}` |",
        f"| Wazuh (Manager + Dashboard + Indexer) | `{ns['wazuh']}` |",
        f"| NGINX Ingress Controller | `ingress-nginx` |",
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
        f"| `ingress-nginx` | `ingress-nginx/ingress-nginx` | `ingress-nginx` |",
        "",
        "---",
        "",
        "## Port-Forward Quick Reference",
        "",
        "Prefer the Ingress URLs above for local access.  These commands are",
        "provided as fallbacks for debugging or when ingress is unavailable:",
        "",
        "```bash",
        "# Zammad (if ingress is disabled)",
        f"# kubectl port-forward svc/{prefix}-zammad -n {ns['managed-it']} 8080:8080",
        "",
        "# CISO Assistant (if ingress is disabled)",
        f"# kubectl port-forward svc/{prefix}-ciso -n {ns['grc']} 8443:8443",
        "",
        "# Wazuh Dashboard",
        f"kubectl port-forward svc/wazuh-dashboard -n {ns['wazuh']} 8443:5601",
        "",
        "# Shuffle",
        f"kubectl port-forward svc/shuffle -n {ns['security-ops']} 3000:80",
        "",
        "# PostgreSQL (debugging)",
        f"kubectl port-forward svc/{prefix}-postgresql -n {ns['managed-it']} 5432:5432",
        "",
        "# OpenSearch (debugging)",
        f"kubectl port-forward svc/{prefix}-opensearch -n {ns['security-ops']} 9200:9200",
        "```",
        "",
        "---",
        "",
        f"_This file was auto-generated by `deploy.py` on {now}._",
        "",
    ]

    summary_text = "\n".join(lines)

    # --- Write the file ---
    summary_file = PROJECT_ROOT / f"deploy-summary-{prefix}.md"
    summary_file.write_text(summary_text, encoding="utf-8")
    logging.info(f"Deployment summary written to {summary_file}")

    # --- Print to console for immediate visibility ---
    print("\n" + "=" * 72)
    print("  MCaaS DEPLOYMENT SUMMARY")
    print("=" * 72)
    print()
    print(f"  Client:      {client_name}")
    print(f"  Prefix:      {prefix}")
    print(f"  Domain:      {domain}")
    print()
    print("  Web Interfaces (via Ingress):")
    print(f"    Zammad:           {zammad_url}")
    print(f"    CISO Assistant:   {ciso_url}")
    print(f"    Shuffle:          {shuffle_url}")
    print(f"    Wazuh Dashboard: {wazuh_url}")
    print()
    print("  Local Access — add to your hosts file:")
    print(f"    127.0.0.1 {zammad_host} {ciso_host} {shuffle_host} {wazuh_host}")
    print()
    print(f"  Secrets & Credentials:")
    print(f"    PostgreSQL password: {postgres_pw}")
    print(f"    OpenSearch password: {opensearch_pw}")
    print(f"    Redis password:      {redis_pw}")
    print(f"    Django secret key:   {django_secret}")
    print(f"    Wazuh default:       admin / MYPASSWORD_  (change immediately!)")
    print()
    print(f"  Full summary saved to: {summary_file}")
    print("=" * 72 + "\n")


def _create_database(pod_name, namespace, db_name, secret_name, secret_key):
    """Create a database in the PostgreSQL instance running in the cluster.

    Connects to the PostgreSQL pod, retrieves the password from the specified
    Kubernetes secret, and runs ``CREATE DATABASE``.  Uses ``IF NOT EXISTS`` so
    the call is idempotent.

    Args:
        pod_name: Name of the PostgreSQL pod (e.g. ``mcaas-postgresql-0``).
        namespace: Namespace of the PostgreSQL pod.
        db_name: Name of the database to create.
        secret_name: Kubernetes secret containing the postgres password.
        secret_key: Key within the secret that holds the password.
    """
    dry_run = globals().get("DRY_RUN", False)
    if dry_run:
        logging.info(f"Dry-run: would create database '{db_name}' in PostgreSQL.")
        return

    logging.info(f"Ensuring database '{db_name}' exists in PostgreSQL...")
    # Retrieve the password from the Kubernetes secret
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

    # Create the database (idempotent — IF NOT EXISTS).
    # We pipe the SQL via stdin rather than using psql's -c flag because
    # PowerShell on Windows strips double-quotes from arguments, which
    # breaks identifiers that contain hyphens (e.g. "ciso-assistant").
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
        # Database may already exist — that's fine
        if "already exists" in result.stderr:
            logging.info(f"Database '{db_name}' already exists.")
        else:
            logging.warning(f"Could not create database '{db_name}': {result.stderr}")
    else:
        logging.info(f"Database '{db_name}' created successfully.")


def main():
    """Main deployment logic.

    Parses command-line arguments to configure the script (e.g. ``--dry-run``,
    ``--client``). When ``--client`` is provided, the deployment uses a
    client-specific configuration loaded from ``clients/<name>/config.yaml``,
    enabling isolated multi-tenant deployments on the same cluster.
    """
    # Argument parsing
    parser = argparse.ArgumentParser(description="Deploy MCaaS stack")
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
    args = parser.parse_args()

    # Set global flag for dry-run mode
    globals()["DRY_RUN"] = args.dry_run

    # Load client configuration (DEFAULT_CONFIG when --client is omitted)
    cfg = load_client_config(args.client)
    prefix = cfg["prefix"]
    ns = cfg["namespaces"]
    values_dir = cfg["values_dir"]

    if cfg["client_name"]:
        logging.info(f"Deploying client '{cfg['client_name']}' with prefix '{prefix}'")
    else:
        logging.info("Deploying default MCaaS configuration")

    try:
        logging.info(f"Starting MCaaS deployment on {PLATFORM}")

        # Load environment variables
        load_env_file()

        # Verify prerequisites
        check_prerequisites()

        # For local deployments, switch to a local k8s context if available
        select_local_context()

        # Verify kubectl can authenticate to the cluster
        check_kubectl_connectivity()

        # Create namespaces first (secrets are namespace-scoped, so namespaces must exist)
        logging.info("Applying namespaces and base manifests...")
        if cfg["client_dir"] is not None:
            # Client-specific deployment — use the client's namespaces.yaml
            client_ns_file = cfg["client_dir"] / "namespaces.yaml"
            run_command(["kubectl", "apply", "-f", str(client_ns_file)])
        else:
            # Default deployment — apply individual manifest files instead of
            # kustomize, because ``kubectl apply -k`` contacts the API server
            # for OpenAPI validation even with ``--dry-run=client``, which
            # fails when no cluster is reachable (e.g. local Windows dry-run).
            deploy_dir = PROJECT_ROOT / "deploy"
            manifest_files = sorted(deploy_dir.glob("*.yaml"))
            # Exclude kustomization.yaml — it is not a standalone resource.
            manifest_files = [
                f for f in manifest_files if f.name != "kustomization.yaml"
            ]
            for manifest in manifest_files:
                run_command(["kubectl", "apply", "-f", str(manifest)])

        # Create required Kubernetes secrets (must happen BEFORE Helm installs)
        logging.info("Creating required Kubernetes secrets...")
        create_secrets(cfg)

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
        run_command(
            [
                "helm",
                "repo",
                "add",
                "ingress-nginx",
                "https://kubernetes.github.io/ingress-nginx",
            ],
            check=False,
        )
        run_command(["helm", "repo", "update"])

        # Deploy NGINX Ingress Controller before services so ingressClassName
        # "nginx" is available when Helm charts create their Ingress objects.
        deploy_ingress_controller(cfg)

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

        # Clone or prepare Wazuh repo
        wazuh_dir = TMP_DIR / "wazuh-kubernetes"
        wazuh_clone_result = clone_or_use_wazuh_repo(wazuh_dir)
        # If the clone failed, wazuh_clone_result is None; fall back to
        # the directory Path anyway so deploy_wazuh can attempt a remote URL.
        effective_wazuh_dir = (
            wazuh_clone_result if wazuh_clone_result is not None else wazuh_dir
        )

        # Deploy Wazuh
        deploy_wazuh(effective_wazuh_dir, cfg)

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

        # Create the zammad database in PostgreSQL before deploying.
        # Zammad's init job needs this database to exist when
        # zammadConfig.postgresql.enabled=false and an external DB is used.
        logging.info("Creating zammad database in PostgreSQL...")
        _create_database(
            f"{prefix}-postgresql-0",
            ns["managed-it"],
            "zammad",
            f"{prefix}-postgresql-secret",
            "postgres-password",
        )

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

        # Create the ciso-assistant database in PostgreSQL before deploying.
        logging.info("Creating ciso-assistant database in PostgreSQL...")
        _create_database(
            f"{prefix}-postgresql-0",
            ns["managed-it"],
            "ciso-assistant",
            f"{prefix}-postgresql-secret",
            "postgres-password",
        )

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

        # Deploy Ingress resources for Shuffle and Wazuh Dashboard.
        # (Zammad and CISO Assistant ingress are managed by their Helm charts.)
        deploy_ingress_resources(cfg)

        logging.info("Deployment complete!")

        # Generate environment-specific summary file with secrets, URLs & credentials
        generate_environment_summary(cfg)

    except Exception as e:
        logging.error(f"An error occurred during deployment: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Logs written to {log_file}")


if __name__ == "__main__":
    main()
