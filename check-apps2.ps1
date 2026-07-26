# Targeted checks - workflow, execution, and app search
$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }
$workflowId = "8d264034-0040-48c6-86f2-aeb5294df90a"
$executionId = "44046918-0b52-407f-89e6-53ee88e69dfe"

# 1. Check workflow
Write-Host "=== Current Workflow ==="
$wf = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Get -Headers $headers
Write-Host "Name: $($wf.name)"
Write-Host "Start: $($wf.start)"
Write-Host "IsValid: $($wf.is_valid)"
Write-Host "Actions count: $($wf.actions.Count)"
foreach ($a in $wf.actions) {
    Write-Host "  Action: id=$($a.id), app_name=$($a.app_name), label=$($a.label), type=$($a.type)"
    if ($a.parameters) {
        foreach ($p in $a.parameters) {
            Write-Host "    Param: name=$($p.name), value=$($p.value), variant=$($p.variant)"
        }
    }
}
Write-Host "Triggers count: $($wf.triggers.Count)"
foreach ($t in $wf.triggers) {
    Write-Host "  Trigger: id=$($t.id), app_name=$($t.app_name), type=$($t.trigger_type), label=$($t.label)"
    if ($t.parameters) {
        foreach ($p in $t.parameters) {
            Write-Host "    Param: name=$($p.name), value=$($p.value)"
        }
    }
}

# 2. Check execution
Write-Host "`n=== Execution Result ==="
try {
    $exec = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/executions/$executionId" -Method Get -Headers $headers
    Write-Host "Status: $($exec.status)"
    Write-Host "Start: $($exec.start)"
    Write-Host "Result: $($exec.result | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Error getting execution: $($_.Exception.Message)"
}

# 3. Search for specific apps
Write-Host "`n=== Searching for Zammad app ==="
try {
    $zammadApps = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/apps?search=zammad" -Method Get -Headers $headers
    if ($zammadApps -is [array]) {
        foreach ($a in $zammadApps) {
            Write-Host "  Found: name=$($a.name), id=$($a.id), validated=$($a.validated)"
            if ($a.actions) {
                foreach ($act in $a.actions) {
                    Write-Host "    Action: $($act.name) - $($act.description)"
                }
            }
        }
    } else {
        Write-Host "  Found: name=$($zammadApps.name), id=$($zammadApps.id), validated=$($zammadApps.validated)"
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

Write-Host "`n=== Searching for Wazuh app ==="
try {
    $wazuhApps = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/apps?search=wazuh" -Method Get -Headers $headers
    if ($wazuhApps -is [array]) {
        foreach ($a in $wazuhApps) {
            Write-Host "  Found: name=$($a.name), id=$($a.id), validated=$($a.validated)"
            if ($a.actions) {
                foreach ($act in $a.actions) {
                    Write-Host "    Action: $($act.name) - $($act.description)"
                }
            }
        }
    } else {
        Write-Host "  Found: name=$($wazuhApps.name), id=$($wazuhApps.id), validated=$($wazuhApps.validated)"
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# 4. List first 30 app names
Write-Host "`n=== Available Apps (first 30) ==="
$allApps = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/apps" -Method Get -Headers $headers
$count = 0
foreach ($a in $allApps) {
    $count++
    if ($count -gt 30) { break }
    Write-Host "  $count. $($a.name) (id: $($a.id))"
}
Write-Host "Total apps: $($allApps.Count)"