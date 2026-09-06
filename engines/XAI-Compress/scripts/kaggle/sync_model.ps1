param([string]$Output = "checkpoints\kaggle")
& (Join-Path $PSScriptRoot "download_model.ps1") -Output $Output
exit $LASTEXITCODE
