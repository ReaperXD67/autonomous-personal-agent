[CmdletBinding()]
param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not $SkipBuild) {
        docker compose build action-worker
        if ($LASTEXITCODE -ne 0) { throw 'Browser test image build failed' }
    }
    $webPath = Join-Path $projectRoot 'services/control-api/app/web'
    $proofPath = Join-Path $projectRoot 'output/playwright/career'
    New-Item -ItemType Directory -Force -Path $proofPath | Out-Null
    Get-Content -Raw (Join-Path $PSScriptRoot 'career-ui-smoke.py') |
        docker run --rm -i --network none --read-only --cap-drop ALL `
            --security-opt no-new-privileges --tmpfs /tmp:size=256m `
            --mount "type=bind,source=$webPath,target=/web,readonly" `
            --mount "type=bind,source=$proofPath,target=/proof" `
            --entrypoint python autonomous-personal-agent/action-worker:local -
    if ($LASTEXITCODE -ne 0) { throw 'Career dashboard browser proof failed' }
}
finally {
    Pop-Location
}
