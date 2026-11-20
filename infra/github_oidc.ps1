<#
  infra/github_oidc.ps1 — GitHub Actions -> Azure OIDC setup (equivalent of github_oidc.sh).
  Requires permission to create Entra app registrations.
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_env.ps1"

$repo = $Cfg['GITHUB_REPO']
if (-not $repo) { throw 'GITHUB_REPO missing in .env' }
$rg = $Names.RG
$appName = 'cloudveil-github-oidc'
$subject = "repo:${repo}:ref:refs/heads/main"

az account set --subscription $Cfg['AZURE_SUBSCRIPTION_ID'] --only-show-errors
$tenantId = az account show --query tenantId -o tsv

Write-Host "=== Entra app registration '$appName' ==="
$appId = az ad app list --display-name $appName --query '[0].appId' -o tsv
if (-not $appId) { $appId = az ad app create --display-name $appName --query appId -o tsv; "created app $appId" }
else { "reusing app $appId" }

az ad sp show --id $appId 2>$null *> $null
if ($LASTEXITCODE -ne 0) { az ad sp create --id $appId -o none }
$spOid = az ad sp show --id $appId --query id -o tsv

Write-Host "=== Federated credential for $subject ==="
$existing = az ad app federated-credential list --id $appId --query "[?subject=='$subject']" -o tsv
if (-not $existing) {
    $params = @{ name='github-main'; issuer='https://token.actions.githubusercontent.com'; subject=$subject; audiences=@('api://AzureADTokenExchange') } | ConvertTo-Json -Compress
    az ad app federated-credential create --id $appId --parameters $params -o none
    'created'
} else { 'exists' }

Write-Host "=== Contributor on resource group $rg ==="
$rgId = az group show -n $rg --query id -o tsv
az role assignment create --assignee-object-id $spOid --assignee-principal-type ServicePrincipal --role Contributor --scope $rgId -o none 2>$null

Write-Host "=== Setting GitHub Actions secrets on $repo ==="
gh secret set AZURE_CLIENT_ID       --repo $repo --body $appId
gh secret set AZURE_TENANT_ID       --repo $repo --body $tenantId
gh secret set AZURE_SUBSCRIPTION_ID --repo $repo --body $Cfg['AZURE_SUBSCRIPTION_ID']
Write-Host 'Done.'
