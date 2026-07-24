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
    dashboard_http  = wazuh_dir / "wazuh" / "certs" / "dashboard_http"

    for directory in (indexer_cluster, dashboard_http):
        directory.mkdir(parents=True, exist_ok=True)

    root_ca_key  = indexer_cluster / "root-ca-key.pem"
    root_ca_cert = indexer_cluster / "root-ca.pem"

    # --- 1. Generate root CA (if not already present) ---
    if not root_ca_cert.exists() or not root_ca_key.exists():
        logging.info("Generating self-signed root CA for Wazuh TLS …")
        run_command([
            "openssl", "req",
            "-x509", "-new", "-nodes",
            "-newkey", "rsa:2048",
            "-keyout", str(root_ca_key),
            "-out", str(root_ca_cert),
            "-days", "3650",
            "-subj", "/CN=WazuhRootCA/O=Wazuh/L=California/C=US",
        ])
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
        run_command([
            "openssl", "req", "-new",
            "-key", str(key_path),
            "-out", str(csr_path),
            "-subj", f"/CN={cn}/OU=Wazuh/O=Wazuh/L=California/C=US",
        ])
        # Sign
        run_command([
            "openssl", "x509", "-req",
            "-in", str(csr_path),
            "-CA", str(root_ca_cert),
            "-CAkey", str(root_ca_key),
            "-CAcreateserial",
            "-out", str(cert_path),
            "-days", "3650",
        ])

    # --- 2. Indexer cluster certificates ---
    # Node cert (CN=indexer)
    _sign_cert(
        "indexer", "indexer",
        indexer_cluster / "node-key.pem",
        indexer_cluster / "node.csr",
        indexer_cluster / "node.pem",
    )
    # Admin client cert (used by the dashboard to authenticate to the indexer)
    _sign_cert(
        "admin", "admin",
        indexer_cluster / "admin-key.pem",
        indexer_cluster / "admin.csr",
        indexer_cluster / "admin.pem",
    )
    # Dashboard-to-indexer cert
    _sign_cert(
        "dashboard", "dashboard",
        indexer_cluster / "dashboard-key.pem",
        indexer_cluster / "dashboard.csr",
        indexer_cluster / "dashboard.pem",
    )
    # Filebeat cert
    _sign_cert(
        "filebeat", "filebeat",
        indexer_cluster / "filebeat-key.pem",
        indexer_cluster / "filebeat.csr",
        indexer_cluster / "filebeat.pem",
    )

    # --- 3. Dashboard HTTP certificate ---
    _sign_cert(
        "dashboard_http", "dashboard",
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
        logging.error("OpenSSL not found. Install OpenSSL or Git for Windows and try again.")
        sys.exit(1)


def check_prerequisites():
    """Verify that required tools are installed.

    In dry‑run mode we only need to log the check – the actual tools are not
    required because no commands will be executed.
    """
    if globals().get("DRY_RUN", False):
        logging.info("Dry‑run mode: skipping prerequisite tool checks.")
        return

    # On Windows, ensure openssl from the Git bundle is on PATH.
    if IS_WINDOWS:
        ensure_openssl_on_path()

    required_tools = ["kubectl", "helm", "git", "openssl"]
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

def run_command(command, check=True, shell=False, cwd=None, input_data=None):
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
        input_data: String data to pass to stdin (e.g. for kubectl apply -f -)
    """
    # Inject dry‑run flag for helm/kubectl when appropriate. For Helm we also
    # strip any "--wait" flag because waiting for a resource that will never be
    # created leads to a timeout in dry‑run mode.
    if isinstance(command, list) and globals().get("DRY_RUN", False):
        # Helm commands: only apply dry‑run to actions that support it (install/upgrade).
        # Helm repo commands (add, update, etc.) do not accept the flag.
        if command[0] == "helm" and ("upgrade" in command or "install" in command):
            # Remove the "--wait" flag if present – waiting is irrelevant in dry‑run.
            command = [c for c in command if c != "--wait"]
            # Append the dry‑run flag (avoid duplicates)
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
            input=input_data
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

    In dry‑run mode the resources are not actually created, so we skip the
    wait entirely.
    """
    if globals().get("DRY_RUN", False):
        logging.info(f"Dry‑run: skipping wait for resource '{resource_name}' in namespace '{namespace}'.")
        return

    logging.info(f"Waiting for resource '{resource_name}' in namespace '{namespace}' to be ready...")

    # Try Deployment first
    deploy_cmd = [
        "kubectl", "wait",
        "--for=condition=available",
        "--namespace", namespace,
        f"deployment/{resource_name}",
        f"--timeout={timeout}"
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
            "kubectl", "wait",
            "--for=condition=ready",
            "--namespace", namespace,
            "pod",
            "-l", label_selector,
            f"--timeout={timeout}"
        ]
        result = run_command(pod_cmd, check=False)
        if result is not None and result.returncode == 0:
            logging.info(f"StatefulSet '{resource_name}' pods are ready (label {label_selector}).")
            return

    # If neither label worked, try StatefulSet polling.  The resource_name
    # might be the Helm release name, which may differ from the actual
    # StatefulSet name (e.g. release "mcaas-opensearch" creates StatefulSet
    # "opensearch-cluster-master").  Discover the actual StatefulSet names
    # using the app.kubernetes.io/instance label.
    logging.info(f"Label-based wait did not find pods for '{resource_name}', discovering StatefulSets...")

    import time
    deadline = time.time() + _parse_timeout(timeout)

    # Discover actual StatefulSet names associated with this Helm release.
    discover_cmd = [
        "kubectl", "get", "statefulset",
        "--namespace", namespace,
        "-l", f"app.kubernetes.io/instance={resource_name}",
        "-o", "jsonpath={.items[*].metadata.name}"
    ]
    discover_result = subprocess.run(discover_cmd, capture_output=True, text=True)
    statefulset_names = []
    if discover_result.returncode == 0 and discover_result.stdout.strip():
        statefulset_names = discover_result.stdout.strip().split()
        logging.info(f"Discovered StatefulSets for release '{resource_name}': {statefulset_names}")

    # Also try the resource_name directly in case it IS the StatefulSet name.
    if resource_name not in statefulset_names:
        check_cmd = [
            "kubectl", "get", "statefulset", resource_name,
            "--namespace", namespace,
            "-o", "jsonpath={.metadata.name}"
        ]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True)
        if check_result.returncode == 0 and check_result.stdout.strip():
            statefulset_names.append(resource_name)

    if not statefulset_names:
        logging.warning(f"No StatefulSets found for '{resource_name}' in namespace '{namespace}'")

    # Poll each discovered StatefulSet until all are ready.
    while time.time() < deadline:
        all_ready = True
        for sts_name in statefulset_names:
            cmd = [
                "kubectl", "get", "statefulset", sts_name,
                "--namespace", namespace,
                "-o", "jsonpath={.status.readyReplicas}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            ready = int(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else 0
            cmd2 = [
                "kubectl", "get", "statefulset", sts_name,
                "--namespace", namespace,
                "-o", "jsonpath={.spec.replicas}"
            ]
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            desired = int(result2.stdout.strip()) if result2.stdout.strip() else 1
            if ready < desired:
                all_ready = False
                break
            else:
                logging.info(f"StatefulSet '{sts_name}' is ready ({ready}/{desired} replicas).")
        if all_ready and statefulset_names:
            logging.info(f"All StatefulSets for '{resource_name}' in namespace '{namespace}' are ready.")
            return
        time.sleep(5)
    raise RuntimeError(f"Timeout waiting for StatefulSets for '{resource_name}' in namespace '{namespace}'")


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
            run_command([
                "git", "clone",
                "--depth", "1",
                "--no-checkout",
                "--branch", "v4.14.6",
                "https://github.com/wazuh/wazuh-kubernetes.git",
                str(wazuh_dir)
            ])
            # Check out the directories required by kustomize:
            #   envs/local-env  — the environment overlay
            #   wazuh           — the base manifests referenced by the overlay
            run_command([
                "git", "checkout", "HEAD", "--",
                "envs/local-env",
                "wazuh",
            ], cwd=str(wazuh_dir))
            # Validate the checkout — if the critical directory is missing the
            # clone is unusable and we should clean up and fall back.
            if not (wazuh_dir / "envs" / "local-env").exists():
                logging.error("Wazuh clone checkout incomplete — envs/local-env missing")
                shutil.rmtree(wazuh_dir, ignore_errors=True)
                return None
        else:
            # On POSIX, normal clone works fine. Use --branch v4.14.6 to
            # match the remote kustomize ref.
            run_command([
                "git", "clone",
                "--depth", "1",
                "--branch", "v4.14.6",
                "https://github.com/wazuh/wazuh-kubernetes.git",
                str(wazuh_dir)
            ])
    except subprocess.CalledProcessError:
        logging.warning("Failed to clone Wazuh repo locally, will use remote URL with kubectl")
        # Clean up any partial clone so deploy_wazuh doesn't try to use it.
        if wazuh_dir.exists():
            import stat as _stat
            def _ro_handler(func, path, _exc):
                os.chmod(path, _stat.S_IWRITE)
                func(path)
            shutil.rmtree(wazuh_dir, onerror=_ro_handler)
        return None
    
    return wazuh_dir

def deploy_wazuh(wazuh_dir):
    """Deploy Wazuh using ``kubectl apply``.

    The upstream Wazuh kustomization references TLS certificate files that are
    not present in a fresh clone. For production deployments on Windows we use
    a remote kustomize URL to avoid symlink and filesystem issues. However, when
    running in **dry‑run** mode those remote manifests still attempt to load the
    missing files, causing ``kubectl apply`` to fail.

    To make dry‑run reliable we fall back to the **local clone** (which we
    already create in ``.tmp/wazuh-kubernetes``) and generate empty placeholder
    certificate files via :func:`ensure_wazuh_certs`. This approach works on both
    Windows and POSIX platforms because the local path is under our control and
    the placeholders satisfy the kustomize ``secretGenerator`` without affecting a
    real deployment.
    """
    logging.info("Deploying Wazuh from manifests...")

    remote_kustomize = "https://github.com/wazuh/wazuh-kubernetes//envs/local-env?ref=v4.14.6"

    # Determine whether we are in dry‑run mode.
    dry_run = globals().get("DRY_RUN", False)

    if dry_run:
        # In dry‑run we prefer the local clone because we can inject placeholder
        # certs. Ensure the clone exists – ``clone_or_use_wazuh_repo`` is called
        # earlier in ``main`` – and then generate the certs.
        if wazuh_dir and wazuh_dir.exists():
            ensure_wazuh_certs(wazuh_dir)
            kustomize_path = str(wazuh_dir / "envs" / "local-env")
            logging.info("Dry‑run: using local Wazuh clone with placeholder TLS files.")
        else:
            # Fallback to remote if the clone is unavailable; this may still
            # error, but we log the situation for visibility.
            kustomize_path = remote_kustomize
            logging.warning("Dry‑run: local Wazuh clone missing; falling back to remote manifests (may fail).")
    else:
        # Normal execution path.
        if IS_WINDOWS:
            # On Windows we prefer a local clone with self-signed certs to
            # avoid symlink and remote-fetch issues.
            if wazuh_dir and wazuh_dir.exists() and (wazuh_dir / "envs" / "local-env").exists():
                ensure_wazuh_certs(wazuh_dir)
                kustomize_path = str(wazuh_dir / "envs" / "local-env")
                logging.info("Running on Windows – using local Wazuh clone with generated TLS certificates.")
            else:
                kustomize_path = remote_kustomize
                logging.warning("Running on Windows – local clone unavailable or incomplete; falling back to remote manifests.")
        else:
            # POSIX: Prefer a local clone; if certs are missing, generate them.
            local_kustomize = wazuh_dir and (wazuh_dir / "envs" / "local-env")
            if local_kustomize and local_kustomize.exists():
                required_cert = wazuh_dir / "wazuh" / "certs" / "indexer_cluster" / "root-ca.pem"
                if not required_cert.exists():
                    logging.info("Wazuh TLS certificates not found – generating them now.")
                    ensure_wazuh_certs(wazuh_dir)
                kustomize_path = str(local_kustomize)
            else:
                logging.warning("Local Wazuh clone is incomplete or missing; falling back to remote manifests")
                kustomize_path = remote_kustomize

    # Execute the apply command.
    run_command(["kubectl", "apply", "-k", kustomize_path])

    # Replace the Wazuh StorageClass for k3s compatibility.
    # The upstream local-env overlay creates a StorageClass with
    # microk8s.io/hostpath provisioner which does not exist on k3s.
    # We must delete and recreate because the provisioner field is immutable.
    # We also set WaitForFirstConsumer so the local-path provisioner knows
    # which node to provision volumes on before binding PVCs.
    logging.info("Replacing wazuh-storage StorageClass for k3s compatibility...")
    run_command([
        "kubectl", "delete", "storageclass", "wazuh-storage",
        "--ignore-not-found"
    ], check=False)
    run_command([
        "kubectl", "apply", "-f", "-"
    ], input_data=(
        "apiVersion: storage.k8s.io/v1\n"
        "kind: StorageClass\n"
        "metadata:\n"
        "  name: wazuh-storage\n"
        "provisioner: rancher.io/local-path\n"
        "reclaimPolicy: Delete\n"
        "volumeBindingMode: WaitForFirstConsumer\n"
    ))

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

def generate_password(length=24):
    """Generate a random password with letters, digits, and symbols."""
    charset = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(charset) for _ in range(length))

def create_secrets():
    """Create Kubernetes secrets required by the MCaaS stack.

    Creates two secrets:
      - ``mcaas-postgresql-secret`` in the ``managed-it`` namespace
        (keys: ``postgres-password`` for Bitnami PostgreSQL, ``password`` for
        CISO Assistant)
      - ``mcaas-opensearch-secret`` in the ``security-ops`` namespace

    Password values are sourced from environment variables
    (``MCAAS_POSTGRES_PASSWORD`` and ``MCAAS_OPENSEARCH_PASSWORD``) which can
    be set directly or loaded from a ``.env`` file via :func:`load_env_file`.
    If the variables are not set, random passwords are generated and persisted
    to the ``.env`` file for future use.
    """
    env_file = PROJECT_ROOT / ".env"

    # Ensure passwords exist — generate if missing
    postgres_pw = os.environ.get("MCAAS_POSTGRES_PASSWORD")
    opensearch_pw = os.environ.get("MCAAS_OPENSEARCH_PASSWORD")

    if not postgres_pw or not opensearch_pw:
        if not env_file.exists():
            logging.info("No .env file found. Generating passwords and creating .env file...")
            postgres_pw = postgres_pw or generate_password()
            opensearch_pw = opensearch_pw or generate_password()
            env_file.write_text(
                f"MCAAS_POSTGRES_PASSWORD={postgres_pw}\n"
                f"MCAAS_OPENSEARCH_PASSWORD={opensearch_pw}\n"
            )
            logging.info(f"Created {env_file} with generated passwords. Back this file up for redeployments.")
        else:
            # .env exists but variables may not have been loaded properly
            if not postgres_pw:
                logging.error("MCAAS_POSTGRES_PASSWORD is not set. Set it in your .env file or environment.")
                sys.exit(1)
            if not opensearch_pw:
                logging.error("MCAAS_OPENSEARCH_PASSWORD is not set. Set it in your .env file or environment.")
                sys.exit(1)

    logging.info("Creating/updating Kubernetes secrets...")

    dry_run = globals().get("DRY_RUN", False)

    # PostgreSQL secret
    proc = subprocess.run(
        ["kubectl", "-n", "managed-it", "create", "secret", "generic",
         "mcaas-postgresql-secret",
         f"--from-literal=postgres-password={postgres_pw}",
         f"--from-literal=password={postgres_pw}",
         "--dry-run=client", "-o", "yaml"],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        logging.error(f"Failed to generate PostgreSQL secret manifest: {proc.stderr}")
        raise RuntimeError("Failed to create PostgreSQL secret")
    if dry_run:
        logging.info(f"Dry‑run: would apply PostgreSQL secret. Manifest:\n{proc.stdout}")
    else:
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error("Failed to apply PostgreSQL secret")
            raise RuntimeError("Failed to apply PostgreSQL secret")
        logging.info("PostgreSQL secret created/updated in managed-it namespace.")

    # OpenSearch secret
    proc = subprocess.run(
        ["kubectl", "-n", "security-ops", "create", "secret", "generic",
         "mcaas-opensearch-secret",
         f"--from-literal=opensearch-password={opensearch_pw}",
         "--dry-run=client", "-o", "yaml"],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        logging.error(f"Failed to generate OpenSearch secret manifest: {proc.stderr}")
        raise RuntimeError("Failed to create OpenSearch secret")
    if dry_run:
        logging.info(f"Dry‑run: would apply OpenSearch secret. Manifest:\n{proc.stdout}")
    else:
        apply_proc = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=proc.stdout, text=True
        )
        if apply_proc.returncode != 0:
            logging.error("Failed to apply OpenSearch secret")
            raise RuntimeError("Failed to apply OpenSearch secret")
        logging.info("OpenSearch secret created/updated in security-ops namespace.")

def main():
    """Main deployment logic.

    Parses command‑line arguments to configure the script (e.g. ``--dry-run``).
    """
    # Argument parsing
    parser = argparse.ArgumentParser(description="Deploy MCaaS stack")
    parser.add_argument("--dry-run", action="store_true", help="Run deployment in dry‑run mode (no changes applied)")
    args = parser.parse_args()
    # Set global flag for dry‑run mode
    globals()["DRY_RUN"] = args.dry_run

    try:
        logging.info(f"Starting MCaaS deployment on {PLATFORM}")
        
        # Load environment variables
        load_env_file()
        
        # Verify prerequisites
        check_prerequisites()
        
        # Create namespaces first (secrets are namespace-scoped, so namespaces must exist)
        logging.info("Applying namespaces and base manifests...")
        run_command(["kubectl", "apply", "-k", str(PROJECT_ROOT / "deploy")])

        # Create required Kubernetes secrets (must happen BEFORE Helm installs)
        logging.info("Creating required Kubernetes secrets...")
        create_secrets()
        
        logging.info("Adding and updating Helm repositories...")
        run_command(["helm", "repo", "add", "bitnami", "https://charts.bitnami.com/bitnami"], check=False)
        run_command(["helm", "repo", "add", "opensearch", "https://opensearch-project.github.io/helm-charts"], check=False)
        run_command(["helm", "repo", "add", "zammad", "https://zammad.github.io/zammad-helm"], check=False)
        run_command(["helm", "repo", "update"])

        logging.info("Deploying PostgreSQL...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-postgresql", "bitnami/postgresql",
            "--namespace", "managed-it",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "postgresql.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_resource("managed-it", "mcaas-postgresql")

        logging.info("Deploying OpenSearch...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-opensearch", "opensearch/opensearch",
            "--namespace", "security-ops",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "opensearch.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_resource("security-ops", "mcaas-opensearch")

        # Clone or prepare Wazuh repo
        wazuh_dir = TMP_DIR / "wazuh-kubernetes"
        wazuh_clone_result = clone_or_use_wazuh_repo(wazuh_dir)
        # If the clone failed, wazuh_clone_result is None; fall back to
        # the directory Path anyway so deploy_wazuh can attempt a remote URL.
        effective_wazuh_dir = wazuh_clone_result if wazuh_clone_result is not None else wazuh_dir
        
        # Deploy Wazuh
        deploy_wazuh(effective_wazuh_dir)

        logging.info("Waiting for Wazuh components to be ready...")
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-manager", "-n", "wazuh", "--timeout=5m"], check=False)
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-indexer", "-n", "wazuh", "--timeout=5m"], check=False)
        run_command(["kubectl", "wait", "--for=condition=ready", "pod", "-l", "app=wazuh-dashboard", "-n", "wazuh", "--timeout=5m"], check=False)

        logging.info("Deploying Shuffle (OCI chart)...")
        run_command([
            "helm", "upgrade", "--install", "mcaas-shuffle", "oci://ghcr.io/shuffle/charts/shuffle",
            "--namespace", "security-ops",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "shuffle.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_resource("security-ops", "mcaas-shuffle")

        logging.info("Deploying Zammad...")
        run_command([
            "helm", "upgrade", "--install", "zammad", "zammad/zammad",
            "--namespace", "managed-it",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "zammad.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_resource("managed-it", "zammad-zammad-scheduler")
        wait_for_resource("managed-it", "zammad-zammad-websocket")
        wait_for_resource("managed-it", "zammad-zammad-web")

        logging.info("Deploying CISO Assistant...")
        run_command([
            "helm", "upgrade", "--install", "ciso-assistant", "oci://ghcr.io/intuitem/helm-charts/ce/ciso-assistant",
            "--version", "0.11.4",
            "--namespace", "grc",
            "--values", str(PROJECT_ROOT / "deploy" / "values" / "ciso-assistant.yaml"),
            "--wait", "--timeout", "5m"
        ])
        wait_for_resource("grc", "ciso-assistant-frontend")
        wait_for_resource("grc", "ciso-assistant-backend")

        logging.info("Deployment complete!")

    except Exception as e:
        logging.error(f"An error occurred during deployment: {e}")
        sys.exit(1)
    finally:
        logging.info(f"Logs written to {log_file}")

if __name__ == "__main__":
    main()