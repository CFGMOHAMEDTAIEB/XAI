param([string]$Username = $env:KAGGLE_USERNAME)
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle = Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not $Username) { throw "Set KAGGLE_USERNAME or pass -Username." }
$Stage = Join-Path $Project ".kaggle_kernel_v2_multi_epoch_diagnostic"
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "run_v2_multi_epoch_diagnostic.py") -Destination (Join-Path $Stage "run.py") -Force
$Metadata = @{
    id = "$Username/xai-compress-v2-multi-epoch-stability"
    title = "XAI Compress V2 Multi Epoch Stability"
    code_file = "run.py"
    language = "python"
    kernel_type = "script"
    is_private = $true
    enable_gpu = $true
    machine_shape = "NvidiaTeslaT4"
    enable_internet = $false
    dataset_sources = @("$Username/xai-compress-source", "xdxd003/ff-c23")
    competition_sources = @()
    kernel_sources = @()
} | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $Stage "kernel-metadata.json"), $Metadata, [Text.UTF8Encoding]::new($false))
& $Kaggle kernels push -p $Stage
if ($LASTEXITCODE) { throw "Multi-epoch diagnostic submission failed." }
