param([string]$Message = "Initial XAI-Compress deployment")
& (Join-Path $PSScriptRoot "deploy.ps1") -Message $Message -ForceCreate
exit $LASTEXITCODE
