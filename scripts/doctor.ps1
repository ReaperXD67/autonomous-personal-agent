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
    if ($Agent) { $requiredServices += @('omniroute', 'hermes') }
    if ($LocalModel) { $requiredServices += 'ollama' }
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

    $gpu = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1
    if ($LASTEXITCODE -eq 0 -and $gpu) {
        Write-Check OK 'NVIDIA GPU' $gpu
        Write-Check INFO 'Nemotron 3' 'use a remote free provider; current local checkpoints exceed 8 GB VRAM'
    }
    else { Write-Check WARN 'NVIDIA GPU' 'not detected; local-model profile unavailable' }

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
            Write-Check OK 'OpenRouter route' 'enabled with an ignored worker-only key; run scripts/openrouter.ps1 -Smoke'
        }
        elseif ($openRouterEnabled) {
            Write-Check FAIL 'OpenRouter route' 'enabled without a usable key'
        }
        else { Write-Check INFO 'OpenRouter route' 'optional; configure with scripts/openrouter.ps1 -Configure' }

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
                    Write-Check WARN 'Shared free quota' 'OpenRouter is enabled both directly and in OmniRoute; remove it from OmniRoute so the PostgreSQL daily cap stays authoritative'
                }
                else {
                    Write-Check OK 'Quota isolation' 'OpenRouter career calls and OmniRoute interactive pools do not overlap'
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
                    $localFallback = @($fallbacks | Where-Object {
                        [string]$_.provider -eq 'custom' -and
                        [string]$_.model -eq 'qwen3:8b' -and
                        ([string]$_.base_url).TrimEnd('/') -eq 'http://ollama:11434/v1'
                    }).Count -gt 0
                    if ($localFallback) {
                        Write-Check OK 'Hermes continuity' 'internal qwen3:8b fallback configured'
                    }
                    else {
                        Write-Check WARN 'Hermes continuity' 'local fallback not rendered; apply services/hermes/config.example.yaml'
                    }
                }
                catch {
                    Write-Check WARN 'Hermes continuity' 'fallback configuration could not be inspected'
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
