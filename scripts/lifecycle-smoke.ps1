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

    function New-LifecycleTask {
        param([string]$Title, [string]$Kind, [hashtable]$Payload)
        $body = @{
            title = $Title
            kind = $Kind
            payload = $Payload
            risk_level = 'low'
            requested_by = 'lifecycle-smoke'
            idempotency_key = "lifecycle-$([guid]::NewGuid())"
        } | ConvertTo-Json -Depth 5
        Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks" -Headers $headers -ContentType 'application/json' -Body $body
    }

    function Wait-LifecycleStatus {
        param([string]$TaskId, [string[]]$Statuses, [int]$Attempts = 80)
        for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
            $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$TaskId" -Headers $headers
            if ($task.status -in $Statuses) { return $task }
            Start-Sleep -Milliseconds 500
        }
        throw "Task $TaskId did not reach: $($Statuses -join ', ')"
    }

    function Stop-LifecycleTask {
        param([string]$TaskId, [string]$Reason)
        $body = @{
            actor = 'lifecycle-smoke'
            reason = $Reason
        } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks/$TaskId/cancel" -Headers $headers -ContentType 'application/json' -Body $body
    }

    docker compose stop worker | Out-Null
    $queued = New-LifecycleTask -Title 'Queued cancellation smoke' -Kind 'foundation.echo' -Payload @{ message = 'must-not-run' }
    $queued = Stop-LifecycleTask -TaskId $queued.id -Reason 'Verify cancellation before claim'
    if ($queued.status -ne 'cancelled') {
        throw "Queued cancellation failed: $($queued.status)"
    }

    docker compose start worker | Out-Null
    $running = New-LifecycleTask -Title 'Running cancellation smoke' -Kind 'foundation.wait' -Payload @{ seconds = 30 }
    $null = Wait-LifecycleStatus -TaskId $running.id -Statuses @('running')
    $null = Stop-LifecycleTask -TaskId $running.id -Reason 'Verify cooperative cancellation'
    $running = Wait-LifecycleStatus -TaskId $running.id -Statuses @('cancelled')
    if (-not $running.cancellation_requested_at) {
        throw 'Running cancellation did not preserve request metadata'
    }

    $deadLetters = @(Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/dead-letters?limit=20" -Headers $headers)
    $leaseDeadLetter = $deadLetters | Where-Object { $_.error_code -eq 'WORKER_LEASE_EXHAUSTED' } | Select-Object -First 1
    if (-not $leaseDeadLetter) {
        throw 'Dead-letter inspection did not return the recovery-smoke exhausted task'
    }

    Write-Host "Queued cancellation passed:  $($queued.id)"
    Write-Host "Running cancellation passed: $($running.id)"
    Write-Host "Dead-letter inspection passed: $($leaseDeadLetter.id)"
}
finally {
    docker compose start worker | Out-Null
    Pop-Location
}
