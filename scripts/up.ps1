[CmdletBinding()]
param(
    [switch]$Agent,
    [switch]$LocalModel
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }
    $arguments = @('compose')
    if ($Agent) { $arguments += @('--profile', 'agent') }
    if ($LocalModel) { $arguments += @('--profile', 'local-model') }
    $arguments += @('up', '-d', '--build')
    & docker $arguments
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
}
finally {
    Pop-Location
}
