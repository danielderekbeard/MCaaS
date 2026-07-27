<#
.SYNOPSIS
    MCaaS Deployment Script for Windows

.DESCRIPTION
    This script orchestrates the deployment of the MCaaS stack on Windows.
    It validates prerequisites, loads environment variables, and delegates
    to the Python deployment orchestrator for cross-platform consistency.

.EXAMPLE
    .\deploy.ps1
#>

param()

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
$envFile = Join-Path $projectRoot '.env'
$deployer = Join-Path $projectRoot 'scripts\deploy.py'
$logDir = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDir ("deploy-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))

# Ensure logs directory exists
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

# Logging function
function Log-Message {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [string]$Level = 'INFO'
    )
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $logEntry = "[$timestamp] $Level: $Message"
    Write-Host $logEntry
    Add-Content -Path $logFile -Value $logEntry
}

# Error handler
function Handle-Error {
    param(
        [string]$Message = "An error occurred"
    )
    Log-Message "❌ $Message" -Level 'ERROR'
    Log-Message "For more details, check logs at: $logFile" -Level 'ERROR'
    exit 1
}

# Prerequisite checker
function Test-Prerequisites {
    Log-Message "Checking prerequisites..."
    
    $missingTools = @()
    
    # Check Python 3
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $python) {
        $missingTools += "python"
    }
    else {
        Log-Message "✅ Python: $($python.Version)"
    }
    
    # Check kubectl
    $kubectl = Get-Command kubectl -ErrorAction SilentlyContinue
    if (-not $kubectl) {
        $missingTools += "kubectl"
    }
    else {
        Log-Message "✅ kubectl: Found"
    }
    
    # Check helm
    $helm = Get-Command helm -ErrorAction SilentlyContinue
    if (-not $helm) {
        $missingTools += "helm"
    }
    else {
        Log-Message "✅ helm: Found"
    }
    
    # Check git
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        $missingTools += "git"
    }
    else {
        Log-Message "✅ git: Found"
    }
    
    # Check openssl (required for Wazuh TLS cert generation)
    $openssl = Get-Command openssl -ErrorAction SilentlyContinue
    if (-not $openssl) {
        $missingTools += "openssl"
    }
    else {
        Log-Message "✅ openssl: Found"
    }
    
    if ($missingTools.Count -gt 0) {
        Handle-Error "Missing required tools: $($missingTools -join ', ')"
    }
    
    Log-Message "✅ All prerequisites present"
}

# Load environment variables from .env file
function Load-EnvironmentFile {
    if (Test-Path $envFile) {
        Log-Message "Loading environment from .env file"
        Get-Content $envFile | ForEach-Object {
            if ($_ -and -not $_.StartsWith('#')) {
                $parts = $_ -split '=', 2
                if ($parts.Count -eq 2) {
                    $key = $parts[0].Trim()
                    $value = $parts[1].Trim()
                    [Environment]::SetEnvironmentVariable($key, $value, [EnvironmentVariableTarget]::Process)
                    Log-Message "Loaded env: $key"
                }
            }
        }
    }
    else {
        Log-Message "⚠️  No .env file found. Using existing environment variables."
        Log-Message "Create a .env file or set environment variables manually."
    }
}

# Set up kubeconfig
function Initialize-KubeEnvironment {
    Log-Message "Initializing Kubernetes environment..."
    
    $kubeConfigPath = Join-Path $HOME '.kube\config'
    if (Test-Path $kubeConfigPath) {
        $env:KUBECONFIG = $kubeConfigPath
        Log-Message "✅ KUBECONFIG set to $kubeConfigPath"
    }
    
    # Try to use a sensible default context if available
    $contexts = kubectl config get-contexts -o name --kubeconfig $kubeConfigPath 2>$null | Where-Object { $_ }
    
    if ($contexts) {
        foreach ($contextName in @('rancher-desktop', 'docker-desktop', 'mcaas-context')) {
            if ($contexts -contains $contextName) {
                Log-Message "Setting Kubernetes context to: $contextName"
                kubectl config use-context $contextName --kubeconfig $kubeConfigPath | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Log-Message "✅ Kubernetes context configured"
                    return
                }
            }
        }
    }
    
    Log-Message "⚠️  Could not auto-detect Kubernetes context"
    Log-Message "Verify your kubeconfig is configured correctly before deployment"
}

try {
    Log-Message "========================================" 
    Log-Message "MCaaS Deployment for Windows"
    Log-Message "========================================" 
    Log-Message "Starting deployment..."
    
    Test-Prerequisites
    Load-EnvironmentFile
    Initialize-KubeEnvironment
    
    Log-Message "Invoking Python deployment orchestrator..."
    Log-Message "Command: python $deployer"
    
    # Call the Python deployment script
    python $deployer
    
    if ($LASTEXITCODE -ne 0) {
        Handle-Error "Python deployment script exited with code $LASTEXITCODE"
    }
    
    Log-Message "========================================" 
    Log-Message "✅ Deployment completed successfully!"
    Log-Message "========================================" 
    Log-Message "Logs written to: $logFile"
}
catch {
    Handle-Error $_.Exception.Message
}
