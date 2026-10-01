[CmdletBinding()]
param([switch]$NoBrowser, [switch]$NoDesktop, [switch]$NoMobile)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'run-all-common.ps1')

function Test-XaiMobileActivityReady {
    param([string]$Adb, [string]$DeviceId, [int]$TimeoutSeconds = 90, [object]$FlutterEntry = $null)
    $packageName = 'com.example.xai_compress_authenticator'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastReason = 'Android activity has not resumed.'
    do {
        if ($FlutterEntry -and -not (Test-XaiOwnedProcess -Entry $FlutterEntry)) {
            return [pscustomobject]@{ Ready = $false; Reason = 'Flutter mobile launcher process exited before the activity became ready.' }
        }
        $deviceResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('devices') -TimeoutSeconds 10
        $online = -not $deviceResult.TimedOut -and $deviceResult.ExitCode -eq 0 -and
            @($deviceResult.Output -split "`r?`n") -match "^$([regex]::Escape($DeviceId))\s+device(?:\s|$)"
        if (-not $online) {
            $lastReason = "$DeviceId is no longer in ADB device state."
        } else {
            $bootResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('-s', $DeviceId, 'shell', 'getprop', 'sys.boot_completed') -TimeoutSeconds 8
            $booted = -not $bootResult.TimedOut -and $bootResult.ExitCode -eq 0 -and $bootResult.Output.Trim() -eq '1'
            if (-not $booted) {
                $lastReason = 'Android sys.boot_completed is not 1.'
            } else {
                $pidResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('-s', $DeviceId, 'shell', 'pidof', $packageName) -TimeoutSeconds 8
                $activityResult = Invoke-XaiProcessCapture -FilePath $Adb -ArgumentList @('-s', $DeviceId, 'shell', 'dumpsys', 'activity', 'activities') -TimeoutSeconds 12
                $hasPid = -not $pidResult.TimedOut -and $pidResult.ExitCode -eq 0 -and $pidResult.Output.Trim().Length -gt 0
                $resumed = -not $activityResult.TimedOut -and $activityResult.ExitCode -eq 0 -and
                    $activityResult.Output -match "(?m)(Resumed:|ResumedActivity:).*${packageName}/(?:\.?MainActivity|${packageName}\.MainActivity)"
                if ($hasPid -and $resumed) {
                    return [pscustomobject]@{ Ready = $true; Reason = 'Android app PID exists and MainActivity is resumed.' }
                }
                $lastReason = if (-not $hasPid) { 'Authenticator process is not running.' } else { 'Authenticator MainActivity is not the resumed activity.' }
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    return [pscustomobject]@{ Ready = $false; Reason = "Timed out after $TimeoutSeconds seconds: $lastReason" }
}

$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
$ports = Get-XaiPorts -RepoRoot $repoRoot
$state = Read-XaiRunAllState -RepoRoot $repoRoot
if (-not $state) { $state = New-XaiRunAllState }
$state.processes = @(Get-XaiLiveOwnedProcesses -State $state)
$hadFailure = $false
$desktopState = if ($NoDesktop) { 'SKIPPED' } else { 'BLOCKED' }
$desktopDependencies = 'NOT CHECKED'
$mobileState = if ($NoMobile) { 'SKIPPED' } else { 'BLOCKED' }
$emulatorState = if ($NoMobile) { 'SKIPPED' } else { 'BLOCKED' }
$mobileDependencies = 'NOT CHECKED'
$deviceId = $null
$avdName = $null

Write-Host '========================================'
Write-Host '       XAI-COMPRESS LOCAL PLATFORM'
Write-Host '========================================'
Write-Host '[CORE] Starting infrastructure...'

$oldSkipDesktop = $env:XAI_SKIP_DESKTOP
$oldNoBuild = $env:XAI_NO_BUILD
try {
    $env:XAI_SKIP_DESKTOP = '1'
    if (Test-XaiComposeImagesPresent -RepoRoot $repoRoot) { $env:XAI_NO_BUILD = '1' } else { Remove-Item Env:XAI_NO_BUILD -ErrorAction SilentlyContinue }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'scripts\xai.ps1') start
    if ($LASTEXITCODE -ne 0) { throw "Core launcher exited with code $LASTEXITCODE." }
} catch {
    $hadFailure = $true
    Write-Warning "Core startup did not complete: $($_.Exception.Message)"
} finally {
    if ($null -eq $oldSkipDesktop) { Remove-Item Env:XAI_SKIP_DESKTOP -ErrorAction SilentlyContinue } else { $env:XAI_SKIP_DESKTOP = $oldSkipDesktop }
    if ($null -eq $oldNoBuild) { Remove-Item Env:XAI_NO_BUILD -ErrorAction SilentlyContinue } else { $env:XAI_NO_BUILD = $oldNoBuild }
}

$deadline = (Get-Date).AddSeconds(45)
do {
    $readiness = Get-XaiReadiness -Ports $ports
    if (@($readiness.Values | Where-Object { $_ -ne 'READY' }).Count -eq 0) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

$android = $null
if (-not $NoMobile) {
    $android = Set-XaiAndroidEnvironment
    try { Set-XaiAndroidUserPaths }
    catch {
        Write-Warning "Android user environment is not ready: $($_.Exception.Message)"
        $hadFailure = $true
    }
}

$flutter = Get-XaiFlutterCommand
$flutterVersion = 'MISSING'
if ($flutter) {
    try {
        $flutterVersionOutput = @(& $flutter --version 2>&1)
        if ($LASTEXITCODE -ne 0) { throw "flutter --version exited with code $LASTEXITCODE." }
        $flutterVersion = ([string]($flutterVersionOutput | Select-Object -First 1)).Trim()
    } catch {
        Write-Warning "Flutter validation failed: $($_.Exception.Message)"
        $flutter = $null
        $hadFailure = $true
    }
}
if (-not $NoMobile) {
    if (-not $flutter) {
        Write-Warning 'Flutter was not found; Mobile was not launched.'
        $hadFailure = $true
    } elseif (-not $android.Adb) {
        Write-Warning "ADB was not found under Android SDK '$($android.Sdk)'; Mobile was not launched."
        $hadFailure = $true
    } elseif (-not $android.Emulator) {
        Write-Warning "Android Emulator was not found under SDK '$($android.Sdk)'; Mobile was not launched."
        $hadFailure = $true
    } else {
        try {
            $launcher = Join-Path $PSScriptRoot 'launch-emulator.ps1'
            $launcherOutput = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -TimeoutSeconds 300 2>&1 | ForEach-Object { Write-Host $_; [string]$_ })
            if ($LASTEXITCODE -ne 0) { throw 'Android emulator launcher did not report READY.' }
            $resultLine = $launcherOutput | Where-Object { $_ -match '^RESULT\|' } | Select-Object -Last 1
            if (-not $resultLine) { throw 'Android emulator launcher returned no device identity.' }
            $parts = $resultLine -split '\|'
            $deviceId = $parts[1]; $avdName = $parts[2]
            $startedByThisRun = $parts[3] -eq 'True'
            $emulatorPid = if ($parts[4]) { [int]$parts[4] } else { $null }
            $matching = @(Get-XaiOnlineEmulators -Adb $android.Adb | Where-Object { $_.deviceId -eq $deviceId -and $_.avdName -eq $avdName })
            if (-not $matching.Count) { throw "Launcher reported $deviceId READY but the AVD identity could not be verified." }
            $knownOwned = $state.emulator -and $state.emulator.startedByRunAll -eq $true -and
                $state.emulator.deviceId -eq $deviceId -and $state.emulator.avdName -eq $avdName -and
                (Test-XaiOwnedProcess -Entry $state.emulator)
            if (-not $knownOwned) {
                $state.emulator = [pscustomobject][ordered]@{
                    startedByRunAll = [bool]($startedByThisRun -or ($state.emulator -and $state.emulator.startedByRunAll -eq $true -and $state.emulator.avdName -eq $avdName -and (Test-XaiOwnedProcess -Entry $state.emulator)))
                    avdName = $avdName; deviceId = $deviceId
                    pid = if ($startedByThisRun) { $emulatorPid } else { $null }
                    startedAt = if ($startedByThisRun) { (Get-Date).ToUniversalTime().ToString('o') } else { $null }
                }
                Write-XaiRunAllState -RepoRoot $repoRoot -State $state
            }
            $emulatorState = 'READY'
            $mobilePath = Join-Path $repoRoot 'apps\mobile_authenticator_flutter'
            $mobileEntry = $null
            if (Test-XaiFlutterProjectRunning -ProjectPath $mobilePath -ProcessName 'flutter-mobile' -State $state) {
                $mobileDependencies = 'EXISTING PROCESS'
                $mobileEntry = @($state.processes | Where-Object { $_.name -eq 'flutter-mobile' -and (Test-XaiOwnedProcess -Entry $_) } | Select-Object -First 1)[0]
            } else {
                $flutterDevicesJson = & $flutter devices --machine 2>$null
                if ($LASTEXITCODE -ne 0) { throw 'flutter devices failed after Android boot.' }
                $flutterDevice = @($flutterDevicesJson | ConvertFrom-Json) | Where-Object { $_.id -eq $deviceId -and $_.targetPlatform -like 'android-*' } | Select-Object -First 1
                if (-not $flutterDevice) { throw "Flutter does not detect $deviceId as an Android device." }
                $mobileDependencies = Initialize-XaiFlutterDependencies -Flutter $flutter -ProjectPath $mobilePath
                $entry = Start-XaiFlutterTerminal -Name 'flutter-mobile' -Flutter $flutter -ProjectPath $mobilePath -FlutterArguments @('run', '-d', $deviceId, "--dart-define=XAI_API_URL=http://10.0.2.2:$($ports.backend)")
                $state.processes = @($state.processes) + $entry
                Write-XaiRunAllState -RepoRoot $repoRoot -State $state
                $mobileEntry = $entry
                $mobileDependencies = 'ANDROID READY'
            }
            $mobileReadiness = Test-XaiMobileActivityReady -Adb $android.Adb -DeviceId $deviceId -TimeoutSeconds 90 -FlutterEntry $mobileEntry
            if ($mobileReadiness.Ready) {
                $mobileState = 'READY'
                Write-Host "[MOBILE] Authenticator readiness verified: $($mobileReadiness.Reason)"
            } else {
                $mobileState = 'FAILED'
                $hadFailure = $true
                Write-Warning "Mobile did not become ready: $($mobileReadiness.Reason)"
            }
        } catch {
            Write-Warning "Mobile launch blocked: $($_.Exception.Message)"
            if ($emulatorState -eq 'STARTING') { $emulatorState = 'BLOCKED' }
            $mobileState = 'BLOCKED'
            $hadFailure = $true
        }
    }
}

if (-not $NoDesktop) {
    $desktopPath = Join-Path $repoRoot 'apps\desktop_flutter'
    if (-not $flutter) {
        Write-Warning 'Flutter was not found; Desktop was not launched.'
        $hadFailure = $true
    } elseif (Test-XaiFlutterProjectRunning -ProjectPath $desktopPath -ProcessName 'flutter-desktop' -State $state) {
        $desktopState = 'READY'
        $desktopDependencies = 'EXISTING PROCESS'
    } else {
        try {
            $devicesJson = & $flutter devices --machine 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'flutter devices failed.' }
            $windowsDevice = @($devicesJson | ConvertFrom-Json) | Where-Object { $_.id -eq 'windows' } | Select-Object -First 1
            if (-not $windowsDevice) { throw 'Flutter Windows device/build tools are unavailable.' }
            $desktopDependencies = Initialize-XaiFlutterDependencies -Flutter $flutter -ProjectPath $desktopPath
            $entry = Start-XaiFlutterTerminal -Name 'flutter-desktop' -Flutter $flutter -ProjectPath $desktopPath -FlutterArguments @('run', '-d', 'windows', "--dart-define=XAI_API_URL=http://localhost:$($ports.backend)")
            $state.processes = @($state.processes) + $entry
            Write-XaiRunAllState -RepoRoot $repoRoot -State $state
            $desktopState = 'STARTING'
        } catch {
            Write-Warning "Desktop launch failed: $($_.Exception.Message)"
            $desktopState = 'FAILED'
            $hadFailure = $true
        }
    }
}

if (-not $NoBrowser) {
    $recentlyOpened = $false
    if ($state.browserOpenedAt) {
        try { $recentlyOpened = ((Get-Date).ToUniversalTime() - [datetime]::Parse([string]$state.browserOpenedAt).ToUniversalTime()).TotalMinutes -lt 5 } catch { $recentlyOpened = $false }
    }
    if (-not $recentlyOpened) {
        $pages = @("http://localhost:$($ports.nextjs)", "http://localhost:$($ports.nextjs)/downloads", "http://localhost:$($ports.angular)", "http://localhost:$($ports.admin)", "http://localhost:$($ports.pgadmin)", "http://localhost:$($ports.mailpit)")
        foreach ($page in $pages) { Start-Process $page }
        $state.browserOpenedAt = (Get-Date).ToUniversalTime().ToString('o')
    } else { Write-Host '[WEB] Browser tabs were opened recently; duplicate tabs skipped.' }
}
Write-XaiRunAllState -RepoRoot $repoRoot -State $state

Write-Host ''
Write-Host ('[CORE] PostgreSQL ............ {0}' -f $readiness.PostgreSQL)
Write-Host ('[CORE] FastAPI ............... {0}' -f $readiness.FastAPI)
Write-Host ('[WEB]  Angular ............... {0}' -f $readiness.Angular)
Write-Host ('[WEB]  Next.js ............... {0}' -f $readiness.'Next.js')
Write-Host ('[ADMIN] .NET Admin ........... {0}' -f $readiness.Admin)
Write-Host ('[TOOLS] pgAdmin .............. {0}' -f $readiness.pgAdmin)
Write-Host ('[TOOLS] Mailpit .............. {0}' -f $readiness.Mailpit)
Write-Host ('[TOOLS] Flutter .............. {0}' -f $flutterVersion)
Write-Host ('[DESKTOP] Flutter Desktop .... {0} ({1})' -f $desktopState, $desktopDependencies)
Write-Host ('[MOBILE] Android Emulator .... {0}' -f $emulatorState)
Write-Host ('[MOBILE] Authenticator ....... {0} ({1})' -f $mobileState, $mobileDependencies)
Write-Host ''
Write-Host '========================================'
Write-Host 'URLs'
Write-Host '========================================'
Write-Host "Public:     http://localhost:$($ports.nextjs)"
Write-Host "Downloads:  http://localhost:$($ports.nextjs)/downloads"
Write-Host "Portal:     http://localhost:$($ports.angular)"
Write-Host "Admin:      http://localhost:$($ports.admin)"
Write-Host "pgAdmin:    http://localhost:$($ports.pgadmin)"
Write-Host "Mailpit:    http://localhost:$($ports.mailpit)"
Write-Host "API:        http://localhost:$($ports.backend)"
Write-Host '========================================'
if ($hadFailure -or @($readiness.Values | Where-Object { $_ -ne 'READY' }).Count -gt 0) { exit 1 }
exit 0
