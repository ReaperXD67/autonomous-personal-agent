[CmdletBinding()]
param()

# Synthetic native proof. A copied helper resolves only this temporary fixture .env.
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot 'creator-review-api.ps1'
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($helper, [ref]$null, [ref]$errors)
if ($errors.Count -or @($ast.EndBlock.Statements | Where-Object {
    $_ -isnot [Management.Automation.Language.FunctionDefinitionAst]
}).Count) { throw 'Helper must contain function definitions only.' }
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('hermes-creator-review-' + [Guid]::NewGuid().ToString('N'))
$fixtureScripts = Join-Path $fixture 'scripts'
$fixtureHelper = Join-Path $fixtureScripts 'creator-review-api.ps1'
$fixtureEnv = Join-Path $fixture '.env'
$script:requestCount = 0
$script:requestMode = 'ok'
$script:expectedToken = ''
$script:capturedHeaders = $null
$campaignA, $campaignB, $otherCampaign = [Guid]::NewGuid(), [Guid]::NewGuid(), [Guid]::NewGuid()
$script:campaignIds = @($campaignA.ToString(), $campaignB.ToString())
$script:historyFull = $false
$script:readOnlyProbe = $false
$script:windowMode = 'normal'

function Assert-Rejected {
    param([scriptblock]$Action)
    $rejected = $false
    try { & $Action | Out-Null } catch {
        $rejected = $true
        if ([string]$_ -match 'PRIVATE_PROVIDER_RESPONSE|dummy-secret') {
            throw 'Sensitive error detail escaped sanitization.'
        }
    }
    if (-not $rejected) { throw 'Unsafe input was accepted.' }
}

function Invoke-RestMethod {
    [CmdletBinding()]
    param($Uri, $Method, $Headers, $TimeoutSec, $MaximumRedirection, $ContentType, $Body)
    $script:requestCount++
    $script:capturedHeaders = $Headers
    if ($TimeoutSec -ne 30 -or $MaximumRedirection -ne 0 -or
        -not ([string]$Uri).StartsWith('http://127.0.0.1:8080/v1/')) {
        throw 'Unsafe HTTP options.'
    }
    if ($Headers.Authorization -cne ('Bearer ' + $script:expectedToken)) { throw 'Token round trip failed.' }
    if ($script:readOnlyProbe -and $Method -ne 'Get') { throw 'Snapshot attempted a mutation.' }
    if ($script:requestMode -eq 'http409') {
        $response = [Net.Http.HttpResponseMessage]::new([Net.HttpStatusCode]::Conflict)
        throw [Microsoft.PowerShell.Commands.HttpResponseException]::new('PRIVATE_PROVIDER_RESPONSE dummy-secret', $response)
    }
    if ($script:requestMode -ne 'ok') { throw 'PRIVATE_PROVIDER_RESPONSE dummy-secret' }
    if ($Method -eq 'Post') {
        if ($ContentType -ne 'application/json' -or ($Body | ConvertFrom-Json).actor -cne 'synthetic') {
            throw 'JSON request encoding failed.'
        }
        return [pscustomobject]@{ status = 'synthetic' }
    }
    if ($Uri -like '*/communications/status') {
        return [pscustomobject]@{ transport = 'smtp'; sender_configured = $true
            pacing = @{ daily_limit = 24 }; latest_check = @{ status = 'succeeded'; completed_at = 'fixture' } }
    }
    if ($Uri -like '*/external-actions?*') {
        $now = [DateTimeOffset]::UtcNow
        $records = @(
            @{ id = 'recent'; task_id = 'task'; status = 'queued'; created_at = $now.AddHours(-1).ToString('o')
               public_context = @{ marketing = @{ campaign_id = $script:campaignIds[0]; stage = 'initial' }; body = 'PRIVATE_BODY' } },
            @{ id = 'executed'; status = 'succeeded'; created_at = $now.AddHours(-25).ToString('o'); executed_at = $now.AddMinutes(-5).ToString('o')
               public_context = @{ marketing = @{ campaign_id = $script:campaignIds[1]; stage = 'initial' } } },
            @{ id = 'old'; created_at = $now.AddHours(-25).ToString('o'); public_context = @{ marketing = @{ campaign_id = $script:campaignIds[0]; stage = 'initial' } } },
            @{ id = 'handoff'; created_at = $now.ToString('o'); public_context = @{ marketing = @{ campaign_id = $script:campaignIds[0]; stage = 'handoff' } } },
            @{ id = 'foreign'; created_at = $now.ToString('o'); public_context = @{ marketing = @{ campaign_id = $otherCampaign.ToString(); stage = 'initial' } } }
        )
        if ($script:windowMode -ne 'normal') {
            $records = @(1..200 | ForEach-Object {
                @{ id = $_; created_at = $now.AddMinutes(-1).ToString('o'); public_context = @{} }
            })
            if ($script:windowMode -in @('boundary', 'ambiguous')) {
                $records[-1].created_at = $now.AddHours(-25).ToString('o')
            }
            if ($script:windowMode -eq 'ambiguous') { $records[0].created_at = '11/02/2026 18:00:00' }
        } elseif ($script:historyFull) {
            $records += 1..195 | ForEach-Object { @{ id = 'unrelated'; public_context = @{} } }
        }
        # Invoke-RestMethod emits a JSON array as one pipeline collection object.
        $parsed = ConvertFrom-Json -InputObject (ConvertTo-Json -InputObject $records -Depth 12) -NoEnumerate
        Write-Output -NoEnumerate $parsed
        return
    }
    if ($Uri -like '*/automation') {
        $age = if ($Uri -like ('*/' + $script:campaignIds[0] + '/*')) { -2 } else { -31 }
        $wire = [pscustomobject]@{ readiness = @{ gmail_configured = $true }
            gmail_sync = @{ last_complete_at = [DateTimeOffset]::UtcNow.AddMinutes($age).ToString('o') }
            pending_reply_count = 12; pending_replies = @(1..12 | ForEach-Object { @{ id = $_; snippet = 'PRIVATE_REPLY' } }) }
        $parsed = ($wire | ConvertTo-Json -Depth 12) | ConvertFrom-Json
        if ($parsed.gmail_sync.last_complete_at -isnot [DateTime]) { throw 'Fixture did not exercise parsed ISO dates.' }
        return $parsed
    }
    if ($Uri -like '*/draft-batches') {
        return [pscustomobject]@{ task = @{ id = 'batch'; status = 'succeeded' }
            items = @(@{ prospect_id = 'prospect'; draft_id = 'draft'; status = 'ready'; body = 'PRIVATE_BODY' }) }
    }
    throw 'Unexpected request.'
}

try {
    New-Item -ItemType Directory -Path $fixtureScripts -Force | Out-Null
    Copy-Item -LiteralPath $helper -Destination $fixtureHelper
    $defined = . $fixtureHelper
    if ($null -ne $defined -or $script:requestCount -ne 0) { throw 'Dot-sourcing performed work.' }
    foreach ($value in @('ordinary-fixture-token-at-least-32-characters',
        'fixture-token-with-dollar$VALUE ${VALUE} $$', 'fixture-token-with-double" and single''quotes',
        'fixture-token-with-backslash\one\\two and Unicode-é')) {
        $script:expectedToken = $value
        $encoded = (ConvertTo-Json -InputObject $value -Compress).Replace('$', '$$')
        [IO.File]::WriteAllText($fixtureEnv, "CONTROL_API_TOKEN=$encoded`nUNRELATED=ignored`n")
        Invoke-CreatorControlApi -Path '/v1/marketing/campaigns' -Method Post -Body @{ actor = 'synthetic' } | Out-Null
        if ($script:capturedHeaders.Count -ne 0) { throw 'Headers were retained after success.' }
    }
    $singleQuoted = 'single-quoted-fixture-token-$VALUE $$ and a ''quote'
    foreach ($literalCase in @(
        @{ value = 'unquoted-fixture-token-at-least-32-characters'; literal = 'unquoted-fixture-token-at-least-32-characters' },
        @{ value = $singleQuoted; literal = "'" + $singleQuoted.Replace("'", "\'") + "'" }
    )) {
        $script:expectedToken = $literalCase.value
        [IO.File]::WriteAllText($fixtureEnv, 'CONTROL_API_TOKEN=' + $literalCase.literal)
        Invoke-CreatorControlApi -Path '/v1/marketing/campaigns' -Method Post -Body @{ actor = 'synthetic' } | Out-Null
    }
    $before = $script:requestCount
    foreach ($path in @('https://example.test/v1/marketing', '//example.test/v1/marketing',
        '/v1/career/profiles', '/v1/marketing/../tasks', '/v1/tasks\other',
        '/v1/marketing/%2e%2e/tasks', '/v1/marketing?x=1#fragment')) {
        Assert-Rejected { Invoke-CreatorControlApi -Path $path }
    }
    if ($script:requestCount -ne $before) { throw 'Rejected paths reached HTTP.' }
    foreach ($mode in @('redirect', 'provider-error')) {
        $script:requestMode = $mode
        Assert-Rejected { Invoke-CreatorControlApi -Path '/v1/marketing/campaigns' }
        if ($script:capturedHeaders.Count -ne 0) { throw 'Headers were retained after failure.' }
    }
    $script:requestMode = 'http409'
    try { Invoke-CreatorControlApi -Path '/v1/marketing/campaigns' | Out-Null; throw 'Expected conflict.' }
    catch {
        if ([string]$_ -notmatch 'CREATOR_CONTROL_HTTP_409' -or
            [string]$_ -match 'PRIVATE_|dummy-secret') { throw 'HTTP status sanitization failed.' }
    }
    if ($script:capturedHeaders.Count -ne 0) { throw 'Headers were retained after conflict.' }
    $script:requestMode = 'ok'
    $utc = [DateTime]::SpecifyKind([DateTime]::new(2026, 11, 2, 18, 0, 0), [DateTimeKind]::Utc)
    $offset = [DateTimeOffset]::new($utc)
    foreach ($date in @($utc, $utc.ToLocalTime(), $offset, '2026-11-02T23:30:00+05:30')) {
        if ((ConvertTo-CreatorReviewInstant $date).UtcDateTime -ne $utc) { throw 'Timestamp kind or offset was lost.' }
    }
    foreach ($date in @([DateTime]::SpecifyKind($utc, [DateTimeKind]::Unspecified),
        '2026-11-02T18:00:00', '11/02/2026 18:00:00', 'ambiguous')) {
        if ($null -ne (ConvertTo-CreatorReviewInstant $date)) { throw 'Ambiguous timestamp was accepted.' }
    }
    Assert-Rejected { Get-CreatorReviewSnapshot -CampaignId @($campaignA, $campaignA) }
    Assert-Rejected { Get-CreatorReviewSnapshot -CampaignId @($campaignA, $campaignB, $otherCampaign) }
    Assert-Rejected { Get-CreatorReviewSnapshot -CampaignId @([Guid]::Empty) }
    foreach ($full in @($false, $true)) {
        $script:historyFull = $full
        $script:readOnlyProbe = $true
        $before = $script:requestCount
        $snapshot = Get-CreatorReviewSnapshot -CampaignId @($campaignA, $campaignB)
        if ($script:requestCount - $before -ne 6 -or $snapshot.initial_actions.Count -ne 2 -or
            $snapshot.action_history_may_be_truncated -ne $full -or
            $snapshot.initial_creation_window_complete -ne (-not $full) -or
            -not $snapshot.campaigns[0].monitor_fresh -or $snapshot.campaigns[1].monitor_fresh -or
            $snapshot.campaigns[0].pending_reply_ids.Count -ne 10) { throw 'Scoped snapshot mismatch.' }
        if (($snapshot | ConvertTo-Json -Depth 15) -match 'PRIVATE_|dummy-secret|@') {
            throw 'Snapshot exposed private content.'
        }
    }
    foreach ($mode in @('recent', 'boundary', 'ambiguous')) {
        $script:windowMode = $mode
        $snapshot = Get-CreatorReviewSnapshot -CampaignId @($campaignA, $campaignB)
        if (-not $snapshot.action_history_may_be_truncated -or
            $snapshot.initial_creation_window_complete -ne ($mode -eq 'boundary')) {
            throw 'Bounded creation-window coverage was inferred incorrectly.'
        }
    }
    [IO.File]::WriteAllText($fixtureEnv, "CONTROL_API_TOKEN=`"bad`n")
    Assert-Rejected { Invoke-CreatorControlApi -Path '/v1/marketing/campaigns' }
    [IO.File]::WriteAllText($fixtureEnv, "CONTROL_API_TOKEN=one`nCONTROL_API_TOKEN=two`n")
    Assert-Rejected { Invoke-CreatorControlApi -Path '/v1/marketing/campaigns' }
    Write-Host 'Creator review API smoke passed (synthetic fixtures; no live requests).'
} finally {
    foreach ($path in @($fixtureHelper, $fixtureEnv, $fixtureScripts, $fixture)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
}
