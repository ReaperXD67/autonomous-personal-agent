[CmdletBinding()]
param(
    [ValidateRange(30, 300)]
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$campaignId = $null
$runId = [Guid]::NewGuid().ToString('N')
$savedProcessEnvironment = @{}

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
    param(
        [Parameter(Mandatory)][string]$BaseUrl,
        [Parameter(Mandatory)][hashtable]$Headers,
        [Parameter(Mandatory)][string]$TaskId
    )
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/tasks/$TaskId" -Headers $Headers
        if ($task.status -in @(
            'succeeded',
            'failed',
            'rejected',
            'cancelled',
            'dead_lettered'
        )) {
            return $task
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "Task $TaskId did not finish in $TimeoutSeconds seconds."
}

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

    $testMailSettings = @{
        MAIL_TRANSPORT = 'mailpit'
        SMTP_HOST = 'mailpit'
        SMTP_PORT = '1025'
        SMTP_USERNAME = ''
        SMTP_PASSWORD = ''
        SMTP_FROM = 'hermes@local.invalid'
        SMTP_TLS_MODE = 'none'
    }
    foreach ($name in $testMailSettings.Keys) {
        $savedProcessEnvironment[$name] = [Environment]::GetEnvironmentVariable(
            $name,
            'Process'
        )
        [Environment]::SetEnvironmentVariable(
            $name,
            [string]$testMailSettings[$name],
            'Process'
        )
    }

    & docker compose --profile side-effects-test up -d mailpit
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the local email sink.' }
    & docker compose --profile side-effects-test up -d --build --force-recreate control-api dispatcher action-worker
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not start the creator-outreach test services.'
    }

    Wait-HttpReady -Uri "$baseUrl/health/ready"
    Wait-HttpReady -Uri "$mailpitUrl/readyz"

    $campaignBody = @{
        name = "Disposable creator smoke $runId"
        product_name = 'Synthetic KarixMC test'
        product_url = 'https://example.test/karixmc'
        privacy_url = 'https://example.test/privacy'
        product_summary = 'a synthetic Minecraft reward network used only for local validation'
        target_audience = 'Synthetic Minecraft viewers and server owners'
        viewer_offer = 'a synthetic no-value test offer for local validation'
        creator_offer = 'a synthetic no-value server pilot for local validation'
        paid_offer_enabled = $false
        paid_offer_details = $null
        sender_name = 'Hermes local test'
        discovery_queries = @('Synthetic Minecraft creator')
        relevance_language = 'en'
        region_code = $null
        min_subscribers = 0
        max_subscribers = 1000
        max_video_age_days = 30
        results_per_query = 1
        schedule_hours = 24
        adaptive_mode = $false
        active = $false
        requested_by = "local-creator-outreach-smoke:$runId"
    } | ConvertTo-Json -Depth 6
    $campaign = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/campaigns" -Headers $headers -ContentType 'application/json' -Body $campaignBody
    $campaignId = [Guid]::Parse([string]$campaign.id)

    $kit = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/marketing/campaigns/$campaignId/promotion-kit" -Headers $headers
    $trackingUrls = @($kit.assets | ForEach-Object { $_.tracking_url } | Sort-Object -Unique)
    if (@($kit.assets).Count -ne 5 -or $trackingUrls.Count -ne 5) {
        throw 'The campaign did not produce five distinct attributable promotion assets.'
    }

    $recipient = "creator-$runId@example.test"
    $prospectBody = @{
        campaign_id = $campaignId
        platform = 'youtube'
        external_id = "local-youtube-$runId"
        display_name = 'Synthetic Block Builder'
        profile_url = "https://example.test/creator/$runId"
        audience_size = 500
        latest_content_title = 'Synthetic Minecraft server review'
        latest_content_url = "https://example.test/video/$runId"
        contact_email = $recipient
        contact_source_url = "https://example.test/contact/$runId"
        contact_basis_note = 'Synthetic public-business-contact evidence for a local no-egress test'
        authorize_contact = $true
        requested_by = "local-creator-outreach-smoke:$runId"
    } | ConvertTo-Json -Depth 6
    $prospect = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/prospects" -Headers $headers -ContentType 'application/json' -Body $prospectBody
    $prospectId = [Guid]::Parse([string]$prospect.id)

    $planBody = @{
        stage = 'initial'
        subject = "Personalized local pilot $runId"
        body = 'Hello Synthetic Block Builder, this is a reviewed local-only introduction. No real offer or external recipient is involved.'
        actor = "local-creator-outreach-smoke:$runId"
        approval_window_minutes = 15
    } | ConvertTo-Json
    $action = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/prospects/$prospectId/email-plan" -Headers $headers -ContentType 'application/json' -Body $planBody
    if (
        $action.status -ne 'pending_approval' -or
        $action.context_hash.Length -ne 64 -or
        $action.public_context.recipient -ne $recipient -or
        $action.public_context.marketing.variant -ne 'manual_initial' -or
        $action.public_context.body -notmatch 'reviewed local-only introduction' -or
        $action.public_context.body -notmatch 'do not contact'
    ) {
        throw 'The exact creator introduction was not prepared with the expected safeguards.'
    }

    $decisionBody = @{
        decision = 'approved'
        actor = 'local-creator-outreach-smoke'
        reason = 'Synthetic Mailpit validation only'
    } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks/$($action.task_id)/decision" -Headers $headers -ContentType 'application/json' -Body $decisionBody | Out-Null
    $task = Wait-AgentTask -BaseUrl $baseUrl -Headers $headers -TaskId $action.task_id
    if ($task.status -ne 'succeeded' -or $task.output.transport -ne 'mailpit' -or -not $task.output.smtp_accepted) {
        throw "Creator introduction delivery failed: $($task.error_message)"
    }

    $mailbox = Invoke-RestMethod -Method Get -Uri "$mailpitUrl/api/v1/messages"
    if (-not ($mailbox.messages | Where-Object {
        $_.Subject -eq $action.public_context.subject
    })) {
        throw 'Mailpit did not capture the approved creator introduction.'
    }

    $outcomeBody = @{
        classification = 'do_not_contact'
        note = 'Synthetic opt-out used to verify durable suppression locally.'
        actor = "local-creator-outreach-smoke:$runId"
    } | ConvertTo-Json
    $suppressed = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/prospects/$prospectId/outcomes" -Headers $headers -ContentType 'application/json' -Body $outcomeBody
    if (
        $suppressed.status -ne 'suppressed' -or
        -not $suppressed.suppressed_at -or
        $suppressed.contact_authorized_at
    ) {
        throw 'The creator opt-out did not durably withdraw contact authorization.'
    }

    $blocked = $false
    try {
        Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/prospects/$prospectId/email-plan" -Headers $headers -ContentType 'application/json' -Body $planBody | Out-Null
    }
    catch {
        if ([int]$_.Exception.Response.StatusCode -eq 409) {
            $blocked = $true
        }
        else { throw }
    }
    if (-not $blocked) {
        throw 'A suppressed creator contact unexpectedly accepted another email plan.'
    }

    $results = @(Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/marketing/results?campaign_id=$campaignId" -Headers $headers)
    if (
        $results.Count -ne 1 -or
        [int]$results[0].metrics.emails_sent -ne 1 -or
        [int]$results[0].metrics.suppressed -ne 1
    ) {
        throw 'Creator campaign metrics did not reflect delivery and suppression.'
    }
    if (($results[0].variants | Measure-Object -Property sent -Sum).Sum -ne 0) {
        throw 'The personalized introduction incorrectly entered template A/B learning.'
    }

    $exact = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/external-actions/$($action.id)" -Headers $headers
    if ($exact.status -ne 'succeeded' -or $exact.context_hash -ne $action.context_hash) {
        throw 'The historical exact-action lookup did not preserve SMTP acceptance and the reviewed digest.'
    }

    Write-Host "Creator campaign passed: $campaignId"
    Write-Host "Exact introduction passed: $($action.task_id)"
    Write-Host 'Promotion kit passed: five distinct attributed assets'
    Write-Host 'Personalized introduction, exact-action lookup, and A/B isolation passed'
    Write-Host 'Suppression guard passed: future outreach refused'
    Write-Host 'No discovery request or email left the local Docker test network.'
}
finally {
    if ($campaignId) {
        $cleanupSql = @"
BEGIN;
CREATE TEMP TABLE smoke_prospect_ids AS
    SELECT id FROM marketing_prospects WHERE campaign_id = '$campaignId'::uuid;
CREATE TEMP TABLE smoke_action_ids AS
    SELECT action_id FROM marketing_outreach_messages
    WHERE prospect_id IN (SELECT id FROM smoke_prospect_ids);
CREATE TEMP TABLE smoke_task_ids AS
    SELECT task_id FROM external_actions
    WHERE id IN (SELECT action_id FROM smoke_action_ids);
DELETE FROM marketing_outcomes
WHERE prospect_id IN (SELECT id FROM smoke_prospect_ids);
DELETE FROM marketing_outreach_messages
WHERE prospect_id IN (SELECT id FROM smoke_prospect_ids);
DELETE FROM side_effect_receipts
WHERE action_id IN (SELECT action_id FROM smoke_action_ids);
DELETE FROM external_actions
WHERE id IN (SELECT action_id FROM smoke_action_ids);
DELETE FROM task_outbox WHERE task_id IN (SELECT task_id FROM smoke_task_ids);
DELETE FROM task_approvals WHERE task_id IN (SELECT task_id FROM smoke_task_ids);
DELETE FROM audit_events
WHERE task_id IN (SELECT task_id FROM smoke_task_ids)
   OR input_metadata->>'campaign_id' = '$campaignId';
DELETE FROM agent_tasks WHERE id IN (SELECT task_id FROM smoke_task_ids);
DELETE FROM marketing_prospects WHERE id IN (SELECT id FROM smoke_prospect_ids);
DELETE FROM marketing_campaigns
WHERE id = '$campaignId'::uuid
  AND created_by = 'local-creator-outreach-smoke:$runId';
COMMIT;
"@
        & docker compose exec -T postgres psql -v ON_ERROR_STOP=1 --username $postgresUser --dbname $postgresDatabase --command $cleanupSql | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not remove disposable creator-outreach records for campaign $campaignId."
        }
    }
    foreach ($name in $savedProcessEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $savedProcessEnvironment[$name],
            'Process'
        )
    }
    Pop-Location
}
