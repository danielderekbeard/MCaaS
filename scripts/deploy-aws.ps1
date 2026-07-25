<#
.SYNOPSIS
    MCaaS AWS/EKS Deployment Wrapper Script for Windows

.DESCRIPTION
    This script validates AWS-specific prerequisites, loads environment
    variables, and delegates to the Python deployment orchestrator for
    full Infrastructure-as-Code deployment on AWS EKS.

.EXAMPLE
    .\deploy-aws.ps1
    .\deploy-aws.ps1 -DryRun
    .\deploy-aws.ps1 -Client aws
    .\deploy-aws.ps1 -SkipCluster
    .\deploy-aws.ps1 -SkipInfrastructure
    .\deploy-aws.ps1 -TearDown

.NOTES
    Requires: aws, eksctl, kubectl, helm, git, openssl, python
#>

param(
    [switch]$DryRun,
    [switch]$SkipCluster,
    [switch]$SkipInfrastructure,
    [switch]$TearDown,
    [string]$Client = '',
    [string]$ClusterName = '',
    [string]$Region = ''
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
$deployer = Join-Path $projectRoot 'deploy-aws.py'
$logDir = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDir ("deploy-aws-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))

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

# ── Prerequisite Checks ──────────────────────────────────────────────────────

function Test-Prerequisites {
    Log-Message "Checking AWS deployment prerequisites..."
    
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
        Log-Message "✅ Python: Found"
    }
    
    # Check AWS CLI
    $aws = Get-Command aws -ErrorAction SilentlyContinue
    if (-not $aws) {
        $missingTools += "aws"
    }
    else {
        $awsVersion = (aws --version 2>&1) | Out-String
        Log-Message "✅ aws: $awsVersion"
    }
    
    # Check eksctl
    $eksctl = Get-Command eksctl -ErrorAction SilentlyContinue
    if (-not $eksctl) {
        $missingTools += "eksctl"
    }
    else {
        Log-Message "✅ eksctl: Found"
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
    
    # Check openssl
    $openssl = Get-Command openssl -ErrorAction SilentlyContinue
    if (-not $openssl) {
        # Try Git bundled OpenSSL on Windows
        $gitBin = Join-Path (Split-Path -Parent (Get-Command git).Source) "usr" "bin" "openssl.exe"
        if (Test-Path $gitBin) {
            $env:PATH = "$((Split-Path -Parent (Get-Command git).Source))\usr\bin;$env:PATH"
            Log-Message "✅ openssl: Found via Git bundle"
        }
        else {
            $missingTools += "openssl"
        }
    }
    else {
        Log-Message "✅ openssl: Found"
    }
    
    if ($missingTools.Count -gt 0) {
        Handle-Error "Missing required tools: $($missingTools -join ', '). Install them before proceeding.`n  aws: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html`n  eksctl: https://eksctl.io/`n  kubectl: https://kubernetes.io/docs/tasks/tools/`n  helm: https://helm.sh/docs/intro/install/"
    }
    
    Log-Message "✅ All prerequisites present"
}

# ── AWS Credentials Check ────────────────────────────────────────────────────

function Test-AWSCredentials {
    Log-Message "Checking AWS credentials..."
    
    try {
        $identity = aws sts get-caller-identity --query 'Arn' --output text 2>&1
        if ($LASTEXITCODE -eq 0) {
            Log-Message "✅ AWS credentials configured: $identity"
        }
        else {
            Handle-Error "AWS credentials not configured. Run 'aws configure' or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY environment variables."
        }
    }
    catch {
        Handle-Error "AWS credentials not configured. Run 'aws configure' or set environment variables."
    }
}

# ── Load Environment ─────────────────────────────────────────────────────────

function Load-EnvironmentFile {
    $envFile = Join-Path $projectRoot '.env'
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

# ── Build Arguments ──────────────────────────────────────────────────────────

function Build-Arguments {
    $args = @()
    
    if ($DryRun) { $args += "--dry-run" }
    if ($SkipCluster) { $args += "--skip-cluster" }
    if ($SkipInfrastructure) { $args += "--skip-infrastructure" }
    if ($TearDown) { $args += "--tear-down" }
    if ($Client) { $args += "--client"; $args += $Client }
    if ($ClusterName) { $args += "--cluster-name"; $args += $ClusterName }
    if ($Region) { $args += "--region"; $args += $Region }
    
    return $args
}

# ── Main ─────────────────────────────────────────────────────────────────────

try {
    Log-Message "========================================"
    Log-Message "MCaaS AWS/EKS Deployment (Windows)"
    Log-Message "========================================"
    Log-Message "Starting deployment..."
    
    Test-Prerequisites
    Test-AWSCredentials
    Load-EnvironmentFile
    
    $arguments = Build-Arguments
    $argString = $arguments -join ' '
    
    Log-Message "Invoking Python deployment orchestrator..."
    Log-Message "Command: python $deployer $argString"
    
    # Call the Python deployment script
    python $deployer @arguments
    
    if ($LASTEXITCODE -ne 0) {
        Handle-Error "Python deployment script exited with code $LASTEXITCODE"
    }
    
    Log-Message "========================================"
    Log-Message "✅ AWS deployment completed successfully!"
    Log-Message "========================================"
    Log-Message "Logs written to: $logFile"
}
catch {
    Handle-Error $_.Exception.Message
}