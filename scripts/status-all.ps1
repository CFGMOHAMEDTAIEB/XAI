[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'run-all-common.ps1')
$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
$state = Read-XaiRunAllState -RepoRoot $repoRoot
Write-Host '========================================'
Write-Host '          XAICD PLATFORM STATUS'
Write-Host '========================================'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'scripts\xai.ps1') status
$desktop = if (Test-XaiFlutterProjectRunning -ProjectPath (Join-Path $repoRoot 'apps\desktop_flutter') -ProcessName 'flutter-desktop' -State $state) { 'RUNNING' } else { 'STOPPED' }
$mobile = if (Test-XaiFlutterProjectRunning -ProjectPath (Join-Path $repoRoot 'apps\mobile_authenticator_flutter') -ProcessName 'flutter-mobile' -State $state) { 'RUNNING' } else { 'STOPPED' }
$emulator = 'STOPPED'
$emulatorDetail = ''
if (Get-Process adb -ErrorAction SilentlyContinue | Select-Object -First 1) {
    $android = Set-XaiAndroidEnvironment
    if ($android.Adb) {
        $online = @(Get-XaiOnlineEmulators -Adb $android.Adb)
        if ($online.Count) { $emulator = 'RUNNING'; $emulatorDetail = ($online | ForEach-Object { "$($_.deviceId) [$($_.avdName)]" }) -join ', ' }
    }
}
if ($emulator -eq 'STOPPED' -and (Get-Process emulator,qemu-system-x86_64 -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    $emulator = 'BLOCKED'
    $emulatorDetail = '(process exists but no online ADB emulator was verified)'
}
Write-Host ''
Write-Host ('Flutter Desktop : {0}' -f $desktop)
Write-Host ('Android emulator: {0} {1}' -f $emulator, $emulatorDetail)
Write-Host ('Flutter Mobile  : {0}' -f $mobile)
Write-Host 'Status is read-only; no service, ADB server, emulator, or application was started.'
