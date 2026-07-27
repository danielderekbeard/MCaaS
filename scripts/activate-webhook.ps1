# Activate Shuffle webhook via API key authentication
$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{
    "Authorization" = "Bearer $apiKey"
    "Content-Type" = "application/json"
}

$triggerId = "4ec040d0-2ba5-4135-bf69-050cad1d115b"
$workflowId = "8d264034-0040-48c6-86f2-aeb5294df90a"
$orgId = "2dab79be-d87a-43dd-99ad-232a3d7161fc"

# Try 1: POST /api/v1/hooks/new with full hook data
Write-Host "`n=== Try 1: POST /api/v1/hooks/new ==="
$hookData = @{
    id = $triggerId
    name = "Webhook Trigger"
    type = "webhook"
    start = $triggerId
    workflow = $workflowId
    environment = "Shuffle"
} | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/hooks/new" -Method Post -Headers $headers -Body $hookData -ContentType "application/json"
    Write-Host "SUCCESS:"
    $r | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {
        Write-Host "Could not read response"
    }
}

# Try 2: POST /api/v1/hooks (alternative route)
Write-Host "`n=== Try 2: POST /api/v1/hooks ==="
try {
    $r2 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/hooks" -Method Post -Headers $headers -Body $hookData -ContentType "application/json"
    Write-Host "SUCCESS:"
    $r2 | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {
        Write-Host "Could not read response"
    }
}

# Try 3: PUT /api/v1/hooks/{workflowId} with full hook structure
Write-Host "`n=== Try 3: PUT /api/v1/hooks/$workflowId ==="
$fullHookData = @{
    id = $triggerId
    start = $triggerId
    info = @{
        name = "Webhook Trigger"
        url = "http://kydoimos.mcaas.example.com/api/v1/hooks/webhook_$($triggerId -replace '-','')"
        description = "Wazuh alert webhook trigger"
    }
    actions = @(
        @{
            type = "workflow"
            name = "Wazuh Alert Handler"
            id = $workflowId
            field = ""
        }
    )
    type = "webhook"
    owner = "admin@mcaas.local"
    status = "running"
    workflows = @($workflowId)
    running = $true
    orgId = $orgId
    environment = "Shuffle"
} | ConvertTo-Json -Depth 5

$putHeaders = @{
    "Authorization" = "Bearer $apiKey"
    "Content-Type" = "application/json"
}

try {
    $r3 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/hooks/$workflowId" -Method Put -Headers $putHeaders -Body $fullHookData -ContentType "application/json"
    Write-Host "SUCCESS:"
    $r3 | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {
        Write-Host "Could not read response"
    }
}

# Try 4: POST /api/v1/hooks/new with the full hook structure matching the HandleNewWidget format
Write-Host "`n=== Try 4: POST /api/v1/hooks/new with full structure ==="
$newHookData = @{
    id = $triggerId
    name = "Webhook Trigger"
    type = "webhook"
    start = $triggerId
    auth = ""
    workflow = $workflowId
    environment = "Shuffle"
    description = "Wazuh alert webhook trigger"
    custom_response = ""
} | ConvertTo-Json

try {
    $r4 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/hooks/new" -Method Post -Headers $headers -Body $newHookData -ContentType "application/json"
    Write-Host "SUCCESS:"
    $r4 | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {
        Write-Host "Could not read response"
    }
}

# Try 5: POST /api/v1/hooks/new with Org-Id header added
Write-Host "`n=== Try 5: POST /api/v1/hooks/new with Org-Id header ==="
$orgHeaders = @{
    "Authorization" = "Bearer $apiKey"
    "Content-Type" = "application/json"
    "Org-Id" = $orgId
}

try {
    $r5 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/hooks/new" -Method Post -Headers $orgHeaders -Body $newHookData -ContentType "application/json"
    Write-Host "SUCCESS:"
    $r5 | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {
        Write-Host "Could not read response"
    }
}

Write-Host "`nDone."