[CmdletBinding()]
param([int]$TimeoutSeconds = 300)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'run-all-common.ps1')
$sdk = 'C:\Users\ss\AppData\Local\Android\sdk'
$adb = Join-Path $sdk 'platform-tools\adb.exe'
$emulator = Join-Path $sdk 'emulator\emulator.exe'
$avd = 'xai_mobile_x86_64'
$device = 'emulator-5554'
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:ANDROID_AVD_HOME = 'D:\Android\Avd'

function Invoke-Adb {
    param([string[]]$Arguments, [int]$Limit = 8)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $adb
    $info.Arguments = ($Arguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' '
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $p = New-Object System.Diagnostics.Process; $p.StartInfo = $info
    if (-not $p.Start()) { throw 'Could not start ADB.' }
    if (-not $p.WaitForExit($Limit * 1000)) { try { $p.Kill() } catch {}; return [pscustomobject]@{ Code = $null; Out = ''; Err = ''; Timeout = $true } }
    return [pscustomobject]@{ Code = $p.ExitCode; Out = $p.StandardOutput.ReadToEnd(); Err = $p.StandardError.ReadToEnd(); Timeout = $false }
}

function Test-EmulatorProcess {
    return [bool](Get-CimInstance Win32_Process -Filter "Name='emulator.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match ('(?i)-avd\s+' + [regex]::Escape($avd) + '(\s|$)') } | Select-Object -First 1)
}

function Get-DeviceState {
    $r = Invoke-Adb @('-s', $device, 'get-state') 6
    if ($r.Code -eq 0 -and $r.Out.Trim() -eq 'device') { return 'device' }
    return ''
}

try {
    if (-not (Test-Path -LiteralPath $adb) -or -not (Test-Path -LiteralPath $emulator)) { throw "Android SDK tools missing under '$sdk'." }
    Set-XaiAndroidUserPaths
    Write-Host '[Android Emulator] Checking ADB...'
    $start = Invoke-Adb @('start-server') 15
    if ($start.Timeout -or $start.Code -ne 0) {
        $detail = if ($start.Err) { $start.Err.Trim() } else { "exit code $($start.Code)" }
        throw "ADB server could not be started: $detail"
    }
    Write-Host '[Android Emulator] Checking existing device...'
    $state = Get-DeviceState
    $hasProcess = Test-EmulatorProcess
    $started = $false
    $emulatorPid = $null
    if (-not $hasProcess -and -not $state) {
        Write-Host '[Android Emulator] Starting AVD...'
        # Host GPU stalled SurfaceControl during system_server startup; SwiftShader completed a cold-boot diagnostic.
        # Keep the existing AVD CPU, RAM, and Quick Boot snapshot settings unchanged.
        $p = Start-Process -FilePath $emulator -ArgumentList @('-avd', $avd, '-no-boot-anim', '-gpu', 'swiftshader', '-accel', 'on') -PassThru
        $emulatorPid = $p.Id; $started = $true
    }
    Write-Host '[Android Emulator] Waiting for device...'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $recovered = $false
    do {
        $devices = Invoke-Adb @('devices') 8
        $line = @($devices.Out -split "`r?`n" | Where-Object { $_ -match ('^' + [regex]::Escape($device) + '\s+') } | Select-Object -First 1)
        if ($line.Count -and $line[0] -match '\sdevice\s*$') { $state = Get-DeviceState } else { $state = '' }
        if (-not $state -and $line.Count -and -not $recovered) {
            Write-Host '[Android Emulator] Device is offline; restarting ADB server safely...'
            Invoke-Adb @('kill-server') 8 | Out-Null
            $restart = Invoke-Adb @('start-server') 15
            if ($restart.Code -ne 0 -or $restart.Timeout) { throw 'ADB server recovery failed.' }
            $recovered = $true
        }
        if (-not $state -and -not $hasProcess -and -not $started) { throw "AVD '$avd' process is not running and could not be started." }
        if (-not $state) { Start-Sleep -Seconds 2 }
        $hasProcess = Test-EmulatorProcess
    } while (-not $state -and (Get-Date) -lt $deadline)
    if (-not $state) { throw "$device did not reach ADB state 'device' within $TimeoutSeconds seconds." }

    Write-Host '[Android Emulator] Waiting for Android boot...'
    do {
        $boot = Invoke-Adb @('-s', $device, 'shell', 'getprop', 'sys.boot_completed') 10
        if ($boot.Code -eq 0 -and $boot.Out.Trim() -eq '1') { break }
        if ((Get-Date) -ge $deadline) { throw "Android boot did not complete within $TimeoutSeconds seconds." }
        Start-Sleep -Seconds 2
        if ((Get-DeviceState) -ne 'device') { $state = '' }
        if (-not $state) {
            $state = Get-DeviceState
            if (-not $state -and -not $recovered) { Invoke-Adb @('kill-server') 8 | Out-Null; Invoke-Adb @('start-server') 15 | Out-Null; $recovered = $true }
        }
    } while ($true)
    Write-Host '[Android Emulator] Testing ADB...'
    $shell = Invoke-Adb @('-s', $device, 'shell', 'echo', 'XAI_ADB_READY') 10
    if ($shell.Code -ne 0 -or $shell.Timeout -or $shell.Out -notmatch 'XAI_ADB_READY') { throw 'ADB shell communication check failed.' }
    Write-Host '[Android Emulator] READY'
    Write-Host "AVD: $avd"
    Write-Host "ADB: $device"
    Write-Host 'Status: READY'
    Write-Output "RESULT|$device|$avd|$started|$emulatorPid"
    exit 0
} catch {
    Write-Error "[Android Emulator] FAILED: $($_.Exception.Message)"
    exit 1
}
