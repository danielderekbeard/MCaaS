# Explore Zammad API and Shuffle credential API
$apiKey = "17c8ea2c-2c78-4e64-aedc-abd69ddd0c2d"
$headers = @{ "Authorization" = "Bearer $apiKey"; "Content-Type" = "application/json" }

# Step 1: Explore Zammad API
Write-Host "=== Exploring Zammad API ==="

# Try to check Zammad availability
try {
    $result = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1" -Method Get -Headers @{ "Content-Type" = "application/json" }
    Write-Host "Zammad API root: $($result | ConvertTo-Json -Depth 2)"
} catch {
    Write-Host "Zammad API root error: $($_.Exception.Message)"
}

# Try Zammad sessions endpoint with correct format
try {
    $body = @{ "username" = "admin@mcaas.local"; "password" = "MCaaSadmin2026!" } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/sessions" -Method Post -Body $body -Headers @{ "Content-Type" = "application/json" } -SessionVariable session
    Write-Host "Zammad session created: $($result | ConvertTo-Json -Depth 2)"
    
    # Now try to create token with session cookie
    $tokenBody = @{
        name = "shuffle-integration"
        permission = @("ticket.agent", "ticket.customer")
    } | ConvertTo-Json -Depth 3
    Write-Host "Creating token with session..."
    $tokenResult = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/user_access_token" -Method Post -Body $tokenBody -Headers @{ "Content-Type" = "application/json" } -WebSession $session
    Write-Host "Token created: $($tokenResult | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Zammad session/token error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {}
}

# Try basic auth with Zammad
Write-Host "`n=== Trying Zammad with Basic Auth ==="
try {
    $basicAuth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin@mcaas.local:MCaaSadmin2026!"))
    $zHeaders = @{ "Authorization" = "Basic $basicAuth"; "Content-Type" = "application/json" }
    $result = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/users/me" -Method Get -Headers $zHeaders
    Write-Host "Zammad user info: $($result.login), id=$($result.id), name=$($result.firstname) $($result.lastname)"
    
    # Try creating token with basic auth
    Write-Host "Creating token with basic auth..."
    $tokenBody = @{
        name = "shuffle-integration"
        permission = @("ticket.agent")
    } | ConvertTo-Json -Depth 3
    $tokenResult = Invoke-RestMethod -Uri "http://alala.mcaas.example.com/api/v1/user_access_token" -Method Post -Headers $zHeaders -Body $tokenBody
    Write-Host "Token result: $($tokenResult | ConvertTo-Json -Depth 3)"
} catch {
    Write-Host "Basic auth error: $($_.Exception.Message)"
    try {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "Response: $($reader.ReadToEnd())"
    } catch {}
}

# Step 2: Explore Shuffle credential API
Write-Host "`n=== Exploring Shuffle credential API ==="

# Try different credential endpoints
foreach ($endpoint in @(
    "/api/v1/app/authentication",
    "/api/v1/credentials",
    "/api/v1/orgs/$orgId/credentials",
    "/api/v1/app/auths"
)) {
    try {
        $result = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com$endpoint" -Method Get -Headers $headers
        Write-Host "GET $endpoint : Success - $($result | ConvertTo-Json -Depth 2)"
    } catch {
        Write-Host "GET $endpoint : $($_.Exception.Message)"
    }
}

# Try POST to /api/v1/credentials
Write-Host "`n=== Trying to create Shuffle credential ==="
$orgId = "2dab79be-d87a-43dd-99ad-232a3d7161fc"
foreach ($endpoint in @(
    "/api/v1/credentials",
    "/api/v1/orgs/$orgId/credentials"
)) {
    try {
        $credBody = @{
            org_id = $orgId
            name = "test-credential"
            value = "test-value"
            type = "apikey"
        } | ConvertTo-Json
        
        $result = Invoke-RestMethod -Uri "http://kydoimos.mcaas.example.com$endpoint" -Method Post -Headers $headers -Body $credBody
        Write-Host "POST $endpoint : Success - $($result | ConvertTo-Json -Depth 2)"
    } catch {
        Write-Host "POST $endpoint : $($_.Exception.Message)"
        try {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            Write-Host "Response: $($reader.ReadToEnd())"
        } catch {}
    }
}