[CmdletBinding()]
param(
    [switch]$LocalModel,
    [switch]$SideEffects,
    [switch]$SideEffectsTest,
    [switch]$CopyToken
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }

    & (Join-Path $PSScriptRoot 'up.ps1') -Agent -LocalModel:$LocalModel -SideEffects:$SideEffects -SideEffectsTest:$SideEffectsTest
    & (Join-Path $PSScriptRoot 'health.ps1') -Agent -SideEffects:$SideEffects -SideEffectsTest:$SideEffectsTest

    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $dashboardUrl = "http://127.0.0.1:$port/"

    $headers = @{ Authorization = "Bearer $($values.CONTROL_API_TOKEN)" }
    $bootstrap = Invoke-RestMethod -Method Post -Uri "${dashboardUrl}v1/auth/browser-bootstrap" -Headers $headers -TimeoutSec 15
    if (-not $bootstrap.code) { throw 'The control API did not return a browser bootstrap code.' }
    $launchUrl = "$dashboardUrl#bootstrap=$($bootstrap.code)"

    if ($CopyToken) {
        Set-Clipboard -Value $values.CONTROL_API_TOKEN
        Write-Warning '-CopyToken is a recovery option. The dashboard will already authenticate automatically; clear the clipboard after troubleshooting.'
    }

    Start-Process $launchUrl
    Write-Host "Dashboard opened and authenticated automatically: $dashboardUrl"
    if (-not $CopyToken) {
        Write-Host 'The long-lived control token was not copied, printed, or stored by the browser.'
    }
    if (-not $LocalModel) {
        Write-Host 'Qwen remains unloaded unless both hosted routes fail. Add -LocalModel only to exercise that fallback now.'
    }
    if (-not $SideEffects -and -not $SideEffectsTest) {
        Write-Host 'Add -SideEffects for the isolated browser/email executor, or -SideEffectsTest for harmless local fixtures.'
    }
}
finally {
    Pop-Location
}
