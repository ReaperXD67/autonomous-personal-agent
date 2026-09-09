[CmdletBinding()]
param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not $SkipBuild) {
        docker compose --profile tools build test
        if ($LASTEXITCODE -ne 0) { throw 'Test image build failed' }
    }
    docker compose --profile tools run --rm test
    if ($LASTEXITCODE -ne 0) { throw 'Containerized tests failed' }
}
finally {
    Pop-Location
}
