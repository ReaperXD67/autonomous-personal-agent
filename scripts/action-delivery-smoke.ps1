$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'action-delivery-smoke.py') |
        docker compose exec -T control-api python -
    if ($LASTEXITCODE -ne 0) { throw 'Action delivery guard smoke failed' }
}
finally {
    Pop-Location
}
