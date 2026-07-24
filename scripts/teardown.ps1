param()

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Set-KubeContextIfAvailable {
    $kubeConfigPath = Join-Path $HOME '.kube\config'
    if (-not (Test-Path $kubeConfigPath)) {
        return
    }

    $contexts = kubectl config get-contexts -o name --kubeconfig $kubeConfigPath 2>$null
    if ($LASTEXITCODE -ne 0) {
        return
    }

    foreach ($contextName in @('rancher-desktop', 'docker-desktop', 'mcaas-context')) {
        if ($contexts -contains $contextName) {
            kubectl config use-context $contextName --kubeconfig $kubeConfigPath | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return
            }
        }
    }
}

function Set-KubeEnv {
    $kubeConfigPath = Join-Path $HOME '.kube\config'
    if (Test-Path $kubeConfigPath) {
        $env:KUBECONFIG = $kubeConfigPath
    }

    if ($env:KUBECONFIG) {
        $env:KUBECONFIG = $env:KUBECONFIG
    }

    if (-not $env:KUBECONFIG) {
        $env:KUBECONFIG = Join-Path $HOME '.kube\config'
    }
}

Set-KubeEnv
Set-KubeContextIfAvailable

# Logging (PowerShell transcript)
$LogDir = Join-Path $scriptRoot '..\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("teardown-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))
Start-Transcript -Path $LogFile -Force
function Log([string]$msg) { $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); $line = "${ts} ${msg}"; Write-Host $line }

try {
    Log "Starting MCaaS teardown..."

    # --- Uninstall Helm Releases ---
    $releases = @{
        "ciso-assistant"   = "grc"
        "zammad"           = "managed-it"
        "mcaas-wazuh"      = "security-ops"
        "mcaas-shuffle"    = "security-ops"
        "mcaas-opensearch" = "security-ops"
        "mcaas-postgresql" = "managed-it"
    }

    foreach ($release in $releases.GetEnumerator()) {
        $exists = $false
        try {
            helm status $release.Name --namespace $release.Value --output json | Out-Null
            $exists = $true
        } catch {
            $exists = $false
        }

        if ($exists) {
            Log "Uninstalling Helm release '$($release.Name)' from namespace '$($release.Value)'..."
            helm uninstall $release.Name --namespace $release.Value
        } else {
            Log "Helm release '$($release.Name)' not found, skipping."
        }
    }

    # --- Delete Manifest-Based Deployments (Wazuh) ---
    Log "Deleting Wazuh resources and namespace..."
    $wazuhEnv = Join-Path (Join-Path $scriptRoot '..') '.tmp\wazuh-kubernetes\envs\local-env'
    if (Test-Path $wazuhEnv) {
        kubectl delete -k $wazuhEnv --ignore-not-found=$true --insecure-skip-tls-verify=true 2>$null
    }
    kubectl delete namespace wazuh --ignore-not-found=$true --insecure-skip-tls-verify=true 2>$null

    # --- Delete Persistent Volume Claims ---
    Log "Deleting persistent volume claims..."
    kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=$true --insecure-skip-tls-verify=true 2>$null
    kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=$true --insecure-skip-tls-verify=true 2>$null

    # --- Delete Namespaces and other base resources ---
    Log "Deleting resources from kustomization (including namespaces)..."
    kubectl delete -k (Join-Path $scriptRoot '..\deploy') --ignore-not-found=$true --insecure-skip-tls-verify=true 2>$null

    Log "Teardown complete."
} finally {
    Stop-Transcript | Out-Null
    Write-Host "Logs written to $LogFile"
}
