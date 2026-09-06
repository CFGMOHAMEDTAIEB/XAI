param(
    [string]$Output = "checkpoints\kaggle",
    [string]$Dataset = "mohameddtaieb/xai-compress-trained-model"
)
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Project ".venv\Scripts\python.exe"
$Kaggle = Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Project Python environment not found: $Python" }
if (-not (Test-Path -LiteralPath $Kaggle)) { throw "Kaggle CLI not found: $Kaggle" }
& $Kaggle config view | Out-Null
if ($LASTEXITCODE) { throw "Kaggle authentication failed. Run: .\.venv\Scripts\kaggle.exe auth login" }

$Destination = if ([IO.Path]::IsPathRooted($Output)) { [IO.Path]::GetFullPath($Output) } else { [IO.Path]::GetFullPath((Join-Path $Project $Output)) }
$ProjectFull = [IO.Path]::GetFullPath($Project)
if (-not $Destination.StartsWith($ProjectFull, [StringComparison]::OrdinalIgnoreCase)) { throw "Output must remain inside the XAI-Compress project." }
$Parent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Path $Parent -Force | Out-Null
$Stage = Join-Path $Parent (".kaggle-download-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Stage | Out-Null
try {
    & $Kaggle datasets download -d $Dataset -p $Stage
    if ($LASTEXITCODE) { throw "Kaggle model download failed." }
    $Extract = Join-Path $Stage "extracted"
    New-Item -ItemType Directory -Path $Extract | Out-Null
    Get-ChildItem -LiteralPath $Stage -Filter "*.zip" -File | ForEach-Object { Expand-Archive -LiteralPath $_.FullName -DestinationPath $Extract -Force }
    $Best = Get-ChildItem -LiteralPath $Extract -Filter "best.pt" -File -Recurse | Select-Object -First 1
    if (-not $Best -or $Best.Length -le 0) { throw "Downloaded dataset does not contain a non-empty best.pt." }
    & $Python -c "from xai_compress.checkpoint import load_checkpoint; import json,sys; m,o=load_checkpoint(sys.argv[1],'cpu'); print(json.dumps({'epoch':o.get('epoch'),'fingerprint':o.get('fingerprint'),'parameters':sum(p.numel() for p in m.parameters()),'config':m.config.__dict__},indent=2))" $Best.FullName
    if ($LASTEXITCODE) { throw "Checkpoint validation failed." }
    if (Test-Path -LiteralPath $Destination) {
        $Backup = "$Destination.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Move-Item -LiteralPath $Destination -Destination $Backup
        Write-Host "Existing destination backed up to: $Backup"
    }
    New-Item -ItemType Directory -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Extract -Force | Copy-Item -Destination $Destination -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $Destination "best.pt"))) { Copy-Item -LiteralPath $Best.FullName -Destination (Join-Path $Destination "best.pt") }
    Write-Host "Validated model synchronized to: $Destination"
}
finally {
    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
