param()

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path -Resolve
$projectRoot = Join-Path $scriptRoot '..'

Write-Host "Executing consolidated teardown script..."

# Ensure python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "python is required but it's not installed or not in your PATH. Aborting." }

python (Join-Path $projectRoot 'teardown.py')
