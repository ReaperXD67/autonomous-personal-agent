[CmdletBinding()]
param(
    [string]$Destination
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = Join-Path $projectRoot 'backups'
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

if (-not $Destination) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $Destination = Join-Path $backupRoot "agent-$stamp.dump"
}
$destinationPath = [IO.Path]::GetFullPath($Destination)
$backupPrefix = [IO.Path]::GetFullPath($backupRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $destinationPath.StartsWith($backupPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Backup destination must stay inside $backupRoot"
}

Push-Location $projectRoot
try {
    $containerId = docker compose ps --quiet postgres
    if (-not $containerId) { throw 'PostgreSQL container is not running' }

    $databaseLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^POSTGRES_DB=' } | Select-Object -First 1
    $userLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^POSTGRES_USER=' } | Select-Object -First 1
    $database = if ($databaseLine) { $databaseLine.Split('=', 2)[1] } else { 'agent' }
    $user = if ($userLine) { $userLine.Split('=', 2)[1] } else { 'agent_app' }
    $containerBackup = '/tmp/autonomous-personal-agent.dump'

    docker compose exec -T postgres pg_dump --format=custom --no-owner --no-acl --file=$containerBackup --username $user $database
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
    docker cp "${containerId}:$containerBackup" $destinationPath
    if ($LASTEXITCODE -ne 0) { throw 'docker cp failed' }
    docker compose exec -T postgres rm -f $containerBackup
    if ($LASTEXITCODE -ne 0) { throw 'Temporary backup cleanup failed' }

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destinationPath).Hash.ToLowerInvariant()
    $hashPath = "$destinationPath.sha256"
    "$hash  $([IO.Path]::GetFileName($destinationPath))" | Set-Content -LiteralPath $hashPath -Encoding ascii
    Write-Host "Backup: $destinationPath"
    Write-Host "SHA256: $hash"
    Write-Host "Checksum: $hashPath"
    Write-Host 'Encrypt before off-host storage; validate through a separate restore drill.'
}
finally {
    Pop-Location
}
