[CmdletBinding()]
param()

# Native PowerShell tests, synthetic credentials, mocked Google responses.
# The live entrypoint, real .env, and internet are never used.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'environment-lock.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$probeRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'runtime/gmail-oauth-smoke'))
$probeDirectory = Join-Path $probeRoot ([Guid]::NewGuid().ToString('N'))
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'gmail-oauth.ps1'), [ref]$null, [ref]$null)
foreach ($node in $ast.FindAll({
    param($candidate)
    $candidate -is [Management.Automation.Language.FunctionDefinitionAst]
}, $true)) { Invoke-Expression $node.Extent.Text }

function Assert-Rejected {
    param([scriptblock]$Action)
    $rejected = $false
    try { & $Action | Out-Null }
    catch {
        $rejected = $true
        if ([string]$_ -match 'DUMMY_SECRET_RESPONSE') { throw 'Provider response escaped sanitization.' }
    }
    if (-not $rejected) { throw 'Expected input was not rejected.' }
}

$requestMode = 'ok'
$requestCount = 0
function Invoke-RestMethod {
    [CmdletBinding()]
    param($Method, $Uri, $ContentType, $Body, $Headers, $TimeoutSec, $MaximumRedirection)
    $script:requestCount++
    if ($MaximumRedirection -ne 0 -or $TimeoutSec -ne 20) { throw 'Unsafe request options.' }
    if ($requestMode -eq 'error') { throw 'DUMMY_SECRET_RESPONSE' }
    if ($Uri -eq 'https://oauth2.googleapis.com/token' -and $Method -eq 'Post') {
        if ($ContentType -ne 'application/x-www-form-urlencoded' -or $Body -notmatch 'grant_type=refresh_token') {
            throw 'Unexpected token request.'
        }
        return @{ access_token = 'synthetic-access' }
    }
    if ($Uri -eq 'https://gmail.googleapis.com/gmail/v1/users/me/profile') {
        $email = if ($requestMode -eq 'other-account') { 'other@example.test' } else { 'owner@example.test' }
        return @{ emailAddress = $email }
    }
    if ($Uri -eq 'https://gmail.googleapis.com/gmail/v1/users/me/labels') {
        if ($requestMode -eq 'no-label') { return @{ labels = @() } }
        return @{ labels = @(@{ name = 'Hermes/Creators' }) }
    }
    throw 'Unexpected provider request.'
}

try {
    New-Item -ItemType Directory -Path $probeDirectory -Force | Out-Null
    $path = Join-Path $probeDirectory '.env'
    $seed = "# unchanged comment`r`nUNRELATED=old`r`n`r`nGMAIL_CLIENT_ID=old`r`n"
    [IO.File]::WriteAllText($path, $seed)
    $baseline = ConvertFrom-GmailEnvironment $seed
    # An unrelated edit completed while the browser was open must survive.
    [IO.File]::WriteAllText($path, $seed.Replace('UNRELATED=old', 'UNRELATED=new'))
    $dummy = 'dollar$VALUE ${OTHER} quote" slash\ #'
    Set-GmailEnvironment $path $baseline ([ordered]@{
        GMAIL_CLIENT_ID = 'new'; GMAIL_CLIENT_SECRET = $dummy; CREATOR_GMAIL_ENABLED = 'true'
    })
    $written = [IO.File]::ReadAllText($path)
    $loaded = ConvertFrom-GmailEnvironment $written
    if ($loaded.GMAIL_CLIENT_SECRET -cne $dummy -or $loaded.UNRELATED -cne 'new' -or
        -not $written.Contains("`r`n`r`nGMAIL_CLIENT_ID=new")) { throw 'Atomic merge did not preserve values/format.' }
    Assert-Rejected { Set-GmailEnvironment $path $baseline @{ GMAIL_CLIENT_ID = 'stale' } }
    if ([IO.File]::ReadAllText($path) -cne $written) { throw 'Stale setup changed settings.' }
    Assert-Rejected { Set-GmailEnvironment $path $loaded @{ SMTP_PASSWORD = 'not-allowed' } }
    Assert-Rejected { Set-GmailEnvironment $path $loaded @{ GMAIL_CLIENT_ID = "bad`nvalue" } }
    Assert-Rejected { ConvertFrom-GmailEnvironment "GMAIL_CLIENT_ID=a`nGMAIL_CLIENT_ID=b" }
    if (@(Get-ChildItem -LiteralPath $probeDirectory -Filter '.env.*.tmp').Count) { throw 'Temporary credentials remain.' }

    # Start two independent PowerShell processes at a barrier, then update one
    # synthetic file. The lock must serialize the whole read/modify/write phase.
    $lockHelper = Join-Path $PSScriptRoot 'environment-lock.ps1'
    $counterPath = Join-Path $probeDirectory 'counter.txt'
    [IO.File]::WriteAllText($counterPath, '0')
    $writers = @(foreach ($index in 1..2) {
        Start-Job -ArgumentList $lockHelper, $counterPath, $probeDirectory, $index -ScriptBlock {
            param($Helper, $Counter, $Directory, $Index)
            $ErrorActionPreference = 'Stop'
            . $Helper
            [IO.File]::WriteAllText((Join-Path $Directory "ready-$Index"), 'ready')
            $deadline = [DateTime]::UtcNow.AddSeconds(15)
            while (-not (Test-Path -LiteralPath (Join-Path $Directory 'ready-1')) -or
                -not (Test-Path -LiteralPath (Join-Path $Directory 'ready-2'))) {
                if ([DateTime]::UtcNow -gt $deadline) { throw 'Writer barrier timed out.' }
                Start-Sleep -Milliseconds 50
            }
            Invoke-HermesEnvironmentLock $Counter {
                $value = [int][IO.File]::ReadAllText($Counter)
                Start-Sleep -Milliseconds 500
                [IO.File]::WriteAllText($Counter, [string]($value + 1))
            }
            'writer-ok'
        }
    })
    try {
        $writers | Wait-Job -Timeout 20 | Out-Null
        $writerResults = @($writers | Receive-Job -ErrorAction Stop)
        if ($writerResults.Count -ne 2 -or @($writerResults | Where-Object { $_ -cne 'writer-ok' }).Count -or
            [IO.File]::ReadAllText($counterPath) -cne '2') { throw 'Concurrent configuration writes were not serialized.' }
        Assert-Rejected { Invoke-HermesEnvironmentLock $counterPath { throw 'synthetic save failure' } }
        $released = Invoke-HermesEnvironmentLock $counterPath { 'released' }
        if ($released -cne 'released') { throw 'Failed save retained the configuration lock.' }
    }
    finally {
        $writers | Stop-Job
        $writers | Remove-Job -Force
    }

    $challenge = Get-GmailCodeChallenge 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
    if ($challenge -cne 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM') { throw 'PKCE RFC 7636 vector failed.' }
    $first = New-GmailNonce
    $second = New-GmailNonce
    if ($first -notmatch '^[A-Za-z0-9_-]{43}$' -or $first -ceq $second) { throw 'Nonce generation failed.' }
    $request = "GET /?state=$first&code=synthetic%2Bcode HTTP/1.1`r`nHost: 127.0.0.1:12345`r`n`r`n"
    $callback = Read-GmailCallback $request 12345 $first
    if ($callback.denied -or $callback.code -cne 'synthetic+code') { throw 'Callback parsing failed.' }
    $denied = Read-GmailCallback ($request.Replace('code=synthetic%2Bcode', 'error=access_denied')) 12345 $first
    if (-not $denied.denied -or $denied.code) { throw 'Consent denial was not preserved.' }
    foreach ($invalid in @(
        $request.Replace($first, $second),
        $request.Replace('Host: 127.0.0.1:12345', 'Host: attacker.example'),
        $request.Replace('GET /?', 'POST /?'),
        $request.Replace('GET /?', 'GET /wrong?'),
        $request.Replace('&code=', "&state=$first&code="),
        $request.Replace('synthetic%2Bcode', 'bad%0Acode'),
        $request.Replace('synthetic%2Bcode', 'bad%ZZ'),
        $request.Replace('synthetic%2Bcode', ''),
        ($request + ('x' * 8192))
    )) { Assert-Rejected { Read-GmailCallback $invalid 12345 $first } }

    $clientPath = Join-Path $probeDirectory 'oauth-client.json'
    $config = @{ installed = @{
        client_id = 'synthetic.apps.googleusercontent.com'; client_secret = 'synthetic-secret'
        auth_uri = 'https://accounts.google.com/o/oauth2/auth'; token_uri = 'https://oauth2.googleapis.com/token'
    } }
    [IO.File]::WriteAllText($clientPath, ($config | ConvertTo-Json))
    $client = Read-GmailDesktopClient $clientPath
    if ($client.client_id -cne $config.installed.client_id) { throw 'Client parsing failed.' }
    $config.installed.token_uri = 'https://attacker.example/token'
    [IO.File]::WriteAllText($clientPath, ($config | ConvertTo-Json))
    Assert-Rejected { Read-GmailDesktopClient $clientPath }
    Assert-Rejected { Read-GmailDesktopClient 'relative.json' }

    $token = @{ scope = 'https://www.googleapis.com/auth/gmail.readonly'; token_type = 'Bearer'
        access_token = 'synthetic-access'; refresh_token = 'synthetic-refresh' }
    Assert-GmailReadOnlyToken $token
    $token.scope += ' https://mail.google.com/'
    Assert-Rejected { Assert-GmailReadOnlyToken $token }
    $token.scope = 'https://www.googleapis.com/auth/gmail.readonly'
    $token.refresh_token = ''
    Assert-Rejected { Assert-GmailReadOnlyToken $token }
    $token.refresh_token = 'synthetic-refresh'
    $token.scope = ''
    Assert-Rejected { Assert-GmailReadOnlyToken $token }

    $shared = @{ GMAIL_CLIENT_ID = 'synthetic.apps.googleusercontent.com'
        GMAIL_CLIENT_SECRET = 'synthetic-secret'; GMAIL_REFRESH_TOKEN = 'synthetic-refresh' }
    Assert-GmailExistingIdentity $shared 'owner@example.test'
    $requestMode = 'other-account'
    Assert-Rejected { Assert-GmailExistingIdentity $shared 'owner@example.test' }
    Assert-Rejected { Assert-GmailExistingIdentity @{ GMAIL_CLIENT_ID = 'incomplete' } 'owner@example.test' }
    $requestMode = 'ok'
    Assert-GmailCreatorLabel 'synthetic-access' 'Hermes/Creators'
    $requestMode = 'no-label'
    Assert-Rejected { Assert-GmailCreatorLabel 'synthetic-access' 'Hermes/Creators' }
    $requestMode = 'error'
    Assert-Rejected { Invoke-GmailToken @{ grant_type = 'refresh_token' } }
    Assert-Rejected { Get-GmailIdentity 'synthetic-access' }
    Assert-Rejected { Assert-GmailCreatorLabel 'synthetic-access' 'Hermes/Creators' }

    # Exercise the actual bounded callback server over loopback with a dummy
    # authorization code. No Google request or live entrypoint is invoked.
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $job = Start-Job -ArgumentList $port, $first -ScriptBlock {
        param($Port, $State)
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $client.Connect([Net.IPAddress]::Loopback, $Port)
            $stream = $client.GetStream()
            $stream.ReadTimeout = 5000
            $request = "GET /?state=$State&code=synthetic-loopback-code HTTP/1.1`r`nHost: 127.0.0.1:$Port`r`n`r`n"
            $bytes = [Text.Encoding]::ASCII.GetBytes($request)
            $stream.Write($bytes, 0, $bytes.Length)
            $reader = [IO.StreamReader]::new($stream)
            $response = $reader.ReadToEnd()
            if (-not $response.StartsWith('HTTP/1.1 200 OK') -or
                -not $response.Contains('history.replaceState') -or
                $response.Contains('synthetic-loopback-code') -or $response.Contains($State)) {
                throw 'Unsafe callback response.'
            }
            return 'callback-ok'
        }
        finally { $client.Dispose() }
    }
    try {
        $result = Receive-GmailAuthorization $listener $port $first 20
        if ($result.code -cne 'synthetic-loopback-code') { throw 'Loopback code was not received.' }
        $job | Wait-Job -Timeout 10 | Out-Null
        if ((Receive-Job $job -ErrorAction Stop) -cne 'callback-ok') { throw 'Loopback client failed.' }
    }
    finally {
        $listener.Stop()
        $job | Stop-Job
        $job | Remove-Job -Force
    }
}
finally {
    if (Test-Path -LiteralPath $probeDirectory) {
        $resolved = [IO.Path]::GetFullPath((Get-Item -LiteralPath $probeDirectory).FullName)
        if ([IO.Path]::GetDirectoryName($resolved) -ne $probeRoot -or
            [IO.Path]::GetFileName($resolved) -notmatch '^[0-9a-f]{32}$' -or
            (Get-Item -LiteralPath $resolved).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) {
            throw 'Refusing to clean an unexpected smoke directory.'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
Write-Host 'Gmail OAuth smoke passed: PKCE, nonce/state, callback bounds, scope, identity/conflicts, label, redacted failures, atomic merge, concurrent writers, and real loopback response. No live account or environment accessed.'
