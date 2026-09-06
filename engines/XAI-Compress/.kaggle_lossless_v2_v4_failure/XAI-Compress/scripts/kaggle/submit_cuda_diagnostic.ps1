param()
$ErrorActionPreference="Stop"
$Project=(Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle=Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not $env:KAGGLE_USERNAME) { throw "Set KAGGLE_USERNAME first." }
$Stage=Join-Path $Project ".kaggle_kernel_lossless_v2_diagnostic"
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "run_lossless_v2_cuda_diagnostic.py") -Destination (Join-Path $Stage "run.py") -Force
$Metadata=@{id="$($env:KAGGLE_USERNAME)/xai-compress-lossless-v2-diagnostic";title="XAI Compress Lossless V2 CUDA Diagnostic";code_file="run.py";language="python";kernel_type="script";is_private=$true;enable_gpu=$true;machine_shape="NvidiaTeslaT4";enable_internet=$false;dataset_sources=@("$($env:KAGGLE_USERNAME)/xai-compress-source","xdxd003/ff-c23");competition_sources=@();kernel_sources=@()} | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $Stage "kernel-metadata.json"),$Metadata,[Text.UTF8Encoding]::new($false))
& $Kaggle kernels push -p $Stage
if ($LASTEXITCODE) { throw "CUDA diagnostic submission failed." }
