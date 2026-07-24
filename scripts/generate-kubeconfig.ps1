# ============================================================
# generate-kubeconfig.ps1
#
# Creates a kubeconfig for the github-actions-deployer
# ServiceAccount and prints the base64-encoded value ready
# for the KUBE_CONFIG_DATA GitHub Actions secret.
#
# Prerequisites:
#   - kubectl pointing at the target cluster (active context)
#   - deploy/cicd-service-account.yaml already applied
#
# Usage:
#   .\scripts\generate-kubeconfig.ps1
# ============================================================

$ErrorActionPreference = "Stop"

$ServiceAccount = "github-actions-deployer"
$Namespace       = "kube-system"
$SecretName      = "github-actions-deployer-token"

# --- 1. Grab the bearer token from the Secret ---
Write-Host "Fetching token from Secret/$SecretName..."
$tokenBytes = kubectl -n $Namespace get secret $SecretName -o jsonpath='{.data.token}' 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($tokenBytes)) {
    Write-Error "ERROR: Could not retrieve token. Make sure deploy/cicd-service-account.yaml is applied."
    exit 1
}
$Token = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($tokenBytes))

# --- 2. Grab cluster info ---
$ClusterName = (kubectl config current-context 2>$null) ?? "local"
$Server  = kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
$CaData  = kubectl config view --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}'

# --- 3. Build the kubeconfig ---
$kubeconfig = @"
apiVersion: v1
kind: Config
clusters:
  - cluster:
      certificate-authority-data: $CaData
      server: $Server
      insecure-skip-tls-verify: true
    name: $ClusterName
contexts:
  - context:
      cluster: $ClusterName
      user: $ServiceAccount
      namespace: default
    name: ${ServiceAccount}-context
current-context: ${ServiceAccount}-context
preferences: {}
users:
  - name: $ServiceAccount
    user:
      token: $Token
"@

# --- 4. Output ---
Write-Host "Kubeconfig generated successfully."
Write-Host ""

# Base64-encode (UTF-8, no BOM) — matches what the workflows expect
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($kubeconfig))
Write-Host "Base64-encoded value for KUBE_CONFIG_DATA GitHub secret:"
Write-Host "---"
Write-Host $b64
Write-Host "---"
Write-Host ""
Write-Host "Raw kubeconfig:"
Write-Host $kubeconfig

# Optionally write to file
$outPath = Join-Path $PSScriptRoot "..\kubeconfig-generated.yaml"
[System.IO.File]::WriteAllText($outPath, $kubeconfig, [System.Text.Encoding]::UTF8)
Write-Host ""
Write-Host "Raw kubeconfig also written to: $outPath"