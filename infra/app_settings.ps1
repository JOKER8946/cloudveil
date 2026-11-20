<#
  infra/app_settings.ps1 — push application settings to the App Service
  (PowerShell equivalent of app_settings.sh). Secrets are set but never echoed.
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
$rg = $Names.RG; $webapp = $Names.WEBAPP

if (-not $Cfg['KEYVAULT_URL'])        { throw 'Run provision first (KEYVAULT_URL missing).' }
if (-not $Cfg['STORAGE_ACCOUNT_URL']) { throw 'Run provision first (STORAGE_ACCOUNT_URL missing).' }
if (-not $Cfg['MYSQL_HOST'])          { throw 'Run provision first (MYSQL_HOST missing).' }

# Reuse an existing JWT secret if one is already set; otherwise generate once.
$jwt = az webapp config appsettings list -g $rg -n $webapp --query "[?name=='JWT_SECRET'].value | [0]" -o tsv 2>$null
if (-not $jwt) { $jwt = python -c 'import secrets; print(secrets.token_urlsafe(48))' }

$primaryRegion = if ($Cfg['PRIMARY_REGION']) { $Cfg['PRIMARY_REGION'] } else { $Cfg['AZURE_PRIMARY_REGION'] }
$kek           = if ($Cfg['KEK_NAME']) { $Cfg['KEK_NAME'] } else { 'cloudveil-kek' }
$container     = if ($Cfg['STORAGE_CONTAINER']) { $Cfg['STORAGE_CONTAINER'] } else { 'encrypted-files' }
$mysqlDb       = if ($Cfg['MYSQL_DATABASE']) { $Cfg['MYSQL_DATABASE'] } else { 'cloudveil' }

Write-Host "Pushing application settings to $webapp (secrets not displayed)..."
az webapp config appsettings set -g $rg -n $webapp --only-show-errors -o none --settings `
    FLASK_CONFIG=prod `
    FLASK_APP=app:create_app `
    SCM_DO_BUILD_DURING_DEPLOYMENT=true `
    RUN_SEED=false `
    KEYVAULT_URL=$($Cfg['KEYVAULT_URL']) `
    KEK_NAME=$kek `
    STORAGE_ACCOUNT_URL=$($Cfg['STORAGE_ACCOUNT_URL']) `
    STORAGE_CONTAINER=$container `
    PRIMARY_REGION=$primaryRegion `
    MYSQL_HOST=$($Cfg['MYSQL_HOST']) `
    MYSQL_PORT=3306 `
    MYSQL_USER=$($Cfg['MYSQL_ADMIN_USER']) `
    MYSQL_PASSWORD=$($Cfg['MYSQL_ADMIN_PASSWORD']) `
    MYSQL_DATABASE=$mysqlDb `
    MYSQL_SSL_CA=app/certs/DigiCertGlobalRootCA.crt.pem `
    JWT_SECRET=$jwt `
    SEED_ADMIN_EMAIL=$($Cfg['SEED_ADMIN_EMAIL']) `
    SEED_ADMIN_PASSWORD=$($Cfg['SEED_ADMIN_PASSWORD']) `
    APPLICATIONINSIGHTS_CONNECTION_STRING=$($Cfg['APPLICATIONINSIGHTS_CONNECTION_STRING'])

Write-Host 'Application settings updated.'
