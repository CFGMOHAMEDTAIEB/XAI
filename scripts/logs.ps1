$ErrorActionPreference='Stop'; Set-Location (Split-Path $PSScriptRoot -Parent); docker compose logs --tail=200 -f @args
