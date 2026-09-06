param([ValidateSet("lossless_v2","lossy_v1")][string]$Family)
$ErrorActionPreference="Stop"
$Project=(Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle=Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not $env:KAGGLE_USERNAME) { throw "Set KAGGLE_USERNAME first." }
$Stage=Join-Path $Project ".kaggle_kernel_$Family"
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
$Entry="run_kaggle_$Family.py"
$Runner=[System.IO.File]::ReadAllText((Join-Path $PSScriptRoot "run_kaggle_training.py"))
# Kaggle script kernels upload only code_file. Produce one self-contained file
# and insert the family after future imports so Python syntax remains valid.
$Marker="from __future__ import annotations"
$Specialized=$Runner.Replace($Marker,"$Marker`nimport os as _family_os`n_family_os.environ['XAI_TRAINING_FAMILY']='$Family'")
[System.IO.File]::WriteAllText((Join-Path $Stage $Entry),$Specialized,[System.Text.UTF8Encoding]::new($false))
$Slug="xai-compress-$($Family.Replace('_','-'))"
$Metadata=@{id="$($env:KAGGLE_USERNAME)/$Slug";title="XAI Compress $Family";code_file=$Entry;language="python";kernel_type="script";is_private=$true;enable_gpu=$true;machine_shape="NvidiaTeslaT4";enable_internet=$false;dataset_sources=@("$($env:KAGGLE_USERNAME)/xai-compress-source","xdxd003/ff-c23");competition_sources=@();kernel_sources=@()} | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $Stage "kernel-metadata.json"),$Metadata,[System.Text.UTF8Encoding]::new($false))
& $Kaggle kernels push -p $Stage
if ($LASTEXITCODE) { throw "Kaggle $Family submission failed." }
