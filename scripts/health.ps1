[CmdletBinding()]
param(
    [ValidateRange(5, 300)][int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $required = @('postgres', 'redis', 'control-api', 'dispatcher', 'worker', 'job-worker')
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $states = @{}
    do {
        $allHealthy = $true
        foreach ($service in $required) {
            $containerId = docker compose ps --quiet $service
            if (-not $containerId) {
                $states[$service] = 'not-running'
                $allHealthy = $false
                continue
            }
            $states[$service] = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId
            if ($states[$service] -ne 'healthy') { $allHealthy = $false }
        }
        if (-not $allHealthy) { Start-Sleep -Seconds 2 }
    } while (-not $allHealthy -and (Get-Date) -lt $deadline)

    $failed = @()
    foreach ($service in $required) {
        $health = $states[$service]
        Write-Host ("{0,-14} {1}" -f $service, $health)
        if ($health -ne 'healthy') { $failed += "${service}:$health" }
    }

    $portLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^CONTROL_API_PORT=' } | Select-Object -First 1
    $port = if ($portLine) { $portLine.Split('=', 2)[1] } else { '8080' }
    $ready = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$port/health/ready" -TimeoutSec 5
    Write-Host ("control-ready  {0}" -f $ready.status)
    if ($ready.status -ne 'ready') {
        $failed += 'control-api:not-ready'
    }

    if ($failed.Count -gt 0) {
        throw "Health checks failed: $($failed -join ', ')"
    }
}
finally {
    Pop-Location
}
