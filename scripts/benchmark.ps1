[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$repoRoot=Split-Path $PSScriptRoot -Parent
& python (Join-Path $PSScriptRoot 'benchmark-report.py')
if($LASTEXITCODE){throw 'Benchmark evidence validation/export failed.'}
Write-Host 'Validated export created without overwriting historical benchmark evidence.'
