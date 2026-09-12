[CmdletBinding()]
param()

# Tests only dummy settings, isolated containers, and mocked HTTP responses.
# It neither loads a real SMTP credential nor invokes the live setup entrypoint.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$realEnvPath = Join-Path $projectRoot '.env'
$realEnvExisted = Test-Path -LiteralPath $realEnvPath
$beforeRealEnv = if ($realEnvExisted) { (Get-FileHash -LiteralPath $realEnvPath -Algorithm SHA256).Hash }
$probeRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'runtime/smtp-setup-smoke'))
$probeDirectory = Join-Path $probeRoot ([Guid]::NewGuid().ToString('N'))
$sourcePath = Join-Path $PSScriptRoot 'promotion.ps1'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($sourcePath, [ref]$tokens, [ref]$errors)
if ($errors) { throw 'Setup helper syntax failed.' }
$functionNames = @('Read-EnvironmentFile', 'ConvertTo-EnvironmentLiteral', 'Set-EnvironmentEntries',
    'Set-EnvironmentEntry', 'Convert-SecureValue', 'Configure-SmtpTransport', 'Invoke-SmtpCheck')
foreach ($functionName in $functionNames) {
    $node = $ast.Find({
        param($candidate)
        $candidate -is [Management.Automation.Language.FunctionDefinitionAst] -and $candidate.Name -eq $functionName
    }, $true)
    if (-not $node) { throw 'Required setup helper not found.' }
    # Load only the named repository functions; the live setup body never runs.
    Invoke-Expression $node.Extent.Text
}

Push-Location $projectRoot
try {
    & docker image inspect autonomous-personal-agent/control-api:local *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Build the local control-api image before running this smoke.' }
    New-Item -ItemType Directory -Path $probeDirectory -Force | Out-Null
    $envPath = Join-Path $probeDirectory '.env'
    $seed = "# preserve this comment`r`nUNRELATED=literal`r`n`r`nSMTP_PASSWORD=old-dummy`r`n"
    [IO.File]::WriteAllText($envPath, $seed)
    $dummyValues = @(
        'ordinary', 'dollar$PROBE ${NO_SUCH_KEY} $$', 'double" and single''quotes',
        'one\two\\three\', ' spaces # ; = ` & Unicode-é '
    )
    $composePath = Join-Path $probeDirectory 'compose.yaml'
    $composeContent = @'
services:
  probe:
    image: autonomous-personal-agent/control-api:local
    network_mode: none
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    environment:

'@
    $entries = [ordered]@{}
    for ($index = 0; $index -lt $dummyValues.Count; $index++) {
        $dummyValue = $dummyValues[$index]
        $hasher = [Security.Cryptography.SHA256]::Create()
        try {
            $sha = [BitConverter]::ToString(
                $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($dummyValue))
            ).Replace('-', '').ToLowerInvariant()
        }
        finally { $hasher.Dispose() }
        $valueKey = "SMTP_SETUP_DUMMY_$index"
        $hashKey = "SMTP_SETUP_HASH_$index"
        $entries[$valueKey] = $dummyValue
        $entries[$hashKey] = $sha
        $composeContent += '      ' + $valueKey + ': ${' + $valueKey + '}' + "`n"
        $composeContent += '      ' + $hashKey + ': ${' + $hashKey + '}' + "`n"
    }
    Set-EnvironmentEntries $entries
    $loaded = Read-EnvironmentFile
    foreach ($key in $entries.Keys) {
        if ($loaded[$key] -cne $entries[$key]) { throw 'Helper literal decoding mismatch.' }
    }
    if (-not [IO.File]::ReadAllText($envPath).StartsWith($seed)) { throw 'Unrelated environment lines changed.' }
    [IO.File]::WriteAllText($composePath, $composeContent, [Text.UTF8Encoding]::new($false))
    $containerProof = @'
import hashlib, os
for i in range(5):
    actual = hashlib.sha256(os.environ[f"SMTP_SETUP_DUMMY_{i}"].encode()).hexdigest()
    assert actual == os.environ[f"SMTP_SETUP_HASH_{i}"], "dummy literal mismatch"
'@
    & docker compose --project-directory $probeDirectory --env-file $envPath -f $composePath `
        run --rm --no-deps --entrypoint python probe -c $containerProof 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Container credential round trip failed.' }

    $answers = [Collections.Generic.Queue[string]]::new()
    $hiddenPrompts = 0
    function Read-Host {
        param([string]$Prompt, [switch]$AsSecureString)
        if ($answers.Count -eq 0) { throw 'Unexpected setup prompt.' }
        $answer = $answers.Dequeue()
        if ($AsSecureString) {
            $script:hiddenPrompts++
            return ConvertTo-SecureString $answer -AsPlainText -Force
        }
        return $answer
    }
    function Set-Answers {
        param([string[]]$Items)
        $answers.Clear()
        foreach ($item in $Items) { $answers.Enqueue($item) }
    }
    $dummyPassword = '  local-$SMTP_PROBE "single''quoted" \ trailing\  '
    $dummyUsername = 'dummy-$USERNAME '' \ " #'
    Set-Answers @('smtp.example.test', 'ssl', '', 'sender@example.test', $dummyUsername, $dummyPassword)
    Configure-SmtpTransport 6>$null
    $loaded = Read-EnvironmentFile
    if ($loaded.SMTP_PASSWORD -cne $dummyPassword -or $loaded.SMTP_USERNAME -cne $dummyUsername -or
        $loaded.SMTP_PORT -ne '465' -or $loaded.SMTP_TLS_MODE -ne 'ssl' -or $answers.Count -ne 0 -or $hiddenPrompts -ne 1) {
        throw 'Generic SMTP setup did not preserve the exact configuration.'
    }
    if (-not [IO.File]::ReadAllText($envPath).StartsWith("# preserve this comment`r`nUNRELATED=literal`r`n`r`n")) {
        throw 'Setup changed unrelated configuration.'
    }
    Set-Answers @('sender@example.test', 'abcd efgh ijkl mnop')
    Configure-SmtpTransport -Gmail 6>$null
    $loaded = Read-EnvironmentFile
    if ($loaded.SMTP_HOST -ne 'smtp.gmail.com' -or $loaded.SMTP_PORT -ne '587' -or
        $loaded.SMTP_TLS_MODE -ne 'starttls' -or $loaded.SMTP_PASSWORD -cne 'abcdefghijklmnop' -or $hiddenPrompts -ne 2) {
        throw 'Gmail compatibility failed.'
    }
    $invalidInputs = @(
        @('https://smtp.example.test'),
        @('smtp.example.test', 'none'),
        @('smtp.example.test', 'ssl', '99999'),
        @('smtp.example.test', 'ssl', '', 'Display Name <sender@example.test>'),
        @('smtp.example.test', 'ssl', '', 'sender@example.test', '', "line1`nline2")
    )
    foreach ($invalidInput in $invalidInputs) {
        $unchanged = [IO.File]::ReadAllText($envPath)
        Set-Answers $invalidInput
        $rejected = $false
        try { Configure-SmtpTransport } catch { $rejected = $true }
        if (-not $rejected -or [IO.File]::ReadAllText($envPath) -cne $unchanged) {
            throw 'Invalid setup changed configuration.'
        }
    }
    if (@(Get-ChildItem -LiteralPath $probeDirectory -Filter '.env.*.tmp').Count -ne 0) {
        throw 'Atomic setup left temporary credential files.'
    }

    $taskId = [Guid]::NewGuid().ToString()
    $requestCount = 0
    $mockMode = 'success'
    function Invoke-RestMethod {
        param($Method, $Uri, $Headers, $ContentType, $Body, $TimeoutSec)
        $script:requestCount++
        if ($mockMode -eq 'submission-error') { throw 'DUMMY_PROVIDER_SECRET_NEVER_PRINT' }
        if ($Method -eq 'Post') {
            if ($Uri -notmatch '/v1/communications/smtp-check$' -or ($Body | ConvertFrom-Json).requested_by -ne 'smtp-setup') {
                throw 'Check did not use the governed route.'
            }
            return @{ id = $taskId; status = 'queued' }
        }
        if ($mockMode -eq 'failure') {
            return @{ id = $taskId; status = 'failed'; error_code = 'SMTP_AUTH_FAILED'; error_message = 'DUMMY_PROVIDER_SECRET_NEVER_PRINT' }
        }
        return @{ id = $taskId; status = 'succeeded'; output = @{
                handler = 'communications.smtp_check'; checked = $true
                transport = 'mailpit'; tls_mode = 'none'; authenticated = $false
            } }
    }
    function Start-Sleep { param($Milliseconds) }
    Invoke-SmtpCheck 6>$null
    if ($requestCount -ne 2) { throw 'Expected one governed submission and one status read.' }
    foreach ($mode in @('failure', 'submission-error')) {
        $mockMode = $mode
        $failed = $false
        try { Invoke-SmtpCheck 6>$null } catch {
            $failed = $true
            if ([string]$_ -match 'DUMMY_PROVIDER_SECRET_NEVER_PRINT') { throw 'Raw provider text escaped sanitization.' }
        }
        if (-not $failed) { throw 'A failed check was accepted.' }
    }
}
finally {
    if (Test-Path -LiteralPath $probeDirectory) {
        $resolvedProbe = [IO.Path]::GetFullPath((Get-Item -LiteralPath $probeDirectory).FullName)
        if ([IO.Path]::GetDirectoryName($resolvedProbe) -ne $probeRoot -or
            [IO.Path]::GetFileName($resolvedProbe) -notmatch '^[0-9a-f]{32}$' -or
            (Get-Item -LiteralPath $resolvedProbe).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) {
            throw 'Refusing to clean an unexpected smoke directory.'
        }
        Remove-Item -LiteralPath $resolvedProbe -Recurse -Force
    }
    Pop-Location
    if ((Test-Path -LiteralPath $realEnvPath) -ne $realEnvExisted -or
        ($realEnvExisted -and (Get-FileHash -LiteralPath $realEnvPath -Algorithm SHA256).Hash -cne $beforeRealEnv)) {
        throw 'Real environment was changed during the smoke.'
    }
}
Write-Host 'SMTP setup smoke passed: five credential round trips in one isolated container; generic/Gmail hidden prompts; atomic preservation; five invalid-input rejections; governed check reporting.'
