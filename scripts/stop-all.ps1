[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'run-all-common.ps1')
$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
$state = Read-XaiRunAllState -RepoRoot $repoRoot
$statePath = Get-XaiRunAllStatePath -RepoRoot $repoRoot

function Stop-XaiOwnedProcessTree {
    param([object]$Entry)
    if (-not (Test-XaiOwnedProcess -Entry $Entry)) {
        Write-Warning "$($Entry.name) PID $($Entry.pid) is absent or was reused; it was not stopped."
        return
    }
    $queue = New-Object 'System.Collections.Generic.Queue[int]'
    $queue.Enqueue([int]$Entry.pid)
    $descendants = @()
    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$parent" -ErrorAction SilentlyContinue)) {
            $descendants += [int]$child.ProcessId
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    foreach ($id in @($descendants | Select-Object -Unique | Sort-Object -Descending)) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id ([int]$Entry.pid) -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped owned $($Entry.name) process tree (PID $($Entry.pid))."
}

if ($state) {
    foreach ($entry in @($state.processes)) { Stop-XaiOwnedProcessTree -Entry $entry }
    if ($state.emulator -and $state.emulator.startedByRunAll -eq $true -and $state.emulator.deviceId -and $state.emulator.avdName -and (Test-XaiOwnedProcess -Entry $state.emulator)) {
        $android = Set-XaiAndroidEnvironment
        if ($android.Adb) {
            $match = Get-XaiOnlineEmulators -Adb $android.Adb | Where-Object { $_.deviceId -eq $state.emulator.deviceId -and $_.avdName -eq $state.emulator.avdName } | Select-Object -First 1
            if ($match) {
                & $android.Adb -s $match.deviceId emu kill | Out-Null
                if ($LASTEXITCODE -eq 0) { Write-Host "Requested clean shutdown of owned AVD '$($match.avdName)' ($($match.deviceId))." }
                else { Write-Warning "ADB could not stop owned AVD '$($match.avdName)'." }
            } else { Write-Warning 'The recorded emulator identity no longer matches; it was not stopped.' }
        } else { Write-Warning 'ADB is unavailable; the recorded owned emulator was not stopped.' }
    } elseif ($state.emulator) { Write-Host 'The emulator was pre-existing or not provably owned; it was left running.' }
} else { Write-Host 'No run-all host-process state exists; no Flutter or emulator process was stopped.' }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'scripts\xai.ps1') stop
$coreExit = $LASTEXITCODE
if ($coreExit -eq 0 -and (Test-Path -LiteralPath $statePath)) { Remove-Item -LiteralPath $statePath -Force }
if ($coreExit -ne 0) { throw "Core stop launcher exited with code $coreExit; run-all state was retained for safe retry." }
Write-Host 'Stopped processes owned by run-all. Persistent Docker volumes and Android data were retained.'
