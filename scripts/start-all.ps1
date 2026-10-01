[CmdletBinding()]
param(
    [switch]$SkipDesktop,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$effectiveSkipDesktop = $SkipDesktop -or $env:XAI_SKIP_DESKTOP -eq '1'
$effectiveNoBuild = $NoBuild -or $env:XAI_NO_BUILD -eq '1'
$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
Assert-XaiTools
Initialize-XaiLocalEnv -RepoRoot $repoRoot
$localEnv = Read-XaiEnv (Join-Path $repoRoot '.env')
$ports = [ordered]@{
    db = [int](Get-XaiEnvValue $localEnv 'POSTGRES_PORT' '15432')
    backend = [int](Get-XaiEnvValue $localEnv 'API_PORT' '18000')
    angular = [int](Get-XaiEnvValue $localEnv 'ANGULAR_PORT' '4200')
    nextjs = [int](Get-XaiEnvValue $localEnv 'NEXTJS_PORT' '3000')
    admin = [int](Get-XaiEnvValue $localEnv 'ADMIN_PORT' '5050')
    pgadmin = [int](Get-XaiEnvValue $localEnv 'PGADMIN_PORT' '5051')
    mailpit = [int](Get-XaiEnvValue $localEnv 'MAILPIT_UI_PORT' '18025')
    smtp = [int](Get-XaiEnvValue $localEnv 'MAILPIT_SMTP_PORT' '11025')
}

& docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration is invalid.' }

foreach ($service in $ports.Keys) {
    if (Test-XaiTcpPort -Port $ports[$service]) {
        $composeService = if ($service -eq 'smtp') { 'mailpit' } else { $service }
        if (-not (Get-XaiContainerId -Service $composeService)) {
            throw "Port $($ports[$service]) for $service is already in use by a non-project process."
        }
    }
}

if (-not $effectiveNoBuild) {
    & docker compose build clamav backend angular nextjs admin
    if ($LASTEXITCODE -ne 0) { throw 'One or more container images failed to build.' }
}

& docker compose up -d db clamav mailpit pgadmin
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure startup failed.' }
Wait-XaiContainerHealthy -Service db -TimeoutSeconds 120
Wait-XaiContainerHealthy -Service mailpit -TimeoutSeconds 120
Wait-XaiContainerHealthy -Service clamav -TimeoutSeconds 300

& docker compose run --rm --no-deps --user root backend chown -R 10001:10001 /data
if ($LASTEXITCODE -ne 0) { throw 'Artifact-volume ownership preparation failed.' }

& docker compose run --rm --no-deps backend python scripts/run_all_migrations.py --apply
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; application services were not started.' }

& docker compose up -d backend
if ($LASTEXITCODE -ne 0) { throw 'FastAPI startup failed.' }
Wait-XaiHttp -Url "http://localhost:$($ports.backend)/health" -TimeoutSeconds 180

& docker compose up -d angular nextjs admin
if ($LASTEXITCODE -ne 0) { throw 'One or more web applications failed to start.' }
Wait-XaiHttp -Url "http://localhost:$($ports.angular)" -TimeoutSeconds 180
Wait-XaiHttp -Url "http://localhost:$($ports.nextjs)" -TimeoutSeconds 180
Wait-XaiHttp -Url "http://localhost:$($ports.admin)" -TimeoutSeconds 180
Wait-XaiHttp -Url "http://localhost:$($ports.pgadmin)" -TimeoutSeconds 120
Wait-XaiHttp -Url "http://localhost:$($ports.mailpit)" -TimeoutSeconds 120

$runtimePath = Get-XaiRuntimePath -RepoRoot $repoRoot
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$runtime = [ordered]@{ startedAt=(Get-Date).ToUniversalTime().ToString('o'); processes=@() }
$existingRuntime = Join-Path $runtimePath 'runtime.json'
if (Test-Path -LiteralPath $existingRuntime) {
    try {
        $old = Get-Content -LiteralPath $existingRuntime -Raw | ConvertFrom-Json
        foreach ($entry in @($old.processes)) {
            $oldProcess = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            if (-not $oldProcess) { continue }
            $expectedStart = [datetime]::Parse($entry.startedAt).ToUniversalTime()
            if ([math]::Abs(($oldProcess.StartTime.ToUniversalTime() - $expectedStart).TotalSeconds) -le 2) {
                $runtime.processes += $entry
            }
        }
    } catch { Write-Warning 'Existing core runtime metadata was invalid; stale entries were ignored.' }
}
if (-not $effectiveSkipDesktop) {
    $devicesJson = & flutter.bat devices --machine 2>$null
    $windowsDevice = $null
    if ($LASTEXITCODE -eq 0 -and $devicesJson) {
        $windowsDevice = @($devicesJson | ConvertFrom-Json) | Where-Object { $_.id -eq 'windows' } | Select-Object -First 1
    }
    if ($windowsDevice) {
        $alreadyRunning = $false
        if (Test-Path -LiteralPath $existingRuntime) {
            try {
                $old = Get-Content -LiteralPath $existingRuntime -Raw | ConvertFrom-Json
                $desktop = @($old.processes) | Where-Object name -eq 'flutter-desktop' | Select-Object -First 1
                if ($desktop) { $alreadyRunning = [bool](Get-Process -Id $desktop.pid -ErrorAction SilentlyContinue) }
            } catch { $alreadyRunning = $false }
        }
        if (-not $alreadyRunning) {
            $desktopDir = Join-Path $repoRoot 'apps/desktop_flutter'
            $stdout = Join-Path $runtimePath 'flutter-desktop.out.log'
            $stderr = Join-Path $runtimePath 'flutter-desktop.err.log'
            $process = Start-Process -FilePath (Get-Command flutter.bat).Source -ArgumentList @('run','-d','windows',"--dart-define=XAI_API_URL=http://localhost:$($ports.backend)") -WorkingDirectory $desktopDir -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
            $runtime.processes += [ordered]@{name='flutter-desktop';pid=$process.Id;startedAt=$process.StartTime.ToUniversalTime().ToString('o');workingDirectory=$desktopDir}
        }
    } else {
        Write-Warning 'Flutter Windows device is not available; desktop launch was skipped.'
    }
}
[IO.File]::WriteAllText((Join-Path $runtimePath 'runtime.json'),($runtime|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))

Write-Host ''
Write-Host '========================================================'
Write-Host '                 XAICD LOCAL ENVIRONMENT'
Write-Host '========================================================'
Write-Host "FastAPI:                http://localhost:$($ports.backend)"
Write-Host "API documentation:      http://localhost:$($ports.backend)/docs"
Write-Host "Angular Portal:         http://localhost:$($ports.angular)"
Write-Host "Public Next.js:         http://localhost:$($ports.nextjs)"
Write-Host "Downloads:              http://localhost:$($ports.nextjs)/downloads"
Write-Host "Database Administration:http://localhost:$($ports.pgadmin)"
Write-Host "Mailpit:                http://localhost:$($ports.mailpit)"
Write-Host "PostgreSQL:             localhost:$($ports.db)"
Write-Host ".NET Administration:    http://localhost:$($ports.admin)"
Write-Host '========================================================'
