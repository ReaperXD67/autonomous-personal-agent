[CmdletBinding()]
param(
    [switch]$LocalModel,
    [switch]$CopyToken
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }

    & (Join-Path $PSScriptRoot 'up.ps1')
    if ($LocalModel) {
        & (Join-Path $PSScriptRoot 'local-model.ps1')
    }
    & (Join-Path $PSScriptRoot 'health.ps1')

    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $dashboardUrl = "http://127.0.0.1:$port/"

    if ($CopyToken) {
        Set-Clipboard -Value $values.CONTROL_API_TOKEN
        Write-Warning 'The private dashboard token is on the Windows clipboard. Paste it only into this local dashboard, then replace the clipboard contents.'
    }

    Start-Process $dashboardUrl
    Write-Host "Dashboard opened: $dashboardUrl"
    if (-not $CopyToken) {
        Write-Host 'Run again with -CopyToken to place the private connection token on the clipboard without printing it.'
    }
    if (-not $LocalModel) {
        Write-Host 'Add -LocalModel when you want private resume-tailored application drafts.'
    }
}
finally {
    Pop-Location
}
