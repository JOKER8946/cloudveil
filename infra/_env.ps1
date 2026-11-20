<#
  infra/_env.ps1 — shared helper for the PowerShell infra scripts.
  Dot-source it:  . "$PSScriptRoot/_env.ps1"
  Then use $Cfg['KEY'] and Set-EnvValue / Get-DerivedNames.
#>

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { throw "Env file not found: $Path" }
    $cfg = @{}
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $idx = $line.IndexOf('=')
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1)
        if ($key) { $cfg[$key] = $val }
    }
    return $cfg
}

function Set-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content $Path | Where-Object { $_ -notmatch "^$([regex]::Escape($Key))=" }
    }
    $lines += "$Key=$Value"
    Set-Content -Path $Path -Value $lines -Encoding utf8
}

$Script:EnvFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
$Cfg = Import-DotEnv -Path $Script:EnvFile

# Derived, non-secret resource names (mirror of provision.sh).
$Names = @{
    RG           = $Cfg['AZURE_RESOURCE_GROUP']
    LOC          = $Cfg['AZURE_PRIMARY_REGION']
    LOC2         = $Cfg['AZURE_SECONDARY_REGION']
    KV           = "kv-$($Cfg['NAME_PREFIX'])"
    KEK          = if ($Cfg['KEK_NAME']) { $Cfg['KEK_NAME'] } else { 'cloudveil-kek' }
    SA_PRIMARY   = "$($Cfg['NAME_PREFIX'])pri"
    SA_SECONDARY = "$($Cfg['NAME_PREFIX'])sec"
    CONTAINER    = if ($Cfg['STORAGE_CONTAINER']) { $Cfg['STORAGE_CONTAINER'] } else { 'encrypted-files' }
    MYSQL        = "mysql-$($Cfg['NAME_PREFIX'])"
    MYSQL_DB     = 'cloudveil'
    LAW          = "log-$($Cfg['NAME_PREFIX'])"
    APPI         = "appi-$($Cfg['NAME_PREFIX'])"
    PLAN         = "plan-$($Cfg['NAME_PREFIX'])"
    WEBAPP       = $Cfg['NAME_PREFIX']
}
