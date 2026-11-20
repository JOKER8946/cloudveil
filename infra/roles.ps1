<#
  infra/roles.ps1 — idempotent RBAC role assignments (PowerShell equivalent of roles.sh).
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
$rg = $Names.RG
$kvId = az keyvault show -n $Names.KV -g $rg --query id -o tsv
$saId = az storage account show -n $Names.SA_PRIMARY -g $rg --query id -o tsv
$mi   = az webapp identity show -g $rg -n $Names.WEBAPP --query principalId -o tsv
$usr  = az ad signed-in-user show --query id -o tsv

function Add-Role { param($Assignee, $PType, $Role, $Scope)
    Write-Host "  -> $Role"
    az role assignment create --assignee-object-id $Assignee --assignee-principal-type $PType --role $Role --scope $Scope -o none 2>$null
}

Write-Host "=== Web App managed identity ($mi) ==="
Add-Role $mi ServicePrincipal 'Key Vault Crypto User'         $kvId
Add-Role $mi ServicePrincipal 'Storage Blob Data Contributor' $saId
Write-Host "=== Signed-in user ($usr) ==="
Add-Role $usr User 'Key Vault Crypto Officer'      $kvId
Add-Role $usr User 'Storage Blob Data Contributor' $saId
Write-Host 'Done.'
