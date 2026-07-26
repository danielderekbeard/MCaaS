$pythonCode = [System.IO.File]::ReadAllText("C:\projects\skyddex\MCaaS\logs\parse-action-v2.py")
Write-Host "Python code loaded: $($pythonCode.Length) chars"

$headers = @{ "Authorization" = "Bearer 17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"; "Content-Type" = "application/json" }
$workflow = Invoke-RestMethod -Uri "http://localhost:5001/api/v1/workflows/8d264034-0040-48c6-86f2-aeb5294df90a" -Headers $headers -Method Get
Write-Host "Workflow loaded. Actions count: $($workflow.actions.Count)"

$actionIdx = -1
for ($i = 0; $i -lt $workflow.actions.Count; $i++) {
    if ($workflow.actions[$i].id -eq "88da65c7-08c7-41cc-9f18-a5354534d260") {
        $actionIdx = $i
        break
    }
}
Write-Host "Action index: $actionIdx"

for ($j = 0; $j -lt $workflow.actions[$actionIdx].parameters.Count; $j++) {
    $pName = $workflow.actions[$actionIdx].parameters[$j].name
    Write-Host "  Param[$j]: name=$pName, value_len=$($workflow.actions[$actionIdx].parameters[$j].value.Length)"
    if ($pName -eq "code") {
        Write-Host "Updating 'code' param (old length: $($workflow.actions[$actionIdx].parameters[$j].value.Length))"
        $workflow.actions[$actionIdx].parameters[$j].value = $pythonCode
        Write-Host "New length: $($workflow.actions[$actionIdx].parameters[$j].value.Length)"
        break
    }
}

# Keep the action name as "execute_python" - this is the Shuffle Tools function name, not a display name
# The label field controls the visible name in Shuffle UI
Write-Host "Action name remains: $($workflow.actions[$actionIdx].name)"

# Convert to JSON without BOM
$jsonBody = $workflow | ConvertTo-Json -Depth 20
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$writer = New-Object System.IO.StreamWriter("C:\projects\skyddex\MCaaS\logs\workflow-update.json", $false, $utf8NoBom)
$writer.Write($jsonBody)
$writer.Close()
Write-Host "Saved workflow update JSON (UTF8 no BOM). Size: $((Get-Item 'C:\projects\skyddex\MCaaS\logs\workflow-update.json').Length) bytes"

# PUT the updated workflow back
$jsonBytes = [System.IO.File]::ReadAllBytes("C:\projects\skyddex\MCaaS\logs\workflow-update.json")
Write-Host "JSON first 80 bytes: $([System.Text.Encoding]::UTF8.GetString($jsonBytes[0..79]))"

try {
    $putResult = Invoke-RestMethod -Uri "http://localhost:5001/api/v1/workflows/8d264034-0040-48c6-86f2-aeb5294df90a" -Headers $headers -Method Put -Body $jsonBytes -ContentType "application/json; charset=utf-8"
    Write-Host "PUT result success: $($putResult.success)"
    Write-Host "PUT result status: $($putResult.status)"
    Write-Host "PUT result message: $($putResult.message)"
} catch {
    Write-Host "PUT FAILED: $($_.Exception.Message)"
    $responseStream = $_.Exception.Response.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($responseStream)
    $errorBody = $reader.ReadToEnd()
    Write-Host "Error response body: $errorBody"
}