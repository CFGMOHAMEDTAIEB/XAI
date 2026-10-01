[CmdletBinding()]
param([switch]$SkipAndroid,[switch]$SkipWindows,[switch]$SkipAdmin,[switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'xai-common.ps1')
$repoRoot = Get-XaiRepoRoot
$releaseRoot = Join-Path $repoRoot 'releases'
$runtimeRoot = Get-XaiRuntimePath -RepoRoot $repoRoot
foreach ($directory in @('android','windows','cli','manifests')) { New-Item -ItemType Directory -Path (Join-Path $releaseRoot $directory) -Force | Out-Null }
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$entries = @()
function Get-FlutterVersion([string]$Project) { $line=Get-Content (Join-Path $Project 'pubspec.yaml')|Where-Object{$_ -match '^version:\s*'}|Select-Object -First 1; return (($line-replace '^version:\s*','')-split '\+')[0].Trim() }
function Add-Artifact([string]$Product,[string]$Platform,[string]$Version,[string]$Path,[string]$Architecture,[string]$Status,[bool]$Signed,[string]$Requirements) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $item=Get-Item -LiteralPath $Path
    $resolvedRoot=[IO.Path]::GetFullPath($releaseRoot).TrimEnd('\')+'\';$resolvedItem=[IO.Path]::GetFullPath($item.FullName)
    if(-not $resolvedItem.StartsWith($resolvedRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Artifact must be inside releases/.'}
    $script:entries += [ordered]@{product=$Product;platform=$Platform;version=$Version;filename=$item.Name;relativePath=($resolvedItem.Substring($resolvedRoot.Length).Replace('\','/'));size=$item.Length;sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant();buildDate=$item.LastWriteTimeUtc.ToString('o');status=$Status;architecture=$Architecture;minimumRequirements=$Requirements;signed=$Signed;downloadAvailable=$true}
}
$flutter=(Get-Command flutter.bat -ErrorAction SilentlyContinue).Source
if(-not $SkipAndroid){
 $project=Join-Path $repoRoot 'apps/mobile_authenticator_flutter';$version=Get-FlutterVersion $project
 $missingSigning=@('XAI_ANDROID_KEYSTORE','XAI_ANDROID_STORE_PASSWORD','XAI_ANDROID_KEY_ALIAS','XAI_ANDROID_KEY_PASSWORD')|Where-Object{-not [Environment]::GetEnvironmentVariable($_)};$signed=$missingSigning.Count -eq 0
 if(-not $SkipBuild){if(-not $flutter){throw 'Flutter is required for Android.'};Push-Location $project;try{if($signed){& $flutter build apk --release}else{& $flutter build apk --debug};if($LASTEXITCODE){throw 'Android build failed.'}}finally{Pop-Location}}
 $source=Join-Path $project $(if($signed){'build/app/outputs/flutter-apk/app-release.apk'}else{'build/app/outputs/flutter-apk/app-debug.apk'});if(Test-Path $source){$destination=Join-Path $releaseRoot "android/xaicd-authenticator-$version-$(if($signed){'release'}else{'debug'}).apk";Copy-Item -LiteralPath $source -Destination $destination -Force;Add-Artifact 'XAICD Authenticator' 'Android' $version $destination 'Flutter multi-ABI APK' $(if($signed){'LOCAL_SIGNED_UNVERIFIED'}else{'TEST_ONLY_DEBUG_SIGNED'}) $signed 'Android supported by the current Flutter toolchain; installation not certified'}
}
if(-not $SkipWindows){
 $project=Join-Path $repoRoot 'apps/desktop_flutter';$version=Get-FlutterVersion $project
 if(-not $SkipBuild){if(-not $flutter){throw 'Flutter is required for Windows.'};Push-Location $project;try{& $flutter build windows --release;if($LASTEXITCODE){throw 'Windows Flutter build failed.'}}finally{Pop-Location}}
 $source=Join-Path $project 'build/windows/x64/runner/Release';$destination=Join-Path $releaseRoot "windows/xaicd-desktop-$version-windows-x64.zip"
 if(Test-Path $source){if(Test-Path $destination){Remove-Item -LiteralPath $destination -Force};Compress-Archive -Path (Join-Path $source '*') -DestinationPath $destination -CompressionLevel Optimal;Add-Artifact 'XAICD Desktop' 'Windows' $version $destination 'x64' 'TEST_ONLY_UNSIGNED' $false 'Windows 10/11 x64; Visual C++ runtime may be required'}
 elseif($SkipBuild){$prior=Get-ChildItem 'D:\GradleCache\xai-desktop-build\xai-windows-*.zip' -File -ErrorAction SilentlyContinue|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1;if($prior){Copy-Item -LiteralPath $prior.FullName -Destination $destination -Force;Add-Artifact 'XAICD Desktop' 'Windows' $version $destination 'x64' 'TEST_ONLY_EXISTING_UNSIGNED_BUILD' $false 'Windows 10/11 x64; fresh rebuild was not completed in this run'}}
}
$engine=Join-Path $repoRoot 'engines/XAI-Compress';if(-not $SkipBuild){& python -m pip wheel $engine --no-deps --no-build-isolation --wheel-dir (Join-Path $releaseRoot 'cli');if($LASTEXITCODE){throw 'CLI wheel build failed.'}}
$wheel=Get-ChildItem (Join-Path $releaseRoot 'cli') -Filter 'xai_compress-*.whl' -File|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1;if($wheel){Add-Artifact 'XAICD CLI' 'Cross-platform Python' '0.2.0' $wheel.FullName 'py3-none-any' 'LOCAL_PACKAGE_UNSIGNED' $false 'Python >=3.10 with declared PyTorch and NumPy dependencies'}
if(-not $SkipAdmin){$publish=Join-Path $runtimeRoot 'admin-publish-win-x64';if(-not $SkipBuild){& dotnet publish (Join-Path $repoRoot 'apps/admin_dotnet/AdminDotNet.csproj') -c Release -r win-x64 --self-contained false -o $publish;if($LASTEXITCODE){throw '.NET Admin publish failed.'}};if(Test-Path $publish){$destination=Join-Path $releaseRoot 'windows/xaicd-admin-0.1.0-win-x64.zip';if(Test-Path $destination){Remove-Item -LiteralPath $destination -Force};Compress-Archive -Path (Join-Path $publish '*') -DestinationPath $destination -CompressionLevel Optimal;Add-Artifact 'XAICD Admin' 'Windows' '0.1.0' $destination 'win-x64 framework-dependent' 'TEST_ONLY_UNSIGNED' $false '.NET 8 runtime; local API access'}}
$manifest=[ordered]@{schemaVersion=1;generatedAt=(Get-Date).ToUniversalTime().ToString('o');artifacts=$entries};$manifestPath=Join-Path $releaseRoot 'manifest.json';[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false));Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $releaseRoot 'manifests/manifest.json') -Force
$entries|ForEach-Object{"{0} | {1} bytes | SHA-256 {2} | SIGNED={3}" -f $_.relativePath,$_.size,$_.sha256,$_.signed};Write-Host "Manifest: $manifestPath"
