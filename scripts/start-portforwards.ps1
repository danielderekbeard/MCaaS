# MCaaS Port-Forward Script
# Run this to access services from Windows browser

Write-Host "Starting port-forwards for MCaaS services..." -ForegroundColor Green
Write-Host ""
Write-Host "Access URLs:" -ForegroundColor Cyan
Write-Host "  Shuffle:    http://localhost:8080"  
Write-Host "  Zammad:     http://localhost:8081"
Write-Host "  CISO:       http://localhost:8082"
Write-Host "  Wazuh:      https://localhost:8083 (accept cert warning)"
Write-Host ""
Write-Host "Press Ctrl+C to stop all port-forwards" -ForegroundColor Yellow
Write-Host ""

# Start port-forwards
$shuffle = Start-Process -FilePath "kubectl" -ArgumentList "port-forward", "-n", "security-ops", "svc/shuffle-frontend", "8080:80", "--address", "0.0.0.0" -WindowStyle Hidden -PassThru
$zammad = Start-Process -FilePath "kubectl" -ArgumentList "port-forward", "-n", "managed-it", "svc/mcaas-zammad-nginx", "8081:8080", "--address", "0.0.0.0" -WindowStyle Hidden -PassThru
$ciso = Start-Process -FilePath "kubectl" -ArgumentList "port-forward", "-n", "grc", "svc/mcaas-ciso-ciso-assistant-frontend", "8082:80", "--address", "0.0.0.0" -WindowStyle Hidden -PassThru
$wazuh = Start-Process -FilePath "kubectl" -ArgumentList "port-forward", "-n", "wazuh", "svc/dashboard", "8083:443", "--address", "0.0.0.0" -WindowStyle Hidden -PassThru

Write-Host "Port-forwards started. PIDs: $($shuffle.Id), $($zammad.Id), $($ciso.Id), $($wazuh.Id)"

# Wait for interrupt
Write-Host ""
Write-Host "Services are ready!" -ForegroundColor Green
pause

# Cleanup
Stop-Process -Id $shuffle.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $zammad.Id -Force -ErrorAction SilentlyContinue  
Stop-Process -Id $ciso.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $wazuh.Id -Force -ErrorAction SilentlyContinue
Write-Host "Port-forwards stopped." -ForegroundColor Red
