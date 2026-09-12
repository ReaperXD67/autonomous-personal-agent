[CmdletBinding()]
param(
    [switch]$SkipRestore,
    [switch]$SkipRemoteInference,
    [switch]$SkipOpenRouter,
    [switch]$SkipLocalInference,
    [switch]$SkipHermes
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$results = [System.Collections.Generic.List[object]]::new()
$failures = [System.Collections.Generic.List[string]]::new()
$runStarted = [DateTime]::UtcNow

function Add-SkippedCheck {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$Reason = 'Explicitly skipped by the selected command options.'
    )
    $results.Add([ordered]@{
        name = $Name
        status = 'skipped'
        duration_seconds = 0
        reason = $Reason
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
        $global:LASTEXITCODE = 0
        & $Action
        if (-not $? -or $LASTEXITCODE -ne 0) {
            throw 'The check returned a nonzero exit status.'
        }
        $results.Add([ordered]@{
            name = $Name
            status = 'passed'
            duration_seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2)
            reason = 'The named end-to-end check completed successfully.'
        })
    }
    catch {
        $failures.Add($Name)
        $results.Add([ordered]@{
            name = $Name
            status = 'failed'
            duration_seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2)
            reason = 'The named check failed; inspect its terminal diagnostics before retrying.'
            error_code = 'READINESS_CHECK_FAILED'
        })
        Write-Warning "$Name failed. Raw exception text is excluded from the readiness report."
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

    $openRouterEnabled = $false
    if (Test-Path -LiteralPath '.env') {
        $openRouterEnabled = [bool](
            Get-Content -LiteralPath '.env' |
                Where-Object { $_ -match '^OPENROUTER_ENABLED=true$' } |
                Select-Object -First 1
        )
    }
    if ($SkipOpenRouter -or -not $openRouterEnabled) {
        $reason = if ($SkipOpenRouter) {
            'Explicitly skipped by the selected command options.'
        } else {
            'OpenRouter is not enabled in the local configuration.'
        }
        Add-SkippedCheck 'OpenRouter attested-free inference' -Reason $reason
    }
    else {
        Invoke-ReadinessCheck 'OpenRouter attested-free inference' {
            & (Join-Path $PSScriptRoot 'openrouter.ps1') -Smoke
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
                throw 'Hermes did not return the expected exact harmless canary.'
            }
            Write-Host 'Hermes returned HERMES_READY_OK.'
        }
    }

    $reportRoot = Join-Path $projectRoot 'runtime/readiness'
    New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
    $report = [ordered]@{
        schema_version = 1
        started_at = $runStarted.ToString('o')
        generated_at = [DateTime]::UtcNow.ToString('o')
        git_commit = (git rev-parse HEAD).Trim()
        overall = if ($failures.Count -eq 0) { 'passed' } else { 'failed' }
        checks = $results
    }
    $reportPath = Join-Path $reportRoot 'latest.json'
    $temporaryReportPath = Join-Path $reportRoot ('.latest-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporaryReportPath -Encoding utf8
    if (Test-Path -LiteralPath $reportPath) {
        [IO.File]::Replace($temporaryReportPath, $reportPath, [NullString]::Value)
    } else {
        [IO.File]::Move($temporaryReportPath, $reportPath)
    }

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
