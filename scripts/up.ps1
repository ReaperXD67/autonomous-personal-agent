[CmdletBinding()]
param(
    [switch]$Agent,
    [switch]$LocalModel,
    [switch]$SideEffects,
    [switch]$SideEffectsTest
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$savedProcessEnvironment = @{}
Push-Location $projectRoot
try {
    if ($SideEffects -and $SideEffectsTest) {
        throw 'Choose either -SideEffects or -SideEffectsTest, not both.'
    }
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }
    if ($SideEffectsTest) {
        $testMailSettings = @{
            MAIL_TRANSPORT = 'mailpit'
            SMTP_HOST = 'mailpit'
            SMTP_PORT = '1025'
            SMTP_USERNAME = ''
            SMTP_PASSWORD = ''
            SMTP_FROM = 'hermes@local.invalid'
            SMTP_TLS_MODE = 'none'
        }
        foreach ($name in $testMailSettings.Keys) {
            $savedProcessEnvironment[$name] = [Environment]::GetEnvironmentVariable(
                $name,
                'Process'
            )
            [Environment]::SetEnvironmentVariable(
                $name,
                [string]$testMailSettings[$name],
                'Process'
            )
        }
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
    foreach ($name in $savedProcessEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $savedProcessEnvironment[$name],
            'Process'
        )
    }
    Pop-Location
}
