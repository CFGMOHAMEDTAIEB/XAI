[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$repoRoot=Split-Path $PSScriptRoot -Parent
$python=Join-Path $repoRoot '.venv/Scripts/python.exe'
if(-not(Test-Path $python)){throw 'The analysis virtual environment .venv is unavailable.'}
& $python (Join-Path $PSScriptRoot 'verify-notebook.py')
if($LASTEXITCODE){throw 'Notebook validation failed.'}
Write-Host "Notebook: $(Join-Path $repoRoot 'notebooks/XAI_Compress_Model_Analysis.ipynb')"
