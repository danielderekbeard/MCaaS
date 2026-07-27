#!/usr/bin/env powershell
<#
.SYNOPSIS
    MCaaS Teardown Script - PowerShell Version
    Removes all MCaaS deployments from the Kubernetes cluster.

.DESCRIPTION
    This script performs a complete teardown of the MCaaS infrastructure:
    - Uninstalls all Helm releases
    - Deletes Wazuh resources
    - Removes Persistent Volume Claims
    - Deletes Kubernetes secrets
    - Cleans up temporary files

.EXAMPLE
    .\teardown.ps1

.EXAMPLE
    .\teardown.ps1 -SkipConfirmation
#>

param(
    [switch]$SkipConfirmation
)

$ErrorActionPreference = "Stop"

# Setup logging
$LogDir = "$PSScriptRoot\..\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = "$LogDir\teardown-$(Get-Date -Format 'yyyyMMdd-HHmmss')Z.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ'
    $LogEntry = "[$Timestamp] $Message"
    Write-Host $LogEntry
    Add-Content -Path $LogFile -Value $LogEntry
}

# Initialize log
Write-Log "Starting MCaaS teardown..."
Write-Log "Log file: $LogFile"

# Confirmation prompt
if (-not $SkipConfirmation) {
    Write-Host "`n⚠️  WARNING: This will delete ALL MCaaS resources!" -ForegroundColor Red
    Write-Host "The following will be removed:"
    Write-Host "  - Helm releases: mcaas-ciso, mcaas-zammad, mcaas-shuffle, mcaas-opensearch, mcaas-postgresql"
    Write-Host "  - Wazuh resources and namespace"
    Write-Host "  - All Persistent Volume Claims"
    Write-Host "  - Kubernetes secrets"
    Write-Host "  - Temporary files`n"
    
    $Confirm = Read-Host "Type 'DELETE' to confirm teardown"
    if ($Confirm -ne "DELETE") {
        Write-Log "Teardown cancelled by user"
        exit 0
    }
}

# Track success/failure
$Failed = $false

# --- Uninstall Helm Releases ---
$Releases = @{
    "mcaas-ciso" = "grc"
    "mcaas-zammad" = "managed-it"
    "mcaas-shuffle" = "security-ops"
    "mcaas-opensearch" = "security-ops"
    "mcaas-postgresql" = "managed-it"
}

Write-Log "Uninstalling Helm releases..."
foreach ($Release in $Releases.GetEnumerator()) {
    $ReleaseName = $Release.Key
    $Namespace = $Release.Value
    
    try {
        $Status = helm status $ReleaseName --namespace $Namespace 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Uninstalling Helm release '$ReleaseName' from namespace '$Namespace'..."
            helm uninstall $ReleaseName --namespace $Namespace 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
            Write-Log "  ✓ Uninstalled $ReleaseName"
        } else {
            Write-Log "  - Helm release '$ReleaseName' not found, skipping"
        }
    } catch {
        Write-Log "  ! Warning: Could not uninstall $ReleaseName : $_"
        $Failed = $true
    }
}

# --- Delete Manifest-Based Deployments (Wazuh) ---
Write-Log "Deleting Wazuh resources..."
try {
    $TmpDir = "$PSScriptRoot\..\.tmp"
    $WazuhEnv = "$TmpDir\wazuh-kubernetes\envs\local-env"
    
    if (Test-Path $WazuhEnv) {
        Write-Log "  Deleting Wazuh kustomization..."
        kubectl delete -k $WazuhEnv --ignore-not-found=true 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
    }
    
    Write-Log "  Deleting Wazuh namespace..."
    kubectl delete namespace wazuh --ignore-not-found=true 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
    Write-Log "  ✓ Wazuh resources deleted"
} catch {
    Write-Log "  ! Warning: Error deleting Wazuh: $_"
    $Failed = $true
}

# --- Delete Persistent Volume Claims ---
Write-Log "Deleting persistent volume claims..."
try {
    kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-zammad --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-shuffle --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete pvc -n wazuh -l app=wazuh-indexer --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete pvc -n wazuh -l app=wazuh-manager --ignore-not-found=true 2>&1 | Out-Null
    Write-Log "  ✓ PVCs deleted"
} catch {
    Write-Log "  ! Warning: Error deleting PVCs: $_"
}

# --- Delete Kubernetes Secrets ---
Write-Log "Deleting Kubernetes secrets..."
try {
    kubectl delete secret mcaas-postgresql-secret --namespace managed-it --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete secret mcaas-opensearch-secret --namespace security-ops --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete secret mcaas-postgresql-secret --namespace grc --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete secret mcaas-zammad-redis-pass --namespace managed-it --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete secret mcaas-ciso-secret --namespace grc --ignore-not-found=true 2>&1 | Out-Null
    Write-Log "  ✓ Secrets deleted"
} catch {
    Write-Log "  ! Warning: Error deleting secrets: $_"
}

# --- Delete Namespaces ---
Write-Log "Deleting namespaces..."
try {
    kubectl delete namespace security-ops --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete namespace managed-it --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete namespace grc --ignore-not-found=true 2>&1 | Out-Null
    kubectl delete namespace wazuh --ignore-not-found=true 2>&1 | Out-Null
    Write-Log "  ✓ Namespaces deleted"
} catch {
    Write-Log "  ! Warning: Error deleting namespaces: $_"
}

# --- Clean up temporary files ---
Write-Log "Cleaning up temporary files..."
try {
    $ProjectRoot = "$PSScriptRoot\.."
    $TmpWazuh = "$ProjectRoot\.tmp\wazuh-kubernetes"
    $TmpShuffle = "$ProjectRoot\.tmp\shuffle"
    $EnvFile = "$ProjectRoot\.env"
    
    if (Test-Path $TmpWazuh) {
        Remove-Item -Recurse -Force $TmpWazuh -ErrorAction SilentlyContinue
        Write-Log "  ✓ Removed $TmpWazuh"
    }
    if (Test-Path $TmpShuffle) {
        Remove-Item -Recurse -Force $TmpShuffle -ErrorAction SilentlyContinue
        Write-Log "  ✓ Removed $TmpShuffle"
    }
    if (Test-Path $EnvFile) {
        Remove-Item -Force $EnvFile -ErrorAction SilentlyContinue
        Write-Log "  ✓ Removed $EnvFile"
    }
} catch {
    Write-Log "  ! Warning: Error cleaning up files: $_"
}

Write-Log "Teardown complete."
Write-Log "Logs written to: $LogFile"

if ($Failed) {
    Write-Host "`n⚠️  Teardown completed with warnings. Check log file for details." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "`n✅ Teardown completed successfully!" -ForegroundColor Green
    exit 0
}
