[CmdletBinding()]
param(
    [string]$BackupPath
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'backups'))

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        throw 'Missing .env; run scripts/init-env.ps1 first'
    }
    if (-not (docker compose ps --quiet postgres)) {
        throw 'PostgreSQL container is not running'
    }

    if (-not $BackupPath) {
        & (Join-Path $PSScriptRoot 'backup.ps1')
        $BackupPath = Get-ChildItem -LiteralPath $backupRoot -Filter '*.dump' -File |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $BackupPath) { throw 'No backup dump is available for the restore drill' }

    $resolvedBackup = [IO.Path]::GetFullPath($BackupPath)
    $backupPrefix = $backupRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedBackup.StartsWith($backupPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Restore drill accepts dumps only from $backupRoot"
    }
    if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Leaf)) {
        throw "Backup does not exist: $resolvedBackup"
    }

    $checksumPath = "$resolvedBackup.sha256"
    if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
        throw "Checksum sidecar is missing: $checksumPath"
    }
    $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackup).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw 'Backup SHA-256 verification failed' }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $database = if ($values.POSTGRES_DB) { $values.POSTGRES_DB } else { 'agent' }
    $user = if ($values.POSTGRES_USER) { $values.POSTGRES_USER } else { 'agent_app' }
    $suffix = ([guid]::NewGuid().ToString('N')).Substring(0, 12)
    $restoreDatabase = "agent_restore_$suffix"
    if ($restoreDatabase -notmatch '^agent_restore_[0-9a-f]{12}$' -or $restoreDatabase -eq $database) {
        throw 'Generated restore database name failed the safety check'
    }
    $containerDump = "/tmp/$restoreDatabase.dump"
    $containerId = docker compose ps --quiet postgres
    $created = $false

    function Invoke-RestoreScalar {
        param([Parameter(Mandatory)][string]$Sql)
        $value = docker compose exec -T postgres psql -X -A -t -U $user -d $restoreDatabase -v ON_ERROR_STOP=1 -c $Sql
        if ($LASTEXITCODE -ne 0) { throw "Restore validation query failed: $Sql" }
        ($value -join '').Trim()
    }

    try {
        docker cp $resolvedBackup "${containerId}:$containerDump"
        if ($LASTEXITCODE -ne 0) { throw 'Could not copy dump into PostgreSQL container' }

        $createSql = "CREATE DATABASE `"$restoreDatabase`" TEMPLATE template0;"
        docker compose exec -T postgres psql -X -U $user -d postgres -v ON_ERROR_STOP=1 -c $createSql | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not create disposable restore database' }
        $created = $true

        docker compose exec -T postgres pg_restore --exit-on-error --no-owner --no-acl --username $user --dbname $restoreDatabase $containerDump
        if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }

        if ((Invoke-RestoreScalar "SELECT count(*) FROM pg_extension WHERE extname='vector';") -ne '1') {
            throw 'Restored database is missing the vector extension'
        }
        $migrationCount = [int](Invoke-RestoreScalar 'SELECT count(*) FROM schema_migrations;')
        if ($migrationCount -lt 4) { throw "Expected at least 4 migrations; restored $migrationCount" }
        $taskCount = [int](Invoke-RestoreScalar 'SELECT count(*) FROM agent_tasks;')
        $auditCount = [int](Invoke-RestoreScalar 'SELECT count(*) FROM audit_events;')
        $orphanAuditCount = [int](Invoke-RestoreScalar 'SELECT count(*) FROM audit_events a LEFT JOIN agent_tasks t ON t.id=a.task_id WHERE a.task_id IS NOT NULL AND t.id IS NULL;')
        if ($orphanAuditCount -ne 0) { throw "Restored audit linkage has $orphanAuditCount orphan rows" }

        $probe = @'
import os
from urllib.parse import urlsplit, urlunsplit
from app.store import Database

parts = urlsplit(os.environ["DATABASE_URL"])
restore_url = urlunsplit((parts.scheme, parts.netloc, "/" + os.environ["RESTORE_DATABASE"], "", ""))
if not Database(restore_url).check():
    raise SystemExit("application database readiness probe failed")
'@
        docker compose run --rm --no-deps -e "RESTORE_DATABASE=$restoreDatabase" control-api python -c $probe
        if ($LASTEXITCODE -ne 0) { throw 'Application readiness failed against restored database' }

        Write-Host "Restore drill passed: $([IO.Path]::GetFileName($resolvedBackup))"
        Write-Host "Disposable database: $restoreDatabase"
        Write-Host "Migrations: $migrationCount; tasks: $taskCount; audits: $auditCount; orphan audits: 0"
    }
    finally {
        docker compose exec -T postgres rm -f $containerDump 2>$null
        if ($created) {
            $terminateSql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$restoreDatabase' AND pid <> pg_backend_pid();"
            docker compose exec -T postgres psql -X -U $user -d postgres -v ON_ERROR_STOP=1 -c $terminateSql | Out-Null
            docker compose exec -T postgres dropdb --if-exists --username $user $restoreDatabase
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Could not remove disposable database $restoreDatabase"
            }
        }
    }
}
finally {
    Pop-Location
}
