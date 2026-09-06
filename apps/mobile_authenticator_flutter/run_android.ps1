[CmdletBinding()]
param(
    [string]$AvdName = 'pixel_emulator',
    [int]$AdbTimeoutSeconds = 180,
    [int]$BootTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$FlutterRoot = 'C:\src\flutter'
$Flutter = Join-Path $FlutterRoot 'bin\flutter.bat'
$AndroidSdk = 'C:\Users\ss\AppData\Local\Android\sdk'
$Adb = Join-Path $AndroidSdk 'platform-tools\adb.exe'
$Emulator = Join-Path $AndroidSdk 'emulator\emulator.exe'
$ExpectedGradleHome = 'E:\GradleCache'
$ProjectRoot = $PSScriptRoot

function Fail([string]$Message) {
    throw "Android workflow failed: $Message"
}

function Invoke-Checked {
    param([string]$FilePath, [string[]]$ArgumentList)
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        Fail "'$FilePath $($ArgumentList -join ' ')' exited with code $LASTEXITCODE."
    }
}

function Get-RunningAvdDevice {
    $deviceIds = @(& $Adb devices | Select-Object -Skip 1 | ForEach-Object {
        if ($_ -match '^(emulator-\d+)\s+device(?:\s|$)') { $Matches[1] }
    })

    foreach ($deviceId in $deviceIds) {
        $runningAvd = (& $Adb -s $deviceId emu avd name 2>$null | Select-Object -First 1).Trim()
        if ($runningAvd -eq $AvdName) { return $deviceId }
    }
    return $null
}

function Test-LockAvailable([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        $stream = [System.IO.File]::Open($Path, 'Open', 'ReadWrite', 'None')
        $stream.Dispose()
        return $true
    } catch [System.IO.IOException] {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $Flutter)) { Fail "Flutter was not found at $Flutter." }
if (-not (Test-Path -LiteralPath $Adb)) { Fail "ADB was not found at $Adb." }
if (-not (Test-Path -LiteralPath $Emulator)) { Fail "Android Emulator was not found at $Emulator." }
if (-not (Test-Path -LiteralPath $ExpectedGradleHome)) { Fail "Gradle cache drive/path is unavailable: $ExpectedGradleHome." }

$env:GRADLE_USER_HOME = $ExpectedGradleHome
$env:ANDROID_HOME = $AndroidSdk
$env:ANDROID_SDK_ROOT = $AndroidSdk
$env:Path = "$FlutterRoot\bin;$AndroidSdk\platform-tools;$AndroidSdk\emulator;$env:Path"

$flutterVersion = (& $Flutter --version --machine | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { Fail 'The required Flutter executable could not run.' }
if ($flutterVersion.frameworkVersion -ne '3.47.1' -or $flutterVersion.dartSdkVersion -notlike '3.13.1*') {
    Fail "Wrong SDK version at $Flutter (Flutter $($flutterVersion.frameworkVersion), Dart $($flutterVersion.dartSdkVersion))."
}
Write-Host "Using Flutter $($flutterVersion.frameworkVersion), Dart $($flutterVersion.dartSdkVersion)."

$availableAvds = @(& $Emulator -list-avds)
if ($LASTEXITCODE -ne 0 -or $AvdName -notin $availableAvds) {
    Fail "AVD '$AvdName' is not registered with the Android emulator."
}

$lockPath = Join-Path $ProjectRoot 'android\.gradle\noVersion\buildLogic.lock'
if (-not (Test-LockAvailable $lockPath)) {
    Write-Warning 'The project Gradle build-logic lock is active; asking this project Gradle installation to stop its daemons.'
    Invoke-Checked (Join-Path $ProjectRoot 'android\gradlew.bat') @('--stop')
    Start-Sleep -Seconds 2
    if (-not (Test-LockAvailable $lockPath)) {
        Fail "Gradle lock remains owned after 'gradlew --stop': $lockPath. No unrelated Java process was killed."
    }
}

Invoke-Checked $Adb @('start-server')
$deviceId = Get-RunningAvdDevice
if (-not $deviceId) {
    Write-Host "Launching AVD '$AvdName' from its registered storage..."
    $emulatorProcess = Start-Process -FilePath $Emulator -ArgumentList @('-avd', $AvdName) -PassThru
    $deadline = (Get-Date).AddSeconds($AdbTimeoutSeconds)
    do {
        if ($emulatorProcess.HasExited) { Fail "The emulator exited early with code $($emulatorProcess.ExitCode)." }
        Start-Sleep -Seconds 2
        $deviceId = Get-RunningAvdDevice
    } until ($deviceId -or (Get-Date) -ge $deadline)
    if (-not $deviceId) { Fail "ADB did not report AVD '$AvdName' within $AdbTimeoutSeconds seconds." }
} else {
    Write-Host "AVD '$AvdName' is already running as $deviceId."
}

Write-Host "Waiting for $deviceId to finish booting..."
Invoke-Checked $Adb @('-s', $deviceId, 'wait-for-device')
$deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
do {
    $bootCompleted = (& $Adb -s $deviceId shell getprop sys.boot_completed 2>$null).Trim()
    if ($bootCompleted -eq '1') { break }
    Start-Sleep -Seconds 2
} until ((Get-Date) -ge $deadline)
if ($bootCompleted -ne '1') { Fail "Android did not finish booting within $BootTimeoutSeconds seconds." }

Invoke-Checked $Adb @('-s', $deviceId, 'shell', 'input', 'keyevent', '82')
$flutterDevices = (& $Flutter devices --machine | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { Fail "'flutter devices' failed." }
if (-not ($flutterDevices | Where-Object { $_.id -eq $deviceId -and $_.targetPlatform -like 'android-*' })) {
    Fail "Flutter does not detect $deviceId as an Android device."
}

Write-Host "Android is ready as $deviceId. Starting the app..."
Push-Location $ProjectRoot
try {
    & $Flutter run -d $deviceId --dart-define=XAI_API_URL=http://10.0.2.2:8000
    if ($LASTEXITCODE -ne 0) { Fail "'flutter run' exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
