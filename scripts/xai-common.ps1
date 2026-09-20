$ErrorActionPreference = 'Stop'

function Get-XaiRepoRoot {
    return (Split-Path $PSScriptRoot -Parent)
}

function Read-XaiEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line -split '=', 2
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function Get-XaiEnvValue {
    param([hashtable]$Values, [string]$Name, [string]$Default)
    if ($Values.ContainsKey($Name) -and $Values[$Name]) { return $Values[$Name] }
    return $Default
}

function New-XaiSecret {
    param([int]$Bytes = 32)
    $buffer = [byte[]]::new($Bytes)
    $generator=[Security.Cryptography.RandomNumberGenerator]::Create()
    try{$generator.GetBytes($buffer)}finally{$generator.Dispose()}
    # URL-safe Base64 is required because the local database password is
    # interpolated into a SQLAlchemy PostgreSQL URL by Compose.
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+','-').Replace('/','_')
}

function Initialize-XaiLocalEnv {
    param([string]$RepoRoot)
    $envPath = Join-Path $RepoRoot '.env'
    if (Test-Path -LiteralPath $envPath) {
        $values = Read-XaiEnv $envPath
        $databasePassword = Get-XaiEnvValue $values 'POSTGRES_PASSWORD' ''
        if ($databasePassword -match '[+/=]') {
            $content = Get-Content -LiteralPath $envPath -Raw
            $content = [regex]::Replace($content, '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$(New-XaiSecret 32)")
            [IO.File]::WriteAllText($envPath,$content,[Text.UTF8Encoding]::new($false))
            Write-Warning 'Rotated the local PostgreSQL password to URL-safe encoding; synchronize the retained database role before startup.'
        }
        return
    }
    $template = Join-Path $RepoRoot '.env.example'
    if (-not (Test-Path -LiteralPath $template)) { throw 'Missing .env.example.' }
    $content = Get-Content -LiteralPath $template -Raw
    $content = $content.Replace('REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS', (New-XaiSecret 48))
    $first = New-XaiSecret 32
    $content = $content.Replace('REPLACE_WITH_RANDOM_LOCAL_PASSWORD', $first)
    $content = $content.Replace('REPLACE_WITH_RANDOM_WEB_DEMO_PASSWORD', (New-XaiSecret 24))
    $content = $content.Replace('REPLACE_WITH_RANDOM_DESKTOP_DEMO_PASSWORD', (New-XaiSecret 24))
    [IO.File]::WriteAllText($envPath,$content,[Text.UTF8Encoding]::new($false))
    Write-Host 'Created ignored .env with generated local-only secrets.' -ForegroundColor Yellow
}

function Assert-XaiTools {
    $required = @(
        @{Name='Docker'; Command='docker'},
        @{Name='Python'; Command='python'},
        @{Name='Node'; Command='node'},
        @{Name='npm'; Command='npm.cmd'},
        @{Name='Flutter'; Command='flutter.bat'},
        @{Name='.NET'; Command='dotnet'}
    )
    $missing = @()
    foreach ($tool in $required) {
        if (-not (Get-Command $tool.Command -ErrorAction SilentlyContinue)) { $missing += $tool.Name }
    }
    if ($missing.Count) { throw "Missing required tools: $($missing -join ', ')" }
    & docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop/Engine is not available.' }
}

function Test-XaiTcpPort {
    param([int]$Port, [string]$HostName = '127.0.0.1', [int]$TimeoutMs = 750)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return ($task.Wait($TimeoutMs) -and $client.Connected)
    } catch { return $false } finally { $client.Dispose() }
}

function Test-XaiHttp {
    param([string]$Url, [int]$TimeoutSeconds = 3)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
        return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 400
    } catch { return $false }
}

function Wait-XaiHttp {
    param([string]$Url, [int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-XaiHttp -Url $Url -TimeoutSeconds 3) { return }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

function Get-XaiContainerId {
    param([string]$Service)
    $id = (& docker compose ps -q $Service 2>$null | Select-Object -First 1)
    if ($id) { return $id.Trim() }
    return ''
}

function Wait-XaiContainerHealthy {
    param([string]$Service, [int]$TimeoutSeconds = 240)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $id = Get-XaiContainerId -Service $Service
        if ($id) {
            $state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $id 2>$null).Trim()
            if ($state -in @('healthy','running')) { return }
            if ($state -in @('unhealthy','exited','dead')) { throw "$Service entered state $state" }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Service"
}

function Get-XaiRuntimePath {
    param([string]$RepoRoot)
    return (Join-Path $RepoRoot '.xai-runtime')
}
