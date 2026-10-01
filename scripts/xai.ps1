[CmdletBinding()]
param([Parameter(Position=0,Mandatory=$true)][ValidateSet('start','stop','status','health','seed','test','benchmark','notebook','build','release','demo','clean')][string]$Command)
$ErrorActionPreference='Stop'
$map=@{start='start-all.ps1';stop='stop-core.ps1';status='status.ps1';health='health-check.ps1';seed='seed-demo-users.ps1';test='test-all.ps1';benchmark='benchmark.ps1';notebook='notebook.ps1';build='build-releases.ps1';release='build-releases.ps1';demo='demo-e2e.ps1';clean='cleanup.ps1'}
& (Join-Path $PSScriptRoot $map[$Command])
exit $LASTEXITCODE
