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

    function Wait-Task {
        param([Parameter(Mandatory)][string]$TaskId)
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$TaskId" -Headers $headers
            if ($task.status -in @('succeeded', 'failed', 'rejected')) { return $task }
            Start-Sleep -Milliseconds 500
        }
        throw "Task $TaskId did not reach a terminal state"
    }

    $safeBody = @{
        title = 'Smoke test: safe queue path'
        kind = 'foundation.echo'
        payload = @{ message = 'core-stack-ok' }
        risk_level = 'low'
        requested_by = 'local-smoke-test'
    } | ConvertTo-Json -Depth 5
    $safe = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks" -Headers $headers -ContentType 'application/json' -Body $safeBody
    $safe = Wait-Task -TaskId $safe.id
    if ($safe.status -ne 'succeeded' -or $safe.output.echo -ne 'core-stack-ok') {
        throw 'Safe task did not complete with expected output'
    }

    $gatedBody = @{
        title = 'Smoke test: approval gate path'
        kind = 'foundation.echo'
        payload = @{ message = 'approval-gate-ok' }
        risk_level = 'high'
        requested_by = 'local-smoke-test'
    } | ConvertTo-Json -Depth 5
    $gated = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks" -Headers $headers -ContentType 'application/json' -Body $gatedBody
    if ($gated.status -ne 'pending_approval') {
        throw 'High-risk task bypassed approval gate'
    }
    $decisionBody = @{
        decision = 'approved'
        actor = 'local-smoke-approver'
        reason = 'Automated safe foundation validation'
    } | ConvertTo-Json
    $null = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks/$($gated.id)/decision" -Headers $headers -ContentType 'application/json' -Body $decisionBody
    $gated = Wait-Task -TaskId $gated.id
    if ($gated.status -ne 'succeeded' -or $gated.output.echo -ne 'approval-gate-ok') {
        throw 'Approved high-risk task did not complete with expected output'
    }

    Write-Host "Safe path passed:     $($safe.id)"
    Write-Host "Approval path passed: $($gated.id)"
}
finally {
    Pop-Location
}

