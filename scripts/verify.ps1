$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed' }
    docker compose build control-api dispatcher worker job-worker action-worker test
    if ($LASTEXITCODE -ne 0) { throw 'Image build failed' }
    & (Join-Path $PSScriptRoot 'test.ps1') -SkipBuild
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'Stack startup failed' }
    & (Join-Path $PSScriptRoot 'health.ps1')
    & (Join-Path $PSScriptRoot 'smoke.ps1')
    & (Join-Path $PSScriptRoot 'recovery-smoke.ps1')
    & (Join-Path $PSScriptRoot 'lifecycle-smoke.ps1')
    & (Join-Path $PSScriptRoot 'workflow-smoke.ps1')
    & (Join-Path $PSScriptRoot 'scheduler-smoke.ps1')
    & (Join-Path $PSScriptRoot 'creator-research-smoke.ps1')
    & (Join-Path $PSScriptRoot 'career-autopilot-smoke.ps1')
    & (Join-Path $PSScriptRoot 'planning-smoke.ps1')
    & (Join-Path $PSScriptRoot 'action-delivery-smoke.ps1')
    Get-Content -Raw (Join-Path $PSScriptRoot 'queue-recovery-smoke.py') |
        docker compose exec -T control-api python -
    if ($LASTEXITCODE -ne 0) { throw 'Queue recovery smoke failed' }
}
finally {
    Pop-Location
}
