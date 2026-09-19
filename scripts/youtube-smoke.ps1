$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$campaignId = $null
$taskId = $null
$runId = [Guid]::NewGuid().ToString('N')
Push-Location $projectRoot
try {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $postgresUser = if ($values.POSTGRES_USER) { $values.POSTGRES_USER } else { 'agent_app' }
    $postgresDatabase = if ($values.POSTGRES_DB) { $values.POSTGRES_DB } else { 'agent' }
    $baseUrl = "http://127.0.0.1:$port"
    $headers = @{ Authorization = "Bearer $($values.CONTROL_API_TOKEN)" }
    $body = @{
        name = "Disposable YouTube discovery smoke $runId"
        product_name = 'Synthetic local validation'
        product_url = 'https://example.test/product'
        privacy_url = 'https://example.test/privacy'
        product_summary = 'a synthetic product used only to validate public discovery'
        target_audience = 'Minecraft server viewers'
        viewer_offer = 'a synthetic no-value test offer'
        creator_offer = 'a synthetic no-value test offer'
        paid_offer_enabled = $false
        sender_name = 'Synthetic discovery test'
        discovery_queries = @('Minecraft server')
        relevance_language = 'en'
        min_subscribers = 0
        max_subscribers = 200000000
        max_video_age_days = 30
        results_per_query = 1
        schedule_hours = 24
        adaptive_mode = $false
        active = $false
        requested_by = "local-youtube-smoke:$runId"
    } | ConvertTo-Json -Depth 6
    $campaign = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/campaigns" `
        -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 20
    $campaignId = [Guid]::Parse([string]$campaign.id)
    $task = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/marketing/campaigns/$campaignId/scan" `
        -Headers $headers -TimeoutSec 20
    $taskId = [Guid]::Parse([string]$task.id)
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    do {
        $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$taskId" -Headers $headers -TimeoutSec 10
        if ($task.status -in @('succeeded', 'failed', 'rejected', 'cancelled', 'dead_lettered')) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($task.status -ne 'succeeded' -or [int]$task.output.queries -ne 1) {
        throw 'YOUTUBE_DISCOVERY_FAILED: the bounded public API scan did not complete successfully.'
    }
    Write-Host 'YouTube research passed: one query, one result per page, no pagination or outreach.'
    if ([int]$task.output.contact_authorizations_granted -ne 0) {
        throw 'YOUTUBE_RESEARCH_AUTHORITY_FAILED: research must not grant contact authorization.'
    }
    $prospects = @(Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/marketing/prospects?campaign_id=$campaignId" `
        -Headers $headers -TimeoutSec 15)
    foreach ($prospect in $prospects) {
        if ($prospect.intelligence.schema_version -ne 1 -or $prospect.contact_authorized_at) {
            throw 'YOUTUBE_RESEARCH_EVIDENCE_FAILED: missing dossier or unexpected contact authority.'
        }
        foreach ($candidate in $prospect.intelligence.contact_candidates) {
            if ($candidate.status -ne 'unreviewed' -or -not $candidate.source_url -or -not $candidate.evidence) {
                throw 'YOUTUBE_RESEARCH_EVIDENCE_FAILED: a candidate lacks unreviewed provenance.'
            }
        }
    }
    Write-Host ('Public discovery counts: {0} found, {1} newly persisted.' -f $task.output.discovered, $task.output.new)
}
finally {
    if ($campaignId) {
        if ($taskId -and $task.status -notin @('succeeded', 'failed', 'rejected', 'cancelled', 'dead_lettered')) {
            $cancelBody = @{ actor = 'local-youtube-smoke'; reason = 'Disposable probe cleanup' } | ConvertTo-Json
            try {
                Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/tasks/$taskId/cancel" -Headers $headers `
                    -ContentType 'application/json' -Body $cancelBody -TimeoutSec 10 | Out-Null
            } catch { Write-Warning 'Could not request synthetic discovery cancellation.' }
        }
        $cleanupSql = @"
BEGIN;
CREATE TEMP TABLE youtube_smoke_tasks AS
  SELECT id FROM agent_tasks WHERE payload->>'campaign_id' = '$campaignId';
DELETE FROM marketing_prospects WHERE campaign_id = '$campaignId'::uuid;
DELETE FROM marketing_campaigns WHERE id = '$campaignId'::uuid AND created_by = 'local-youtube-smoke:$runId';
DELETE FROM task_outbox WHERE task_id IN (SELECT id FROM youtube_smoke_tasks);
DELETE FROM task_approvals WHERE task_id IN (SELECT id FROM youtube_smoke_tasks);
DELETE FROM audit_events WHERE task_id IN (SELECT id FROM youtube_smoke_tasks)
  OR input_metadata->>'campaign_id' = '$campaignId';
DELETE FROM agent_tasks WHERE id IN (SELECT id FROM youtube_smoke_tasks) AND status <> 'running';
COMMIT;
"@
        & docker compose exec -T postgres psql -v ON_ERROR_STOP=1 --username $postgresUser `
            --dbname $postgresDatabase --command $cleanupSql | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'YOUTUBE_FIXTURE_CLEANUP_FAILED' }
    }
    Pop-Location
}
