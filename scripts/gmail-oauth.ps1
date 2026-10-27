[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ClientJsonPath,
    [Parameter(Mandatory)][string]$Mailbox,
    [ValidateRange(60, 900)][int]$TimeoutSeconds = 600,
    [switch]$ReauthorizeExistingMailbox
)

# Operator-only credential onboarding. This cannot send mail, grant a creator
# run, or fetch message content. Runtime mailbox reads still use governed tasks.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'environment-lock.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
$gmailScope = 'https://www.googleapis.com/auth/gmail.readonly'

function ConvertFrom-GmailEnvironment {
    param([string]$Content)
    $values = @{}
    foreach ($line in ($Content -split '\r?\n')) {
        if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Z][A-Z0-9_]*)\s*=(.*)$') { continue }
        $name = $Matches[1]
        $literal = $Matches[2].Trim()
        if ($values.ContainsKey($name)) { throw 'Duplicate environment keys must be resolved before Gmail setup.' }
        if ($literal.StartsWith('"')) {
            try { $literal = ([string]($literal | ConvertFrom-Json)).Replace('$$', '$') }
            catch { throw 'A quoted environment value is malformed. Check it locally without sharing it.' }
        }
        elseif ($literal.StartsWith("'") -and $literal.EndsWith("'")) {
            $literal = $literal.Substring(1, $literal.Length - 2).Replace("\'", "'")
        }
        $values[$name] = $literal
    }
    return $values
}

function ConvertTo-GmailEnvironmentLiteral {
    param([AllowEmptyString()][string]$Value)
    if ($Value -match '[\x00-\x1f\x7f]') { throw 'Environment values must be one line. Nothing was written.' }
    if ($Value -match '^[a-zA-Z0-9_./:@+\-]*$') { return $Value }
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"').Replace('$', '$$') + '"'
}

function Set-GmailEnvironment {
    param([string]$Path, [Collections.IDictionary]$Baseline, [Collections.IDictionary]$Entries)
    Invoke-HermesEnvironmentLock -Path $Path -Action {
    # Re-read after browser consent: preserve edits to unrelated settings, but
    # never replace OAuth/monitoring settings another setup changed meanwhile.
    $current = [IO.File]::ReadAllText($Path)
    $values = ConvertFrom-GmailEnvironment $current
    $guarded = @('GMAIL_CLIENT_ID', 'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN',
        'GMAIL_ENABLED', 'GMAIL_CAREER_LABEL', 'GMAIL_CREATOR_LABEL',
        'CREATOR_GMAIL_ENABLED', 'CREATOR_GMAIL_MAILBOX')
    foreach ($key in $guarded) {
        if ([string]$Baseline[$key] -cne [string]$values[$key]) {
            throw 'Gmail settings changed during consent. Nothing was written; rerun setup.'
        }
    }
    $content = $current
    $newline = if ($current.Contains("`r`n")) { "`r`n" } else { "`n" }
    foreach ($key in $Entries.Keys) {
        if ([string]$key -notin $guarded) { throw 'Unsupported Gmail configuration key. Nothing was written.' }
        $entry = [string]$key + '=' + (ConvertTo-GmailEnvironmentLiteral ([string]$Entries[$key]))
        $pattern = '(?m)^[ \t]*' + [regex]::Escape([string]$key) + '[ \t]*=[^\r\n]*'
        if ([regex]::IsMatch($content, $pattern)) {
            $content = [regex]::Replace($content, $pattern, [Text.RegularExpressions.MatchEvaluator]{ $entry })
        }
        else {
            if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) { $content += $newline }
            $content += $entry + $newline
        }
    }
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, $content, [Text.UTF8Encoding]::new($false))
        if ([IO.File]::ReadAllText($Path) -cne $current) {
            throw 'Environment changed while saving. Nothing was written; rerun setup.'
        }
        [IO.File]::Replace($temporary, $Path, [NullString]::Value)
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
    }
}

function ConvertTo-GmailBase64Url {
    param([byte[]]$Bytes)
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-GmailNonce {
    $bytes = [byte[]]::new(32)
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    return ConvertTo-GmailBase64Url $bytes
}

function Get-GmailCodeChallenge {
    param([string]$Verifier)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ConvertTo-GmailBase64Url ($sha.ComputeHash([Text.Encoding]::ASCII.GetBytes($Verifier))) }
    finally { $sha.Dispose() }
}

function ConvertTo-GmailForm {
    param([Collections.IDictionary]$Values)
    return (@($Values.Keys | ForEach-Object {
        [Uri]::EscapeDataString([string]$_) + '=' + [Uri]::EscapeDataString([string]$Values[$_])
    }) -join '&')
}

function Read-GmailDesktopClient {
    param([string]$Path)
    if (-not [IO.Path]::IsPathRooted($Path)) { throw 'Use the absolute path to your downloaded Desktop OAuth client JSON.' }
    try {
        $file = Get-Item -LiteralPath $Path
        if ($file.PSIsContainer -or $file.Length -gt 32768) { throw 'invalid' }
        $config = [IO.File]::ReadAllText($file.FullName) | ConvertFrom-Json
    }
    catch { throw 'Cannot read the Desktop OAuth client JSON. Its content has not been printed.' }
    $client = $config.installed
    if (-not $client -or $config.web -or
        [string]$client.client_id -notmatch '^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$' -or
        [string]$client.client_secret -notmatch '^[\x21-\x7e]{1,1024}$' -or
        [string]$client.auth_uri -cne 'https://accounts.google.com/o/oauth2/auth' -or
        [string]$client.token_uri -cne 'https://oauth2.googleapis.com/token') {
        throw 'Expected a Google Desktop app client JSON with official Google endpoints.'
    }
    # Never use provider URLs supplied by a local JSON document.
    return @{ client_id = [string]$client.client_id; client_secret = [string]$client.client_secret }
}

function Invoke-GmailToken {
    param([Collections.IDictionary]$Fields)
    try {
        return Invoke-RestMethod -Method Post -Uri 'https://oauth2.googleapis.com/token' `
            -ContentType 'application/x-www-form-urlencoded' -Body (ConvertTo-GmailForm $Fields) `
            -TimeoutSec 20 -MaximumRedirection 0 -ErrorAction Stop
    }
    catch {
        # Only the refresh endpoint's exact invalid_grant response identifies
        # an unusable old grant. Do not treat outages, bad clients, malformed
        # responses or failed authorization-code exchanges as renewal authority.
        $invalidRefreshGrant = $false
        if ($Fields.grant_type -ceq 'refresh_token') {
            try {
                $details = ([string]$_.ErrorDetails.Message).Trim()
                if ([int]$_.Exception.Response.StatusCode -eq 400 -and
                    $details.Length -le 2048 -and $details.StartsWith('{') -and $details.EndsWith('}')) {
                    $failure = $details | ConvertFrom-Json -ErrorAction Stop
                    $invalidRefreshGrant = $failure.error -is [string] -and $failure.error -ceq 'invalid_grant'
                }
            }
            catch { $invalidRefreshGrant = $false }
        }
        if ($invalidRefreshGrant) {
            $sanitized = [InvalidOperationException]::new(
                'The existing Gmail refresh grant is no longer valid. No credentials were saved; explicit same-mailbox reauthorization is required.')
            $sanitized.Data['HermesGmailFailure'] = 'invalid_refresh_grant'
            throw $sanitized
        }
        throw 'Google token request failed. No credentials were saved; provider response was withheld.'
    }
}

function Get-GmailIdentity {
    param([string]$AccessToken)
    try {
        $profile = Invoke-RestMethod -Method Get -Uri 'https://gmail.googleapis.com/gmail/v1/users/me/profile' `
            -Headers @{ Authorization = "Bearer $AccessToken" } -TimeoutSec 20 -MaximumRedirection 0 -ErrorAction Stop
        if ([string]$profile.emailAddress -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw 'invalid' }
        return ([string]$profile.emailAddress).Trim().ToLowerInvariant()
    }
    catch { throw 'Gmail identity check failed. Enable Gmail API and verify account access; no settings were changed.' }
}

function Assert-GmailExistingIdentity {
    param(
        [Collections.IDictionary]$Values,
        [string]$ExpectedMailbox,
        [Collections.IDictionary]$DesktopClient,
        [switch]$ReauthorizeExistingMailbox
    )
    $configured = @('GMAIL_CLIENT_ID', 'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN' |
        Where-Object { $Values[$_] })
    if ($configured.Count -eq 0 -and -not $ReauthorizeExistingMailbox) { return }
    if ($configured.Count -ne 3) {
        throw 'Existing shared Gmail credentials are incomplete. Resolve them locally before replacing them.'
    }
    if ($ReauthorizeExistingMailbox -and (
        -not $Values.CREATOR_GMAIL_MAILBOX -or
        ([string]$Values.CREATOR_GMAIL_MAILBOX).Trim().ToLowerInvariant() -cne $ExpectedMailbox -or
        [string]$Values.CREATOR_GMAIL_ENABLED -ine 'true' -or
        -not $Values.GMAIL_CREATOR_LABEL -or
        [string]$Values.GMAIL_ENABLED -notin @('', 'false', '0') -or
        -not $DesktopClient -or
        [string]$DesktopClient.client_id -cne [string]$Values.GMAIL_CLIENT_ID -or
        [string]$DesktopClient.client_secret -cne [string]$Values.GMAIL_CLIENT_SECRET
    )) {
        throw 'Same-mailbox renewal requires the recorded creator identity, enabled creator monitoring, the same Desktop client, and disabled career monitoring. No settings were changed.'
    }
    $existing = $null
    try {
        try {
            $existing = Invoke-GmailToken @{
                client_id = $Values.GMAIL_CLIENT_ID; client_secret = $Values.GMAIL_CLIENT_SECRET
                refresh_token = $Values.GMAIL_REFRESH_TOKEN; grant_type = 'refresh_token'
            }
        }
        catch {
            if ($ReauthorizeExistingMailbox -and
                $_.Exception.Data['HermesGmailFailure'] -ceq 'invalid_refresh_grant') {
                # The new grant is still checked for exact account, scope and
                # label before the guarded atomic configuration save below.
                Write-Host 'The previous grant is invalid; renewing only the recorded creator mailbox with the same Desktop client.'
                return
            }
            throw
        }
        if ((Get-GmailIdentity ([string]$existing.access_token)) -cne $ExpectedMailbox) {
            throw 'Existing Gmail credentials belong to another mailbox. Shared career credentials were preserved.'
        }
    }
    finally { $existing = $null }
}

function Assert-GmailReadOnlyToken {
    param($Token)
    $scopes = @(([string]$Token.scope).Split(' ', [StringSplitOptions]::RemoveEmptyEntries) | Select-Object -Unique)
    if ($scopes.Count -ne 1 -or $scopes[0] -cne 'https://www.googleapis.com/auth/gmail.readonly' -or
        [string]$Token.token_type -ine 'Bearer' -or
        [string]$Token.access_token -notmatch '^[\x21-\x7e]{1,8192}$' -or
        [string]$Token.refresh_token -notmatch '^[\x21-\x7e]{1,8192}$') {
        throw 'Google did not return an exact read-only offline grant. Nothing was saved; review this app grant in Google.'
    }
}

function Assert-GmailCreatorLabel {
    param([string]$AccessToken, [string]$Label)
    try {
        $result = Invoke-RestMethod -Method Get -Uri 'https://gmail.googleapis.com/gmail/v1/users/me/labels' `
            -Headers @{ Authorization = "Bearer $AccessToken" } -TimeoutSec 20 -MaximumRedirection 0 -ErrorAction Stop
    }
    catch { throw 'Gmail label check failed. No settings were changed; provider response was withheld.' }
    if (-not @($result.labels | Where-Object { $_.name -ceq $Label }).Count) {
        throw 'Create the configured creator label in Gmail first, then rerun setup. No settings were changed.'
    }
}

function Read-GmailCallback {
    param([string]$Request, [int]$Port, [string]$State)
    if ($Request.Length -gt 8192 -or $Request -notmatch '\r\n\r\n$') { throw 'Invalid local callback.' }
    $lines = $Request -split '\r\n'
    if ($lines[0] -notmatch '^GET (/\?[^ ]+) HTTP/1\.[01]$') { throw 'Invalid local callback.' }
    $target = $Matches[1]
    $hosts = @($lines | Where-Object { $_ -match '^Host:' })
    if ($hosts.Count -ne 1 -or $hosts[0] -ine "Host: 127.0.0.1:$Port") { throw 'Invalid local callback.' }
    $query = @{}
    foreach ($pair in $target.Substring(2).Split('&')) {
        $parts = $pair.Split('=', 2)
        if ($parts.Count -ne 2 -or $parts[0] -match '%(?![0-9a-fA-F]{2})' -or
            $parts[1] -match '%(?![0-9a-fA-F]{2})') { throw 'Invalid local callback.' }
        $key = [Uri]::UnescapeDataString($parts[0].Replace('+', ' '))
        $value = [Uri]::UnescapeDataString($parts[1].Replace('+', ' '))
        if ($query.ContainsKey($key) -or $value -match '[\x00-\x1f\x7f]') { throw 'Invalid local callback.' }
        $query[$key] = $value
    }
    $received = [Text.Encoding]::UTF8.GetBytes([string]$query.state)
    $expected = [Text.Encoding]::UTF8.GetBytes($State)
    if ($received.Length -ne $expected.Length) { throw 'Invalid local callback state.' }
    $difference = 0
    for ($i = 0; $i -lt $expected.Length; $i++) { $difference = $difference -bor ($received[$i] -bxor $expected[$i]) }
    if ($difference -ne 0) { throw 'Invalid local callback state.' }
    if ($query.error) { return @{ denied = $true; code = '' } }
    if (-not $query.code -or $query.code.Length -gt 4096) { throw 'Invalid local callback code.' }
    return @{ denied = $false; code = [string]$query.code }
}

function Receive-GmailAuthorization {
    param([Net.Sockets.TcpListener]$Listener, [int]$Port, [string]$State, [int]$TimeoutSeconds)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $Listener.Pending()) { Start-Sleep -Milliseconds 100; continue }
        $socket = $Listener.AcceptTcpClient()
        $parsed = $null
        try {
            $socket.ReceiveTimeout = 2000
            $socket.SendTimeout = 2000
            $stream = $socket.GetStream()
            $bytes = [Collections.Generic.List[byte]]::new()
            $headerDeadline = [DateTime]::UtcNow.AddSeconds(2)
            while ($bytes.Count -le 8192 -and [DateTime]::UtcNow -lt $headerDeadline -and
                [DateTime]::UtcNow -lt $deadline) {
                $next = $stream.ReadByte()
                if ($next -lt 0) { break }
                $bytes.Add([byte]$next)
                $count = $bytes.Count
                if ($count -ge 4 -and $bytes[$count - 4] -eq 13 -and $bytes[$count - 3] -eq 10 -and
                    $bytes[$count - 2] -eq 13 -and $bytes[$count - 1] -eq 10) { break }
            }
            try { $parsed = Read-GmailCallback ([Text.Encoding]::ASCII.GetString($bytes.ToArray())) $Port $State }
            catch { $parsed = $null }
            $status = if ($parsed) { '200 OK' } else { '400 Bad Request' }
            # Do not reflect any callback data; replace the code-bearing browser
            # URL immediately. CSP permits only this one nonce-bound local script.
            $nonce = New-GmailNonce
            $html = '<!doctype html><meta charset="utf-8"><title>Hermes Gmail setup</title>' +
                '<script nonce="' + $nonce + '">history.replaceState(null,"","/");</script>' +
                '<p>Return to the local Hermes setup terminal for the result. You may close this tab.</p>'
            $body = [Text.Encoding]::UTF8.GetBytes($html)
            $headers = "HTTP/1.1 $status`r`nContent-Type: text/html; charset=utf-8`r`n" +
                "Content-Length: $($body.Length)`r`nCache-Control: no-store`r`n" +
                "Referrer-Policy: no-referrer`r`nContent-Security-Policy: default-src 'none'; script-src 'nonce-$nonce'; frame-ancestors 'none'`r`n" +
                "Connection: close`r`n`r`n"
            $headerBytes = [Text.Encoding]::ASCII.GetBytes($headers)
            $stream.Write($headerBytes, 0, $headerBytes.Length)
            $stream.Write($body, 0, $body.Length)
        }
        catch { $parsed = $null }
        finally { $socket.Dispose() }
        if ($parsed) { return $parsed }
    }
    throw 'Gmail consent timed out. No settings were changed; rerun setup when ready.'
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { throw 'Run the project bootstrap first; .env is missing.' }
try {
    $address = [Net.Mail.MailAddress]::new($Mailbox)
    if ($address.Address -cne $Mailbox -or $Mailbox -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw 'invalid' }
}
catch { throw 'Mailbox must be the exact sender email address without a display name.' }
$Mailbox = $Mailbox.Trim().ToLowerInvariant()
$client = Read-GmailDesktopClient $ClientJsonPath
$baseline = ConvertFrom-GmailEnvironment ([IO.File]::ReadAllText($envPath))
if ($baseline.CREATOR_GMAIL_MAILBOX -and $baseline.CREATOR_GMAIL_MAILBOX.ToLowerInvariant() -cne $Mailbox) {
    throw 'Creator monitoring already names another mailbox. Resolve the account change explicitly before setup.'
}
Assert-GmailExistingIdentity $baseline $Mailbox -DesktopClient $client `
    -ReauthorizeExistingMailbox:$ReauthorizeExistingMailbox
$label = if ($baseline.GMAIL_CREATOR_LABEL) { $baseline.GMAIL_CREATOR_LABEL } else { 'Hermes/Creators' }
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$token = $null
$callback = $null
$entries = $null
$verifier = $null
try {
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $redirect = "http://127.0.0.1:$port/"
    $verifier = New-GmailNonce
    $state = New-GmailNonce
    $authorization = 'https://accounts.google.com/o/oauth2/v2/auth?' + (ConvertTo-GmailForm ([ordered]@{
        client_id = $client.client_id; redirect_uri = $redirect; response_type = 'code'
        scope = $gmailScope; state = $state; code_challenge = (Get-GmailCodeChallenge $verifier)
        code_challenge_method = 'S256'; access_type = 'offline'; prompt = 'consent select_account'; login_hint = $Mailbox
    }))
    Write-Host 'Opening Google consent in your default browser. Choose the expected mailbox and review read-only access.'
    Write-Host 'The Gmail permission covers the mailbox; Hermes limits message reads to the configured creator label.'
    Write-Host 'The local callback expires in ten minutes by default. No authorization URL, code, or token will be printed.'
    try { Start-Process -FilePath $authorization | Out-Null }
    catch { throw 'The consent browser could not open. Nothing was saved; check your default browser and retry.' }
    $callback = Receive-GmailAuthorization $listener $port $state $TimeoutSeconds
    if ($callback.denied) { throw 'Google consent was declined. No settings were changed.' }
    $token = Invoke-GmailToken @{
        client_id = $client.client_id; client_secret = $client.client_secret; code = $callback.code
        code_verifier = $verifier; grant_type = 'authorization_code'; redirect_uri = $redirect
    }
    Assert-GmailReadOnlyToken $token
    if ((Get-GmailIdentity ([string]$token.access_token)) -cne $Mailbox) {
        throw 'Google authorized a different mailbox. No settings were changed; select the expected account.'
    }
    Assert-GmailCreatorLabel ([string]$token.access_token) $label
    $entries = [ordered]@{
        GMAIL_CLIENT_ID = $client.client_id; GMAIL_CLIENT_SECRET = $client.client_secret
        GMAIL_REFRESH_TOKEN = [string]$token.refresh_token; CREATOR_GMAIL_ENABLED = 'true'
        CREATOR_GMAIL_MAILBOX = $Mailbox; GMAIL_CREATOR_LABEL = $label
    }
    Set-GmailEnvironment $envPath $baseline $entries
    Write-Host 'Gmail read-only credentials saved atomically in ignored .env; mailbox identity and label verified.' -ForegroundColor Green
    Write-Host 'Restart control-api and job-worker, then run a governed creator reply sync with an owned-inbox canary.'
    Write-Host 'This proves account access only. Reply ingestion, SMTP sending, and creator outreach remain separate checks.'
}
finally {
    $listener.Stop()
    if ($entries) { $entries.Clear() }
    if ($client) { $client.Clear() }
    if ($baseline) { $baseline.Clear() }
    $token = $null
    $callback = $null
    $verifier = $null
    $authorization = $null
}
