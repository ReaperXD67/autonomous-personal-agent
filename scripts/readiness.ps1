[CmdletBinding()]
param(
    [switch]$SkipRestore,
    [switch]$SkipRemoteInference,
    [switch]$SkipLocalInference,
    [switch]$SkipHermes
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$results = [System.Collections.Generic.List[object]]::new()
$failures = [System.Collections.Generic.List[string]]::new()

function Add-SkippedCheck {
    param([Parameter(Mandatory)][string]$Name)
    $results.Add([ordered]@{
        name = $Name
        status = 'skipped'
        duration_seconds = 0
    })
}

function Invoke-ReadinessCheck {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $started = [DateTime]::UtcNow
    Write-Host "`n=== $Name ==="
    try {
        & $Action
        $results.Add([ordered]@{
            name = $Name
            status = 'passed'
            duration_seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2)
        })
    }
    catch {
        $failures.Add($Name)
        $results.Add([ordered]@{
            name = $Name
            status = 'failed'
            duration_seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2)
            error = $_.Exception.Message
        })
        Write-Warning "$Name failed: $($_.Exception.Message)"
    }
}

Push-Location $projectRoot
try {
    Invoke-ReadinessCheck 'Core lifecycle verification' {
        & (Join-Path $PSScriptRoot 'verify.ps1')
    }

    if ($SkipRestore) {
        Add-SkippedCheck 'Disposable restore drill'
    }
    else {
        Invoke-ReadinessCheck 'Disposable restore drill' {
            & (Join-Path $PSScriptRoot 'restore-drill.ps1')
        }
    }

    Invoke-ReadinessCheck 'Environment and optional-agent doctor' {
        & (Join-Path $PSScriptRoot 'doctor.ps1') -Agent
    }

    if ($SkipRemoteInference) {
        Add-SkippedCheck 'OmniRoute free/default inference'
    }
    else {
        Invoke-ReadinessCheck 'OmniRoute free/default inference' {
            & (Join-Path $PSScriptRoot 'agent-smoke.ps1')
        }
    }

    if ($SkipLocalInference) {
        Add-SkippedCheck 'Local Qwen GPU inference'
    }
    else {
        Invoke-ReadinessCheck 'Local Qwen GPU inference' {
            & (Join-Path $PSScriptRoot 'local-model.ps1')
        }
    }

    if ($SkipHermes) {
        Add-SkippedCheck 'Hermes routed inference'
    }
    else {
        Invoke-ReadinessCheck 'Hermes routed inference' {
            $output = docker compose --profile agent exec -T hermes hermes -z 'Reply with exactly HERMES_READY_OK and nothing else.' --reasoning none
            $response = ($output -join "`n").Trim()
            if ($LASTEXITCODE -ne 0 -or $response -ne 'HERMES_READY_OK') {
                throw "Hermes returned an unexpected response: $response"
            }
            Write-Host 'Hermes returned HERMES_READY_OK.'
        }
    }

    $reportRoot = Join-Path $projectRoot 'runtime/readiness'
    New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
    $report = [ordered]@{
        generated_at = [DateTime]::UtcNow.ToString('o')
        git_commit = (git rev-parse HEAD).Trim()
        overall = if ($failures.Count -eq 0) { 'passed' } else { 'failed' }
        checks = $results
    }
    $reportPath = Join-Path $reportRoot 'latest.json'
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8

    Write-Host "`nReadiness report: $reportPath"
    foreach ($result in $results) {
        Write-Host ("[{0}] {1} ({2}s)" -f $result.status.ToUpperInvariant(), $result.name, $result.duration_seconds)
    }
    if ($failures.Count -gt 0) {
        throw "Readiness failed: $($failures -join ', ')"
    }
    Write-Host 'READY: all selected checks passed.'
}
finally {
    Pop-Location
}
