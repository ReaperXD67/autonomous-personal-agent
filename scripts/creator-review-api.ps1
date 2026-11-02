# Operator helper: dot-sourcing defines functions only. Every mutation uses the control API.
function Get-CreatorReviewControlToken {
    $literal = $null
    try {
        $path = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
        foreach ($line in [IO.File]::ReadAllLines($path)) {
            if ($line -notmatch '^\s*CONTROL_API_TOKEN\s*=(.*)$') { continue }
            if ($null -ne $literal) { throw 'Duplicate token.' }
            $literal = $Matches[1].Trim()
        }
        if ($null -eq $literal) { throw 'Missing token.' }
        if ($literal.StartsWith('"')) {
            $token = $literal | ConvertFrom-Json -ErrorAction Stop
            if ($token -isnot [string]) { throw 'Invalid token.' }
            $token = $token.Replace('$$', '$')
        } elseif ($literal.StartsWith("'") -and $literal.EndsWith("'")) {
            $token = $literal.Substring(1, $literal.Length - 2).Replace("\'", "'")
        } else { $token = $literal }
        if ($token.Length -lt 32 -or $token -match '[\x00-\x1f\x7f]') { throw 'Invalid token.' }
        return $token
    } catch { throw 'Creator control API credential is unavailable; check local configuration.' }
}

function Invoke-CreatorControlApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [ValidateSet('Get', 'Post', 'Put')][string]$Method = 'Get',
        [object]$Body = $null
    )
    $allowed = '\A/v1/(?:marketing|tasks|external-actions)(?:/[A-Za-z0-9_-]+(?:\.csv)?)*(?:\?[A-Za-z0-9_=&%.\-]*)?\z|\A/v1/communications/status\z'
    if ($Path -cnotmatch $allowed -or ($Method -eq 'Get' -and $null -ne $Body)) {
        throw 'Unsupported creator control API path or request.'
    }
    $headers = @{}
    try {
        $headers.Authorization = 'Bearer ' + (Get-CreatorReviewControlToken)
        $request = @{ Uri = 'http://127.0.0.1:8080' + $Path; Method = $Method
            Headers = $headers; TimeoutSec = 30; MaximumRedirection = 0; ErrorAction = 'Stop' }
        if ($null -ne $Body) {
            $request.ContentType = 'application/json'
            $request.Body = ConvertTo-Json -InputObject $Body -Depth 25 -Compress
        }
        Invoke-RestMethod @request
    } catch {
        $status = 0
        try { $status = [int]$_.Exception.Response.StatusCode } catch { }
        $code = if ($status -ge 400 -and $status -le 599) { "CREATOR_CONTROL_HTTP_$status" }
            else { 'CREATOR_CONTROL_REQUEST_FAILED' }
        throw "$code. Request failed; inspect local service readiness."
    }
    finally { $headers.Clear() }
}

function ConvertTo-CreatorReviewInstant {
    param([object]$Value)
    if ($Value -is [DateTimeOffset]) { return $Value }
    if ($Value -is [DateTime]) {
        if ($Value.Kind -ne [DateTimeKind]::Unspecified) { return [DateTimeOffset]::new($Value) }
        return $null
    }
    if ($Value -isnot [string] -or $Value -cnotmatch '\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})\z') { return $null }
    $instant = [DateTimeOffset]::MinValue
    if ([DateTimeOffset]::TryParse($Value, [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None, [ref]$instant)) { return $instant }
    return $null
}

function Get-CreatorReviewSnapshot {
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidateCount(1, 2)][Guid[]]$CampaignId)
    if ([Guid]::Empty -in $CampaignId -or @($CampaignId | Select-Object -Unique).Count -ne $CampaignId.Count) {
        throw 'Choose one or two distinct creator campaign IDs.'
    }
    $now = [DateTimeOffset]::UtcNow
    $ids = @($CampaignId | ForEach-Object { $_.ToString() })
    $communication = Invoke-CreatorControlApi -Path '/v1/communications/status'
    $response = Invoke-CreatorControlApi -Path '/v1/external-actions?limit=200'
    $actions = foreach ($group in $response) { foreach ($action in $group) { $action } }
    $creationWindowComplete = @($actions).Count -lt 200
    if (-not $creationWindowComplete) {
        $validDates = $true; $oldBoundary = $false
        foreach ($action in $actions) {
            $created = ConvertTo-CreatorReviewInstant $action.created_at
            if ($null -eq $created) { $validDates = $false; break }
            if ($created -le $now.AddHours(-24)) { $oldBoundary = $true }
        }
        # The API orders this bounded page by creation time descending.
        $creationWindowComplete = $validDates -and $oldBoundary
    }
    $campaigns = foreach ($id in $ids) {
        $automation = Invoke-CreatorControlApi -Path "/v1/marketing/campaigns/$id/automation"
        $batch = Invoke-CreatorControlApi -Path "/v1/marketing/campaigns/$id/draft-batches"
        $completed = ConvertTo-CreatorReviewInstant $automation.gmail_sync.last_complete_at
        [pscustomobject]@{
            campaign_id = $id; monitor_configured = [bool]$automation.readiness.gmail_configured
            last_complete_at = $automation.gmail_sync.last_complete_at
            monitor_fresh = [bool]($automation.readiness.gmail_configured -and $null -ne $completed -and
                $completed -le $now -and $completed -ge $now.AddMinutes(-30))
            pending_reply_count = $automation.pending_reply_count
            pending_reply_ids = @($automation.pending_replies | Select-Object -First 10 -ExpandProperty id)
            batch_task_id = $batch.task.id; batch_status = $batch.task.status
            batch_items = @($batch.items | Select-Object -First 5 -Property prospect_id, draft_id, status, reason)
        }
    }
    $initials = foreach ($action in $actions) {
        if ($action.public_context.marketing.campaign_id -notin $ids -or
            $action.public_context.marketing.stage -ne 'initial') { continue }
        $recent = $false
        foreach ($value in @($action.created_at, $action.executed_at)) {
            $date = ConvertTo-CreatorReviewInstant $value
            if ($null -ne $date -and
                $date -ge $now.AddHours(-24) -and $date -le $now) { $recent = $true }
        }
        if ($recent) { $action | Select-Object id, task_id, status, created_at, executed_at }
    }
    [pscustomobject]@{
        observed_at = $now.ToString('o')
        smtp = [pscustomobject]@{
            transport = $communication.transport; sender_configured = $communication.sender_configured
            pacing = $communication.pacing
            latest_diagnostic_status = $communication.latest_check.status
            latest_diagnostic_completed_at = $communication.latest_check.completed_at
        }
        campaigns = @($campaigns); initial_actions = @($initials)
        action_history_may_be_truncated = @($actions).Count -ge 200
        initial_creation_window_complete = [bool]$creationWindowComplete
    }
}
