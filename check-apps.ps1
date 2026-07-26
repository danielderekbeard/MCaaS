# Check workflow execution result and available Shuffle apps
$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }
$workflowId = "8d264034-0040-48c6-86f2-aeb5294df90a"
$executionId = "44046918-0b52-407f-89e6-53ee88e69dfe"

# Check execution result
Write-Host "=== Getting execution result ==="
try {
    $exec = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/executions/$executionId" -Method Get -Headers $headers
    $exec | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch { Write-Host "Could not read response" }
}

# Search for Zammad app in Shuffle
Write-Host "`n=== Searching for Zammad app ==="
try {
    $apps = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/apps?search=zammad" -Method Get -Headers $headers
    $apps | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# Search for Wazuh app in Shuffle
Write-Host "`n=== Searching for Wazuh app ==="
try {
    $apps2 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/apps?search=wazuh" -Method Get -Headers $headers
    $apps2 | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# Get current workflow details
Write-Host "`n=== Current workflow details ==="
try {
    $wf = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Get -Headers $headers
    Write-Host "Name: $($wf.name)"
    Write-Host "Start: $($wf.start)"
    Write-Host "IsValid: $($wf.is_valid)"
    Write-Host "Actions count: $($wf.actions.Count)"
    Write-Host "Triggers count: $($wf.triggers.Count)"
    foreach ($a in $wf.actions) {
        Write-Host "  Action: id=$($a.id), name=$($a.app_name), label=$($a.label), type=$($a.type)"
        if ($a.parameters) {
            foreach ($p in $a.parameters) {
                Write-Host "    Param: name=$($p.name), value=$($p.value), variant=$($p.variant)"
            }
        }
    }
    foreach ($t in $wf.triggers) {
        Write-Host "  Trigger: id=$($t.id), name=$($t.app_name), type=$($t.trigger_type), label=$($t.label)"
        if ($t.parameters) {
            foreach ($p in $t.parameters) {
                Write-Host "    Param: name=$($p.name), value=$($p.value)"
            }
        }
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# List all available apps (just names)
Write-Host "`n=== Available Shuffle apps (first 50) ==="
try {
    $allApps = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/apps" -Method Get -Headers $headers
    foreach ($a in $allApps[0..49]) {
        Write-Host "  App: name=$($a.name), id=$($a.id)"
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}