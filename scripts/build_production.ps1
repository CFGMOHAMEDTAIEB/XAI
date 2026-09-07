[CmdletBinding()]
param(
    [ValidateSet('android','windows')][string]$Target,
    [Parameter(Mandatory=$true)][string]$ApiUrl,
    [switch]$Aab,
    [switch]$AllowDebugSigning
)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path $PSScriptRoot -Parent
$uri=[Uri]$ApiUrl
if ($uri.Scheme -ne 'https' -or $uri.Host -in @('localhost','127.0.0.1','10.0.2.2','backend') -or $ApiUrl.Contains('REPLACE_') -or $uri.UserInfo -or $uri.AbsolutePath -ne '/' -or $uri.Query -or $uri.Fragment) { throw 'Supply the actual deployed HTTPS backend origin.' }
$health=Invoke-RestMethod ($ApiUrl.TrimEnd('/')+'/health') -TimeoutSec 20
if ($health.status -ne 'ok' -or -not $health.compression.selector_v2) { throw 'Backend is not ready; no production package built.' }
$flutter='C:\src\flutter\bin\flutter.bat'
$env:GRADLE_USER_HOME='E:\GradleCache'
if (!(Test-Path -LiteralPath $env:GRADLE_USER_HOME)) { throw 'E:\GradleCache is required.' }
if (!$Target) { throw 'Specify -Target android or windows.' }
$project=Join-Path $repoRoot $(if($Target -eq 'android'){'apps/mobile_authenticator_flutter'}else{'apps/desktop_flutter'})
$build=Join-Path $project 'build'
$expectedBuild=Join-Path $env:GRADLE_USER_HOME $(if($Target -eq 'android'){'xai-mobile-build'}else{'xai-desktop-build'})
if (!(Test-Path -LiteralPath $build)) {
    New-Item -ItemType Directory -Path $expectedBuild -Force | Out-Null
    New-Item -ItemType Junction -Path $build -Target $expectedBuild | Out-Null
}
$buildItem=Get-Item -LiteralPath $build
if ($buildItem.LinkType -ne 'Junction' -or [string]$buildItem.Target -notlike 'E:\*') { throw 'Build directory must already point to E:. No existing files were moved.' }
Push-Location $project
try {
    if ($Target -eq 'android') {
        if ($AllowDebugSigning) { $env:XAI_ALLOW_DEBUG_SIGNING='true' }
        elseif (@('XAI_ANDROID_KEYSTORE','XAI_ANDROID_STORE_PASSWORD','XAI_ANDROID_KEY_ALIAS','XAI_ANDROID_KEY_PASSWORD') | Where-Object { ![Environment]::GetEnvironmentVariable($_) }) { throw 'Configure Android signing variables, or explicitly use -AllowDebugSigning for test distribution only.' }
        $kind=if($Aab){'appbundle'}else{'apk'}
        & $flutter build $kind --release "--dart-define=XAI_API_URL=$($ApiUrl.TrimEnd('/'))"
        if($LASTEXITCODE -ne 0){throw 'Android build failed.'}
        $artifact=Join-Path $build $(if($Aab){'app/outputs/bundle/release/app-release.aab'}else{'app/outputs/flutter-apk/app-release.apk'})
    } else {
        & $flutter build windows --release "--dart-define=XAI_API_URL=$($ApiUrl.TrimEnd('/'))"
        if($LASTEXITCODE -ne 0){throw 'Windows build failed.'}
        $release=Join-Path $build 'windows/x64/runner/Release'
        $artifact=Join-Path $expectedBuild ('xai-windows-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.zip')
        Compress-Archive -Path (Join-Path $release '*') -DestinationPath $artifact
        # ZIP here packages the EXE, DLLs and assets. It never replaces XAI's compression engine.
    }
    $report=[ordered]@{target=$Target;api_url=$ApiUrl;artifact=$artifact;size=(Get-Item $artifact).Length;sha256=(Get-FileHash -Algorithm SHA256 $artifact).Hash;signing=$(if($Target -eq 'windows'){'unsigned Windows folder distribution'}elseif($AllowDebugSigning){'DEBUG signing - test distribution only'}else{'configured release keystore'})}
    $reportPath=Join-Path $repoRoot 'dist/production-artifacts'
    New-Item -ItemType Directory -Path $reportPath -Force | Out-Null
    $report | ConvertTo-Json | Set-Content (Join-Path $reportPath ($Target+'.json'))
    $report | ConvertTo-Json
} finally { Pop-Location }
