# Fix workflow start field and test webhook
$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }
$workflowId = "8d264034-0040-48c6-86f2-aeb5294df90a"
$triggerId = "4ec040d0-2ba5-4135-bf69-050cad1d115b"

# First get the full workflow with API key
Write-Host "=== Getting workflow with API key ==="
try {
    $wf = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Get -Headers $headers
    Write-Host "Workflow name: $($wf.name)"
    Write-Host "Workflow start: $($wf.start)"
    Write-Host "Workflow isValid: $($wf.is_valid)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    # Try with session cookie instead
    Write-Host "Trying with session cookie..."
    $loginBody = '{"username":"admin@mcaas.local","password":"MCaaSadmin2026!"}'
    $loginResp = Invoke-WebRequest -Uri "http://kydoimos.mcaas.example.com/api/v1/users/login" -Method Post -ContentType "application/json" -Body $loginBody -SessionVariable ws -UseBasicParsing
    Write-Host "Login Status: $($loginResp.StatusCode)"
    $wf = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Get -WebSession $ws
    Write-Host "Workflow name: $($wf.name)"
    Write-Host "Workflow start: $($wf.start)"
    Write-Host "Workflow isValid: $($wf.is_valid)"
}

# Fix the start field to point to the trigger
Write-Host "`n=== Fixing workflow start field ==="
$wf.start = $triggerId
$wfJson = $wf | ConvertTo-Json -Depth 10

# Try updating with API key
try {
    $updateResp = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Put -Headers $headers -Body $wfJson -ContentType "application/json"
    Write-Host "Update response:"
    $updateResp | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error with API key: $($_.Exception.Message)"
    # Try with session cookie
    Write-Host "Trying with session cookie..."
    try {
        $loginBody = '{"username":"admin@mcaas.local","password":"MCaaSadmin2026!"}'
        $loginResp = Invoke-WebRequest -Uri "http://kydoimos.mcaas.example.com/api/v1/users/login" -Method Post -ContentType "application/json" -Body $loginBody -SessionVariable ws2 -UseBasicParsing
        $updateResp2 = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Put -WebSession $ws2 -Body $wfJson -ContentType "application/json"
        Write-Host "Update response:"
        $updateResp2 | ConvertTo-Json -Depth 3
    } catch {
        Write-Host "Error: $($_.Exception.Message)"
        try {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            Write-Host "Response: $($reader.ReadToEnd())"
        } catch { Write-Host "Could not read response" }
    }
}

# Now let's check if there's a different webhook URL format
# The handleWebhookCallback expects /api/v1/hooks/webhook_{triggerId}
# where triggerId should be 36 chars
Write-Host "`n=== Testing webhook callback with different URL formats ==="

# Format 1: with hyphens (36 chars including hyphens)
$url1 = "http://kydoimos.mcaas.example.com/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b"
Write-Host "Testing URL with hyphens: $url1"
try {
    $r1 = Invoke-RestMethod -Uri $url1 -Method Post -ContentType "application/json" -Body '{"test":"hello"}' -UseBasicParsing
    Write-Host "Result: $($r1 | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# Format 2: without hyphens (32 chars)
$url2 = "http://kydoimos.mcaas.example.com/api/v1/hooks/webhook_4ec040d02ba54135bf69050cad1d115b"
Write-Host "`nTesting URL without hyphens: $url2"
try {
    $r2 = Invoke-RestMethod -Uri $url2 -Method Post -ContentType "application/json" -Body '{"test":"hello"}' -UseBasicParsing
    Write-Host "Result: $($r2 | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

# Format 3: direct trigger ID (no webhook_ prefix)
$url3 = "http://kydoimos.mcaas.example.com/api/v1/hooks/4ec040d0-2ba5-4135-bf69-050cad1d115b"
Write-Host "`nTesting URL with just trigger ID: $url3"
try {
    $r3 = Invoke-RestMethod -Uri $url3 -Method Post -ContentType "application/json" -Body '{"test":"hello"}' -UseBasicParsing
    Write-Host "Result: $($r3 | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}

Write-Host "`nDone."