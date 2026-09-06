param(
    [Parameter(Mandatory = $true)][string]$Kernel,
    [int]$IntervalSeconds = 45,
    [string]$OutputRoot
)
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle = Join-Path $Project ".venv\Scripts\kaggle.exe"
$Python = Join-Path $Project ".venv\Scripts\python.exe"
$Orchestrator = Join-Path $Project "scripts\model_search_orchestrator.py"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $Project "results\model_search\imports\candidate_b_$Timestamp"
}
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$AllowedImports = [IO.Path]::GetFullPath((Join-Path $Project "results\model_search\imports"))
if (-not $OutputRoot.StartsWith($AllowedImports, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must remain inside $AllowedImports"
}
if (Test-Path -LiteralPath $OutputRoot) {
    throw "Refusing to overwrite existing watcher output: $OutputRoot"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$Log = Join-Path $OutputRoot "watch.log"

function Write-WatchLog([string]$Message) {
    $Line = "$(Get-Date -Format o) $Message"
    Add-Content -LiteralPath $Log -Value $Line -Encoding UTF8
    Write-Host $Line
}

Write-WatchLog "Monitoring existing kernel $Kernel"
while ($true) {
    $Status = (& $Kaggle kernels status $Kernel 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Write-WatchLog "Transient status error: $Status"
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }
    Write-WatchLog $Status
    if ($Status -notmatch 'RUNNING|QUEUED') { break }
    Start-Sleep -Seconds $IntervalSeconds
}

& $Kaggle kernels output $Kernel -p $OutputRoot 2>&1 | Add-Content -LiteralPath $Log -Encoding UTF8
if ($LASTEXITCODE -ne 0) {
    Write-WatchLog "Kernel output download failed; no state transition performed."
    exit $LASTEXITCODE
}
$ResultRoot = Join-Path $OutputRoot "results\model_search"
if (-not (Test-Path -LiteralPath (Join-Path $ResultRoot "selection.json"))) {
    Write-WatchLog "selection.json missing; downloaded files retained for diagnosis."
    exit 2
}
& $Python $Orchestrator ingest-diagnostic --result $ResultRoot 2>&1 | Add-Content -LiteralPath $Log -Encoding UTF8
if ($LASTEXITCODE -ne 0) {
    Write-WatchLog "Orchestrator ingestion failed; downloaded files retained."
    exit $LASTEXITCODE
}
$State = (& $Python $Orchestrator status | Out-String | ConvertFrom-Json)
if ($State.best_stable_candidate) {
    Write-WatchLog "Stability candidate validated; starting actual paired XAIC/classical benchmark."
    & $Python $Orchestrator benchmark-best 2>&1 | Add-Content -LiteralPath $Log -Encoding UTF8
    if ($LASTEXITCODE -ne 0) {
        Write-WatchLog "Actual benchmark failed; candidate remains stability-validated and unpromoted."
        exit $LASTEXITCODE
    }
}
Write-WatchLog "Watcher complete."
