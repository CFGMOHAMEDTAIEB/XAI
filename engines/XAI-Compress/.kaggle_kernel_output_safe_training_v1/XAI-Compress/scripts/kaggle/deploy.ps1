param([string]$Message = "XAI-Compress source update", [switch]$ForceCreate, [string]$BuildPath)
$ErrorActionPreference = "Stop"
$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Project ".venv\Scripts\python.exe"
$Kaggle = Join-Path $Project ".venv\Scripts\kaggle.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
if (-not (Test-Path -LiteralPath $Kaggle)) { $Kaggle = "kaggle" }
if (-not $env:KAGGLE_USERNAME) { throw "Set KAGGLE_USERNAME to your Kaggle account name." }
if (-not $env:KAGGLE_DATASET) { $env:KAGGLE_DATASET = "xai-compress-source" }
$Build = if ($BuildPath) { $BuildPath } elseif ($env:KAGGLE_BUILD_DIR) { $env:KAGGLE_BUILD_DIR } else { Join-Path $Project ".kaggle_build" }
& $Python (Join-Path $PSScriptRoot "prepare_kaggle_package.py") --project $Project --staging $Build
if ($LASTEXITCODE) { throw "Package preparation failed." }
& $Python (Join-Path $PSScriptRoot "verify_package.py") $Build
if ($LASTEXITCODE) { throw "Package verification failed." }
& $Kaggle config view | Out-Null
if ($LASTEXITCODE) { throw "Kaggle authentication failed. Run 'kaggle auth login', create %USERPROFILE%\.kaggle\access_token, or set KAGGLE_API_TOKEN." }
$DatasetId = "$($env:KAGGLE_USERNAME)/$($env:KAGGLE_DATASET)"
$Exists = $false
if (-not $ForceCreate) {
    # A missing/private-not-yet-created dataset can return 403. That is a
    # normal signal for first deployment, not a fatal PowerShell error.
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Kaggle datasets files $DatasetId --page-size 1 *> $null
        $Exists = ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
}
if ($Exists) { & $Kaggle datasets version -p $Build -m $Message -r zip }
else { & $Kaggle datasets create -p $Build -r zip }
if ($LASTEXITCODE) { throw "Kaggle deployment failed." }
Write-Host "Deployed Kaggle dataset: $DatasetId"
