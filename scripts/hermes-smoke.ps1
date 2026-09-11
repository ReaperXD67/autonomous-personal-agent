$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $output = docker compose --profile agent exec -T hermes hermes -z 'Reply with exactly HERMES_READY_OK and nothing else.' --reasoning none
    if ($LASTEXITCODE -ne 0 -or ($output -join "`n").Trim() -ne 'HERMES_READY_OK') {
        throw 'Hermes did not return the expected exact harmless canary.'
    }
    Write-Host 'Hermes returned HERMES_READY_OK.'
}
finally { Pop-Location }
