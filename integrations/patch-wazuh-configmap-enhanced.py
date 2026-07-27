#!/usr/bin/env python3
"""
Enhanced Wazuh ConfigMap Patcher for Shuffle SOAR Integration.

This script patches the Wazuh ConfigMap to add the Shuffle SOAR integration block.
It supports label selectors for finding the ConfigMap, dry-run mode, rollback,
and comprehensive error handling.

Environment Variables:
    WAZUH_NAMESPACE: Kubernetes namespace for Wazuh (default: wazuh)
    WAZUH_CONFIGMAP_LABELS: Label selector for finding ConfigMap (default: app=wazuh,component=manager)
    WAZUH_CONFIGMAP_NAME: Specific ConfigMap name (overrides label selector)
    SHUFFLE_WEBHOOK_URL: Shuffle webhook URL for integration
    SHUFFLE_ALERT_LEVEL: Minimum alert level to send to Shuffle (default: 3)
    LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR) (default: INFO)
    DRY_RUN: Set to 'true' to preview changes without applying (default: false)

Usage:
    python patch-wazuh-configmap-enhanced.py [--dry-run] [--rollback] [--validate-only]

Exit Codes:
    0: Success
    1: General error
    2: kubectl command failed
    3: ConfigMap not found
    4: Invalid ConfigMap structure
    5: Rollback failed
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Default configuration
DEFAULT_NAMESPACE = "wazuh"
DEFAULT_CONFIGMAP_LABELS = "app=wazuh,component=manager"
DEFAULT_ALERT_LEVEL = "3"
DEFAULT_SHUFFLE_WEBHOOK = (
    "http://shuffle-backend.security-ops.svc.cluster.local:5001"
    "/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b"
)

# Backup directory
BACKUP_DIR = Path(__file__).parent / "backups"


class ConfigMapPatcherError(Exception):
    """Base exception for ConfigMap patcher errors."""
    pass


class KubectlError(ConfigMapPatcherError):
    """Raised when kubectl command fails."""
    pass


class ConfigMapNotFoundError(ConfigMapPatcherError):
    """Raised when ConfigMap cannot be found."""
    pass


class InvalidConfigMapError(ConfigMapPatcherError):
    """Raised when ConfigMap has invalid structure."""
    pass


class RollbackError(ConfigMapPatcherError):
    """Raised when rollback fails."""
    pass


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure logging with structured output.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("wazuh_configmap_patcher")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def run_kubectl(
    args: List[str],
    logger: logging.Logger,
    check: bool = True,
    capture: bool = True
) -> subprocess.CompletedProcess:
    """
    Execute a kubectl command with error handling.
    
    Args:
        args: kubectl command arguments
        logger: Logger instance
        check: Whether to raise exception on non-zero exit
        capture: Whether to capture stdout/stderr
    
    Returns:
        CompletedProcess instance
    
    Raises:
        KubectlError: If kubectl command fails
    """
    cmd = ["kubectl"] + args
    logger.debug(f"Executing: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            check=False
        )
        
        if result.returncode != 0 and check:
            error_msg = f"kubectl failed (exit {result.returncode}): {result.stderr}"
            logger.error(error_msg)
            raise KubectlError(error_msg)
        
        return result
    except FileNotFoundError:
        error_msg = "kubectl not found in PATH"
        logger.error(error_msg)
        raise KubectlError(error_msg)
    except Exception as e:
        error_msg = f"Failed to execute kubectl: {e}"
        logger.error(error_msg)
        raise KubectlError(error_msg)


def find_configmap(
    namespace: str,
    labels: str,
    name: Optional[str],
    logger: logging.Logger
) -> str:
    """
    Find ConfigMap using label selectors or explicit name.
    
    Args:
        namespace: Kubernetes namespace
        labels: Label selector string (e.g., "app=wazuh,component=manager")
        name: Specific ConfigMap name (overrides label selector)
        logger: Logger instance
    
    Returns:
        ConfigMap name
    
    Raises:
        ConfigMapNotFoundError: If ConfigMap cannot be found
    """
    if name:
        logger.info(f"Using explicitly specified ConfigMap: {name}")
        
        # Verify ConfigMap exists
        result = run_kubectl(
            ["get", "configmap", name, "-n", namespace, "-o", "jsonpath={.metadata.name}"],
            logger,
            check=False
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            raise ConfigMapNotFoundError(
                f"ConfigMap '{name}' not found in namespace '{namespace}'"
            )
        
        return name
    
    # Use label selector
    logger.info(f"Searching for ConfigMap with labels: {labels}")
    
    result = run_kubectl(
        ["get", "configmap", "-n", namespace, "-l", labels, "-o", "json"],
        logger,
        check=False
    )
    
    if result.returncode != 0:
        raise ConfigMapNotFoundError(
            f"Failed to query ConfigMaps with labels '{labels}': {result.stderr}"
        )
    
    try:
        configmaps = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ConfigMapNotFoundError(f"Failed to parse kubectl output: {e}")
    
    items = configmaps.get("items", [])
    
    if not items:
        raise ConfigMapNotFoundError(
            f"No ConfigMaps found with labels '{labels}' in namespace '{namespace}'"
        )
    
    if len(items) > 1:
        names = [item["metadata"]["name"] for item in items]
        logger.warning(f"Multiple ConfigMaps found: {names}. Using first: {names[0]}")
    
    configmap_name = items[0]["metadata"]["name"]
    logger.info(f"Found ConfigMap: {configmap_name}")
    
    return configmap_name


def get_configmap(
    name: str,
    namespace: str,
    logger: logging.Logger
) -> Dict:
    """
    Retrieve ConfigMap from Kubernetes.
    
    Args:
        name: ConfigMap name
        namespace: Kubernetes namespace
        logger: Logger instance
    
    Returns:
        ConfigMap as dictionary
    
    Raises:
        InvalidConfigMapError: If ConfigMap cannot be retrieved or parsed
    """
    logger.info(f"Fetching ConfigMap {name}...")
    
    result = run_kubectl(
        ["get", "configmap", name, "-n", namespace, "-o", "json"],
        logger
    )
    
    try:
        configmap = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise InvalidConfigMapError(f"Failed to parse ConfigMap JSON: {e}")
    
    if "data" not in configmap:
        raise InvalidConfigMapError("ConfigMap has no 'data' field")
    
    if "master.conf" not in configmap["data"]:
        raise InvalidConfigMapError("ConfigMap missing 'master.conf' key")
    
    logger.debug(f"Successfully retrieved ConfigMap {name}")
    return configmap


def create_backup(
    configmap: Dict,
    logger: logging.Logger
) -> Path:
    """
    Create a backup of the ConfigMap before modification.
    
    Args:
        configmap: ConfigMap dictionary
        logger: Logger instance
    
    Returns:
        Path to backup file
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    configmap_name = configmap["metadata"]["name"]
    backup_file = BACKUP_DIR / f"{configmap_name}_{timestamp}.json"
    
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(configmap, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Backup created: {backup_file}")
    return backup_file


def build_integration_block(
    webhook_url: str,
    alert_level: str,
    logger: logging.Logger
) -> str:
    """
    Build the Shuffle integration XML block.
    
    Args:
        webhook_url: Shuffle webhook URL
        alert_level: Minimum alert level
        logger: Logger instance
    
    Returns:
        XML integration block as string
    """
    logger.debug(f"Building integration block (level >= {alert_level})")
    
    integration_block = f"""  <!-- Shuffle SOAR Integration -->
  <integration>
    <name>slack</name>
    <hook_url>{webhook_url}</hook_url>
    <level>{alert_level}</level>
    <alert_format>json</alert_format>
  </integration>
"""
    return integration_block


def patch_master_conf(
    master_conf: str,
    integration_block: str,
    logger: logging.Logger
) -> str:
    """
    Patch master.conf with the integration block.
    
    Args:
        master_conf: Current master.conf content
        integration_block: Integration block to insert
        logger: Logger instance
    
    Returns:
        Patched master.conf content
    
    Raises:
        InvalidConfigMapError: If master.conf structure is invalid
    """
    logger.info("Patching master.conf...")
    
    # Remove any existing Shuffle integration blocks
    old_block_pattern = r'\s*<!-- Shuffle SOAR Integration -->\s*<integration>.*?</integration>\s*'
    master_conf = re.sub(old_block_pattern, '\n  ', master_conf, flags=re.DOTALL).rstrip() + '\n'
    
    # Find insertion point before first </ossec_config>
    insert_point = master_conf.find("</ossec_config>")
    if insert_point == -1:
        raise InvalidConfigMapError("Could not find </ossec_config> in master.conf")
    
    # Insert integration block
    new_conf = master_conf[:insert_point] + integration_block + master_conf[insert_point:]
    
    logger.debug("master.conf patched successfully")
    return new_conf


def validate_config(master_conf: str, logger: logging.Logger) -> bool:
    """
    Validate the patched configuration.
    
    Args:
        master_conf: Patched master.conf content
        logger: Logger instance
    
    Returns:
        True if valid, False otherwise
    """
    logger.info("Validating patched configuration...")
    
    checks = [
        ("</ossec_config>" in master_conf, "Missing </ossec_config>"),
        ("<ossec_config>" in master_conf, "Missing <ossec_config>"),
        ("Shuffle SOAR Integration" in master_conf, "Integration block not found"),
        ("<integration>" in master_conf, "Missing <integration> tag"),
        ("</integration>" in master_conf, "Missing </integration> tag"),
    ]
    
    is_valid = True
    for check, message in checks:
        if not check:
            logger.error(f"Validation failed: {message}")
            is_valid = False
    
    # Check for balanced XML tags
    open_tags = master_conf.count("<integration>")
    close_tags = master_conf.count("</integration>")
    if open_tags != close_tags:
        logger.error(f"Unbalanced integration tags: {open_tags} open, {close_tags} close")
        is_valid = False
    
    if is_valid:
        logger.info("Configuration validation passed")
    
    return is_valid


def apply_configmap(
    configmap: Dict,
    namespace: str,
    dry_run: bool,
    logger: logging.Logger
) -> bool:
    """
    Apply the ConfigMap to Kubernetes.
    
    Args:
        configmap: ConfigMap dictionary to apply
        namespace: Kubernetes namespace
        dry_run: Whether to perform dry-run only
        logger: Logger instance
    
    Returns:
        True if successful or dry-run, False otherwise
    """
    if dry_run:
        logger.info("[DRY-RUN] Would apply ConfigMap:")
        print(json.dumps(configmap, indent=2, ensure_ascii=False))
        return True
    
    logger.info("Applying updated ConfigMap...")
    
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False,
        encoding='utf-8'
    ) as f:
        json.dump(configmap, f, ensure_ascii=False)
        temp_file = f.name
    
    try:
        result = run_kubectl(
            ["apply", "-f", temp_file, "-n", namespace],
            logger,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Failed to apply ConfigMap: {result.stderr}")
            return False
        
        logger.info(result.stdout.strip())
        logger.info("ConfigMap updated successfully")
        return True
    finally:
        Path(temp_file).unlink(missing_ok=True)


def restart_wazuh_manager(
    namespace: str,
    dry_run: bool,
    logger: logging.Logger
) -> bool:
    """
    Restart the Wazuh manager StatefulSet.
    
    Args:
        namespace: Kubernetes namespace
        dry_run: Whether to perform dry-run only
        logger: Logger instance
    
    Returns:
        True if successful or dry-run, False otherwise
    """
    if dry_run:
        logger.info("[DRY-RUN] Would restart Wazuh manager StatefulSet")
        return True
    
    logger.info("Restarting Wazuh manager...")
    
    result = run_kubectl(
        ["rollout", "restart", "statefulset/wazuh-manager-master", "-n", namespace],
        logger,
        check=False
    )
    
    if result.returncode != 0:
        logger.error(f"Failed to restart Wazuh manager: {result.stderr}")
        return False
    
    logger.info(result.stdout.strip())
    logger.info("Wazuh manager restart initiated")
    return True


def rollback(
    backup_file: Path,
    namespace: str,
    logger: logging.Logger
) -> bool:
    """
    Rollback to a previous ConfigMap backup.
    
    Args:
        backup_file: Path to backup file
        namespace: Kubernetes namespace
        logger: Logger instance
    
    Returns:
        True if successful, False otherwise
    
    Raises:
        RollbackError: If rollback fails
    """
    logger.info(f"Rolling back from backup: {backup_file}")
    
    if not backup_file.exists():
        raise RollbackError(f"Backup file not found: {backup_file}")
    
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            configmap = json.load(f)
    except json.JSONDecodeError as e:
        raise RollbackError(f"Failed to parse backup file: {e}")
    
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False,
        encoding='utf-8'
    ) as f:
        json.dump(configmap, f, ensure_ascii=False)
        temp_file = f.name
    
    try:
        result = run_kubectl(
            ["apply", "-f", temp_file, "-n", namespace],
            logger,
            check=False
        )
        
        if result.returncode != 0:
            raise RollbackError(f"kubectl apply failed: {result.stderr}")
        
        logger.info("Rollback completed successfully")
        return True
    finally:
        Path(temp_file).unlink(missing_ok=True)


def list_backups(logger: logging.Logger) -> List[Path]:
    """
    List available backup files.
    
    Args:
        logger: Logger instance
    
    Returns:
        List of backup file paths
    """
    if not BACKUP_DIR.exists():
        return []
    
    backups = sorted(BACKUP_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Patch Wazuh ConfigMap with Shuffle SOAR integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                           # Apply with defaults
    %(prog)s --dry-run                 # Preview changes
    %(prog)s --validate-only           # Validate current ConfigMap
    %(prog)s --rollback                # Rollback to latest backup
    %(prog)s --rollback BACKUP_FILE    # Rollback to specific backup
    %(prog)s --list-backups            # Show available backups
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate current configuration"
    )
    parser.add_argument(
        "--rollback",
        nargs="?",
        const="latest",
        metavar="BACKUP_FILE",
        help="Rollback to backup (latest or specific file)"
    )
    parser.add_argument(
        "--list-backups",
        action="store_true",
        help="List available backups"
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Don't restart Wazuh manager after patching"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = setup_logging(log_level)
    
    # List backups mode
    if args.list_backups:
        backups = list_backups(logger)
        if backups:
            print("Available backups:")
            for i, backup in enumerate(backups, 1):
                size = backup.stat().st_size
                mtime = datetime.fromtimestamp(backup.stat().st_mtime)
                print(f"  {i}. {backup.name} ({size} bytes, {mtime})")
        else:
            print("No backups found")
        return 0
    
    # Rollback mode
    if args.rollback:
        namespace = os.getenv("WAZUH_NAMESPACE", DEFAULT_NAMESPACE)
        
        if args.rollback == "latest":
            backups = list_backups(logger)
            if not backups:
                logger.error("No backups available for rollback")
                return 5
            backup_file = backups[0]
        else:
            backup_file = Path(args.rollback)
        
        try:
            if rollback(backup_file, namespace, logger):
                if not args.no_restart:
                    restart_wazuh_manager(namespace, False, logger)
                return 0
            else:
                return 5
        except RollbackError as e:
            logger.error(f"Rollback failed: {e}")
            return 5
    
    # Get configuration from environment
    namespace = os.getenv("WAZUH_NAMESPACE", DEFAULT_NAMESPACE)
    labels = os.getenv("WAZUH_CONFIGMAP_LABELS", DEFAULT_CONFIGMAP_LABELS)
    configmap_name = os.getenv("WAZUH_CONFIGMAP_NAME")
    webhook_url = os.getenv("SHUFFLE_WEBHOOK_URL", DEFAULT_SHUFFLE_WEBHOOK)
    alert_level = os.getenv("SHUFFLE_ALERT_LEVEL", DEFAULT_ALERT_LEVEL)
    dry_run = os.getenv("DRY_RUN", "").lower() == "true" or args.dry_run
    
    logger.info("Starting Wazuh ConfigMap patcher")
    logger.debug(f"Namespace: {namespace}")
    logger.debug(f"Labels: {labels}")
    logger.debug(f"ConfigMap name: {configmap_name or '(auto-detect)'}")
    logger.debug(f"Alert level: {alert_level}")
    logger.debug(f"Dry run: {dry_run}")
    
    try:
        # Find ConfigMap
        configmap_name = find_configmap(namespace, labels, configmap_name, logger)
        
        # Get current ConfigMap
        configmap = get_configmap(configmap_name, namespace, logger)
        
        # Create backup (unless dry-run)
        if not dry_run and not args.validate_only:
            backup_file = create_backup(configmap, logger)
        
        # Get current master.conf
        master_conf = configmap["data"]["master.conf"]
        
        # Validate-only mode
        if args.validate_only:
            if validate_config(master_conf, logger):
                logger.info("Current configuration is valid")
                return 0
            else:
                logger.error("Current configuration has issues")
                return 4
        
        # Build integration block
        integration_block = build_integration_block(webhook_url, alert_level, logger)
        
        # Patch master.conf
        new_conf = patch_master_conf(master_conf, integration_block, logger)
        
        # Validate patched config
        if not validate_config(new_conf, logger):
            logger.error("Validation failed, aborting")
            return 4
        
        # Update ConfigMap
        configmap["data"]["master.conf"] = new_conf
        
        # Apply ConfigMap
        if not apply_configmap(configmap, namespace, dry_run, logger):
            return 1
        
        # Restart Wazuh manager (unless disabled or dry-run)
        if not args.no_restart:
            restart_wazuh_manager(namespace, dry_run, logger)
        
        logger.info("Patch completed successfully")
        return 0
    
    except ConfigMapNotFoundError as e:
        logger.error(f"ConfigMap not found: {e}")
        return 3
    except InvalidConfigMapError as e:
        logger.error(f"Invalid ConfigMap: {e}")
        return 4
    except KubectlError as e:
        logger.error(f"kubectl error: {e}")
        return 2
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
