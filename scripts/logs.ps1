[CmdletBinding()]
param(
    [string]$Service,
    [int]$Tail = 200
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if ($Service) {
        docker compose logs --follow --tail $Tail $Service
    }
    else {
        docker compose logs --follow --tail $Tail
    }
}
finally {
    Pop-Location
}

