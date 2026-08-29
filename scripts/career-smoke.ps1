[CmdletBinding()]
param(
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$profileId = $null

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        throw 'Missing .env. Run scripts/init-env.ps1 first.'
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line.Split('=', 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    $port = if ($values.CONTROL_API_PORT) { $values.CONTROL_API_PORT } else { '8080' }
    $baseUrl = "http://127.0.0.1:$port"
    $headers = @{ Authorization = "Bearer $($values.CONTROL_API_TOKEN)" }

    function Wait-CareerTask {
        param(
            [Parameter(Mandatory)][string]$TaskId,
            [Parameter(Mandatory)][int]$Attempts
        )
        for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
            $task = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/tasks/$TaskId" -Headers $headers
            if ($task.status -in @('succeeded', 'failed', 'rejected', 'cancelled', 'dead_lettered')) {
                return $task
            }
            Start-Sleep -Milliseconds 500
        }
        throw "Career task $TaskId did not finish in time."
    }

    $source = Invoke-RestMethod -Method Get -Uri 'https://www.arbeitnow.com/api/job-board-api'
    $fixtureJob = $source.data | Where-Object { $_.title -and $_.created_at } | Select-Object -First 1
    if (-not $fixtureJob) {
        throw 'The reviewed public source returned no usable fresh job fixture.'
    }

    $profileBody = @{
        name = 'Disposable career workflow smoke'
        candidate_name = 'Synthetic Test Candidate'
        desired_titles = @([string]$fixtureJob.title)
        skills = @('communication')
        required_keywords = @()
        excluded_keywords = @()
        locations = @()
        remote_only = $false
        employment_types = @()
        max_age_hours = 168
        min_score = 0
        schedule_minutes = 360
        source_config = @{ arbeitnow = $true; ashby_boards = @(); greenhouse_boards = @() }
        resume_text = 'Synthetic validation resume. Experience: software testing, documentation, communication, and responsible automation. This is not a real person.'
        active = $false
        requested_by = 'local-career-smoke'
    } | ConvertTo-Json -Depth 8

    $profile = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/profiles" -Headers $headers -ContentType 'application/json' -Body $profileBody
    $profileId = [Guid]::Parse([string]$profile.id)
    $search = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/profiles/$profileId/scan" -Headers $headers
    $search = Wait-CareerTask -TaskId $search.id -Attempts 240
    if ($search.status -ne 'succeeded' -or $search.output.sources_succeeded -lt 1 -or $search.output.matched -lt 1) {
        throw "Career search did not ingest the expected fresh fixture (status: $($search.status))."
    }

    $opportunities = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/career/opportunities?profile_id=$profileId&limit=20" -Headers $headers
    $opportunity = $opportunities | Select-Object -First 1
    if (-not $opportunity -or -not $opportunity.apply_url.StartsWith('https://')) {
        throw 'The career search did not persist an attributable application URL.'
    }

    Write-Host "Fresh discovery passed: $($search.id) ($($search.output.fetched) fetched, $($search.output.matched) matched)"

    if ($Draft) {
        $draftTask = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/career/opportunities/$($opportunity.id)/draft" -Headers $headers
        $draftTask = Wait-CareerTask -TaskId $draftTask.id -Attempts 480
        if ($draftTask.status -ne 'succeeded' -or -not $draftTask.output.draft_created) {
            throw "Private application draft did not succeed (status: $($draftTask.status))."
        }
        $afterDraft = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/career/opportunities?profile_id=$profileId&limit=20" -Headers $headers
        $drafted = $afterDraft | Where-Object { $_.id -eq $opportunity.id } | Select-Object -First 1
        if (-not $drafted.latest_draft.fit_summary -or -not $drafted.latest_draft.cover_letter) {
            throw 'The local model task finished without a persisted structured application draft.'
        }
        Write-Host "Draft route passed:     $($draftTask.id) ($($draftTask.output.model_provider)/$($draftTask.output.model))"
    }
}
finally {
    if ($profileId) {
        $cleanupSql = "DELETE FROM career_profiles WHERE id = '$profileId'::uuid AND requested_by = 'local-career-smoke';"
        & docker compose exec -T postgres psql -v ON_ERROR_STOP=1 --username $values.POSTGRES_USER --dbname $values.POSTGRES_DB --command $cleanupSql | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not remove disposable career profile $profileId."
        }
    }
    Pop-Location
}
