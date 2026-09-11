[CmdletBinding()]
param(
    [string]$Model = 'free/default'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        throw 'Missing .env. Run scripts/init-env.ps1 and complete OmniRoute onboarding first.'
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $key = $values.OMNIROUTE_API_KEY
    if (-not $key -or $key -match '^CHANGE_ME') {
        throw 'OMNIROUTE_API_KEY is not configured. Create a scoped inference key in the loopback dashboard and save it only in .env.'
    }
    $port = if ($values.OMNIROUTE_PORT) { $values.OMNIROUTE_PORT } else { '20128' }
    $baseUrl = "http://127.0.0.1:$port/v1"
    $headers = @{ Authorization = "Bearer $key" }

    $models = Invoke-RestMethod -Method Get -Uri "$baseUrl/models" -Headers $headers -TimeoutSec 20
    if (-not $models.data -or $models.data.Count -eq 0) {
        throw 'OmniRoute returned no usable models. Connect a free or local provider first.'
    }
    Write-Host "OmniRoute listed $($models.data.Count) model(s)."

    $body = @{
        model = $Model
        messages = @(@{ role = 'user'; content = 'Reply with exactly ROUTE_OK and nothing else.' })
        max_tokens = 32
        temperature = 0
        stream = $false
    } | ConvertTo-Json -Depth 6
    try {
        $result = Invoke-RestMethod -Method Post -Uri "$baseUrl/chat/completions" -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 120
    }
    catch {
        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $null }
        $classification = if ($status -in @(401, 403)) { 'the scoped inference key was rejected' }
            elseif ($status -eq 429) { 'the selected free route is rate-limited' }
            elseif ($status) { "the gateway returned HTTP $status" }
            else { 'the gateway was unavailable or timed out' }
        throw "OmniRoute inference failed for '$Model': $classification. Inspect bounded container logs locally for the correlation-safe cause."
    }
    $content = [string]$result.choices[0].message.content
    if ($content.Trim() -ne 'ROUTE_OK') {
        throw 'OmniRoute did not return the expected exact harmless canary.'
    }
    $selectedModel = [string]$result.model
    if ($selectedModel.Length -gt 160) { $selectedModel = $selectedModel.Substring(0, 160) }
    Write-Host "Inference passed through route '$Model'; gateway reported '$selectedModel'."
}
finally {
    Pop-Location
}
