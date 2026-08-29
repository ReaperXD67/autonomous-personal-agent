[CmdletBinding()]
param(
    [switch]$Configure,
    [switch]$Smoke,
    [switch]$ConfirmTenCreditsPurchased
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
$apiBase = 'https://openrouter.ai/api/v1'
$defaultPriority = @(
    'nvidia/nemotron-3-ultra-550b-a55b:free',
    'z-ai/glm-5.2:free',
    'nvidia/nemotron-3-super-120b-a12b:free',
    'minimax/minimax-m3:free',
    'google/gemma-4-31b-it:free',
    'thinkingmachines/inkling:free',
    'dots-studio/dots-3-note-preview:free',
    'google/gemma-4-26b-a4b-it:free'
)
$activePriority = $defaultPriority

function Read-EnvironmentFile {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1]
    }
    return $values
}

function Set-EnvironmentEntry {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Value
    )
    $lines = [Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match "^$([regex]::Escape($Name))=") {
            $lines.Add("$Name=$Value")
            $found = $true
        }
        else { $lines.Add($line) }
    }
    if (-not $found) { $lines.Add("$Name=$Value") }
    $utf8NoBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllLines($envPath, $lines, $utf8NoBom)
}

function Convert-SecureValue {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Get-RankedFreeModels {
    param([Parameter(Mandatory)][object[]]$Models)
    $priority = @{}
    for ($index = 0; $index -lt $activePriority.Count; $index++) {
        $priority[$activePriority[$index]] = $index
    }
    $eligible = @($Models | Where-Object {
        $id = [string]$_.id
        $pricing = $_.pricing
        $inputs = @($_.architecture.input_modalities)
        $outputs = @($_.architecture.output_modalities)
        $id.EndsWith(':free') -and
            $id -notmatch 'content-safety|moderation|embedding' -and
            $inputs -contains 'text' -and $outputs -contains 'text' -and
            [decimal]$pricing.prompt -eq 0 -and
            [decimal]$pricing.completion -eq 0 -and
            [decimal]$(if ($null -eq $pricing.request) { '0' } else { $pricing.request }) -eq 0
    })
    return @($eligible | Sort-Object @{
        Expression = {
            if ($priority.ContainsKey([string]$_.id)) { $priority[[string]$_.id] }
            else { $activePriority.Count + 1 }
        }
    }, @{
        Expression = { -[int64]$_.context_length }
    }, @{
        Expression = { [string]$_.id }
    } | Select-Object -First 8)
}

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $envPath)) {
        throw 'Missing .env. Run scripts/init-env.ps1 first.'
    }

    $values = Read-EnvironmentFile
    $publishedLimit = 50
    if ($values.OPENROUTER_FREE_DAILY_ALLOWANCE) {
        $publishedLimit = [int]$values.OPENROUTER_FREE_DAILY_ALLOWANCE
    }
    if ($ConfirmTenCreditsPurchased) { $publishedLimit = 1000 }
    if ($publishedLimit -notin @(50, 1000)) {
        throw 'OPENROUTER_FREE_DAILY_ALLOWANCE must be 50 or 1000.'
    }
    if ($values.OPENROUTER_MODEL_PRIORITY) {
        $activePriority = @($values.OPENROUTER_MODEL_PRIORITY.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if (@($activePriority | Where-Object { -not $_.EndsWith(':free') }).Count -gt 0) {
            throw 'Every OPENROUTER_MODEL_PRIORITY entry must end with :free.'
        }
    }
    $apiKey = [string]$values.OPENROUTER_API_KEY
    if ($Configure) {
        $secure = Read-Host 'Paste a scoped OpenRouter inference API key (input is hidden)' -AsSecureString
        $apiKey = Convert-SecureValue $secure
        if (-not $apiKey.StartsWith('sk-or-')) {
            throw 'The value does not look like an OpenRouter API key. Nothing was written.'
        }
    }
    if (-not $apiKey) {
        throw 'OpenRouter is not configured. Run scripts/openrouter.ps1 -Configure; do not paste the key into chat or a command argument.'
    }

    $headers = @{ Authorization = "Bearer $apiKey"; Accept = 'application/json' }
    $keyInfo = (Invoke-RestMethod -Uri "$apiBase/key" -Headers $headers -TimeoutSec 20).data
    $catalog = Invoke-RestMethod -Uri "$apiBase/models?output_modalities=text" -Headers $headers -TimeoutSec 30
    $models = @(Get-RankedFreeModels -Models @($catalog.data))
    if ($models.Count -lt 2) {
        throw 'OpenRouter returned fewer than two verified zero-cost text models.'
    }
    if ($publishedLimit -eq 1000 -and $keyInfo.is_free_tier) {
        throw 'The key reports that no credits were purchased; the 1,000-request allowance cannot be enabled.'
    }

    if ($Configure) {
        Set-EnvironmentEntry -Name 'OPENROUTER_API_KEY' -Value $apiKey
        Set-EnvironmentEntry -Name 'OPENROUTER_ENABLED' -Value 'true'
        Set-EnvironmentEntry -Name 'OPENROUTER_FREE_DAILY_ALLOWANCE' -Value ([string]$publishedLimit)
        Write-Host 'Stored the validated key only in ignored .env and enabled free routing.' -ForegroundColor Green
    }

    $runtimeLimit = if ($publishedLimit -eq 1000) { 900 } else { 40 }
    Write-Host "Account status:     $(if ($keyInfo.is_free_tier) { 'no prior credit purchase reported' } else { 'credits purchased before; amount not disclosed to this key' })"
    Write-Host "Configured free cap: $publishedLimit requests/day shared across free models"
    Write-Host "Worker local cap:   $runtimeLimit requests/day (headroom preserved)"
    if (-not $keyInfo.is_free_tier -and $publishedLimit -eq 50) {
        Write-Host 'Higher allowance not assumed. Re-run -Configure -ConfirmTenCreditsPurchased only if all-time purchases are at least USD 10.' -ForegroundColor Yellow
    }
    if ($null -ne $keyInfo.limit) {
        Write-Host "Key spend limit:    `$$($keyInfo.limit) ($$($keyInfo.limit_remaining) remaining)"
    }
    Write-Host 'Verified fallback order:'
    for ($index = 0; $index -lt $models.Count; $index++) {
        Write-Host ("  {0}. {1} ({2:N0} context)" -f ($index + 1), $models[$index].id, $models[$index].context_length)
    }

    if ($Smoke) {
        $body = @{
            model = [string]$models[0].id
            models = @($models | Select-Object -Skip 1 | ForEach-Object { [string]$_.id })
            messages = @(@{ role = 'user'; content = 'Reply with exactly OPENROUTER_FREE_OK and nothing else.' })
            stream = $false
            temperature = 0
            max_tokens = 32
            provider = @{
                allow_fallbacks = $true
                require_parameters = $true
                data_collection = 'deny'
                zdr = $true
            }
        } | ConvertTo-Json -Depth 8
        $smokeHeaders = @{
            Authorization = "Bearer $apiKey"
            'X-OpenRouter-Metadata' = 'enabled'
            'HTTP-Referer' = 'https://github.com/ReaperXD67/autonomous-personal-agent'
            'X-Title' = 'Hermes Autonomous Personal Agent'
        }
        $response = Invoke-RestMethod -Method Post -Uri "$apiBase/chat/completions" -Headers $smokeHeaders -ContentType 'application/json' -Body $body -TimeoutSec 180
        if ([decimal]$response.usage.cost -ne 0) {
            throw "OpenRouter smoke unexpectedly reported non-zero cost; routing remains disabled until investigated."
        }
        $content = [string]$response.choices[0].message.content
        if ($content.Trim() -ne 'OPENROUTER_FREE_OK') {
            throw 'A free model responded, but the exact smoke assertion failed.'
        }
        Write-Host "Free completion passed with $($response.model); reported cost `$$($response.usage.cost)." -ForegroundColor Green
    }

    if ($Configure) {
        Write-Host 'Restart the job worker: docker compose up -d --force-recreate job-worker'
    }
}
finally {
    $apiKey = $null
    Pop-Location
}
