$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')

function Get-XaiRunAllStatePath {
    param([string]$RepoRoot)
    return (Join-Path (Get-XaiRuntimePath -RepoRoot $RepoRoot) 'run-all-state.json')
}

function Read-XaiRunAllState {
    param([string]$RepoRoot)
    $path = Get-XaiRunAllStatePath -RepoRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json) }
    catch {
        Write-Warning 'The run-all state file is invalid; it will not be trusted.'
        return $null
    }
}

function Write-XaiRunAllState {
    param([string]$RepoRoot, [object]$State)
    $runtimePath = Get-XaiRuntimePath -RepoRoot $RepoRoot
    New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
    $path = Get-XaiRunAllStatePath -RepoRoot $RepoRoot
    $temporaryPath = "$path.tmp"
    $State.updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    [IO.File]::WriteAllText($temporaryPath, ($State | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryPath -Destination $path -Force
}

function New-XaiRunAllState {
    return [pscustomobject][ordered]@{
        schemaVersion = 1
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
        browserOpenedAt = $null
        processes = @()
        emulator = $null
    }
}

function Test-XaiOwnedProcess {
    param([object]$Entry)
    if (-not $Entry -or -not $Entry.pid -or -not $Entry.startedAt) { return $false }
    $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    try {
        $expected = [datetime]::Parse([string]$Entry.startedAt).ToUniversalTime()
        return [math]::Abs(($process.StartTime.ToUniversalTime() - $expected).TotalSeconds) -le 2
    } catch { return $false }
}

function Get-XaiLiveOwnedProcesses {
    param([object]$State)
    if (-not $State) { return @() }
    return @($State.processes | Where-Object { Test-XaiOwnedProcess $_ })
}

function Test-XaiFlutterProjectRunning {
    param([string]$ProjectPath, [string]$ProcessName, [object]$State)
    $owned = @(Get-XaiLiveOwnedProcesses -State $State | Where-Object { $_.name -eq $ProcessName })
    if ($owned.Count -gt 0) { return $true }
    $escapedPath = [regex]::Escape([IO.Path]::GetFullPath($ProjectPath))
    $candidate = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -match $escapedPath -and
        ($_.CommandLine -match 'flutter_tools|flutter\.bat|package_config')
    } | Select-Object -First 1
    return [bool]$candidate
}

function Get-XaiFlutterCommand {
    $command = Get-Command flutter.bat -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    $known = 'C:\src\flutter\bin\flutter.bat'
    if (Test-Path -LiteralPath $known) { return $known }
    return $null
}

function Test-XaiFlutterDependenciesCurrent {
    param([string]$ProjectPath)
    $metadata = Join-Path $ProjectPath '.dart_tool\package_config.json'
    if (-not (Test-Path -LiteralPath $metadata)) { return $false }
    $metadataTime = (Get-Item -LiteralPath $metadata).LastWriteTimeUtc
    foreach ($name in @('pubspec.yaml', 'pubspec.lock')) {
        $input = Join-Path $ProjectPath $name
        if (Test-Path -LiteralPath $input) {
            if ((Get-Item -LiteralPath $input).LastWriteTimeUtc -gt $metadataTime) { return $false }
        }
    }
    return $true
}

function Initialize-XaiFlutterDependencies {
    param([string]$Flutter, [string]$ProjectPath)
    if (Test-XaiFlutterDependenciesCurrent -ProjectPath $ProjectPath) { return 'CURRENT' }
    Push-Location $ProjectPath
    try {
        & $Flutter pub get | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed for $ProjectPath (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
    return 'RESTORED'
}

function Start-XaiFlutterTerminal {
    param(
        [string]$Name,
        [string]$Flutter,
        [string]$ProjectPath,
        [string[]]$FlutterArguments
    )
    $quotedFlutter = $Flutter.Replace("'", "''")
    $quotedProject = $ProjectPath.Replace("'", "''")
    $argumentText = ($FlutterArguments | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join ', '
    $title = if ($Name -eq 'flutter-desktop') { 'XAICD Desktop' } else { 'XAICD Authenticator' }
    $script = "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location -LiteralPath '$quotedProject'; & '$quotedFlutter' @($argumentText); if (`$LASTEXITCODE -ne 0) { Write-Host ''; Write-Host 'Flutter exited with code' `$LASTEXITCODE -ForegroundColor Red }"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded) -WorkingDirectory $ProjectPath -PassThru
    Start-Sleep -Milliseconds 300
    return [pscustomobject][ordered]@{
        name = $Name
        pid = $process.Id
        startedAt = $process.StartTime.ToUniversalTime().ToString('o')
        workingDirectory = $ProjectPath
    }
}

function Set-XaiAndroidEnvironment {
    $sdk = $env:ANDROID_SDK_ROOT
    if (-not $sdk) { $sdk = $env:ANDROID_HOME }
    if (-not $sdk) { $sdk = Join-Path $env:LOCALAPPDATA 'Android\sdk' }
    $adb = Join-Path $sdk 'platform-tools\adb.exe'
    $emulator = Join-Path $sdk 'emulator\emulator.exe'
    if (Test-Path -LiteralPath 'D:\Android\Avd') { $env:ANDROID_AVD_HOME = 'D:\Android\Avd' }
    $env:ANDROID_HOME = $sdk
    $env:ANDROID_SDK_ROOT = $sdk
    return [pscustomobject]@{
        Sdk = $sdk
        Adb = if (Test-Path -LiteralPath $adb) { $adb } else { $null }
        Emulator = if (Test-Path -LiteralPath $emulator) { $emulator } else { $null }
    }
}

function Set-XaiAndroidUserPaths {
    $UserProfile = 'C:\Users\ss'
    $androidUserDir = Join-Path $UserProfile '.android'
    foreach ($name in @('ANDROID_SDK_HOME', 'ANDROID_USER_HOME', 'HOME')) {
        $inherited = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ([string]::IsNullOrWhiteSpace($inherited)) {
            Write-Host "[Android Emulator] Inherited $name is unset/empty; setting a process-level override."
        } elseif ($inherited -notmatch '^[A-Za-z]:\\' -or $inherited -match '^[A-Za-z]:\\?$') {
            Write-Warning "Invalid inherited $name='$inherited'; overriding it for this process."
        }
    }
    try {
        if (-not (Test-Path -LiteralPath $UserProfile -PathType Container)) {
            throw "User profile directory does not exist: $UserProfile"
        }
        if (-not (Test-Path -LiteralPath $androidUserDir -PathType Container)) {
            New-Item -ItemType Directory -Path $androidUserDir -Force -ErrorAction Stop | Out-Null
        }
        $probe = Join-Path $androidUserDir ('.xai-adb-write-test-' + [guid]::NewGuid().ToString('N'))
        try {
            $stream = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $stream.Dispose()
        } finally {
            if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Force -ErrorAction Stop }
        }
    } catch {
        throw "Android user directory '$androidUserDir' is not available and writable: $($_.Exception.Message)"
    }
    $env:ANDROID_SDK_HOME = $UserProfile
    $env:ANDROID_USER_HOME = $androidUserDir
    $env:HOME = $UserProfile
    Write-Host "[Android Emulator] Process paths: ANDROID_SDK_HOME=$UserProfile; ANDROID_USER_HOME=$androidUserDir; HOME=$UserProfile"
    Write-Host "[Android Emulator] Android user directory: $androidUserDir (writable)"
}

function Invoke-XaiProcessCapture {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [int]$TimeoutSeconds = 15
    )
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $FilePath
    $info.Arguments = ($ArgumentList | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    if (-not $process.Start()) { throw "Could not start $FilePath." }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch {}
        return [pscustomobject]@{ ExitCode=$null; Output=''; Error=''; TimedOut=$true }
    }
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = $stdout.Result
        Error = $stderr.Result
        TimedOut = $false
    }
}

function Get-XaiOnlineEmulators {
    param([string]$Adb)
    if (-not $Adb) { return @() }
    $devicesResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('devices') -TimeoutSeconds 10
    if ($devicesResult.TimedOut -or $devicesResult.ExitCode -ne 0) { return @() }
    $lines = @($devicesResult.Output -split "`r?`n")
    $result = @()
    foreach ($line in $lines) {
        if ($line -match '^(emulator-\d+)\s+device(?:\s|$)') {
            $deviceId = $Matches[1]
            $nameResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('-s', $deviceId, 'emu', 'avd', 'name') -TimeoutSeconds 5
            $avdName = if (-not $nameResult.TimedOut -and $nameResult.ExitCode -eq 0) { ([string]($nameResult.Output -split "`r?`n" | Select-Object -First 1)).Trim() } else { '' }
            $result += [pscustomobject]@{ deviceId = $deviceId; avdName = $avdName }
        }
    }
    return @($result)
}

function Wait-XaiAndroidBoot {
    param([string]$Adb, [string]$DeviceId, [int]$TimeoutSeconds = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $devicesResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('devices') -TimeoutSeconds 10
        $online = -not $devicesResult.TimedOut -and $devicesResult.ExitCode -eq 0 -and @($devicesResult.Output -split "`r?`n") -match "^$([regex]::Escape($DeviceId))\s+device(?:\s|$)"
        if ($online) {
            $bootResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('-s', $DeviceId, 'shell', 'getprop', 'sys.boot_completed') -TimeoutSeconds 10
            $boot = if (-not $bootResult.TimedOut -and $bootResult.ExitCode -eq 0) { $bootResult.Output.Trim() } else { '' }
            if ($boot -eq '1') { return $true }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-XaiPorts {
    param([string]$RepoRoot)
    $values = Read-XaiEnv (Join-Path $RepoRoot '.env')
    return [ordered]@{
        db = [int](Get-XaiEnvValue $values 'POSTGRES_PORT' '15432')
        backend = [int](Get-XaiEnvValue $values 'API_PORT' '18000')
        angular = [int](Get-XaiEnvValue $values 'ANGULAR_PORT' '4200')
        nextjs = [int](Get-XaiEnvValue $values 'NEXTJS_PORT' '3000')
        admin = [int](Get-XaiEnvValue $values 'ADMIN_PORT' '5050')
        pgadmin = [int](Get-XaiEnvValue $values 'PGADMIN_PORT' '5051')
        mailpit = [int](Get-XaiEnvValue $values 'MAILPIT_UI_PORT' '18025')
    }
}

function Get-XaiReadiness {
    param([System.Collections.IDictionary]$Ports)
    return [ordered]@{
        PostgreSQL = if (Test-XaiTcpPort -Port $Ports.db) { 'READY' } else { 'FAILED' }
        FastAPI = if (Test-XaiHttp -Url "http://localhost:$($Ports.backend)/health" -TimeoutSeconds 3) { 'READY' } else { 'FAILED' }
        Angular = if (Test-XaiHttp -Url "http://localhost:$($Ports.angular)" -TimeoutSeconds 3) { 'READY' } else { 'FAILED' }
        'Next.js' = if (Test-XaiHttp -Url "http://localhost:$($Ports.nextjs)" -TimeoutSeconds 3) { 'READY' } else { 'FAILED' }
        Admin = if (Test-XaiHttp -Url "http://localhost:$($Ports.admin)" -TimeoutSeconds 3) { 'READY' } else { 'FAILED' }
        pgAdmin = if (Test-XaiHttp -Url "http://localhost:$($Ports.pgadmin)" -TimeoutSeconds 3) { 'READY' } else { 'FAILED' }
        Mailpit = if (Test-XaiHttp -Url "http://localhost:$($Ports.mailpit)" -TimeoutSeconds 3) { 'READY' } else { 'FAILED' }
    }
}

function Test-XaiComposeImagesPresent {
    param([string]$RepoRoot)
    Push-Location $RepoRoot
    try {
        $images = @(& docker compose config --images 2>$null | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique)
        if ($LASTEXITCODE -ne 0 -or $images.Count -eq 0) { return $false }
        foreach ($imageName in $images) {
            & docker image inspect $imageName *> $null
            if ($LASTEXITCODE -ne 0) { return $false }
        }
        return $true
    } finally { Pop-Location }
}
