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
$maxModelsPerRequest = 4
$activePriority = @()

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

function Get-ModelPowerScore {
    param([Parameter(Mandatory)][object]$Model)
    $analysis = $Model.benchmarks.artificial_analysis
    if ($null -eq $analysis) { return $null }
    $values = @{}
    foreach ($name in @('intelligence_index', 'coding_index', 'agentic_index')) {
        $value = $analysis.$name
        if ($null -ne $value) {
            try {
                $number = [double]$value
                if (-not [double]::IsNaN($number) -and -not [double]::IsInfinity($number) -and $number -ge 0 -and $number -le 100) {
                    $values[$name] = $number
                }
            }
            catch { }
        }
    }
    if ($values.Count -eq 0) { return $null }
    return 0.50 * $(if ($values.ContainsKey('intelligence_index')) { $values.intelligence_index } else { 0 }) +
        0.30 * $(if ($values.ContainsKey('coding_index')) { $values.coding_index } else { 0 }) +
        0.20 * $(if ($values.ContainsKey('agentic_index')) { $values.agentic_index } else { 0 })
}

function Get-RankedFreeModels {
    param(
        [Parameter(Mandatory)][object[]]$Models,
        [Collections.Generic.HashSet[string]]$AvailableModels
    )
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
            [decimal]$(if ($null -eq $pricing.request) { '0' } else { $pricing.request }) -eq 0 -and
            ($null -eq $AvailableModels -or $AvailableModels.Contains($id))
    })
    return @($eligible | Sort-Object @{
        Expression = { if ($priority.ContainsKey([string]$_.id)) { 0 } else { 1 } }
    }, @{
        Expression = {
            if ($priority.ContainsKey([string]$_.id)) { $priority[[string]$_.id] }
            else { $activePriority.Count }
        }
    }, @{
        Expression = { if ($null -eq (Get-ModelPowerScore -Model $_)) { 1 } else { 0 } }
    }, @{
        Expression = {
            $score = Get-ModelPowerScore -Model $_
            if ($null -eq $score) { 0 } else { -$score }
        }
    }, @{
        Expression = {
            $parameters = @($_.supported_parameters)
            $score = 0
            if ($parameters -contains 'structured_outputs') { $score += 2 }
            if ($parameters -contains 'response_format') { $score += 1 }
            if ($parameters -contains 'tools') { $score += 1 }
            if ($parameters -contains 'reasoning') { $score += 0.5 }
            -$score
        }
    }, @{
        Expression = { -[int64]$_.context_length }
    }, @{
        Expression = { [string]$_.id }
    } | Select-Object -First $maxModelsPerRequest)
}

function Get-SafeOpenRouterFailure {
    param([Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord)
    $status = $null
    if ($ErrorRecord.Exception.Response) {
        $status = [int]$ErrorRecord.Exception.Response.StatusCode
    }
    $message = ''
    if ($ErrorRecord.ErrorDetails.Message) {
        try {
            $envelope = $ErrorRecord.ErrorDetails.Message | ConvertFrom-Json
            $message = [string]$envelope.error.message
        }
        catch { }
    }
    if ($message -match "models.*3 items or fewer") {
        return 'OpenRouter rejected too many fallbacks; this build now caps the request at three fallback entries.'
    }
    if ($message -match 'data policy') {
        return 'No zero-retention/no-training endpoint is currently available for the selected free models.'
    }
    if ($status -eq 429) { return 'The shared OpenRouter free request limit is currently exhausted.' }
    if ($status -in @(401, 403)) { return 'The OpenRouter inference key was rejected.' }
    return "OpenRouter returned HTTP $(if ($status) { $status } else { 'error' })."
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
    $zdrRequired = $true
    if ($values.OPENROUTER_ZDR) {
        if ($values.OPENROUTER_ZDR -match '^(?i:true|1|yes|on)$') { $zdrRequired = $true }
        elseif ($values.OPENROUTER_ZDR -match '^(?i:false|0|no|off)$') { $zdrRequired = $false }
        else { throw 'OPENROUTER_ZDR must be true or false.' }
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
    try {
        $keyInfo = (Invoke-RestMethod -Uri "$apiBase/key" -Headers $headers -TimeoutSec 20).data
        $catalog = Invoke-RestMethod -Uri "$apiBase/models?output_modalities=text" -Headers $headers -TimeoutSec 30
    }
    catch {
        throw "OpenRouter discovery failed safely: $(Get-SafeOpenRouterFailure -ErrorRecord $_)"
    }
    $availableModels = $null
    if ($zdrRequired) {
        $availableModels = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        try {
            $zdrEndpoints = Invoke-RestMethod -Uri "$apiBase/endpoints/zdr" -Headers $headers -TimeoutSec 30
        }
        catch {
            throw "OpenRouter privacy discovery failed safely: $(Get-SafeOpenRouterFailure -ErrorRecord $_)"
        }
        foreach ($endpoint in @($zdrEndpoints.data)) {
            $modelId = [string]$endpoint.model_id
            if ($modelId.EndsWith(':free') -and ($null -eq $endpoint.status -or [string]$endpoint.status -eq '0')) {
                $null = $availableModels.Add($modelId)
            }
        }
    }
    $models = @(Get-RankedFreeModels -Models @($catalog.data) -AvailableModels $availableModels)
    if ($models.Count -eq 0) {
        throw 'OpenRouter returned no verified zero-cost text model compatible with the configured privacy policy.'
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
    Write-Host "Privacy route:      $(if ($zdrRequired) { 'no-training + live ZDR endpoints only' } else { 'no-training; provider retention allowed by configuration' })"
    Write-Host 'Smart fallback order (live benchmark/capability rank):'
    for ($index = 0; $index -lt $models.Count; $index++) {
        $power = Get-ModelPowerScore -Model $models[$index]
        $powerText = if ($null -eq $power) { 'benchmark pending' } else { "power $($power.ToString('0.0'))" }
        Write-Host ("  {0}. {1} ({2}, {3:N0} context)" -f ($index + 1), $models[$index].id, $powerText, $models[$index].context_length)
    }

    if ($Smoke) {
        $body = @{
            model = [string]$models[0].id
            models = @($models | Select-Object -Skip 1 | ForEach-Object { [string]$_.id })
            messages = @(@{ role = 'user'; content = 'Reply with exactly OPENROUTER_FREE_OK and nothing else.' })
            stream = $false
            temperature = 0
            max_tokens = 256
            provider = @{
                allow_fallbacks = $true
                require_parameters = $true
                data_collection = 'deny'
                zdr = $zdrRequired
            }
        } | ConvertTo-Json -Depth 8
        if (@($models | Where-Object { @($_.supported_parameters) -notcontains 'reasoning' }).Count -eq 0) {
            $bodyObject = $body | ConvertFrom-Json
            $bodyObject | Add-Member -NotePropertyName reasoning -NotePropertyValue @{ effort = 'minimal'; exclude = $true }
            $body = $bodyObject | ConvertTo-Json -Depth 8
        }
        $smokeHeaders = @{
            Authorization = "Bearer $apiKey"
            'X-OpenRouter-Metadata' = 'enabled'
            'HTTP-Referer' = 'https://github.com/ReaperXD67/autonomous-personal-agent'
            'X-Title' = 'Hermes Autonomous Personal Agent'
        }
        try {
            $response = Invoke-RestMethod -Method Post -Uri "$apiBase/chat/completions" -Headers $smokeHeaders -ContentType 'application/json' -Body $body -TimeoutSec 180
        }
        catch {
            throw "OpenRouter smoke failed safely: $(Get-SafeOpenRouterFailure -ErrorRecord $_)"
        }
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
        Write-Host 'Applying the key to the managed Hermes and career-worker routes.'
        & (Join-Path $PSScriptRoot 'up.ps1') -Agent
    }
}
finally {
    $apiKey = $null
    Pop-Location
}
