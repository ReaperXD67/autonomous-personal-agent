[CmdletBinding()]
param(
    [ValidateSet('core', 'restore', 'environment', 'omniroute', 'openrouter', 'local_model',
        'hermes', 'career', 'side_effects', 'creator_outreach', 'youtube', 'planning', 'scheduler')]
    [string[]]$Checks = @('core', 'restore', 'environment', 'omniroute', 'openrouter',
        'local_model', 'hermes', 'career', 'side_effects', 'creator_outreach', 'youtube', 'planning', 'scheduler'),
    [switch]$UseReadinessReport,
    [switch]$PublishReport,
    [switch]$PublishOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportRoot = Join-Path $projectRoot 'runtime/feature-tests'
$reportPath = Join-Path $reportRoot 'latest.json'
$runStarted = [DateTime]::UtcNow
$powershellExecutable = (Get-Process -Id $PID).Path
$checkIds = @('core', 'restore', 'environment', 'omniroute', 'openrouter', 'local_model',
    'hermes', 'career', 'side_effects', 'creator_outreach', 'youtube', 'planning', 'scheduler')
$results = [ordered]@{}
foreach ($checkId in $checkIds) {
    $results[$checkId] = [ordered]@{
        id = $checkId; status = 'skipped'; duration_seconds = 0; reason_code = 'NOT_SELECTED'
    }
}

function Invoke-FeatureCheck {
    param([string]$Id, [string]$Script, [string[]]$Arguments = @())
    if ($Checks -notcontains $Id) { return }
    $scriptPath = Join-Path $PSScriptRoot $Script
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        $results[$Id].reason_code = 'NOT_IMPLEMENTED'
        return
    }
    $started = [DateTime]::UtcNow
    Write-Host "`nFeature check: $Id"
    try {
        & $powershellExecutable -NoLogo -NoProfile -File $scriptPath @Arguments
        $checkExitCode = $LASTEXITCODE
        if ($checkExitCode -ne 0) { throw 'Feature subprocess returned a nonzero exit status.' }
        $results[$Id].status = 'passed'
        $results[$Id].reason_code = 'CHECK_PASSED'
    }
    catch {
        $results[$Id].status = 'failed'
        $results[$Id].reason_code = 'CHECK_FAILED'
        Write-Warning "Feature check '$Id' failed; no raw output or exception is saved in the report."
    }
    $results[$Id].duration_seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2)
}

function Get-FeatureSignals {
    $signals = [ordered]@{
        core_online = $false; research_worker_online = $false; action_worker_online = $false
        ollama_online = $false; hermes_online = $false; omniroute_online = $false
        openrouter_enabled = $false; youtube_configured = $false; mail_transport = 'disabled'
        external_smtp_configured = $false; local_model_cached = $false
    }
    $healthDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $serviceStates = @{}
        $healthStarting = $false
        $stateLines = @(& docker compose ps --all --format json 2>$null)
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect runtime service state.' }
        foreach ($line in $stateLines) {
            foreach ($service in @($line | ConvertFrom-Json)) {
                if ([string]$service.Health -eq 'starting') { $healthStarting = $true }
                $serviceStates[[string]$service.Service] = (
                    [string]$service.State -eq 'running' -and [string]$service.Health -eq 'healthy'
                )
            }
        }
        if ($healthStarting -and [DateTime]::UtcNow -lt $healthDeadline) { Start-Sleep -Seconds 1 }
    } while ($healthStarting -and [DateTime]::UtcNow -lt $healthDeadline)
    $signals.core_online = @('postgres', 'redis', 'control-api', 'dispatcher', 'worker') |
        ForEach-Object { [bool]$serviceStates[$_] } |
        Where-Object { -not $_ } |
        Measure-Object | Select-Object -ExpandProperty Count
    $signals.core_online = $signals.core_online -eq 0
    $signals.research_worker_online = [bool]$serviceStates['job-worker']
    $signals.action_worker_online = [bool]$serviceStates['action-worker']
    $signals.ollama_online = [bool]$serviceStates['ollama']
    $signals.hermes_online = [bool]$serviceStates['hermes']
    $signals.omniroute_online = [bool]$serviceStates['omniroute']
    if ($signals.research_worker_online) {
        $probe = @'
import json, os, urllib.request
from app.settings import get_settings
s = get_settings()
result = {"openrouter_enabled": s.openrouter_enabled, "youtube_configured": bool(s.youtube_api_key), "local_model_cached": False}
try:
    with urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5) as response:
        models = json.load(response).get("models", [])
    result["local_model_cached"] = any(item.get("name") == s.local_model for item in models)
except Exception:
    pass
print(json.dumps(result))
'@
        $probeOutput = $probe | & docker compose exec -T job-worker python - 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect allowlisted research-worker signals.' }
        $modelSignals = ($probeOutput -join "`n") | ConvertFrom-Json
        $signals.openrouter_enabled = [bool]$modelSignals.openrouter_enabled
        $signals.youtube_configured = [bool]$modelSignals.youtube_configured
        $signals.local_model_cached = [bool]$modelSignals.local_model_cached
    }
    if ($signals.action_worker_online) {
        $probe = @'
import json
from app.settings import get_settings
s = get_settings()
transport = s.mail_transport if s.mail_transport in {"disabled", "mailpit", "smtp"} else "disabled"
external = transport == "smtp" and bool(s.smtp_host and s.smtp_from) and s.smtp_tls_mode in {"starttls", "ssl"}
print(json.dumps({"mail_transport": transport, "external_smtp_configured": external}))
'@
        $probeOutput = $probe | & docker compose exec -T action-worker python - 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect allowlisted action-worker signals.' }
        $mailSignals = ($probeOutput -join "`n") | ConvertFrom-Json
        $signals.mail_transport = [string]$mailSignals.mail_transport
        $signals.external_smtp_configured = [bool]$mailSignals.external_smtp_configured
    }
    return $signals
}

function Publish-FeatureReport {
    param([Parameter(Mandatory)]$Report)
    # Read only the two launcher settings required for this authenticated local
    # request. The bearer value is never printed, saved, or passed to a process.
    $token = $null
    $port = '8080'
    foreach ($line in Get-Content -LiteralPath (Join-Path $projectRoot '.env')) {
        if ($line -match '^CONTROL_API_TOKEN=(.*)$') { $token = $Matches[1].Trim() }
        elseif ($line -match '^CONTROL_API_PORT=([0-9]+)$') { $port = $Matches[1] }
    }
    if (-not $token) { throw 'REPORT_PUBLISH_AUTH_UNAVAILABLE' }
    try {
        $body = $Report | ConvertTo-Json -Depth 8
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/v1/readiness/reports" `
            -Headers @{ Authorization = "Bearer $token" } -ContentType 'application/json' `
            -Body $body -TimeoutSec 20 | Out-Null
        Write-Host 'Readiness evidence persisted through the authenticated control API.'
    }
    catch {
        throw 'REPORT_PUBLISH_FAILED: local JSON is retained; database publication was not confirmed.'
    }
    finally { $token = $null }
}

Push-Location $projectRoot
try {
    if ($PublishOnly) {
        if (-not (Test-Path -LiteralPath $reportPath)) { throw 'No previous feature report exists.' }
        Publish-FeatureReport -Report (Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json)
        return
    }
    $commit = (& git rev-parse HEAD).Trim()
    if ($commit -notmatch '^[0-9a-f]{40}$') { throw 'Could not identify the source revision.' }
    $dirtyAtStart = [bool](@(& git status --porcelain).Count)
    $baselineNames = [ordered]@{
        core = 'Core lifecycle verification'; restore = 'Disposable restore drill'
        environment = 'Environment and optional-agent doctor'; omniroute = 'OmniRoute free/default inference'
        openrouter = 'OpenRouter attested-free inference'; local_model = 'Local Qwen GPU inference'
        hermes = 'Hermes routed inference'
    }
    $selectedBaseline = @($baselineNames.Keys | Where-Object { $Checks -contains $_ })
    if ($UseReadinessReport) {
        $readinessPath = Join-Path $projectRoot 'runtime/readiness/latest.json'
        if (-not (Test-Path -LiteralPath $readinessPath)) { throw 'No readiness report exists to reuse.' }
        $baseline = Get-Content -LiteralPath $readinessPath -Raw | ConvertFrom-Json
        if ($baseline.git_commit -ne $commit -or -not $baseline.started_at -or
            ([DateTime]::UtcNow - [DateTime]$baseline.generated_at).TotalHours -gt 2 -or
            [DateTime]$baseline.generated_at -gt [DateTime]::UtcNow) {
            throw 'Readiness reuse requires the same revision and an original report less than two hours old.'
        }
        $runStarted = [DateTime]$baseline.started_at
        foreach ($id in $selectedBaseline) {
            $original = @($baseline.checks | Where-Object { $_.name -eq $baselineNames[$id] })
            if ($original.Count -ne 1 -or $original[0].status -notin @('passed', 'failed', 'skipped')) {
                throw 'The previous readiness report has an unsupported check shape.'
            }
            $results[$id].status = [string]$original[0].status
            $results[$id].duration_seconds = [double]$original[0].duration_seconds
            $results[$id].reason_code = 'REUSED_READINESS_' + $original[0].status.ToUpperInvariant()
        }
    }
    else {
        Invoke-FeatureCheck 'core' 'verify.ps1'
        Invoke-FeatureCheck 'restore' 'restore-drill.ps1'
        Invoke-FeatureCheck 'environment' 'doctor.ps1' @('-Agent')
        Invoke-FeatureCheck 'omniroute' 'agent-smoke.ps1'
        $openrouterConfigured = [bool](Get-Content -LiteralPath '.env' |
            Where-Object { $_ -match '^OPENROUTER_ENABLED=true$' } | Select-Object -First 1)
        if ($openrouterConfigured) { Invoke-FeatureCheck 'openrouter' 'openrouter.ps1' @('-Smoke') }
        elseif ($Checks -contains 'openrouter') { $results['openrouter'].reason_code = 'NOT_CONFIGURED' }
        Invoke-FeatureCheck 'local_model' 'local-model.ps1'
        Invoke-FeatureCheck 'hermes' 'hermes-smoke.ps1'
    }
    Invoke-FeatureCheck 'career' 'career-smoke.ps1' @('-Draft')
    Invoke-FeatureCheck 'side_effects' 'side-effect-smoke.ps1'
    Invoke-FeatureCheck 'creator_outreach' 'creator-outreach-smoke.ps1'
    $youtubeConfigured = [bool](Get-Content -LiteralPath '.env' |
        Where-Object { $_ -match '^YOUTUBE_API_KEY=\S+' -and $_ -notmatch '=CHANGE_ME' } | Select-Object -First 1)
    if ($youtubeConfigured) { Invoke-FeatureCheck 'youtube' 'youtube-smoke.ps1' }
    elseif ($Checks -contains 'youtube') { $results['youtube'].reason_code = 'NOT_CONFIGURED' }
    Invoke-FeatureCheck 'planning' 'planning-smoke.ps1' @('-Live')
    Invoke-FeatureCheck 'scheduler' 'scheduler-smoke.ps1'
    $signals = Get-FeatureSignals
    $report = [ordered]@{
        run_id = [Guid]::NewGuid().ToString()
        git_commit = $commit
        working_tree_dirty = $dirtyAtStart -or [bool](@(& git status --porcelain).Count)
        started_at = $runStarted.ToString('o')
        completed_at = [DateTime]::UtcNow.ToString('o')
        checks = @($results.Values)
        signals = $signals
    }
    New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
    $temporaryPath = Join-Path $reportRoot ('.latest-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryPath -Encoding utf8
    if (Test-Path -LiteralPath $reportPath) { [IO.File]::Replace($temporaryPath, $reportPath, [NullString]::Value) }
    else { [IO.File]::Move($temporaryPath, $reportPath) }
    Write-Host "`nFeature evidence: $reportPath"
    foreach ($result in $results.Values) {
        Write-Host ("[{0}] {1}: {2} ({3}s)" -f $result.status, $result.id, $result.reason_code, $result.duration_seconds)
    }
    if ($PublishReport) { Publish-FeatureReport -Report $report }
    if (@($results.Values | Where-Object { $_.status -eq 'failed' }).Count -gt 0) {
        throw 'FEATURE_CHECKS_FAILED: inspect the safe report and current terminal diagnostics.'
    }
}
finally { Pop-Location }
