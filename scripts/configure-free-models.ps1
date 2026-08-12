[CmdletBinding()]
param(
    [string]$OmniRouteUrl = 'http://127.0.0.1:20128',
    [switch]$SkipInferenceTest
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'

function Get-DotEnvValues {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw 'Missing .env. Run scripts/init-env.ps1 first.'
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $values[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
        }
    }
    return $values
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Value
    )

    $lines = [Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^$([regex]::Escape($Name))=") {
            $lines.Add("$Name=$Value")
            $found = $true
        }
        else {
            $lines.Add($line)
        }
    }
    if (-not $found) {
        $lines.Add("$Name=$Value")
    }

    $utf8NoBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllLines($Path, $lines, $utf8NoBom)
}

function Invoke-OmniRoute {
    param(
        [Parameter(Mandatory)][string]$Path,
        [ValidateSet('Get', 'Post', 'Put', 'Patch', 'Delete')][string]$Method = 'Get',
        [object]$Body,
        [hashtable]$Headers
    )

    $parameters = @{
        Uri = "$($OmniRouteUrl.TrimEnd('/'))$Path"
        Method = $Method
        WebSession = $script:session
        TimeoutSec = 30
    }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = $Body | ConvertTo-Json -Depth 12 -Compress
    }
    if ($Headers) {
        $parameters.Headers = $Headers
    }
    return Invoke-RestMethod @parameters
}

Push-Location $projectRoot
try {
    $envValues = Get-DotEnvValues -Path $envPath
    $managementPassword = $envValues['OMNIROUTE_INITIAL_PASSWORD']
    if (-not $managementPassword -or $managementPassword.StartsWith('CHANGE_ME')) {
        throw 'OMNIROUTE_INITIAL_PASSWORD is missing or still a placeholder.'
    }

    docker compose --profile agent up -d omniroute
    if ($LASTEXITCODE -ne 0) { throw 'Could not start OmniRoute.' }

    $deadline = (Get-Date).AddMinutes(2)
    do {
        try {
            $health = Invoke-RestMethod -Uri "$($OmniRouteUrl.TrimEnd('/'))/healthz" -TimeoutSec 5
        }
        catch {
            $health = $null
        }
        if ($health) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if (-not $health) { throw 'OmniRoute did not become ready within two minutes.' }

    $script:session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-OmniRoute -Path '/api/auth/login' -Method Post -Body @{ password = $managementPassword } | Out-Null

    # Block routes that are reverse-engineered, currently contradict their
    # documented keyless behavior, or carry an upstream ToS warning. AI Horde
    # remains available as its documented anonymous fallback.
    $denyProviders = @(
        'aug', 'auggie',
        'chipotle', 'pepper',
        'ddgw', 'duckduckgo-web',
        'felo', 'felo-web',
        'llm7',
        'mcode', 'mimocode',
        'oc', 'opencode',
        'pol', 'pollinations',
        'theoldllm', 'tllm',
        'veoaifree-web', 'veo-free'
    )
    $settings = Invoke-OmniRoute -Path '/api/settings'
    $blocked = @($settings.blockedProviders | Where-Object { $_ }) + $denyProviders |
        Sort-Object -Unique
    Invoke-OmniRoute -Path '/api/settings' -Method Patch -Headers @{
        'If-Match' = [string]$settings.settingsRevision
    } -Body @{ blockedProviders = $blocked } | Out-Null

    # OVHcloud's anonymous OpenAI-compatible endpoint is official and needs no
    # provider account. A compatible node is used because OmniRoute 3.8.49 does
    # not classify this optional-auth provider as a built-in no-auth provider.
    $nodes = Invoke-OmniRoute -Path '/api/provider-nodes'
    $ovhNode = $nodes.nodes | Where-Object { $_.prefix -eq 'ovhfree' } | Select-Object -First 1
    if (-not $ovhNode) {
        $ovhNode = (Invoke-OmniRoute -Path '/api/provider-nodes' -Method Post -Body @{
            name = 'OVHcloud Anonymous'
            prefix = 'ovhfree'
            apiType = 'chat'
            type = 'openai-compatible'
            baseUrl = 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1'
            chatPath = '/chat/completions'
            modelsPath = '/models'
        }).node
    }

    $providers = Invoke-OmniRoute -Path '/api/providers'
    $ovhConnection = $providers.connections |
        Where-Object { $_.provider -eq $ovhNode.id } |
        Select-Object -First 1
    if (-not $ovhConnection) {
        $ovhConnection = (Invoke-OmniRoute -Path '/api/providers' -Method Post -Body @{
            provider = $ovhNode.id
            name = 'OVHcloud Anonymous'
            priority = 1
            globalPriority = 1
        }).connection
    }

    # Remove stale keyless connections if an older run created them. Their live
    # endpoints returned 401 during verification on 2026-08-12.
    $providers = Invoke-OmniRoute -Path '/api/providers'
    $staleIds = @($providers.connections |
        Where-Object { $_.provider -in @('llm7', 'pollinations') } |
        ForEach-Object { $_.id })
    if ($staleIds.Count -gt 0) {
        Invoke-OmniRoute -Path '/api/providers' -Method Delete -Body @{ ids = $staleIds } | Out-Null
    }

    $comboModels = @(
        @{ kind = 'model'; providerId = 'ovhfree'; model = 'ovhfree/Mistral-Small-3.2-24B-Instruct-2506'; label = 'Mistral Small' },
        @{ kind = 'model'; providerId = 'ovhfree'; model = 'ovhfree/Qwen3-32B'; label = 'Qwen3 32B' },
        @{ kind = 'model'; providerId = 'ovhfree'; model = 'ovhfree/gpt-oss-120b'; label = 'GPT OSS 120B' },
        @{ kind = 'model'; providerId = 'ovhfree'; model = 'ovhfree/Qwen3.6-27B'; label = 'Qwen 3.6 27B' },
        @{ kind = 'model'; providerId = 'ovhfree'; model = 'ovhfree/Meta-Llama-3_3-70B-Instruct'; label = 'Llama 3.3 70B' },
        @{ kind = 'model'; providerId = 'aihorde'; model = 'aihorde/google/gemma-4-31b'; label = 'AI Horde Gemma fallback' },
        @{ kind = 'model'; providerId = 'aihorde'; model = 'aihorde/aphrodite/TheDrummer/Cydonia-24B-v4.3'; label = 'AI Horde Cydonia fallback' }
    )
    $comboBody = @{
        name = 'free/default'
        description = 'Zero-cost failover: OVHcloud official anonymous inference first, AI Horde documented anonymous inference last. No account, card, or provider key required.'
        strategy = 'priority'
        models = $comboModels
        allowedProviders = @('ovhfree', 'aihorde')
        config = @{
            maxRetries = 0
            failoverBeforeRetry = $true
            targetTimeoutMs = 120000
            trackMetrics = $true
            responseValidation = @{ minContentLength = 1 }
        }
    }
    $combos = Invoke-OmniRoute -Path '/api/combos'
    $freeCombo = $combos.combos | Where-Object { $_.name -eq 'free/default' } | Select-Object -First 1
    if ($freeCombo) {
        $freeCombo = Invoke-OmniRoute -Path "/api/combos/$($freeCombo.id)" -Method Put -Body $comboBody
    }
    else {
        $freeCombo = Invoke-OmniRoute -Path '/api/combos' -Method Post -Body $comboBody
    }

    # Create the local inference key once. The cleartext value is only returned
    # on creation, so a present key is reused from ignored .env and never rotated
    # during an ordinary idempotent run.
    $currentGatewayKey = $envValues['OMNIROUTE_API_KEY']
    $keyList = Invoke-OmniRoute -Path '/api/keys'
    $storedKey = $keyList.keys | Where-Object { $_.name -eq 'hermes-local' } | Select-Object -First 1
    $usableLocalKey = $currentGatewayKey -and -not $currentGatewayKey.StartsWith('CHANGE_ME')
    if (-not $storedKey) {
        $createdKey = Invoke-OmniRoute -Path '/api/keys' -Method Post -Body @{
            name = 'hermes-local'
            scopes = @('self:usage')
            noLog = $false
            usageLimitEnabled = $false
        }
        $currentGatewayKey = $createdKey.key
        Set-DotEnvValue -Path $envPath -Name 'OMNIROUTE_API_KEY' -Value $currentGatewayKey
    }
    elseif (-not $usableLocalKey) {
        throw 'OmniRoute already has hermes-local, but .env lacks its cleartext key. Regenerate it deliberately in the dashboard, then update OMNIROUTE_API_KEY.'
    }

    docker compose --profile agent up -d --force-recreate hermes
    if ($LASTEXITCODE -ne 0) { throw 'Could not recreate Hermes with the local gateway key.' }

    $hermesPython = '/opt/hermes/.venv/bin/python'
    $hermesCli = '/opt/hermes/hermes'
    $configCommands = @(
        @('config', 'set', 'model.provider', 'custom'),
        @('config', 'set', 'model.default', 'free/default'),
        @('config', 'set', 'model.base_url', 'http://omniroute:20128/v1'),
        @('config', 'set', 'model.context_length', '65536')
    )
    foreach ($arguments in $configCommands) {
        docker compose exec -T hermes $hermesPython $hermesCli @arguments | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Hermes configuration failed: $($arguments -join ' ')" }
    }

    # Send the local gateway key over stdin so it never appears in the host
    # process list, command history, or a configuration error message.
    $currentGatewayKey | docker compose exec -T hermes sh -lc `
        'IFS= read -r gateway_key; /opt/hermes/.venv/bin/python /opt/hermes/hermes config set model.api_key "$gateway_key" >/dev/null'
    if ($LASTEXITCODE -ne 0) { throw 'Hermes gateway-key configuration failed.' }

    docker compose restart hermes | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restart Hermes.' }

    if (-not $SkipInferenceTest) {
        $testBody = @{
            model = 'free/default'
            messages = @(@{ role = 'user'; content = 'Reply with exactly FREE_ROUTE_OK' })
            max_tokens = 24
            temperature = 0
            stream = $false
        } | ConvertTo-Json -Depth 6 -Compress
        $result = Invoke-RestMethod -Uri "$($OmniRouteUrl.TrimEnd('/'))/v1/chat/completions" `
            -Method Post `
            -Headers @{ Authorization = "Bearer $currentGatewayKey" } `
            -ContentType 'application/json' `
            -Body $testBody `
            -TimeoutSec 300
        if (-not $result.choices[0].message.content) {
            throw 'Free-route inference returned no assistant content.'
        }
        Write-Host ("Verified free/default via {0}." -f $result.model)
    }

    Write-Host 'Configured OVHcloud anonymous + AI Horde anonymous fallback.'
    Write-Host 'Hermes now uses model free/default through OmniRoute.'
}
finally {
    Pop-Location
}
