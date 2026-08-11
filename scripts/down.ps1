$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose down --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw 'docker compose down failed' }
}
finally {
    Pop-Location
}

