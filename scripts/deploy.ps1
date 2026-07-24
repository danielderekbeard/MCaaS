param()

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $scriptRoot '..\.env'
$tmpDir = Join-Path (Join-Path $scriptRoot '..') '.tmp' # Use a local temp dir for clones
if (Test-Path $envFile) { Get-Content $envFile | ForEach-Object {
    if ($_ -and -not $_.StartsWith('#')) {
        $parts = $_ -split '=', 2
        if ($parts.Count -ge 2) {
            $key = $parts[0].Trim()
            $value = $parts[1].Trim()
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}}

# Logging (PowerShell transcript)
$LogDir = Join-Path $scriptRoot '..\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("deploy-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))
Start-Transcript -Path $LogFile -Force
function Log([string]$msg) { $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); $line = "${ts} ${msg}"; Write-Host $line }

# Helper function to wait for a deployment to be ready
function Wait-ForDeployment([string]$namespace, [string]$deploymentName, [string]$timeout = "5m") {
    Log "Waiting for deployment '$deploymentName' in namespace '$namespace' to be ready..."
    kubectl wait --for=condition=available --namespace $namespace deployment/$deploymentName --timeout=$timeout
    Log "Deployment '$deploymentName' is ready."
}

try {
    Log "Adding and updating Helm repositories..."
    helm repo add bitnami https://charts.bitnami.com/bitnami | Out-Null
    helm repo add opensearch https://opensearch-project.github.io/helm-charts | Out-Null
    helm repo add zammad https://zammad.github.io/zammad-helm | Out-Null
    # Wazuh, Shuffle, and CISO-Assistant do not use traditional Helm repos.
    helm repo update | Out-Null
    
    Log "Applying namespaces and base manifests..."
    kubectl apply -k (Join-Path $scriptRoot '../deploy')
    
    Log "Deploying PostgreSQL..."
    helm upgrade --install mcaas-postgresql bitnami/postgresql `
      --namespace managed-it `
      --values (Join-Path $scriptRoot '../deploy/values/postgresql.yaml') `
      --wait --timeout 5m
    
    Log "Deploying OpenSearch..."
    helm upgrade --install mcaas-opensearch opensearch/opensearch `
      --namespace security-ops `
      --values (Join-Path $scriptRoot '../deploy/values/opensearch.yaml') `
      --wait --timeout 5m
    
    Log "Cloning Wazuh and Shuffle repositories..."
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null    
    $wazuhDir = Join-Path $tmpDir 'wazuh-kubernetes'
    $shuffleDir = Join-Path $tmpDir 'shuffle'
    if (-not (Test-Path -Path $wazuhDir)) { git clone --depth 1 https://github.com/wazuh/wazuh-kubernetes.git $wazuhDir }
    if (-not (Test-Path -Path $shuffleDir)) { git clone --depth 1 https://github.com/shuffle/shuffle.git $shuffleDir }
    
    Log "Preparing Wazuh manifests for Windows..."
    # The wazuh-kubernetes repo uses symlinks which don't work well on Windows.
    # We must run their provided script to generate the certs and configs.
    Push-Location -Path $wazuhDir
    try {
        # This script generates certificates and config files, replacing the broken symlinks.
        & ./generate-local-env.ps1
    } finally {
        Pop-Location
    }

    Log "Deploying Wazuh from manifests..."
    kubectl apply -k (Join-Path $wazuhDir 'envs/local-env')
    
    Log "Deploying Shuffle..."
    helm upgrade --install mcaas-shuffle (Join-Path $shuffleDir 'deploy\helm\shuffle') `
      --namespace security-ops `
      --values (Join-Path $scriptRoot '../deploy/values/shuffle.yaml') `
      --wait --timeout 5m
    Wait-ForDeployment "security-ops" "mcaas-shuffle"
    
    Log "Deploying Zammad..."
    helm upgrade --install zammad zammad/zammad `
      --namespace managed-it `
      --values (Join-Path $scriptRoot '../deploy/values/zammad.yaml') `
      --wait --timeout 5m
    Wait-ForDeployment "managed-it" "zammad-zammad-scheduler"
    Wait-ForDeployment "managed-it" "zammad-zammad-websocket"
    Wait-ForDeployment "managed-it" "zammad-zammad-web"
    
    Log "Deploying CISO Assistant..."
    helm upgrade --install ciso-assistant oci://ghcr.io/intuitem/ca-helm-chart/ciso-assistant `
      --version 0.1.0 `
      --namespace grc `
      --values (Join-Path $scriptRoot '../deploy/values/ciso-assistant.yaml') `
      --wait --timeout 5m
    Wait-ForDeployment "grc" "ciso-assistant-frontend"
    Wait-ForDeployment "grc" "ciso-assistant-backend"
    
    Log 'Deployment complete.'
} finally {
  Stop-Transcript | Out-Null
  Write-Host "Logs written to $LogFile"
}
