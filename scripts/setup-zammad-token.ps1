# Configure Shuffle Workflow with Zammad and Wazuh integration
# Since there are no native Zammad/Wazuh apps, we use the http app for both

$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }
$workflowId = "8d264034-0040-48c6-86f2-aeb5294df90a"
$orgId = "2dab79be-d87a-43dd-99ad-232a3d7161fc"

# Step 1: Get current workflow state
Write-Host "=== Getting current workflow ==="
$wf = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/workflows/$workflowId" -Method Get -Headers $headers
Write-Host "Name: $($wf.name)"
Write-Host "Start: $($wf.start)"
Write-Host "IsValid: $($wf.is_valid)"
Write-Host "Actions: $($wf.actions.Count)"
Write-Host "Triggers: $($wf.triggers.Count)"

# Step 2: Get Zammad API token
Write-Host "`n=== Getting Zammad API token ==="
$zammadToken = ""
try {
    # Try to login to Zammad and get/create an API token
    $zammadHeaders = @{ "Content-Type" = "application/json" }
    
    # First try to create a session
    $loginBody = @{
        username = "admin@mcaas.local"
        password = "MCaaSadmin2026!"
    } | ConvertTo-Json
    
    Write-Host "Attempting Zammad login..."
    $loginResult = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/sessions" -Method Post -Headers $zammadHeaders -Body $loginBody -SessionVariable zammadSession
    Write-Host "Zammad login successful!"
    
    # Now create an API token
    Write-Host "Creating Zammad API token..."
    $tokenBody = @{
        name = "shuffle-integration"
        permission = @("ticket.agent", "ticket.customer")
    } | ConvertTo-Json
    
    $tokenResult = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/user_access_token" -Method Post -Headers @{ "Content-Type" = "application/json" } -Body $tokenBody -WebSession $zammadSession
    $zammadToken = $tokenResult.token
    Write-Host "Zammad API token created: $zammadToken"
} catch {
    Write-Host "Error getting Zammad token: $($_.Exception.Message)"
    Write-Host "Will try alternative approach..."
    
    # Try direct API approach
    try {
        # Try creating token with basic auth
        $basicAuth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin@mcaas.local:MCaaSadmin2026!"))
        $tokenHeaders = @{ "Authorization" = "Basic $basicAuth"; "Content-Type" = "application/json" }
        $tokenBody = @{
            name = "shuffle-integration"
            permission = @("ticket.agent", "ticket.customer")
        } | ConvertTo-Json -Depth 3
        
        $tokenResult = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/user_access_token" -Method Post -Headers $tokenHeaders -Body $tokenBody
        $zammadToken = $tokenResult.token
        Write-Host "Zammad API token created via basic auth: $zammadToken"
    } catch {
        Write-Host "Basic auth approach also failed: $($_.Exception.Message)"
        try {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            Write-Host "Response: $($reader.ReadToEnd())"
        } catch { Write-Host "Could not read response" }
    }
}

if ([string]::IsNullOrEmpty($zammadToken)) {
    Write-Host "`nWARNING: Could not create Zammad API token automatically."
    Write-Host "You'll need to manually create one in Zammad UI:"
    Write-Host "  1. Go to http://alala.mcaas.example.com"
    Write-Host "  2. Login as admin@mcaas.local / MCaaSadmin2026!"
    Write-Host "  3. Go to Profile -> Token Access"
    Write-Host "  4. Create token with ticket.agent permissions"
    Write-Host ""
    Write-Host "Using placeholder token for now - will need to be updated."
    $zammadToken = "PLACEHOLDER_ZAMMAD_TOKEN"
}

# Step 3: Save Zammad token as Shuffle credential
Write-Host "`n=== Saving Zammad credential in Shuffle ==="
try {
    $credBody = @{
        org_id = $orgId
        name = "zammad-api-key"
        value = $zammadToken
        type = "apikey"
    } | ConvertTo-Json
    
    $credResult = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com/api/v1/app/authentication" -Method Post -Headers $headers -Body $credBody
    Write-Host "Credential saved: $($credResult | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Error saving credential: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch { Write-Host "Could not read response" }
}

Write-Host "`n=== Done with credential setup ==="
Write-Host "Zammad token: $zammadToken"