# Explore Zammad and Shuffle API endpoints more carefully

Write-Host "=== Checking Zammad availability ==="
try {
    $result = Invoke-WebRequest -Uri "http://alala.mcaas.example.com/" -UseBasicParsing
    Write-Host "Zammad root status: $($result.StatusCode)"
    Write-Host "Content length: $($result.Content.Length)"
} catch {
    Write-Host "Zammad root error: $($_.Exception.Message)"
}

# Try Zammad API v1 endpoints
Write-Host "`n=== Trying Zammad API endpoints ==="
$zammadUrls = @(
    "http://alala.mcaas.example.com/api/v1/users",
    "http://alala.mcaas.example.com/api/v1/tickets",
    "http://alala.mcaas.example.com/api/v1/ticket_states",
    "http://alala.mcaas.example.com/api/v1/ticket_priorities"
)
foreach ($url in $zammadUrls) {
    try {
        $result = Invoke-RestMethod -Uri $url -Method Get -Headers @{ "Content-Type" = "application/json" }
        Write-Host "GET $url : Success"
        Write-Host ($result | ConvertTo-Json -Depth 1 | Select-Object -First 5)
    } catch {
        Write-Host "GET $url : $($_.Exception.Message)"
    }
}

# Try Zammad login via POST to sessions (different body format)
Write-Host "`n=== Trying Zammad authentication ==="
try {
    # Zammad expects form data or different JSON format
    $body = @{ "username" = "admin@mcaas.local"; "password" = "MCaaSadmin2026!" } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/sessions" -Method Post -Body $body -Headers @{ "Content-Type" = "application/json" } -SessionVariable session
    Write-Host "Zammad session: $($result | ConvertTo-Json -Depth 2)"
    
    # Try to get current user with session
    $userResult = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/users/me" -Method Get -WebSession $session
    Write-Host "Current user: $($userResult | ConvertTo-Json -Depth 2)"
} catch {
    Write-Host "Session auth error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $errBody = $reader.ReadToEnd()
        Write-Host "Error response: $errBody"
    } catch {}
}

# Try getting Zammad internal service directly
Write-Host "`n=== Trying Zammad internal K8s service ==="
try {
    $result = Invoke-RestMethod -Uri "http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080/api/v1/sessions" -Method Post -Body '{"username":"admin@mcaas.local","password":"MCaaSadmin2026!"}' -Headers @{ "Content-Type" = "application/json" } -SessionVariable session2
    Write-Host "Internal session: $($result | ConvertTo-Json -Depth 2)"
} catch {
    Write-Host "Internal session error: $($_.Exception.Message)"
}

# Check Shuffle OpenAPI for the correct credential/auth endpoints  
Write-Host "`n=== Exploring Shuffle API docs ==="
$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }

# Try different Shuffle API paths
$shuffleUrls = @(
    "http://kydoimos.mcaas.example.com/api/v1/workflows",
    "http://kydoimos.mcaas.example.com/api/v1/orgs/2dab79be-d87a-43dd-99ad-232a3d7161fc",
    "http://kydoimos.mcaas.example.com/api/v1/authentication",
    "http://kydoimos.mcaas.example.com/api/v1/apikey",
    "http://kydoimos.mcaas.example.com/api/v1/environment/2dab79be-d87a-43dd-99ad-232a3d7161fc",
    "http://kydoimos.mcaas.example.com/api/v1/actions"
)
foreach ($url in $shuffleUrls) {
    try {
        $result = Invoke-RestMethod -Uri $url -Method Get -Headers $headers
        Write-Host "GET $url : Success"
        $jsonResult = $result | ConvertTo-Json -Depth 1
        if ($jsonResult.Length -gt 200) {
            Write-Host ($jsonResult.Substring(0, 200) + "...")
        } else {
            Write-Host $jsonResult
        }
    } catch {
        Write-Host "GET $url : $($_.Exception.Message)"
    }
}

# Try getting the workflow with full details
Write-Host "`n=== Getting full workflow details ==="
try {
    $wf = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/8d264034-0040-48c6-86f2-aeb5294df90a" -Method Get -Headers $headers
    Write-Host "Workflow JSON:"
    $wfJson = $wf | ConvertTo-Json -Depth 10
    Write-Host $wfJson
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}