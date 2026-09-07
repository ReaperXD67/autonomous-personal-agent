[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$ConfigureYouTube,
    [switch]$ConfigureGmail,
    [switch]$LocalTest,
    [switch]$Start,
    [switch]$OpenDashboard
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'

function Read-EnvironmentFile {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function Set-EnvironmentEntry {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value
    )
    $lines = [Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match "^$([regex]::Escape($Name))=") {
            $lines.Add("$Name=$Value")
            $found = $true
        }
        else { $lines.Add($line) }
    }
    if (-not $found) { $lines.Add("$Name=$Value") }
    [IO.File]::WriteAllLines($envPath, $lines, [Text.UTF8Encoding]::new($false))
}

function Convert-SecureValue {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Test-ConfiguredSecret {
    param([AllowEmptyString()][string]$Value)
    return $Value -and -not $Value.StartsWith('CHANGE_ME')
}

function Test-DockerReady {
    $probe = Start-Job -ScriptBlock {
        & docker version --format '{{.Server.Version}}' *> $null
        return $LASTEXITCODE
    }
    try {
        if (-not (Wait-Job -Job $probe -Timeout 3)) { return $false }
        return [int](Receive-Job -Job $probe) -eq 0
    }
    finally {
        Stop-Job -Job $probe -ErrorAction SilentlyContinue
        Remove-Job -Job $probe -Force -ErrorAction SilentlyContinue
    }
}

function Start-DockerIfNeeded {
    if (Test-DockerReady) { return }
    $desktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $desktop)) {
        throw 'Docker Desktop is not running and its standard executable was not found.'
    }
    Write-Host 'Starting Docker Desktop...'
    Start-Process -FilePath $desktop -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        if (Test-DockerReady) { return }
        Start-Sleep -Seconds 1
    }
    throw 'Docker Desktop did not become ready within 40 seconds. Open it once, then rerun this command.'
}

function Get-RunningServiceEnvironment {
    param([Parameter(Mandatory)][string]$Service)
    try {
        $containerId = @(& docker compose ps --status running -q $Service 2>$null) |
            Select-Object -First 1
        if (-not $containerId) { return $null }
        $environmentJson = & docker inspect --format '{{json .Config.Env}}' $containerId 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $environmentJson) { return $null }
        $environment = @{}
        foreach ($entry in @($environmentJson | ConvertFrom-Json)) {
            $parts = ([string]$entry).Split('=', 2)
            $environment[$parts[0]] = if ($parts.Count -eq 2) { $parts[1] } else { '' }
        }
        return $environment
    }
    catch { return $null }
}

function Show-PromotionStatus {
    $values = Read-EnvironmentFile
    $youtubeReady = Test-ConfiguredSecret ([string]$values.YOUTUBE_API_KEY)
    $smtpReady = (
        $values.MAIL_TRANSPORT -eq 'smtp' -and
        $values.SMTP_HOST -and
        $values.SMTP_FROM -and
        $values.SMTP_USERNAME -and
        (Test-ConfiguredSecret ([string]$values.SMTP_PASSWORD)) -and
        $values.SMTP_TLS_MODE -in @('starttls', 'ssl')
    )
    $dockerReady = Test-DockerReady
    $apiReady = $false
    $emailExecutorReady = $false
    $jobWorkerEnvironment = $null
    $actionWorkerEnvironment = $null
    if ($dockerReady) {
        $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health/ready" -TimeoutSec 3
            $apiReady = $health.status -eq 'ready'
        }
        catch { $apiReady = $false }
        $jobWorkerEnvironment = Get-RunningServiceEnvironment -Service 'job-worker'
        $actionWorkerEnvironment = Get-RunningServiceEnvironment -Service 'action-worker'
        try {
            $actionState = @(& docker compose ps --status running --format json action-worker 2>$null)
            if ($LASTEXITCODE -eq 0 -and $actionState.Count -gt 0) {
                $containers = @($actionState | ConvertFrom-Json)
                $emailExecutorReady = @(
                    $containers | Where-Object { $_.Health -eq 'healthy' }
                ).Count -gt 0
            }
        }
        catch { $emailExecutorReady = $false }
    }

    $youtubeLoaded = (
        $youtubeReady -and
        $jobWorkerEnvironment -and
        $jobWorkerEnvironment.YOUTUBE_API_KEY -eq $values.YOUTUBE_API_KEY
    )
    $smtpConfigurationLoaded = (
        $smtpReady -and
        $actionWorkerEnvironment -and
        $actionWorkerEnvironment.MAIL_TRANSPORT -eq $values.MAIL_TRANSPORT -and
        $actionWorkerEnvironment.SMTP_HOST -eq $values.SMTP_HOST -and
        $actionWorkerEnvironment.SMTP_PORT -eq $values.SMTP_PORT -and
        $actionWorkerEnvironment.SMTP_USERNAME -eq $values.SMTP_USERNAME -and
        $actionWorkerEnvironment.SMTP_PASSWORD -eq $values.SMTP_PASSWORD -and
        $actionWorkerEnvironment.SMTP_FROM -eq $values.SMTP_FROM -and
        $actionWorkerEnvironment.SMTP_TLS_MODE -eq $values.SMTP_TLS_MODE
    )
    $smtpRuntimeMatches = $smtpConfigurationLoaded -and $emailExecutorReady
    $localMailpitConfigurationLoaded = (
        $actionWorkerEnvironment -and
        $actionWorkerEnvironment.MAIL_TRANSPORT -eq 'mailpit' -and
        -not $actionWorkerEnvironment.SMTP_USERNAME -and
        -not $actionWorkerEnvironment.SMTP_PASSWORD
    )
    $youtubeStatus = if (-not $youtubeReady) {
        'needs restricted API key'
    }
    elseif ($youtubeLoaded) {
        'key loaded; one real scan still needs proof'
    }
    elseif ($jobWorkerEnvironment) {
        'key saved; restart job-worker to load it'
    }
    else {
        'key saved; it will load on start'
    }
    $smtpStatus = if ($smtpReady) {
        'settings saved; owned-inbox proof still required'
    }
    else {
        'needs provider credential after local proof'
    }
    $executorStatus = if ($smtpRuntimeMatches) {
        'running with current SMTP settings'
    }
    elseif ($smtpConfigurationLoaded) {
        'current SMTP settings loaded; health pending or failed'
    }
    elseif ($localMailpitConfigurationLoaded -and $emailExecutorReady) {
        'running in isolated Mailpit test mode'
    }
    elseif ($localMailpitConfigurationLoaded) {
        'Mailpit test mode loaded; health pending or failed'
    }
    elseif ($emailExecutorReady) {
        'running with stale or different settings'
    }
    elseif ($actionWorkerEnvironment) {
        'started with stale or different settings; health pending or failed'
    }
    else {
        'not running'
    }

    Write-Host 'Promotion readiness'
    Write-Host ("  Docker engine:        {0}" -f $(if ($dockerReady) { 'ready' } else { 'stopped' }))
    Write-Host ("  Control dashboard:    {0}" -f $(if ($apiReady) { 'ready' } else { 'not running' }))
    Write-Host ("  YouTube discovery:    {0}" -f $youtubeStatus)
    Write-Host ("  Real email transport: {0}" -f $smtpStatus)
    Write-Host ("  Email executor:       {0}" -f $executorStatus)
    Write-Host '  Promotion kit:        built in; no account or API key required'
    Write-Host 'Local proof: ./scripts/promotion.ps1 -LocalTest' -ForegroundColor Cyan
    if (-not $youtubeReady) { Write-Host 'Next: ./scripts/promotion.ps1 -ConfigureYouTube' -ForegroundColor Yellow }
    if (-not $smtpReady) { Write-Host 'After local proof: ./scripts/promotion.ps1 -ConfigureGmail' -ForegroundColor Yellow }
    if (
        $youtubeReady -and
        $smtpReady -and
        (-not $apiReady -or -not $youtubeLoaded -or -not $smtpRuntimeMatches)
    ) {
        Write-Host 'Next: ./scripts/promotion.ps1 -OpenDashboard' -ForegroundColor Cyan
    }
}

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $envPath)) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }

    if ($ConfigureYouTube) {
        $secure = Read-Host 'Paste a restricted YouTube Data API v3 key (input is hidden)' -AsSecureString
        $apiKey = Convert-SecureValue $secure
        if (-not $apiKey -or $apiKey.Length -lt 20) {
            throw 'The YouTube API key is empty or too short. Nothing was written.'
        }
        $verified = $false
        try {
            $encoded = [Uri]::EscapeDataString($apiKey)
            $uri = "https://www.googleapis.com/youtube/v3/channels?part=id&id=UC_x5XG1OV2P6uZZ5FSM9Ttw&key=$encoded"
            $response = Invoke-RestMethod -Uri $uri -TimeoutSec 20
            $verified = @($response.items).Count -eq 1
        }
        catch { $verified = $false }
        if (-not $verified) {
            throw 'YouTube rejected the key or the API is unreachable. Nothing was written; verify API enablement and restrictions.'
        }
        Set-EnvironmentEntry -Name 'YOUTUBE_API_KEY' -Value $apiKey
        $apiKey = $null
        Write-Host 'Validated the key and stored it only in ignored .env.' -ForegroundColor Green
    }

    if ($ConfigureGmail) {
        $sender = (Read-Host 'Gmail or Google Workspace sender address').Trim()
        try { $sender = ([Net.Mail.MailAddress]::new($sender)).Address }
        catch { throw 'Enter one valid sender email address. Nothing was written.' }
        $secure = Read-Host 'Paste the Google app password (input is hidden)' -AsSecureString
        $password = (Convert-SecureValue $secure) -replace '\s', ''
        if ($password.Length -lt 16) {
            throw 'The app password is too short. Nothing was written.'
        }
        Set-EnvironmentEntry -Name 'MAIL_TRANSPORT' -Value 'smtp'
        Set-EnvironmentEntry -Name 'SMTP_HOST' -Value 'smtp.gmail.com'
        Set-EnvironmentEntry -Name 'SMTP_PORT' -Value '587'
        Set-EnvironmentEntry -Name 'SMTP_USERNAME' -Value $sender
        Set-EnvironmentEntry -Name 'SMTP_PASSWORD' -Value $password
        Set-EnvironmentEntry -Name 'SMTP_FROM' -Value $sender
        Set-EnvironmentEntry -Name 'SMTP_TLS_MODE' -Value 'starttls'
        $password = $null
        Write-Host 'Stored Gmail TLS SMTP settings only in ignored .env.' -ForegroundColor Green
        Write-Host 'The first real proof must be one approved test email to an inbox you own.' -ForegroundColor Yellow
    }

    if ($LocalTest) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'creator-outreach-smoke.ps1')
    }

    if ($OpenDashboard) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'open-dashboard.ps1') -SideEffects -CopyToken
    }
    elseif ($Start) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'up.ps1') -SideEffects
    }

    if ($Status -or -not (
        $ConfigureYouTube -or
        $ConfigureGmail -or
        $LocalTest -or
        $Start -or
        $OpenDashboard
    )) {
        Show-PromotionStatus
    }
    elseif ($ConfigureYouTube -or $ConfigureGmail -or $LocalTest) {
        Show-PromotionStatus
    }
}
finally {
    Pop-Location
}
