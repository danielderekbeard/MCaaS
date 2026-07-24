param()

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

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
        "mcaas-shuffle"    = "security-ops"
        "mcaas-opensearch" = "security-ops"
        "mcaas-postgresql" = "managed-it"
    }

    foreach ($release in $releases.GetEnumerator()) {
        # Check if the release exists before trying to uninstall
        $status = helm status $release.Name --namespace $release.Value --output json --ignore-not-found
        if ($status) {
            Log "Uninstalling Helm release '$($release.Name)' from namespace '$($release.Value)'..."
            helm uninstall $release.Name --namespace $release.Value
        } else {
            Log "Helm release '$($release.Name)' not found, skipping."
        }
    }

    # --- Delete Manifest-Based Deployments (Wazuh) ---
    Log "Deleting Wazuh resources from manifests..."
    if (-not (Test-Path "$env:TEMP\wazuh-kubernetes")) {
        git clone --depth 1 https://github.com/wazuh/wazuh-kubernetes.git "$env:TEMP\wazuh-kubernetes"
    }
    kubectl delete -k "$env:TEMP\wazuh-kubernetes\envs\local-env" --ignore-not-found=$true

    # --- Delete Persistent Volume Claims ---
    Log "Deleting persistent volume claims..."
    kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=$true
    kubectl delete pvc -n security-ops -l app=wazuh-indexer --ignore-not-found=$true
    kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=$true

    # --- Delete Namespaces and other base resources ---
    Log "Deleting resources from kustomization (including namespaces)..."
    kubectl delete -k (Join-Path $scriptRoot '..\deploy') --ignore-not-found=$true

    Log "Teardown complete."
} finally {
    Stop-Transcript | Out-Null
    Write-Host "Logs written to $LogFile"
}
