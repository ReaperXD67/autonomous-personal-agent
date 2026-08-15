$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $headers = @{ Authorization = "Bearer $($values.CONTROL_API_TOKEN)" }
    $baseUrl = "http://127.0.0.1:$port"

    function New-TestTask {
        param([string]$Title, [string]$Message)
        $body = @{
            title = $Title
            kind = 'foundation.echo'
            payload = @{ message = $Message }
            risk_level = 'low'
            requested_by = 'lease-recovery-smoke'
            idempotency_key = "lease-$([guid]::NewGuid())"
        } | ConvertTo-Json -Depth 5
        Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks" -Headers $headers -ContentType 'application/json' -Body $body
    }

    function Set-ExpiredLease {
        param([string]$TaskId, [string]$AttemptsExpression)
        $sql = "UPDATE agent_tasks SET status='running', attempt_count=$AttemptsExpression, started_at=now()-interval '5 minutes', last_heartbeat_at=now()-interval '5 minutes', lease_expires_at=now()-interval '1 second' WHERE id='$TaskId';"
        docker compose exec -T postgres psql -U $values.POSTGRES_USER -d $values.POSTGRES_DB -v ON_ERROR_STOP=1 -c $sql | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not create expired lease for $TaskId" }
    }

    function Wait-TaskStatus {
        param([string]$TaskId, [string[]]$Statuses, [int]$Attempts = 40)
        for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
            Start-Sleep -Milliseconds 500
            $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$TaskId" -Headers $headers
            if ($task.status -in $Statuses) { return $task }
        }
        throw "Task $TaskId did not reach: $($Statuses -join ', ')"
    }

    docker compose stop worker | Out-Null
    $retryTask = New-TestTask -Title 'Lease retry smoke' -Message 'lease-recovery-ok'
    Set-ExpiredLease -TaskId $retryTask.id -AttemptsExpression '1'
    $null = Wait-TaskStatus -TaskId $retryTask.id -Statuses @('queued')
    docker compose start worker | Out-Null
    $retryResult = Wait-TaskStatus -TaskId $retryTask.id -Statuses @('succeeded', 'dead_lettered')
    if ($retryResult.status -ne 'succeeded' -or $retryResult.output.echo -ne 'lease-recovery-ok' -or $retryResult.attempt_count -ne 2) {
        throw "Lease retry failed: status=$($retryResult.status) attempts=$($retryResult.attempt_count)"
    }

    docker compose stop worker | Out-Null
    $exhaustTask = New-TestTask -Title 'Lease exhaustion smoke' -Message 'must-not-run'
    Set-ExpiredLease -TaskId $exhaustTask.id -AttemptsExpression 'max_attempts'
    $exhaustResult = Wait-TaskStatus -TaskId $exhaustTask.id -Statuses @('dead_lettered')
    if ($exhaustResult.error_code -ne 'WORKER_LEASE_EXHAUSTED') {
        throw "Lease exhaustion used unexpected error: $($exhaustResult.error_code)"
    }

    Write-Host "Lease retry passed:      $($retryTask.id)"
    Write-Host "Lease exhaustion passed: $($exhaustTask.id)"
}
finally {
    docker compose start worker | Out-Null
    Pop-Location
}
