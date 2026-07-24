param()

$ErrorActionPreference = 'Stop'

# Helper to generate a random password
function New-RandomPassword {
    param([int]$length = 24)
    $charSet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*'
    -join ((0..($length - 1)) | ForEach-Object { $charSet[(Get-Random -Maximum $charSet.Length)] })
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $scriptRoot '..\.env'

# Load environment variables from .env file if it exists
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        # Skip comments and empty lines
        if ($_ -and -not $_.StartsWith('#')) {
            $parts = $_ -split '=', 2
            if ($parts.Count -ge 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()
                Set-Item -Path Env:$key -Value $value
            }
        }
    }
}

# Logging (PowerShell transcript)
$LogDir = Join-Path $scriptRoot '..\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("init-secrets-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))
Start-Transcript -Path $LogFile -Force
function Log([string]$msg) { $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); $line = "${ts} ${msg}"; Write-Host $line }

try {
    Log "Checking for required secrets..."
    if (-not ($env:MCAAS_POSTGRES_PASSWORD -and $env:MCAAS_OPENSEARCH_PASSWORD)) {
        Log "Secrets not found in environment. Checking for .env file..."
        if (-not (Test-Path $envFile)) {
            Log "No .env file found. Generating new secrets and creating .env file..."
            $env:MCAAS_POSTGRES_PASSWORD = New-RandomPassword
            $env:MCAAS_OPENSEARCH_PASSWORD = New-RandomPassword
            Set-Content -Path $envFile -Value "MCAAS_POSTGRES_PASSWORD=$($env:MCAAS_POSTGRES_PASSWORD)`nMCAAS_OPENSEARCH_PASSWORD=$($env:MCAAS_OPENSEARCH_PASSWORD)"
            Log "Successfully created .env with generated passwords. Please back this file up if you need to redeploy."
        } else {
            Log "ERROR: .env file exists but secrets are not loaded correctly or are missing."
            Log "Please check your .env file or shell environment."
            throw "Missing required environment variables for secrets."
        }
    }

    Log "Applying namespaces..."
    kubectl apply -k (Join-Path $scriptRoot '../deploy')

    Log "Creating/updating PostgreSQL secret..."
    kubectl -n managed-it create secret generic mcaas-postgresql-secret `
      --from-literal=postgres-password="$env:MCAAS_POSTGRES_PASSWORD" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log "Creating/updating OpenSearch secret..."
    kubectl -n security-ops create secret generic mcaas-opensearch-secret `
      --from-literal=opensearch-password="$env:MCAAS_OPENSEARCH_PASSWORD" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log 'Secrets and namespaces are ready.'
} finally {
    Stop-Transcript | Out-Null
    Write-Host "Logs written to $LogFile"
}
