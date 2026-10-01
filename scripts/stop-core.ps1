[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
$runtimePath = Get-XaiRuntimePath -RepoRoot $repoRoot
$runtimeFile = Join-Path $runtimePath 'runtime.json'
if (Test-Path -LiteralPath $runtimeFile) {
    try {
        $runtime = Get-Content -LiteralPath $runtimeFile -Raw | ConvertFrom-Json
        foreach ($entry in @($runtime.processes)) {
            $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            if (-not $process) { continue }
            $expectedStart = [datetime]::Parse($entry.startedAt).ToUniversalTime()
            if ([math]::Abs(($process.StartTime.ToUniversalTime() - $expectedStart).TotalSeconds) -gt 2) {
                Write-Warning "PID $($entry.pid) was reused; it was not stopped."
                continue
            }
            $children = @(Get-CimInstance Win32_Process | Where-Object ParentProcessId -eq $entry.pid)
            foreach ($child in $children) { Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped $($entry.name) (PID $($entry.pid))."
        }
    } catch { Write-Warning "Could not process runtime metadata: $($_.Exception.Message)" }
    Remove-Item -LiteralPath $runtimeFile -Force -ErrorAction SilentlyContinue
}
& docker compose down
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose shutdown failed.' }
Write-Host 'Stopped XAICD core services. Persistent volumes were retained.'
