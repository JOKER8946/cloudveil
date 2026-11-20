<#
  infra/replication.ps1 — enable Object Replication primary -> secondary
  (PowerShell equivalent of replication.sh). Idempotent.
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
$rg = $Names.RG
$src = $Names.SA_PRIMARY
$dest = $Names.SA_SECONDARY
$container = $Names.CONTAINER

$existing = az storage account or-policy list -g $rg -n $src --query "[?contains(destinationAccount, '$dest')]" -o tsv 2>$null
if ($existing) { Write-Host "Object replication already exists ($src -> $dest)."; return }

Write-Host "Creating object replication policy on destination $dest..."
$policy = az storage account or-policy create -g $rg -n $dest `
    --source-account $src --destination-account $dest `
    --source-container $container --destination-container $container -o json

$tmp = Join-Path $PSScriptRoot '.orpolicy.json'
$policy | Set-Content -Path $tmp -Encoding utf8
Write-Host "Applying the same policy to source $src..."
az storage account or-policy create -g $rg -n $src --policy "@$tmp" -o none
Remove-Item $tmp -Force

Write-Host "Object replication enabled: $src/$container -> $dest/$container"
