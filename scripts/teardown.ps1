param()

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tmpDir = Join-Path (Join-Path $scriptRoot '..') '.tmp'

# Logging (PowerShell transcript)
$LogDir = Join-Path $scriptRoot '..\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("teardown-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))
Start-Transcript -Path $LogFile -Force
function Log([string]$msg) { $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); $line = "${ts} ${msg}"; Write-Host $line }

try {
    $releases = @{
        'ciso-assistant'   = 'grc'
        'zammad'           = 'managed-it'
        'wazuh'            = 'security-ops'
        'mcaas-shuffle'    = 'security-ops'
        'mcaas-opensearch' = 'security-ops'
        'mcaas-postgresql' = 'managed-it'
    }
    foreach ($release in $releases.Keys) {
        $namespace = $releases[$release]
        Log "Uninstalling Helm release '$release' from namespace '$namespace'..."
        # Run helm status and check the success variable ($?) to see if the release exists.
        # This avoids a terminating error when ErrorActionPreference is 'Stop'.
        helm status $release --namespace $namespace 2>$null | Out-Null -ErrorAction SilentlyContinue
        if ($?) {
            helm uninstall $release --namespace $namespace
        } else {
            Log "Release '$release' not found, skipping."
        }
    }
    
    Log "Cleaning up cloned repositories..."
    if (Test-Path -Path $tmpDir) { Remove-Item -Recurse -Force $tmpDir }
    
    Log "Deleting persistent volume claims..."
    kubectl delete pvc -n security-ops -l app.kubernetes.io/instance=mcaas-opensearch --ignore-not-found=true
    kubectl delete pvc -n security-ops -l app=wazuh-indexer --ignore-not-found=true
    kubectl delete pvc -n managed-it -l app.kubernetes.io/instance=mcaas-postgresql --ignore-not-found=true
    
    Log "Deleting namespaces..."
    # Using --ignore-not-found to prevent errors if they are already gone
    kubectl delete -k (Join-Path $scriptRoot '../deploy') --ignore-not-found=true
    
    Log 'Teardown complete.'
} finally {
    Stop-Transcript | Out-Null
    Write-Host "Logs written to $LogFile"
}
