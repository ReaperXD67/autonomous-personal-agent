[CmdletBinding()]
param(
    [string]$Model,
    [switch]$SkipPull,
    [switch]$ForcePull,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        & (Join-Path $PSScriptRoot 'init-env.ps1')
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    if (-not $Model) {
        $Model = if ($values.LOCAL_MODEL) { $values.LOCAL_MODEL } else { 'qwen3:8b' }
    }

    $gpu = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1
    if (-not $gpu) {
        throw 'An NVIDIA GPU visible to Windows is required by the local-model profile.'
    }
    Write-Host "GPU: $gpu"

    docker compose --profile local-model up -d ollama
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the Ollama container.' }

    $healthy = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $containerId = docker compose --profile local-model ps --quiet ollama
        if ($containerId) {
            $state = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId
            if ($state -eq 'healthy') { $healthy = $true; break }
        }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw 'Ollama did not become healthy. Run scripts/logs.ps1 ollama.' }

    if ($SkipPull -and $ForcePull) {
        throw 'SkipPull and ForcePull cannot be used together.'
    }

    $installedModels = docker compose --profile local-model exec -T ollama ollama list
    if ($LASTEXITCODE -ne 0) { throw 'Could not list the locally installed Ollama models.' }
    $modelPattern = '(?m)^' + [regex]::Escape($Model) + '\s'
    $modelInstalled = (($installedModels -join "`n") -match $modelPattern)

    if ($ForcePull -or (-not $SkipPull -and -not $modelInstalled)) {
        Write-Host "Downloading local model $Model. This is resumable and may take several minutes."
        docker compose --profile local-model exec -T ollama ollama pull $Model
        if ($LASTEXITCODE -ne 0) { throw "Model pull failed: $Model" }
    }
    elseif ($modelInstalled) {
        Write-Host "Using locally cached model $Model. Use -ForcePull to refresh it."
    }

    if (-not $SkipSmoke) {
        $output = docker compose --profile local-model exec -T ollama ollama run $Model --think=false 'Reply with exactly LOCAL_MODEL_OK and nothing else.'
        $response = ($output -join "`n").Trim()
        if ($LASTEXITCODE -ne 0 -or $response -ne 'LOCAL_MODEL_OK') {
            throw "The local model returned an unexpected response: $response"
        }
        $placement = docker compose --profile local-model exec -T ollama ollama ps
        if ($LASTEXITCODE -ne 0 -or -not (($placement -join "`n") -match 'GPU')) {
            throw 'Local inference completed, but Ollama did not report GPU placement.'
        }
        Write-Host 'Local inference smoke returned LOCAL_MODEL_OK and Ollama reported GPU placement.'
    }

    Write-Host "Local endpoint for containers: http://ollama:11434/v1"
    Write-Host "Model: $Model"
}
finally {
    Pop-Location
}
