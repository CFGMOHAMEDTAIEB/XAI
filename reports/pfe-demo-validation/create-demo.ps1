$ErrorActionPreference = 'Stop'
$sdk = 'C:\Users\ss\AppData\Local\Android\sdk'
$avdRoot = 'D:\Android\Avd'
$name = 'xai_pfe_demo'
$target = Join-Path $avdRoot "$name.avd"
if (-not (Test-Path -LiteralPath "$sdk\system-images\android-35\default\x86_64\source.properties")) {
    throw 'The full AOSP API 35 x86_64 image must finish installing first.'
}
if ((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath (Join-Path $avdRoot "$name.ini"))) {
    throw 'The demo AVD already exists; refusing to overwrite it.'
}
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:ANDROID_AVD_HOME = $avdRoot
$env:ANDROID_SDK_HOME = 'C:\Users\ss'
$env:ANDROID_USER_HOME = 'C:\Users\ss\.android'
$env:HOME = 'C:\Users\ss'
'no' | & "$sdk\cmdline-tools\latest\bin\avdmanager.bat" create avd --name $name --package 'system-images;android-35;default;x86_64' --path $target --device 'pixel_2'
if ($LASTEXITCODE -ne 0) { throw "avdmanager failed: $LASTEXITCODE" }
$config = Join-Path $target 'config.ini'
$values = [ordered]@{
    'hw.cpu.ncore' = '4'
    'hw.ramSize' = '2048'
    'vm.heapSize' = '256'
    'hw.lcd.width' = '720'
    'hw.lcd.height' = '1280'
    'hw.lcd.density' = '320'
    'skin.name' = '720x1280'
    'skin.path' = '_no_skin'
    'showDeviceFrame' = 'no'
    'hw.gpu.enabled' = 'yes'
    'hw.gpu.mode' = 'swiftshader'
    'hw.camera.front' = 'none'
    'hw.camera.back' = 'none'
    'hw.audioInput' = 'no'
    'hw.gps' = 'no'
    'hw.sdCard' = 'no'
    'hw.keyboard' = 'yes'
    'disk.dataPartition.size' = '4G'
    'fastboot.forceColdBoot' = 'no'
    'fastboot.forceFastBoot' = 'yes'
    'fastboot.forceChosenSnapshotBoot' = 'no'
}
$lines = @(Get-Content -LiteralPath $config)
foreach ($key in $values.Keys) {
    $pattern = '^' + [regex]::Escape($key) + '\s*='
    $lines = @($lines | Where-Object { $_ -notmatch $pattern }) + "$key=$($values[$key])"
}
[IO.File]::WriteAllLines($config, $lines, [Text.UTF8Encoding]::new($false))
Copy-Item -LiteralPath $config -Destination (Join-Path $PSScriptRoot 'demo-config.ini')
Write-Host "Created separate AVD $name at $target. No Android credential was configured."
