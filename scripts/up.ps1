[CmdletBinding()]
param(
    [switch]$Agent,
    [switch]$LocalModel,
    [switch]$SideEffects,
    [switch]$SideEffectsTest
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if ($SideEffects -and $SideEffectsTest) {
        throw 'Choose either -SideEffects or -SideEffectsTest, not both.'
    }
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }
    if ($SideEffectsTest) {
        $env:MAIL_TRANSPORT = 'mailpit'
        $env:SMTP_HOST = 'mailpit'
        $env:SMTP_PORT = '1025'
        $env:SMTP_FROM = 'hermes@local.invalid'
        $env:SMTP_TLS_MODE = 'none'
    }
    $arguments = @('compose')
    if ($Agent) { $arguments += @('--profile', 'agent') }
    if ($LocalModel) { $arguments += @('--profile', 'local-model') }
    if ($SideEffects) { $arguments += @('--profile', 'side-effects') }
    if ($SideEffectsTest) { $arguments += @('--profile', 'side-effects-test') }
    $arguments += @('up', '-d', '--build')
    & docker $arguments
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
}
finally {
    Pop-Location
}
