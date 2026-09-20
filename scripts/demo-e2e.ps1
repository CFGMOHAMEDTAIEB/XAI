[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'seed-demo-users.ps1')
& python (Join-Path $PSScriptRoot 'demo_e2e.py')
if($LASTEXITCODE){throw 'Local API-level demo E2E failed. See reports/demo_e2e_report.json.'}
Write-Host 'Local API-level demo E2E passed. Reports are in reports/.'
