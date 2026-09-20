[CmdletBinding()]
param([switch]$Json)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$repoRoot = Get-XaiRepoRoot
Set-Location $repoRoot
$values = Read-XaiEnv (Join-Path $repoRoot '.env')
$definitions = @(
    @{service='backend';label='FastAPI';port=(Get-XaiEnvValue $values 'API_PORT' '18000');url="http://localhost:$(Get-XaiEnvValue $values 'API_PORT' '18000')/health"},
    @{service='angular';label='Angular';port=(Get-XaiEnvValue $values 'ANGULAR_PORT' '4200');url="http://localhost:$(Get-XaiEnvValue $values 'ANGULAR_PORT' '4200')"},
    @{service='nextjs';label='Next.js';port=(Get-XaiEnvValue $values 'NEXTJS_PORT' '3000');url="http://localhost:$(Get-XaiEnvValue $values 'NEXTJS_PORT' '3000')"},
    @{service='admin';label='.NET Admin';port=(Get-XaiEnvValue $values 'ADMIN_PORT' '5050');url="http://localhost:$(Get-XaiEnvValue $values 'ADMIN_PORT' '5050')"},
    @{service='pgadmin';label='pgAdmin';port=(Get-XaiEnvValue $values 'PGADMIN_PORT' '5051');url="http://localhost:$(Get-XaiEnvValue $values 'PGADMIN_PORT' '5051')"},
    @{service='mailpit';label='Mailpit';port=(Get-XaiEnvValue $values 'MAILPIT_UI_PORT' '18025');url="http://localhost:$(Get-XaiEnvValue $values 'MAILPIT_UI_PORT' '18025')"},
    @{service='db';label='PostgreSQL';port=(Get-XaiEnvValue $values 'POSTGRES_PORT' '15432');url=''},
    @{service='clamav';label='ClamAV';port='3310 internal';url=''}
)
$rows = foreach ($definition in $definitions) {
    $id = Get-XaiContainerId -Service $definition.service
    $status = 'STOPPED'
    if ($id) { $status = (& docker inspect --format '{{.State.Status}}' $id 2>$null).Trim().ToUpperInvariant() }
    $health = if ($definition.url) { if (Test-XaiHttp $definition.url) {'OK'} else {'UNAVAILABLE'} } elseif ($id) { (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $id 2>$null).Trim().ToUpperInvariant() } else {'UNAVAILABLE'}
    [ordered]@{SERVICE=$definition.label;STATUS=$status;PORT=$definition.port;URL=$definition.url;HEALTH=$health}
}
if ($Json) { $rows | ConvertTo-Json -Depth 4 } else { $rows | ForEach-Object { [pscustomobject]$_ } | Format-Table SERVICE,STATUS,PORT,URL,HEALTH -AutoSize }
