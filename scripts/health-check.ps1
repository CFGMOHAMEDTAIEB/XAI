[CmdletBinding()]
param([switch]$Json)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$repoRoot = Get-XaiRepoRoot
$values = Read-XaiEnv (Join-Path $repoRoot '.env')
$apiPort = [int](Get-XaiEnvValue $values 'API_PORT' '18000')
$checks = @(
    [ordered]@{name='FastAPI health';url="http://localhost:$apiPort/health";healthy=(Test-XaiHttp "http://localhost:$apiPort/health")},
    [ordered]@{name='Scanner/public status';url="http://localhost:$apiPort/public/status";healthy=(Test-XaiHttp "http://localhost:$apiPort/public/status")},
    [ordered]@{name='Angular';url="http://localhost:$(Get-XaiEnvValue $values 'ANGULAR_PORT' '4200')";healthy=(Test-XaiHttp "http://localhost:$(Get-XaiEnvValue $values 'ANGULAR_PORT' '4200')")},
    [ordered]@{name='Next.js';url="http://localhost:$(Get-XaiEnvValue $values 'NEXTJS_PORT' '3000')";healthy=(Test-XaiHttp "http://localhost:$(Get-XaiEnvValue $values 'NEXTJS_PORT' '3000')")},
    [ordered]@{name='.NET Admin';url="http://localhost:$(Get-XaiEnvValue $values 'ADMIN_PORT' '5050')";healthy=(Test-XaiHttp "http://localhost:$(Get-XaiEnvValue $values 'ADMIN_PORT' '5050')")},
    [ordered]@{name='pgAdmin';url="http://localhost:$(Get-XaiEnvValue $values 'PGADMIN_PORT' '5051')";healthy=(Test-XaiHttp "http://localhost:$(Get-XaiEnvValue $values 'PGADMIN_PORT' '5051')")},
    [ordered]@{name='Mailpit';url="http://localhost:$(Get-XaiEnvValue $values 'MAILPIT_UI_PORT' '18025')";healthy=(Test-XaiHttp "http://localhost:$(Get-XaiEnvValue $values 'MAILPIT_UI_PORT' '18025')")}
)
if ($Json) { $checks | ConvertTo-Json -Depth 4 } else { $checks | ForEach-Object { [pscustomobject]$_ } | Format-Table Name,Healthy,Url -AutoSize }
if (@($checks | Where-Object { -not $_.healthy }).Count) { exit 1 }
