<#
  infra/teardown.ps1 — delete the CloudVeil resource group (DESTRUCTIVE).
  Asks for confirmation. Key Vault purge protection keeps the vault name
  soft-deleted for the retention window.
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
$rg = $Names.RG

Write-Host "This will DELETE the entire resource group: $rg"
$confirm = Read-Host "Type the resource group name to confirm"
if ($confirm -ne $rg) { Write-Host 'Aborted.'; exit 1 }

az group delete -n $rg --yes
Write-Host "Deletion started for $rg."
