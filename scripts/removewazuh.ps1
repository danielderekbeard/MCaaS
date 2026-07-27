# 1. Stop Service
Stop-Service -Name "WazuhSvc" -Force -ErrorAction SilentlyContinue

# 2. Uninstall Package
$agent = Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -match "Wazuh Agent" }
if ($agent) {
    Write-Host "Uninstalling Wazuh Agent..."
    $agent.Uninstall() | Out-Null
}

# 3. Purge Files
Remove-Item -Path "C:\Program Files (x86)\ossec-agent" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\ProgramData\ossec" -Recurse -Force -ErrorAction SilentlyContinue

# 4. Wipe Services
sc.exe delete WazuhSvc 
sc.exe delete WazuhAgent

# 5. Clean Registry
Remove-Item -Path "HKLM:\SOFTWARE\ossec" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Wazuh Agent cleanup complete."