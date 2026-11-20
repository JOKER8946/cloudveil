<#
  infra/provision.ps1 — idempotent provisioning of all CloudVeil Azure resources.
  PowerShell equivalent of provision.sh. Reads ../.env. Creates PAID resources —
  run only with approval.  Usage:  pwsh ./infra/provision.ps1
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

function Test-AzExists { param([scriptblock]$Check)
    try { & $Check *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
Write-Host "Subscription: $(az account show --query name -o tsv)"
$signedIn = az ad signed-in-user show --query id -o tsv

$rg = $Names.RG; $loc = $Names.LOC; $loc2 = $Names.LOC2

Write-Host "`n=== Resource group $rg ($loc) ==="
if ((az group exists -n $rg) -eq 'true') { 'exists' } else { az group create -n $rg -l $loc -o none; 'created' }

Write-Host "`n=== Log Analytics workspace $($Names.LAW) ==="
if (Test-AzExists { az monitor log-analytics workspace show -g $rg -n $Names.LAW }) { 'exists' }
else { az monitor log-analytics workspace create -g $rg -n $Names.LAW -l $loc -o none; 'created' }
$workspaceId = az monitor log-analytics workspace show -g $rg -n $Names.LAW --query id -o tsv

Write-Host "`n=== Application Insights $($Names.APPI) ==="
az extension add -n application-insights --only-show-errors -o none 2>$null
if (Test-AzExists { az monitor app-insights component show --app $Names.APPI -g $rg }) { 'exists' }
else { az monitor app-insights component create --app $Names.APPI -g $rg -l $loc --workspace $workspaceId --application-type web -o none; 'created' }
$appiConn = az monitor app-insights component show --app $Names.APPI -g $rg --query connectionString -o tsv

Write-Host "`n=== Key Vault $($Names.KV) ==="
if (-not (Test-AzExists { az keyvault show -n $Names.KV -g $rg })) {
    az keyvault create -n $Names.KV -g $rg -l $loc --enable-rbac-authorization true --enable-purge-protection true --retention-days 90 -o none
    'created'
} else { 'exists' }
$kvUrl = az keyvault show -n $Names.KV -g $rg --query properties.vaultUri -o tsv
$kvId  = az keyvault show -n $Names.KV -g $rg --query id -o tsv

Write-Host "`n=== Grant signed-in user 'Key Vault Crypto Officer' ==="
az role assignment create --assignee-object-id $signedIn --assignee-principal-type User --role 'Key Vault Crypto Officer' --scope $kvId -o none 2>$null
Write-Host 'Waiting 30s for RBAC propagation...'; Start-Sleep -Seconds 30

Write-Host "`n=== RSA-3072 key $($Names.KEK) ==="
if (Test-AzExists { az keyvault key show --vault-name $Names.KV --name $Names.KEK }) { 'exists' }
else { az keyvault key create --vault-name $Names.KV --name $Names.KEK --kty RSA --size 3072 --ops wrapKey unwrapKey -o none; 'created' }

function New-Storage { param([string]$Account, [string]$Location, [bool]$ChangeFeed)
    Write-Host "`n=== Storage account $Account ($Location) ==="
    if (-not (Test-AzExists { az storage account show -n $Account -g $rg })) {
        az storage account create -n $Account -g $rg -l $Location --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false -o none
        'created'
    } else { 'exists' }
    if ($ChangeFeed) { az storage account blob-service-properties update --account-name $Account -g $rg --enable-versioning true --enable-change-feed true -o none }
    else { az storage account blob-service-properties update --account-name $Account -g $rg --enable-versioning true -o none }
    $key = az storage account keys list -n $Account -g $rg --query '[0].value' -o tsv
    if (-not (Test-AzExists { az storage container show --account-name $Account --account-key $key --name $Names.CONTAINER })) {
        az storage container create --account-name $Account --account-key $key --name $Names.CONTAINER --public-access off -o none
        "container $($Names.CONTAINER) created"
    } else { "container exists" }
}
New-Storage -Account $Names.SA_PRIMARY   -Location $loc  -ChangeFeed $true
New-Storage -Account $Names.SA_SECONDARY -Location $loc2 -ChangeFeed $false
$saPrimaryUrl = az storage account show -n $Names.SA_PRIMARY -g $rg --query primaryEndpoints.blob -o tsv

Write-Host "`n=== MySQL Flexible Server $($Names.MYSQL) (may take several minutes) ==="
if (-not (Test-AzExists { az mysql flexible-server show -n $Names.MYSQL -g $rg })) {
    az mysql flexible-server create -n $Names.MYSQL -g $rg -l $loc `
        --admin-user $Cfg['MYSQL_ADMIN_USER'] --admin-password $Cfg['MYSQL_ADMIN_PASSWORD'] `
        --sku-name Standard_B1ms --tier Burstable --storage-size 20 --version 8.0.21 `
        --public-access None --yes -o none
    'created'
} else { 'exists' }
az mysql flexible-server firewall-rule create -g $rg -n $Names.MYSQL --rule-name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none 2>$null
az mysql flexible-server parameter set -g $rg -s $Names.MYSQL --name require_secure_transport --value ON -o none 2>$null
if (-not (Test-AzExists { az mysql flexible-server db show -g $rg -s $Names.MYSQL -d $Names.MYSQL_DB })) {
    az mysql flexible-server db create -g $rg -s $Names.MYSQL -d $Names.MYSQL_DB -o none
}
$mysqlHost = az mysql flexible-server show -n $Names.MYSQL -g $rg --query fullyQualifiedDomainName -o tsv

Write-Host "`n=== App Service plan $($Names.PLAN) ==="
if (-not (Test-AzExists { az appservice plan show -g $rg -n $Names.PLAN })) { az appservice plan create -g $rg -n $Names.PLAN --is-linux --sku B1 -l $loc -o none; 'created' } else { 'exists' }

Write-Host "`n=== Web App $($Names.WEBAPP) ==="
if (-not (Test-AzExists { az webapp show -g $rg -n $Names.WEBAPP })) { az webapp create -g $rg -p $Names.PLAN -n $Names.WEBAPP --runtime 'PYTHON:3.12' -o none; 'created' } else { 'exists' }
az webapp update -g $rg -n $Names.WEBAPP --https-only true -o none
az webapp identity assign -g $rg -n $Names.WEBAPP -o none
az webapp config set -g $rg -n $Names.WEBAPP --startup-file 'bash startup.sh' -o none
$webappHost = az webapp show -g $rg -n $Names.WEBAPP --query defaultHostName -o tsv

Set-EnvValue $Script:EnvFile 'KEYVAULT_URL'        $kvUrl
Set-EnvValue $Script:EnvFile 'KEK_NAME'            $Names.KEK
Set-EnvValue $Script:EnvFile 'STORAGE_ACCOUNT_URL' $saPrimaryUrl
Set-EnvValue $Script:EnvFile 'STORAGE_CONTAINER'   $Names.CONTAINER
Set-EnvValue $Script:EnvFile 'PRIMARY_REGION'      $loc
Set-EnvValue $Script:EnvFile 'MYSQL_HOST'          $mysqlHost
Set-EnvValue $Script:EnvFile 'MYSQL_DATABASE'      $Names.MYSQL_DB
Set-EnvValue $Script:EnvFile 'WEBAPP_NAME'         $Names.WEBAPP
Set-EnvValue $Script:EnvFile 'WEBAPP_HOST'         $webappHost
Set-EnvValue $Script:EnvFile 'SA_SECONDARY'        $Names.SA_SECONDARY
Set-EnvValue $Script:EnvFile 'APPLICATIONINSIGHTS_CONNECTION_STRING' $appiConn

Write-Host "`n=== CloudVeil provisioning complete ==="
Write-Host "  Web App: https://$webappHost"
Write-Host "  Next: roles.ps1, github_oidc.ps1, app_settings.ps1"
