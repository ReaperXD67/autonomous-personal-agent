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
        $keyLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^OMNIROUTE_API_KEY=' } | Select-Object -First 1
        if ($keyLine -and $keyLine -notmatch 'CHANGE_ME') {
            Write-Check OK 'OmniRoute key' 'configured in ignored .env'
        }
        else { Write-Check WARN 'OmniRoute key' 'finish dashboard onboarding and create a scoped inference key' }

        $openRouterEnabled = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^OPENROUTER_ENABLED=true$' } | Select-Object -First 1
        $openRouterKey = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^OPENROUTER_API_KEY=' } | Select-Object -First 1
        if ($openRouterEnabled -and $openRouterKey -and $openRouterKey -notmatch '^OPENROUTER_API_KEY=$|CHANGE_ME') {
            Write-Check OK 'OpenRouter route' 'enabled with an ignored worker-only key; run scripts/openrouter.ps1 -Smoke'
        }
        elseif ($openRouterEnabled) {
            Write-Check FAIL 'OpenRouter route' 'enabled without a usable key'
        }
        else { Write-Check INFO 'OpenRouter route' 'optional; configure with scripts/openrouter.ps1 -Configure' }
    }
}
finally {
    Pop-Location
}

if ($failures -gt 0) { exit 1 }
exit 0
