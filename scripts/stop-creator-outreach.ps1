[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateCount(1, 10)][Guid[]]$CampaignId,
    [Parameter(Mandatory)][ValidateLength(1, 120)][string]$Actor,
    [ValidateLength(1, 1000)][string]$Reason = 'Owner stopped creator mailing until explicitly resumed',
    [switch]$StatusOnly
)

$ErrorActionPreference = 'Stop'
if ([Guid]::Empty -in $CampaignId -or @($CampaignId | Select-Object -Unique).Count -ne $CampaignId.Count) {
    throw 'Choose distinct saved campaign IDs.'
}
. (Join-Path $PSScriptRoot 'creator-review-api.ps1')
$failed = $false
foreach ($id in $CampaignId) {
    try {
        if ($StatusOnly) {
            $result = Invoke-CreatorControlApi -Path "/v1/marketing/campaigns/$id/automation"
            [pscustomobject]@{ campaign_id = $id; stop = $result.outreach_stop }
        } else {
            $result = Invoke-CreatorControlApi -Path "/v1/marketing/campaigns/$id/outreach/stop" -Method Post -Body @{
                actor = $Actor; reason = $Reason
            }
            $result | Select-Object campaign_id, outreach_paused, outreach_epoch, discovery_active,
                cancelled_tasks, cancellation_requested_tasks, in_flight_actions, ambiguous_actions
        }
    } catch {
        $failed = $true
        Write-Warning "Campaign $id stop/status could not be verified through the control API. No restart or sending was attempted."
    }
}
if ($failed) {
    throw 'At least one campaign remains unverified. Keep sending workers stopped until the durable stop is confirmed.'
}
