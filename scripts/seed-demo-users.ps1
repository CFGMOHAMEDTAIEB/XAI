[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$repoRoot=Get-XaiRepoRoot;Set-Location $repoRoot
$values=Read-XaiEnv (Join-Path $repoRoot '.env')
if((Get-XaiEnvValue $values 'APP_ENV' 'development') -ne 'development'){throw 'Demo users can only be seeded in APP_ENV=development.'}
foreach($name in @('XAI_DEMO_WEB_EMAIL','XAI_DEMO_WEB_PASSWORD','XAI_DEMO_DESKTOP_EMAIL','XAI_DEMO_DESKTOP_PASSWORD')){if(-not (Get-XaiEnvValue $values $name '')){throw "$name is missing from the ignored .env file."}}
$backend=Get-XaiContainerId -Service backend
if(-not $backend){throw 'FastAPI is not running. Run scripts/start-all.ps1 first.'}
& docker compose exec -T backend python -m app.scripts.seed_demo_users
if($LASTEXITCODE){throw 'Demo user seeding failed.'}
