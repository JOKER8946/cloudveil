<#
  infra/diagnostics.ps1 — Key Vault AuditEvent + Storage logs -> Log Analytics
  (PowerShell equivalent of diagnostics.sh). Idempotent.
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
$rg = $Names.RG
$workspaceId = az monitor log-analytics workspace show -g $rg -n $Names.LAW --query id -o tsv
$kvId = az keyvault show -n $Names.KV -g $rg --query id -o tsv
$blobId = (az storage account show -n $Names.SA_PRIMARY -g $rg --query id -o tsv) + "/blobServices/default"

Write-Host "Key Vault AuditEvent -> Log Analytics..."
try {
    az monitor diagnostic-settings create --name cv-kv-diag --resource $kvId --workspace $workspaceId `
        --logs '[{\"category\":\"AuditEvent\",\"enabled\":true}]' -o none
} catch { Write-Host "  (already configured)" }

Write-Host "Storage blob read/write/delete -> Log Analytics..."
try {
    az monitor diagnostic-settings create --name cv-blob-diag --resource $blobId --workspace $workspaceId `
        --logs '[{\"category\":\"StorageRead\",\"enabled\":true},{\"category\":\"StorageWrite\",\"enabled\":true},{\"category\":\"StorageDelete\",\"enabled\":true}]' -o none
} catch { Write-Host "  (already configured)" }

Write-Host "Diagnostics configured."
