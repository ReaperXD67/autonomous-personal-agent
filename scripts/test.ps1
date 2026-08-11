$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose --profile tools run --rm test
    if ($LASTEXITCODE -ne 0) { throw 'Containerized tests failed' }
}
finally {
    Pop-Location
}

