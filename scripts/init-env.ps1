[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$examplePath = Join-Path $projectRoot '.env.example'
$targetPath = Join-Path $projectRoot '.env'

if ((Test-Path -LiteralPath $targetPath) -and -not $Force) {
    Write-Host '.env already exists. Use -Force only when rotating all local bootstrap secrets.'
    exit 0
}

function New-RandomHex {
    param([Parameter(Mandatory)][int]$Bytes)

    $buffer = [byte[]]::new($Bytes)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($buffer)
    }
    finally {
        $generator.Dispose()
    }
    return ([BitConverter]::ToString($buffer) -replace '-', '').ToLowerInvariant()
}

$content = [IO.File]::ReadAllText($examplePath)
$replacements = [ordered]@{
    'CHANGE_ME_CONTROL_API_TOKEN' = New-RandomHex -Bytes 32
    'CHANGE_ME_POSTGRES_PASSWORD' = New-RandomHex -Bytes 24
    'CHANGE_ME_REDIS_PASSWORD' = New-RandomHex -Bytes 24
    'CHANGE_ME_OMNIROUTE_INITIAL_PASSWORD' = New-RandomHex -Bytes 24
    'CHANGE_ME_OMNIROUTE_API_KEY_SECRET' = New-RandomHex -Bytes 32
    'CHANGE_ME_OMNIROUTE_JWT_SECRET' = New-RandomHex -Bytes 32
    'CHANGE_ME_OMNIROUTE_MACHINE_ID_SALT' = New-RandomHex -Bytes 32
}

foreach ($entry in $replacements.GetEnumerator()) {
    $content = $content.Replace($entry.Key, $entry.Value)
}

$utf8NoBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($targetPath, $content, $utf8NoBom)
Write-Host 'Created ignored .env with cryptographically random local secrets.'
Write-Host 'Run scripts/configure-free-models.ps1 to create the local OmniRoute inference key.'
