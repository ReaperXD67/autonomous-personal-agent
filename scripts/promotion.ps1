[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$ConfigureYouTube,
    [switch]$ConfigureGmail,
    [switch]$ConfigureSMTP,
    [switch]$CheckSMTP,
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
        $literal = $parts[1].Trim()
        if ($literal.StartsWith('"')) {
            try { $literal = ([string]($literal | ConvertFrom-Json)).Replace('$$', '$') }
            catch { throw 'A quoted environment value is malformed. Check the local file without sharing it.' }
        }
        elseif ($literal.StartsWith("'") -and $literal.EndsWith("'")) {
            $literal = $literal.Substring(1, $literal.Length - 2).Replace("\'", "'")
        }
        $values[$parts[0].Trim()] = $literal
    }
    return $values
}

function ConvertTo-EnvironmentLiteral {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Value)
    if (@($Value.ToCharArray() | Where-Object { [char]::IsControl($_) }).Count -gt 0) {
        throw 'Environment values must be one line without control characters. Nothing was written.'
    }
    if ($Value -match '^[a-zA-Z0-9_./:@+\-]*$') { return $Value }
    # Compose expands double-quoted dotenv values. Escaping backslashes/quotes
    # and doubling dollars preserves literal credentials through interpolation.
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"').Replace('$', '$$') + '"'
}

function Set-EnvironmentEntries {
    param([Parameter(Mandatory)][Collections.IDictionary]$Entries)
    $original = [IO.File]::ReadAllText($envPath)
    $content = $original
    $newline = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }
    foreach ($name in $Entries.Keys) {
        if ([string]$name -notmatch '^[A-Z][A-Z0-9_]*$') {
            throw 'An environment key is invalid. Nothing was written.'
        }
        $entry = [string]$name + '=' + (ConvertTo-EnvironmentLiteral ([string]$Entries[$name]))
        $pattern = '(?m)^' + [regex]::Escape([string]$name) + '=[^\r\n]*'
        if ([regex]::IsMatch($content, $pattern)) {
            $content = [regex]::Replace($content, $pattern, [Text.RegularExpressions.MatchEvaluator]{ $entry })
        }
        else {
            if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) { $content += $newline }
            $content += $entry + $newline
        }
    }
    $temporaryPath = $envPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporaryPath, $content, [Text.UTF8Encoding]::new($false))
        if ([IO.File]::ReadAllText($envPath) -cne $original) {
            throw 'The environment file changed during setup. Rerun setup to preserve those changes.'
        }
        [IO.File]::Replace($temporaryPath, $envPath, [NullString]::Value)
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
}

function Set-EnvironmentEntry {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value
    )
    Set-EnvironmentEntries -Entries ([ordered]@{ $Name = $Value })
}

function Convert-SecureValue {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Configure-SmtpTransport {
    param([switch]$Gmail)
    if ($Gmail) {
        $smtpHost = 'smtp.gmail.com'
        $smtpPort = 587
        $tlsMode = 'starttls'
        $senderPrompt = 'Gmail or Google Workspace sender address'
    }
    else {
        $smtpHost = (Read-Host 'SMTP provider hostname (without a URL scheme)').Trim()
        if ($smtpHost.Length -gt 253 -or [Uri]::CheckHostName($smtpHost) -eq [UriHostNameType]::Unknown) {
            throw 'Enter one valid SMTP hostname. Nothing was written.'
        }
        $tlsMode = (Read-Host 'TLS mode: starttls or ssl [starttls]').Trim().ToLowerInvariant()
        if (-not $tlsMode) { $tlsMode = 'starttls' }
        if ($tlsMode -notin @('starttls', 'ssl')) {
            throw 'External SMTP requires starttls or ssl. Nothing was written.'
        }
        $defaultPort = if ($tlsMode -eq 'ssl') { 465 } else { 587 }
        $portInput = (Read-Host "SMTP port [$defaultPort]").Trim()
        $smtpPort = $defaultPort
        if ($portInput -and (-not [int]::TryParse($portInput, [ref]$smtpPort) -or $smtpPort -lt 1 -or $smtpPort -gt 65535)) {
            throw 'Enter an SMTP port from 1 to 65535. Nothing was written.'
        }
        $senderPrompt = 'Verified sender email address'
    }
    $sender = (Read-Host $senderPrompt).Trim()
    try { $parsedSender = [Net.Mail.MailAddress]::new($sender) }
    catch { throw 'Enter one valid sender email address. Nothing was written.' }
    if ($parsedSender.Address -cne $sender) {
        throw 'Enter only the sender email address, without a display name. Nothing was written.'
    }
    $username = $sender
    if (-not $Gmail) {
        $usernameInput = Read-Host 'SMTP username [use sender address]'
        if ($usernameInput) { $username = $usernameInput }
    }
    $password = $null
    $secure = $null
    $settingsToWrite = $null
    try {
        $credentialPrompt = if ($Gmail) { 'Google app password (input is hidden)' } else { 'SMTP password or provider credential (input is hidden)' }
        $secure = Read-Host $credentialPrompt -AsSecureString
        $password = Convert-SecureValue $secure
        if ($Gmail) { $password = $password -replace '\s', '' }
        if (-not $password -or ($Gmail -and $password.Length -lt 16)) {
            throw 'The provider credential is empty or too short. Nothing was written.'
        }
        $settingsToWrite = [ordered]@{
            MAIL_TRANSPORT = 'smtp'; SMTP_HOST = $smtpHost; SMTP_PORT = [string]$smtpPort
            SMTP_USERNAME = $username; SMTP_PASSWORD = $password; SMTP_FROM = $sender
            SMTP_TLS_MODE = $tlsMode
        }
        Set-EnvironmentEntries -Entries $settingsToWrite
    }
    finally {
        $password = $null
        if ($settingsToWrite) { $settingsToWrite.Clear() }
        if ($secure) { $secure.Dispose() }
    }
    Write-Host 'Stored TLS SMTP settings atomically in ignored .env.' -ForegroundColor Green
    Write-Host 'Restart the action services, then run -CheckSMTP for a governed connection check.'
    Write-Host 'Any actual message must use its reviewed, authorized action.'
}

function Invoke-SmtpCheck {
    $values = Read-EnvironmentFile
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $baseUrl = "http://127.0.0.1:$port"
    $headers = @{ Authorization = "Bearer $($values.CONTROL_API_TOKEN)" }
    try {
        $body = @{ requested_by = 'smtp-setup' } | ConvertTo-Json
        try {
            $task = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/communications/smtp-check" `
                -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 15
        }
        catch {
            throw 'SMTP_CHECK_SUBMISSION_FAILED: check that the current control API is running and authenticated.'
        }
        $taskId = [Guid]::Empty
        if (-not [Guid]::TryParse([string]$task.id, [ref]$taskId)) {
            throw 'SMTP_CHECK_RESPONSE_INVALID: the control API did not return a task ID.'
        }
        Write-Host "SMTP connection check queued through the control plane: $taskId"
        $deadline = [DateTime]::UtcNow.AddSeconds(120)
        while ($task.status -notin @('succeeded', 'failed', 'rejected', 'cancelled', 'dead_lettered')) {
            if ([DateTime]::UtcNow -ge $deadline) {
                throw "SMTP_CHECK_TIMEOUT: inspect task $taskId before requesting another check."
            }
            Start-Sleep -Milliseconds 500
            try {
                $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$taskId" `
                    -Headers $headers -TimeoutSec 10
            }
            catch { throw "SMTP_CHECK_STATUS_UNAVAILABLE: inspect task $taskId in the dashboard." }
        }
        if ($task.status -ne 'succeeded') {
            $safeCode = if ([string]$task.error_code -match '^[A-Z][A-Z0-9_]{0,63}$') {
                [string]$task.error_code
            }
            else { 'SMTP_CHECK_FAILED' }
            throw "SMTP connection check did not pass ($safeCode); task $taskId."
        }
        $result = $task.output
        if ($result.handler -ne 'communications.smtp_check' -or $result.checked -ne $true -or
            $result.transport -notin @('smtp', 'mailpit') -or $result.tls_mode -notin @('ssl', 'starttls', 'none') -or
            $result.authenticated -isnot [bool]) {
            throw 'SMTP_CHECK_RESPONSE_INVALID: no valid connection evidence was returned.'
        }
        Write-Host ("SMTP connection check passed: transport={0}; TLS={1}; authenticated={2}." -f
            $result.transport, $result.tls_mode, $result.authenticated)
        Write-Host 'This check sent no email. SMTP acceptance is separate from recipient inbox delivery.'
    }
    finally {
        $headers.Clear()
        $values.Clear()
    }
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
        'settings saved; connection and delivery are not yet verified'
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
    if (-not $smtpReady) { Write-Host 'After local proof: ./scripts/promotion.ps1 -ConfigureSMTP (or -ConfigureGmail)' -ForegroundColor Yellow }
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
    if ($ConfigureGmail -and $ConfigureSMTP) {
        throw 'Choose either -ConfigureGmail or -ConfigureSMTP.'
    }
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

    if ($ConfigureGmail) { Configure-SmtpTransport -Gmail }
    elseif ($ConfigureSMTP) { Configure-SmtpTransport }

    if ($LocalTest) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'creator-outreach-smoke.ps1')
    }

    if ($OpenDashboard) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'open-dashboard.ps1') -SideEffects
    }
    elseif ($Start) {
        Start-DockerIfNeeded
        & (Join-Path $PSScriptRoot 'up.ps1') -SideEffects
    }

    if ($CheckSMTP) { Invoke-SmtpCheck }

    if ($Status -or -not (
        $ConfigureYouTube -or
        $ConfigureGmail -or
        $ConfigureSMTP -or
        $CheckSMTP -or
        $LocalTest -or
        $Start -or
        $OpenDashboard
    )) {
        Show-PromotionStatus
    }
    elseif ($ConfigureYouTube -or $ConfigureGmail -or $ConfigureSMTP -or $LocalTest) {
        Show-PromotionStatus
    }
}
finally {
    Pop-Location
}
