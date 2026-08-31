[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$ConfigureYouTube,
    [switch]$ConfigureGmail,
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
    if ($dockerReady) {
        $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health/ready" -TimeoutSec 3
            $apiReady = $health.status -eq 'ready'
        }
        catch { $apiReady = $false }
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

    Write-Host 'Promotion readiness'
    Write-Host ("  Docker engine:        {0}" -f $(if ($dockerReady) { 'ready' } else { 'stopped' }))
    Write-Host ("  Control dashboard:    {0}" -f $(if ($apiReady) { 'ready' } else { 'not running' }))
    Write-Host ("  YouTube discovery:    {0}" -f $(if ($youtubeReady) { 'configured' } else { 'needs restricted API key' }))
    Write-Host ("  Real email transport: {0}" -f $(if ($smtpReady) { 'configured TLS SMTP' } else { 'needs provider credential' }))
    Write-Host ("  Email executor:       {0}" -f $(if ($emailExecutorReady) { 'healthy' } else { 'not running' }))
    Write-Host '  Promotion kit:        built in; no account or API key required'
    if (-not $youtubeReady) { Write-Host 'Next: ./scripts/promotion.ps1 -ConfigureYouTube' -ForegroundColor Yellow }
    if (-not $smtpReady) { Write-Host 'Next: ./scripts/promotion.ps1 -ConfigureGmail' -ForegroundColor Yellow }
    if ($youtubeReady -and $smtpReady -and (-not $apiReady -or -not $emailExecutorReady)) {
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

    if ($OpenDashboard) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'open-dashboard.ps1') -SideEffects -CopyToken
    }
    elseif ($Start) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'up.ps1') -SideEffects
    }

    if ($Status -or -not ($ConfigureYouTube -or $ConfigureGmail -or $Start -or $OpenDashboard)) {
        Show-PromotionStatus
    }
    elseif ($ConfigureYouTube -or $ConfigureGmail) {
        Show-PromotionStatus
    }
}
finally {
    Pop-Location
}
