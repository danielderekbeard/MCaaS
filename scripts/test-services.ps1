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

    if (-not $env:KUBECONFIG) {
        $env:KUBECONFIG = Join-Path $HOME '.kube\config'
    }
}

Set-KubeEnv
Set-KubeContextIfAvailable

# Logging (PowerShell transcript)
$LogDir = Join-Path $scriptRoot '..\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("test-services-{0}.log" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssZ"))
Start-Transcript -Path $LogFile -Force
function Log([string]$msg) { $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"); $line = "${ts} ${msg}"; Write-Host $line }

try {
    # For older PowerShell versions (like 5.1), -SkipCertificateCheck is not available.
    # This line globally bypasses certificate validation for the script's execution.
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

    Log "Starting service health checks..."

    $services = @(
        @{ Name = "Wazuh Dashboard";         Namespace = "security-ops"; ServiceName = "wazuh-dashboard";         ServicePort = 443; LocalPort = 8443; Protocol = "https" },
        @{ Name = "Shuffle UI";              Namespace = "security-ops"; ServiceName = "mcaas-shuffle";             ServicePort = 5001; LocalPort = 8081; Protocol = "http" },
        @{ Name = "Zammad Web";              Namespace = "managed-it";   ServiceName = "zammad-zammad-web";         ServicePort = 80;   LocalPort = 8082; Protocol = "http" },
        @{ Name = "CISO Assistant Frontend"; Namespace = "grc";          ServiceName = "ciso-assistant-frontend"; ServicePort = 80;   LocalPort = 8083; Protocol = "http" }
    )

    $allOk = $true

    foreach ($service in $services) {
        Log "Testing '$($service.Name)' (service/$($service.ServiceName) in $($service.Namespace))..."
        
        # Start port-forward as a background job
        $pfJob = Start-Job -ScriptBlock {
            param($ns, $svc, $ports)
            kubectl port-forward -n $ns "service/$svc" $ports
        } -ArgumentList $service.Namespace, $service.ServiceName, "$($service.LocalPort):$($service.ServicePort)"

        try {
            # Give it a moment to establish the connection
            Start-Sleep -Seconds 3

            $uri = "$($service.Protocol)://localhost:$($service.LocalPort)"
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction SilentlyContinue
            
            # StatusCode is 200 for success, 302 for redirects (also a sign of life)
            if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 302) {
                Log "✅ '$($service.Name)' is UP. Received HTTP status $($response.StatusCode)."
            } else {
                Log "❌ '$($service.Name)' is DOWN or not responding correctly. Received HTTP status $($response.StatusCode)."
                $allOk = $false
            }
        } catch {
            Log "❌ '$($service.Name)' failed with an exception: $($_.Exception.Message)"
            $allOk = $false
        } finally {
            # Stop the background port-forward job
            Stop-Job -Job $pfJob
            Remove-Job -Job $pfJob -Force
        }
    }

    if ($allOk) {
        Log "All services are up and running."
    } else {
        throw "One or more services failed the health check."
    }
} finally {
    # Reset the certificate validation callback to its default behavior
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null
    Stop-Transcript | Out-Null
    Write-Host "Logs written to $LogFile"
}