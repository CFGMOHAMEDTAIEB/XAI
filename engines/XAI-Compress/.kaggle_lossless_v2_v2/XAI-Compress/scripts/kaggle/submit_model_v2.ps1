param([ValidateSet("lossless_v2","lossy_v1")][string]$Family)
$ErrorActionPreference="Stop"
$Project=(Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle=Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not $env:KAGGLE_USERNAME) { throw "Set KAGGLE_USERNAME first." }
$Stage=Join-Path $Project ".kaggle_kernel_$Family"
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
$Entry="run_kaggle_$Family.py"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot $Entry) -Destination (Join-Path $Stage $Entry) -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "run_kaggle_training.py") -Destination (Join-Path $Stage "run_kaggle_training.py") -Force
$Slug="xai-compress-$($Family.Replace('_','-'))"
@{id="$($env:KAGGLE_USERNAME)/$Slug";title="XAI Compress $Family";code_file=$Entry;language="python";kernel_type="script";is_private=$true;enable_gpu=$true;machine_shape="NvidiaTeslaT4";enable_internet=$false;dataset_sources=@("$($env:KAGGLE_USERNAME)/xai-compress-source","xdxd003/ff-c23");competition_sources=@();kernel_sources=@()} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Stage "kernel-metadata.json") -Encoding utf8
& $Kaggle kernels push -p $Stage
if ($LASTEXITCODE) { throw "Kaggle $Family submission failed." }
