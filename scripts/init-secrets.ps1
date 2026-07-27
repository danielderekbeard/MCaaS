param()

$ErrorActionPreference = 'Stop'

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

    if (-not $env:KUBECONFIG) {
        $env:KUBECONFIG = Join-Path $HOME '.kube\config'
    }
}

Set-KubeEnv
Set-KubeContextIfAvailable

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
            $env:MCAAS_REDIS_PASSWORD = New-RandomPassword
            $env:MCAAS_DJANGO_SECRET_KEY = New-RandomPassword -length 50
            # Write UTF-8 WITHOUT a BOM. Set-Content defaults to ANSI in PS 5.1
            # and its -Encoding utf8 still emits a BOM, which corrupts the first
            # key when scripts/deploy.py reads the file.
            $envBody = "MCAAS_POSTGRES_PASSWORD=$($env:MCAAS_POSTGRES_PASSWORD)`nMCAAS_OPENSEARCH_PASSWORD=$($env:MCAAS_OPENSEARCH_PASSWORD)`nMCAAS_REDIS_PASSWORD=$($env:MCAAS_REDIS_PASSWORD)`nMCAAS_DJANGO_SECRET_KEY=$($env:MCAAS_DJANGO_SECRET_KEY)`n"
            [System.IO.File]::WriteAllText($envFile, $envBody, (New-Object System.Text.UTF8Encoding($false)))
            Log "Successfully created .env with generated passwords. Please back this file up if you need to redeploy."
        } else {
            Log "ERROR: .env file exists but secrets are not loaded correctly or are missing."
            Log "Please check your .env file or shell environment."
            throw "Missing required environment variables for secrets."
        }
    }

    # Set defaults for optional secrets if not provided
    if (-not $env:MCAAS_REDIS_PASSWORD) {
        $env:MCAAS_REDIS_PASSWORD = 'zammad'
        Log "Using default Redis password"
    }
    if (-not $env:MCAAS_DJANGO_SECRET_KEY) {
        $env:MCAAS_DJANGO_SECRET_KEY = New-RandomPassword -length 50
        Log "Generated Django secret key"
        # Persist to .env so redeployments reuse the same key.
        # Append as BOM-less UTF-8, matching how the file is created above.
        [System.IO.File]::AppendAllText($envFile, "MCAAS_DJANGO_SECRET_KEY=$($env:MCAAS_DJANGO_SECRET_KEY)`n", (New-Object System.Text.UTF8Encoding($false)))
    }

    Log "Applying namespaces..."
    kubectl apply -k (Join-Path $scriptRoot '../deploy')

    Log "Creating/updating PostgreSQL secret in managed-it..."
    kubectl -n managed-it create secret generic mcaas-postgresql-secret `
      --from-literal=postgres-password="$env:MCAAS_POSTGRES_PASSWORD" `
      --from-literal=password="$env:MCAAS_POSTGRES_PASSWORD" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log "Creating/updating OpenSearch secret..."
    kubectl -n security-ops create secret generic mcaas-opensearch-secret `
      --from-literal=opensearch-password="$env:MCAAS_OPENSEARCH_PASSWORD" `
      --from-literal=SHUFFLE_OPENSEARCH_PASSWORD="$env:MCAAS_OPENSEARCH_PASSWORD" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log "Creating/updating PostgreSQL secret in grc..."
    kubectl -n grc create secret generic mcaas-postgresql-secret `
      --from-literal=postgres-password="$env:MCAAS_POSTGRES_PASSWORD" `
      --from-literal=password="$env:MCAAS_POSTGRES_PASSWORD" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log "Creating/updating Redis secret..."
    kubectl -n managed-it create secret generic mcaas-zammad-redis-pass `
      --from-literal=redis-password="$env:MCAAS_REDIS_PASSWORD" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log "Creating/updating CISO Assistant Django secret..."
    kubectl -n grc create secret generic mcaas-ciso-secret `
      --from-literal=django-secret-key="$env:MCAAS_DJANGO_SECRET_KEY" `
      --dry-run=client -o yaml | kubectl apply -f -

    Log 'Secrets and namespaces are ready.'
} finally {
    Stop-Transcript | Out-Null
    Write-Host "Logs written to $LogFile"
}
