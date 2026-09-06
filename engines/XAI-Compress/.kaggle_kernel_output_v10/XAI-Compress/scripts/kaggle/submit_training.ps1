param([string]$KernelSlug = "xai-compress-gpu-training")
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Kaggle = Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not (Test-Path -LiteralPath $Kaggle)) { $Kaggle = "kaggle" }
if (-not $env:KAGGLE_USERNAME) { throw "Set KAGGLE_USERNAME first." }
$Stage = Join-Path $Project ".kaggle_kernel"
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "run_kaggle_training.py") -Destination (Join-Path $Stage "run_kaggle_training.py") -Force
$Metadata = @{
    id = "$($env:KAGGLE_USERNAME)/$KernelSlug"
    title = "XAI-Compress GPU Training"
    code_file = "run_kaggle_training.py"
    language = "python"
    kernel_type = "script"
    is_private = $true
    enable_gpu = $true
    enable_internet = $false
    dataset_sources = @("$($env:KAGGLE_USERNAME)/xai-compress-source", "xdxd003/ff-c23")
    competition_sources = @()
    kernel_sources = @()
} | ConvertTo-Json -Depth 4
$MetadataPath = Join-Path $Stage "kernel-metadata.json"
[System.IO.File]::WriteAllText($MetadataPath, $Metadata, [System.Text.UTF8Encoding]::new($false))
& $Kaggle kernels push -p $Stage
if ($LASTEXITCODE) { throw "Kaggle GPU job submission failed." }
Write-Host "Submitted: https://www.kaggle.com/code/$($env:KAGGLE_USERNAME)/$KernelSlug"
Write-Host "Status: .\.venv\Scripts\kaggle.exe kernels status $($env:KAGGLE_USERNAME)/$KernelSlug"
