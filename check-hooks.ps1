# Login first to get session cookie
$loginBody = '{"username":"admin@mcaas.local","password":"MCaaSadmin2026!"}'
$loginResp = Invoke-WebRequest -Uri "http://kydoimos.mcaas.example.com/api/v1/users/login" -Method Post -ContentType "application/json" -Body $loginBody -SessionVariable ws

Write-Host "Login Status: $($loginResp.StatusCode)"

# Check specific hook with session cookie
Write-Host "`n=== Getting hook 4ec040d0-2ba5-4135-bf69-050cad1d115b ==="
try {
    $r = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/hooks/4ec040d0-2ba5-4135-bf69-050cad1d115b" -Method Get -WebSession $ws
    $r | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch { Write-Host "Could not read response" }
}

# Also check the workflow
Write-Host "`n=== Getting workflow ==="
try {
    $r2 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/8d264034-0040-48c6-86f2-aeb5294df90a" -Method Get -WebSession $ws
    Write-Host "Workflow name: $($r2.name)"
    Write-Host "Workflow is_valid: $($r2.is_valid)"
    Write-Host "Workflow start: $($r2.start)"
    Write-Host "Workflow actions count: $($r2.actions.Count)"
    Write-Host "Workflow triggers count: $($r2.triggers.Count)"
    if ($r2.triggers) {
        foreach ($t in $r2.triggers) {
            Write-Host "  Trigger: name=$($t.app_name), type=$($t.trigger_type), id=$($t.id), label=$($t.label)"
            if ($t.parameters) {
                foreach ($p in $t.parameters) {
                    Write-Host "    Param: name=$($p.name), value=$($p.value)"
                }
            }
        }
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch { Write-Host "Could not read response" }
}

# Test webhook callback
Write-Host "`n=== Testing webhook callback ==="
$webhookUrl = "http://kydoimos.mcaas.example.com/api/v1/hooks/webhook_4ec040d02ba54135bf69050cad1d115b"
$testData = '{"test": "hello from mcaas", "alert": {"rule": {"level": 5}, "description": "Test alert"}}'
try {
    $r3 = Invoke-RestMethod -Uri $webhookUrl -Method Post -ContentType "application/json" -Body $testData
    $r3 | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch { Write-Host "Could not read response" }
}