param([string]$Message = "XAI-Compress source update")
& (Join-Path $PSScriptRoot "deploy.ps1") -Message $Message
exit $LASTEXITCODE
