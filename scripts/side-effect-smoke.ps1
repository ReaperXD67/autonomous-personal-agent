[CmdletBinding()]
param(
    [ValidateRange(60, 900)]
    [int]$TimeoutSeconds = 360
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$profileId = $null
$opportunityId = $null
$runId = [Guid]::NewGuid().ToString('N')
$savedProcessEnvironment = @{}

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        throw 'Missing .env. Run scripts/init-env.ps1 first.'
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $mailpitPort = if ($values.MAILPIT_UI_PORT) { $values.MAILPIT_UI_PORT } else { '8025' }
    $postgresUser = if ($values.POSTGRES_USER) { $values.POSTGRES_USER } else { 'agent_app' }
    $postgresDatabase = if ($values.POSTGRES_DB) { $values.POSTGRES_DB } else { 'agent' }
    $baseUrl = "http://127.0.0.1:$port"
    $mailpitUrl = "http://127.0.0.1:$mailpitPort"
    $headers = @{ Authorization = "Bearer $($values.CONTROL_API_TOKEN)" }

    foreach ($name in @('MAIL_TRANSPORT', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_FROM', 'SMTP_TLS_MODE')) {
        $savedProcessEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    $env:MAIL_TRANSPORT = 'mailpit'
    $env:SMTP_HOST = 'mailpit'
    $env:SMTP_PORT = '1025'
    $env:SMTP_FROM = 'hermes@local.invalid'
    $env:SMTP_TLS_MODE = 'none'

    $runningServices = @(& docker compose ps --status running --services)
    $localModel = if ($values.LOCAL_MODEL) { $values.LOCAL_MODEL } else { 'qwen3:8b' }
    if ($runningServices -notcontains 'ollama') {
        & (Join-Path $PSScriptRoot 'local-model.ps1')
    }
    else {
        & docker compose exec -T ollama ollama show $localModel *> $null
        if ($LASTEXITCODE -ne 0) {
            & (Join-Path $PSScriptRoot 'local-model.ps1')
        }
    }

    & docker compose --profile side-effects-test up -d mailpit
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the local email sink.' }
    & docker compose --profile side-effects-test up -d --build --force-recreate control-api dispatcher job-worker action-worker application-fixture
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the isolated side-effect test services.' }

    function Wait-HttpReady {
        param([Parameter(Mandatory)][string]$Uri)
        $deadline = [DateTimeOffset]::UtcNow.AddSeconds(90)
        do {
            try {
                $response = Invoke-WebRequest -Method Get -Uri $Uri -TimeoutSec 3 -UseBasicParsing
                if ($response.StatusCode -eq 200) { return }
            }
            catch { }
            Start-Sleep -Milliseconds 500
        } while ([DateTimeOffset]::UtcNow -lt $deadline)
        throw "Service did not become ready: $Uri"
    }

    function Wait-AgentTask {
        param([Parameter(Mandatory)][string]$TaskId)
        $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
        do {
            $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$TaskId" -Headers $headers
            if ($task.status -in @('succeeded', 'failed', 'rejected', 'cancelled', 'dead_lettered')) {
                return $task
            }
            Start-Sleep -Milliseconds 500
        } while ([DateTimeOffset]::UtcNow -lt $deadline)
        throw "Task $TaskId did not finish in $TimeoutSeconds seconds."
    }

    function Approve-ExactAction {
        param([Parameter(Mandatory)][string]$TaskId)
        $body = @{
            decision = 'approved'
            actor = 'local-side-effect-smoke'
            reason = 'Disposable local fixture validation only'
        } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks/$TaskId/decision" -Headers $headers -ContentType 'application/json' -Body $body | Out-Null
    }

    Wait-HttpReady -Uri "$baseUrl/health/ready"
    Wait-HttpReady -Uri "$mailpitUrl/readyz"

    $profileBody = @{
        name = "Disposable side-effect smoke $runId"
        candidate_name = 'Synthetic Test Candidate'
        desired_titles = @('Synthetic Reliability Engineer')
        skills = @('testing', 'automation')
        required_keywords = @()
        excluded_keywords = @()
        locations = @()
        remote_only = $false
        employment_types = @()
        max_age_hours = 168
        min_score = 0
        schedule_minutes = 360
        source_config = @{ arbeitnow = $true; ashby_boards = @(); greenhouse_boards = @(); lever_boards = @() }
        application_identity = @{
            first_name = 'Synthetic'
            last_name = 'Candidate'
            email = "candidate-$runId@example.test"
            phone = '+1 555 0100'
            location = 'Local test fixture'
        }
        resume_text = 'Synthetic validation resume. Experience: responsible automation, testing, and documentation. This is not a real person.'
        auto_prepare = $false
        auto_prepare_min_score = 75
        max_auto_prepare_per_scan = 1
        active = $false
        requested_by = "local-side-effect-smoke:$runId"
    } | ConvertTo-Json -Depth 8
    $profile = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/profiles" -Headers $headers -ContentType 'application/json' -Body $profileBody
    $profileId = [Guid]::Parse([string]$profile.id)

    $insertOpportunity = @"
INSERT INTO job_opportunities (
    profile_id, source, source_key, company, title, location, description,
    remote, employment_type, source_url, apply_url, published_at, score,
    score_reasons
) VALUES (
    '$profileId'::uuid, 'greenhouse', 'smoke-$runId', 'Local Fixture Ltd',
    'Synthetic Reliability Engineer', 'Local fixture',
    'A harmless local validation role used only by the Hermes smoke test.',
    true, 'FullTime', 'http://application-fixture:8081/apply',
    'http://application-fixture:8081/apply', now(), 100,
    '["local deterministic fixture"]'::jsonb
) RETURNING id;
"@
    $opportunityId = (& docker compose exec -T postgres psql -v ON_ERROR_STOP=1 --username $postgresUser --dbname $postgresDatabase --quiet --tuples-only --no-align --command $insertOpportunity).Trim()
    $parsedOpportunityId = [Guid]::Empty
    if ($LASTEXITCODE -ne 0 -or -not [Guid]::TryParse($opportunityId, [ref]$parsedOpportunityId)) {
        throw 'Could not create the disposable application opportunity.'
    }

    $draftTask = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/opportunities/$opportunityId/draft" -Headers $headers
    $draftTask = Wait-AgentTask -TaskId $draftTask.id
    if ($draftTask.status -ne 'succeeded' -or -not $draftTask.output.draft_created) {
        throw "Application draft failed: $($draftTask.error_message)"
    }

    $preflightTask = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/opportunities/$opportunityId/preflight" -Headers $headers
    $preflightTask = Wait-AgentTask -TaskId $preflightTask.id
    if ($preflightTask.status -ne 'succeeded' -or $preflightTask.output.field_count -lt 6 -or $preflightTask.output.blocked_reason) {
        throw "Application preflight failed: $($preflightTask.error_message)"
    }

    $planBody = @{ answers = @{}; actor = 'local-side-effect-smoke'; approval_window_minutes = 15 } | ConvertTo-Json -Depth 5
    $applicationAction = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/opportunities/$opportunityId/submit-plan" -Headers $headers -ContentType 'application/json' -Body $planBody
    if ($applicationAction.status -ne 'pending_approval' -or $applicationAction.context_hash.Length -ne 64) {
        throw 'The exact application action was not prepared for approval.'
    }
    Approve-ExactAction -TaskId $applicationAction.task_id
    $applicationTask = Wait-AgentTask -TaskId $applicationAction.task_id
    if ($applicationTask.status -ne 'succeeded' -or -not $applicationTask.output.confirmation_detected) {
        throw "Application fixture submission failed: $($applicationTask.error_message)"
    }

    $emailSubject = "Hermes local sink verification $runId"
    $emailBody = @{
        recipient = "recruiter-$runId@example.test"
        subject = $emailSubject
        body = 'This message is captured by the local Mailpit test sink and never leaves Docker.'
        actor = 'local-side-effect-smoke'
        opportunity_id = $opportunityId
        approval_window_minutes = 15
    } | ConvertTo-Json
    $emailAction = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/external-actions/email" -Headers $headers -ContentType 'application/json' -Body $emailBody
    Approve-ExactAction -TaskId $emailAction.task_id
    $emailTask = Wait-AgentTask -TaskId $emailAction.task_id
    if ($emailTask.status -ne 'succeeded' -or $emailTask.output.transport -ne 'mailpit') {
        throw "Local email delivery failed: $($emailTask.error_message)"
    }
    $mailbox = Invoke-RestMethod -Method Get -Uri "$mailpitUrl/api/v1/messages"
    if (-not ($mailbox.messages | Where-Object { $_.Subject -eq $emailSubject })) {
        throw 'Mailpit did not capture the approved test email.'
    }

    $duplicatePlanBody = @{ answers = @{ 'phone:3' = '+1 555 0199' }; actor = 'local-side-effect-smoke'; approval_window_minutes = 15 } | ConvertTo-Json -Depth 5
    $duplicateAction = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/opportunities/$opportunityId/submit-plan" -Headers $headers -ContentType 'application/json' -Body $duplicatePlanBody
    Approve-ExactAction -TaskId $duplicateAction.task_id
    $duplicateTask = Wait-AgentTask -TaskId $duplicateAction.task_id
    if ($duplicateTask.status -ne 'failed' -or $duplicateTask.error_message -notmatch 'receipt; retry refused') {
        throw 'The duplicate-submission receipt guard did not refuse the second click.'
    }

    Write-Host "Exact application passed: $($applicationAction.task_id)"
    Write-Host "Local email passed:       $($emailAction.task_id)"
    Write-Host "Duplicate guard passed:   $($duplicateAction.task_id)"
    Write-Host 'No application or email left the local Docker test network.'
}
finally {
    if ($profileId -and $opportunityId) {
        $cleanupSql = @"
BEGIN;
CREATE TEMP TABLE smoke_task_ids AS
    SELECT id FROM agent_tasks WHERE payload->>'profile_id' = '$profileId'
    UNION SELECT task_id FROM external_actions WHERE opportunity_id = '$opportunityId'::uuid
    UNION SELECT task_id FROM job_application_drafts WHERE opportunity_id = '$opportunityId'::uuid
    UNION SELECT task_id FROM job_application_preflights WHERE opportunity_id = '$opportunityId'::uuid;
DELETE FROM side_effect_receipts WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM external_actions WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM job_application_preflights WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM job_application_drafts WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM career_profiles WHERE id = '$profileId'::uuid AND requested_by = 'local-side-effect-smoke:$runId';
DELETE FROM task_outbox WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM task_approvals WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM audit_events WHERE task_id IN (SELECT id FROM smoke_task_ids);
DELETE FROM agent_tasks WHERE id IN (SELECT id FROM smoke_task_ids);
COMMIT;
"@
        & docker compose exec -T postgres psql -v ON_ERROR_STOP=1 --username $postgresUser --dbname $postgresDatabase --command $cleanupSql | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not remove disposable smoke records for profile $profileId."
        }
    }
    foreach ($name in $savedProcessEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedProcessEnvironment[$name], 'Process')
    }
    Pop-Location
}
