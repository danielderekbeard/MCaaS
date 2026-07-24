#!/usr/bin/env python3
"""
MCaaS Prerequisites Checker - Cross-platform

Verifies that all required tools are installed and configured for deployment.
Provides helpful guidance for missing tools.
"""

import shutil
import subprocess
import sys
import platform
from pathlib import Path


PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == "Windows"

def run_cmd(cmd, check=False):
    """Run a command and return output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout.strip(), result.returncode
    except FileNotFoundError:
        return None, 1


def check_tool(tool_name, cmd=None, windows_install=None, unix_install=None):
    """Check if a tool is installed and provide guidance if not."""
    if cmd is None:
        cmd = [tool_name, "--version"]
    
    output, code = run_cmd(cmd, check=False)
    
    if code == 0 and output:
        print(f"✅ {tool_name}: OK")
        print(f"   Version: {output.split(chr(10))[0]}")
        return True
    else:
        print(f"❌ {tool_name}: NOT FOUND")
        if IS_WINDOWS and windows_install:
            print(f"   Windows: {windows_install}")
        if unix_install:
            print(f"   macOS/Linux: {unix_install}")
        return False


def check_kubectl():
    """Check kubectl installation and cluster connectivity."""
    if not check_tool("kubectl", ["kubectl", "version", "--client"]):
        return False
    
    # Check cluster connectivity
    ctx_output, code = run_cmd(["kubectl", "config", "current-context"], check=False)
    if code == 0:
        print(f"   Current context: {ctx_output}")
        return True
    else:
        print("   ⚠️  No kubectl context configured. Configure your kubeconfig before deploying.")
        return True  # Still ok, they can fix this later


def check_helm():
    """Check Helm installation."""
    return check_tool(
        "helm",
        ["helm", "version"],
        windows_install="choco install helm OR download from https://github.com/helm/helm/releases",
        unix_install="brew install helm (macOS) OR download from https://github.com/helm/helm/releases"
    )


def check_git():
    """Check Git installation."""
    return check_tool(
        "git",
        ["git", "--version"],
        windows_install="choco install git OR download from https://git-scm.com/download/win",
        unix_install="brew install git (macOS) OR apt-get install git (Linux)"
    )


def check_docker_runtime():
    """Check for a Docker or Kubernetes runtime."""
    docker_available = shutil.which("docker") is not None
    
    runtimes = []
    
    # Check common Kubernetes distributions
    if shutil.which("kubectl") is not None:
        output, code = run_cmd(["kubectl", "config", "current-context"], check=False)
        if code == 0:
            ctx = output.strip()
            if "docker-desktop" in ctx.lower():
                runtimes.append("Docker Desktop (detected)")
            elif "rancher" in ctx.lower():
                runtimes.append("Rancher Desktop (detected)")
            elif "minikube" in ctx.lower():
                runtimes.append("Minikube (detected)")
            else:
                runtimes.append(f"Kubernetes cluster: {ctx}")
    
    if docker_available:
        output, code = run_cmd(["docker", "version", "--format={{.Server.Version}}"], check=False)
        if code == 0:
            runtimes.append(f"Docker: {output}")
    
    if runtimes:
        print(f"✅ Kubernetes Runtime: OK")
        for runtime in runtimes:
            print(f"   {runtime}")
        return True
    else:
        print(f"❌ Kubernetes Runtime: NOT FOUND")
        print("   Required: Docker Desktop, Rancher Desktop, Minikube, or remote Kubernetes cluster")
        print("   Windows: Download Docker Desktop from https://www.docker.com/products/docker-desktop")
        print("   OR Rancher Desktop from https://rancherdesktop.io/")
        return False


def check_powershell():
    """Check PowerShell version (Windows only)."""
    if not IS_WINDOWS:
        return True
    
    output, code = run_cmd(["powershell", "-Command", "$PSVersionTable.PSVersion"], check=False)
    if code == 0 and output:
        # Extract version
        lines = output.strip().split('\n')
        if lines:
            print(f"✅ PowerShell: OK")
            for line in lines[:3]:
                print(f"   {line}")
            return True
    
    print(f"❌ PowerShell: NOT FOUND or incompatible")
    print("   Windows: PowerShell 5.0 or higher is required")
    return False


def main():
    """Run all prerequisite checks."""
    print("=" * 60)
    print("MCaaS Prerequisites Checker")
    print(f"Platform: {PLATFORM}")
    print("=" * 60)
    print()
    
    checks = [
        ("kubectl", check_kubectl),
        ("helm", check_helm),
        ("git", check_git),
        ("Kubernetes Runtime", check_docker_runtime),
    ]
    
    if IS_WINDOWS:
        checks.append(("PowerShell", check_powershell))
    
    results = {}
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        results[name] = check_func()
    
    print("\n" + "=" * 60)
    
    all_ok = all(results.values())
    
    if all_ok:
        print("✅ All prerequisites are met!")
        print("\nNext steps:")
        print("1. Configure your kubeconfig if you haven't already")
        print("2. Run: python deploy.py")
        print("   (or on Windows: python deploy.py)")
        return 0
    else:
        print("❌ Some prerequisites are missing.")
        print("\nPlease install the missing tools and try again.")
        print("\nFor deployment on Windows, you have two options:")
        print("1. Install the missing tools above and run: python deploy.py")
        print("2. Use Windows Subsystem for Linux (WSL):")
        print("   - Install WSL2: wsl --install")
        print("   - Install tools in WSL: apt-get install kubectl helm git")
        print("   - Run deployment from WSL terminal")
        return 1


if __name__ == "__main__":
    sys.exit(main())
