[CmdletBinding()]
param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not $SkipBuild) {
        docker compose build action-worker
        if ($LASTEXITCODE -ne 0) { throw 'Browser proof image build failed' }
    }
    $sourcePath = Join-Path $projectRoot 'services/control-api'
    Get-Content -Raw (Join-Path $PSScriptRoot 'application-field-safety-smoke.py') |
        docker run --rm -i --network none --read-only --cap-drop ALL `
            --security-opt no-new-privileges --tmpfs /tmp:size=256m --workdir /tmp `
            --mount "type=bind,source=$sourcePath,target=/source,readonly" `
            -e PYTHONPATH=/source --entrypoint python autonomous-personal-agent/action-worker:local -
    if ($LASTEXITCODE -ne 0) { throw 'Application field browser safety proof failed' }
}
finally {
    Pop-Location
}
