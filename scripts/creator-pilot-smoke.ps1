$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $migrationSources = @(
        Get-ChildItem -LiteralPath 'config/postgres/init' -Filter '*.sql' -File |
            Sort-Object Name |
            ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw }
    )
    $migrationJson = ConvertTo-Json -InputObject $migrationSources -Compress
    $migrationBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($migrationJson))
    $probeSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'creator-pilot-smoke.py') -Raw
    $probeBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($probeSource))
    $bootstrap = @"
import base64, json
migrations = json.loads(base64.b64decode('$migrationBase64'))
source = base64.b64decode('$probeBase64')
exec(compile(source, 'scripts/creator-pilot-smoke.py', 'exec'), {'__name__': '__main__', 'MIGRATIONS': migrations})
"@
    $bootstrap | docker compose exec -T control-api python -
    if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL creator pilot smoke failed' }
}
finally {
    Pop-Location
}
