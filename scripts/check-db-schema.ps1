[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.env'))) {
    throw 'Missing ignored .env. Run scripts/start-all.ps1 once or create it from .env.example.'
}
$dbId = Get-XaiContainerId -Service db
if (-not $dbId) { throw 'The project PostgreSQL service is not running.' }
$state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $dbId).Trim()
if ($state -ne 'healthy') { throw "PostgreSQL is not healthy (state: $state)." }
Write-Host 'Checking migration ledger, checksums, pending migrations, tables, columns, and indexes...'
& docker compose run --rm --no-deps backend python scripts/run_all_migrations.py --check-only
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Schema verification reported pending migrations, checksum mismatch, or schema drift. No data was changed.'
    exit $LASTEXITCODE
}
Write-Host 'Database schema matches every recorded migration. No data was changed.'
