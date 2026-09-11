param([switch]$Live)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $source = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'planning-smoke.py')
    if ($Live) {
        $source | docker compose exec -T control-api python - --live
    }
    else {
        $source | docker compose exec -T control-api python -
    }
    if ($LASTEXITCODE -ne 0) { throw 'Planner smoke failed' }
}
finally {
    Pop-Location
}
