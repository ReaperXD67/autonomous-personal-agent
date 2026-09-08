[CmdletBinding()]
param(
    [switch]$Agent,
    [switch]$LocalModel
)

$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$failures = 0

function Write-Check {
    param([string]$Level, [string]$Name, [string]$Detail)
    $color = switch ($Level) { 'OK' { 'Green' } 'WARN' { 'Yellow' } 'FAIL' { 'Red' } default { 'Cyan' } }
    Write-Host ("[{0,-4}] {1,-24} {2}" -f $Level, $Name, $Detail) -ForegroundColor $color
    if ($Level -eq 'FAIL') { $script:failures++ }
}

function Read-EnvironmentFile {
    param([Parameter(Mandatory)][string]$Path)
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1]
    }
    return $values
}

Push-Location $projectRoot
try {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Check OK 'Docker CLI' ((docker --version) -join ' ')
    }
    else { Write-Check FAIL 'Docker CLI' 'not found'; exit 1 }

    docker info *> $null
    if ($LASTEXITCODE -eq 0) { Write-Check OK 'Docker Engine' 'reachable' }
    else { Write-Check FAIL 'Docker Engine' 'not reachable; start Docker Desktop' }

    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) { Write-Check OK 'Docker Compose' ((docker compose version --short) -join ' ') }
    else { Write-Check FAIL 'Docker Compose' 'Compose v2 is required' }

    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        wsl.exe --status *> $null
        if ($LASTEXITCODE -eq 0) { Write-Check OK 'WSL2' 'available' }
        else { Write-Check WARN 'WSL2' 'status check failed; Docker must use the WSL2 backend' }
    }
    else { Write-Check WARN 'WSL2' 'wsl.exe not found' }

    $requiredFiles = @('docker-compose.yml', '.env.example', 'config/postgres/init/003_worker_leases.sql')
    $missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missing.Count -eq 0) { Write-Check OK 'Required files' 'present' }
    else { Write-Check FAIL 'Required files' ("missing: " + ($missing -join ', ')) }

    if (-not (Test-Path -LiteralPath '.env')) {
        Write-Check WARN 'Environment' 'missing; run scripts/init-env.ps1'
    }
    else {
        $envText = Get-Content -Raw -LiteralPath '.env'
        if ($envText -match '(?m)^CONTROL_API_TOKEN=CHANGE_ME') {
            Write-Check FAIL 'Environment' 'contains unsafe placeholder secrets'
        }
        else { Write-Check OK 'Environment' 'local secrets initialized' }
    }

    docker compose config --quiet *> $null
    if ($LASTEXITCODE -eq 0) { Write-Check OK 'Compose model' 'valid' }
    else { Write-Check FAIL 'Compose model' 'invalid; run docker compose config' }

    $requiredServices = @('postgres', 'redis', 'control-api', 'dispatcher', 'worker')
    if ($Agent) { $requiredServices += @('omniroute', 'hermes', 'ollama') }
    elseif ($LocalModel) { $requiredServices += 'ollama' }
    foreach ($service in $requiredServices) {
        $profiles = @()
        if ($Agent) { $profiles += @('--profile', 'agent') }
        if ($LocalModel) { $profiles += @('--profile', 'local-model') }
        $containerId = & docker compose @profiles ps --quiet $service 2>$null
        if (-not $containerId) { Write-Check WARN $service 'not running'; continue }
        $state = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId
        if ($state -eq 'healthy' -or $state -eq 'exited') { Write-Check OK $service $state }
        else { Write-Check FAIL $service $state }
    }

    $gpu = $null
    $gpuCommand = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($gpuCommand) {
        $gpuOutput = @(& $gpuCommand.Source --query-gpu=name,memory.total --format=csv,noheader 2>$null)
        $gpuCommandSucceeded = ($LASTEXITCODE -eq 0)
        if ($gpuCommandSucceeded) {
            $gpu = $gpuOutput | Select-Object -First 1
        }
    }
    if ($gpu) {
        Write-Check OK 'NVIDIA GPU' $gpu
        Write-Check INFO 'Nemotron 3' 'use a remote free provider; current local checkpoints exceed 8 GB VRAM'
    }
    else { Write-Check WARN 'NVIDIA GPU' 'not detected; lazy Qwen fallback will use slower CPU inference' }

    if (Test-Path -LiteralPath '.env') {
        $environment = Read-EnvironmentFile -Path '.env'
        $omniRouteKey = [string]$environment.OMNIROUTE_API_KEY
        if ($omniRouteKey -and $omniRouteKey -notmatch 'CHANGE_ME') {
            Write-Check OK 'OmniRoute key' 'configured in ignored .env'
        }
        else { Write-Check WARN 'OmniRoute key' 'finish dashboard onboarding and create a scoped inference key' }

        $openRouterEnabled = [string]$environment.OPENROUTER_ENABLED -eq 'true'
        $openRouterKey = [string]$environment.OPENROUTER_API_KEY
        if ($openRouterEnabled -and $openRouterKey -and $openRouterKey -notmatch 'CHANGE_ME') {
            Write-Check OK 'OpenRouter route' 'enabled for the Hermes fallback and governed career drafting; run scripts/openrouter.ps1 -Smoke'
        }
        elseif ($openRouterEnabled) {
            Write-Check FAIL 'OpenRouter route' 'enabled without a usable key'
        }
        elseif ($Agent) { Write-Check WARN 'OpenRouter route' 'fallback is prepared but unverified; configure with scripts/openrouter.ps1 -Configure' }
        else { Write-Check INFO 'OpenRouter route' 'configure with scripts/openrouter.ps1 -Configure before full agent validation' }

        if ($Agent -and $omniRouteKey) {
            try {
                $headers = @{ Authorization = "Bearer $omniRouteKey" }
                $catalog = Invoke-RestMethod -Uri 'http://127.0.0.1:20128/v1/models' -Headers $headers -TimeoutSec 15
                $concreteModels = @($catalog.data | Where-Object {
                    [string]$_.id -notmatch '^(auto|free)/'
                })
                $owners = @($concreteModels | ForEach-Object { [string]$_.owned_by } | Where-Object { $_ } | Sort-Object -Unique)
                $ownerSummary = if ($owners.Count -gt 0) { $owners -join ', ' } else { 'unreported providers' }
                Write-Check OK 'OmniRoute pool' ("{0} concrete routes across {1}" -f $concreteModels.Count, $ownerSummary)

                $openRouterInOmniRoute = @($concreteModels | Where-Object {
                    [string]$_.owned_by -match 'openrouter' -or [string]$_.id -match 'openrouter'
                }).Count -gt 0
                if ($openRouterEnabled -and $openRouterInOmniRoute) {
                    Write-Check INFO 'Route composition' 'OmniRoute currently exposes OpenRouter candidates; the explicit OpenRouter fallback remains the next independent route'
                }
                else {
                    Write-Check OK 'Route composition' 'OmniRoute primary and explicit OpenRouter fallback are independently configured'
                }
            }
            catch {
                Write-Check WARN 'OmniRoute pool' 'catalog unavailable; run scripts/agent-smoke.ps1 after the gateway is healthy'
            }

            $hermesContainer = docker compose --profile agent ps --quiet hermes 2>$null
            if ($hermesContainer) {
                $primaryRoute = (& docker compose --profile agent exec -T hermes hermes config get model.default 2>$null | Select-Object -Last 1).Trim()
                if ($primaryRoute -eq 'free/default') {
                    Write-Check OK 'Hermes primary route' 'free/default through OmniRoute'
                }
                else {
                    Write-Check FAIL 'Hermes primary route' "expected free/default; found '$primaryRoute'"
                }

                try {
                    $fallbackJson = (& docker compose --profile agent exec -T hermes hermes config get fallback_providers --json 2>$null) -join "`n"
                    $fallbacks = @($fallbackJson | ConvertFrom-Json)
                    $openRouterFallback = @($fallbacks | Where-Object {
                        [string]$_.provider -eq 'openrouter' -and
                        [string]$_.model -eq 'openrouter/free' -and
                        [string]$_.key_env -eq 'OPENROUTER_API_KEY'
                    }).Count -gt 0
                    $localFallback = @($fallbacks | Where-Object {
                        [string]$_.provider -eq 'custom' -and
                        [string]$_.model -eq 'qwen3:8b' -and
                        ([string]$_.base_url).TrimEnd('/') -eq 'http://ollama:11434/v1'
                    }).Count -gt 0
                    $ordered = $fallbacks.Count -eq 2 -and
                        [string]$fallbacks[0].provider -eq 'openrouter' -and
                        [string]$fallbacks[0].model -eq 'openrouter/free' -and
                        [string]$fallbacks[1].model -eq 'qwen3:8b'
                    if ($openRouterFallback -and $localFallback -and $ordered) {
                        Write-Check OK 'Hermes continuity' 'OmniRoute -> OpenRouter free -> local Qwen'
                    }
                    else {
                        Write-Check FAIL 'Hermes continuity' 'managed ordered fallback chain is not active'
                    }
                }
                catch {
                    Write-Check WARN 'Hermes continuity' 'fallback configuration could not be inspected'
                }

                $loadedModels = (& docker compose --profile agent exec -T ollama ollama ps 2>$null) -join "`n"
                $localModelName = if ($environment.LOCAL_MODEL) { [string]$environment.LOCAL_MODEL } else { 'qwen3:8b' }
                if ($loadedModels -match [regex]::Escape($localModelName)) {
                    Write-Check INFO 'Qwen lifecycle' 'loaded by a recent request; Ollama will unload it after the configured idle period'
                }
                else {
                    Write-Check OK 'Qwen lifecycle' 'cached but unloaded; lazy fallback is armed'
                }
            }
        }
    }
}
finally {
    Pop-Location
}

if ($failures -gt 0) { exit 1 }
exit 0
