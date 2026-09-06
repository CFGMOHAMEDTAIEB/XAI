$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Warning 'Created .env from .env.example; replace development secrets before deployment.' }
docker compose config --quiet
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
Write-Host 'Waiting for backend health...'
$health = $null
for ($i=0; $i -lt 60; $i++) { try { $health=Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2; if($health.status -eq 'ok'){break} } catch {}; Start-Sleep 2 }
if (-not $health -or $health.status -ne 'ok') { docker compose ps; throw 'Backend did not become healthy' }
Write-Host 'Backend http://localhost:8000  Angular http://localhost:4200  Next.js http://localhost:3000  Admin http://localhost:5050'
