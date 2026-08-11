[CmdletBinding()]
param(
    [switch]$Agent
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }
    if ($Agent) {
        docker compose --profile agent up -d --build
    }
    else {
        docker compose up -d --build
    }
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
}
finally {
    Pop-Location
}

