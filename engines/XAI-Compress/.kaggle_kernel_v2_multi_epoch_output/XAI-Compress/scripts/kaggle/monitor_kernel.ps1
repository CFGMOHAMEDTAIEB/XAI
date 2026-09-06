param(
    [Parameter(Mandatory = $true)][string]$Kernel,
    [int]$IntervalSeconds = 45
)
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle = Join-Path $Project ".venv\Scripts\kaggle.exe"
while ($true) {
    $Status = (& $Kaggle kernels status $Kernel 2>&1 | Out-String).Trim()
    Write-Host "$(Get-Date -Format o) $Status"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Status -notmatch 'RUNNING|QUEUED') { exit 0 }
    Start-Sleep -Seconds $IntervalSeconds
}
