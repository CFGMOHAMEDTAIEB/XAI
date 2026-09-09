# Final outcome

| Check | Result |
| --- | --- |
| MOBILE API CONFIG | PASS — release AOT and packaged APK checked |
| DESKTOP API CONFIG | PASS — release AOT and packaged ZIP checked |
| PRODUCTION /health | PASS — HTTP 200, model present |
| PRODUCTION /public/status | PASS for endpoint — HTTP 200, degraded service status |
| AUTH FLOW | PASS — direct API, both adapters, and actual Windows release sign-in |
| PRODUCTION COMPRESSION | BLOCKED — HTTP 503 security verification unavailable |
| FLUTTER ANALYZE | PASS — both apps, no issues |
| FLUTTER TESTS | PASS — mobile 4; additional mobile live adapter 1 |
| ANDROID RELEASE BUILD | PASS — release-mode APK, debug signed |
| ANDROID SIGNING | BLOCKED for production — verified Android Debug certificate only |
| DESKTOP TESTS | PASS — 2, 1 opt-in compression test skipped; additional live adapter 1 |
| DESKTOP RELEASE BUILD | PASS — Windows x64 ZIP, 19 entries, ZIP integrity checked |
| DESKTOP SIGNING | BLOCKED for production — EXE NotSigned |

Both release artifacts configure https://xai-1-be9s.onrender.com; no three development fallback URL strings in their compiled application binaries. Real Windows release login to production is confirmed. Mobile API-adapter login is confirmed, but installed APK startup/login is NOT confirmed: emulator package service failed, and current mobile UI has no backend login call site.

Neither artifact is claimed production-ready: production scanning is unavailable, Android uses debug signing, Windows is unsigned, and mobile runtime validation remains blocked.

Artifacts:
- Android APK: C:\Users\ss\Desktop\XAI\XAI\apps\mobile_authenticator_flutter\build\app\outputs\flutter-apk\app-release.apk — 66,651,161 bytes; physical target E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk.
- Windows ZIP: E:\GradleCache\xai-desktop-build\xai-windows-20260908-155201.zip — 12,258,005 bytes.
- Windows executable folder: E:\GradleCache\xai-desktop-build\windows\x64\runner\Release (also apps\desktop_flutter\build\windows\x64\runner\Release through the existing junction).
- Build-generated metadata: dist/production-artifacts/android.json and windows.json.

Portability:
- APK can be offered for manual test sideloading on Android 7+ for supported ARM32/ARM64/x64 devices. Signature verifies, but installation on another device is untested; not suitable as a production-signed release. Existing installs signed with a different key will not accept an in-place update.
- Copy/extract the entire Windows ZIP, not just the EXE. It ran successfully on this Windows x64 machine. dumpbin confirms external MSVCP140.dll, VCRUNTIME140.dll and VCRUNTIME140_1.dll dependencies: target PCs need a compatible Microsoft Visual C++ runtime. A clean second-PC test is not complete. Explicit local engine modes additionally require the Python engine/checkpoint already documented by the app.

Modified tracked files:
1. apps/mobile_authenticator_flutter/lib/services/deployment_config.dart
2. apps/desktop_flutter/lib/services/deployment_config.dart
3. apps/mobile_authenticator_flutter/README.md
4. apps/desktop_flutter/README.md

Added evidence/helpers: this scratch/production-client-validation directory (URL audit, report, backend/adapter/binary checks, one-run Windows UI helper, screenshots). No server secrets saved. Existing unrelated engine changes were left untouched.

# Production client validation — 2026-09-08

Backend: https://xai-1-be9s.onrender.com

Configuration changes are limited to the release default in each existing XAI_API_URL resolver. Documentation now explains release builds and distinguishes development URLs. No security, authentication, compression, or API contract changes.

Validation evidence:
- GET /health: HTTP 200, status ok, selector_v2 true.
- GET /public/status: HTTP 200, status degraded, security_scanner unavailable, notifications degraded.
- Production register, login, GET /auth/me and GET /history: HTTP 200 each.
- Synchronous POST /compression/jobs with harmless text: HTTP 503, File security verification unavailable; retry later. No artifact exists to download/decompress/hash. Scanning was not bypassed; individual ClamAV/YARA availability cannot be determined from this response.
- Mobile flutter analyze: no issues. Existing flutter test: 4 passed.
- Desktop flutter analyze: no issues. Existing flutter test: 2 passed, 1 opt-in live compression test skipped.
- Additional actual mobile API adapter registration/login/history test: 1 passed with production Dart define.
- Additional actual desktop API adapter registration/login/history test: 1 passed with production Dart define.
- SDK: C:\src\flutter, Flutter 3.47.1, Dart 3.13.1. Doctor reports Android license status unknown; Windows Visual Studio toolchain available.
- No Android production signing variables configured. Existing explicit debug-signing workflow selected for test distribution only.
- Four synthetic example.com test accounts created in total (including the packaged Windows UI check). No credentials or tokens saved in source/report. Direct HTTP workflow revoked its refresh tokens.

Commands executed (repository root unless project directory specified):

```powershell
# SDK validation (initial sandboxed doctor did not produce output; unrestricted retry succeeded)
& 'C:\src\flutter\bin\flutter.bat' doctor
& 'C:\src\flutter\bin\flutter.bat' doctor -v

# In each of apps/mobile_authenticator_flutter and apps/desktop_flutter:
& 'C:\src\flutter\bin\flutter.bat' pub get
& 'C:\src\flutter\bin\flutter.bat' analyze
& 'C:\src\flutter\bin\flutter.bat' test

# Network probe (initial restricted attempt failed; network-enabled retry returned 200)
foreach ($route in @('/health','/public/status')) {
  $r=Invoke-WebRequest -UseBasicParsing -Uri ('https://xai-1-be9s.onrender.com'+$route) -TimeoutSec 60
  Write-Output "$route HTTP $($r.StatusCode) $($r.Content)"
}
python scratch/production-client-validation/check_backend.py

# In apps/mobile_authenticator_flutter:
& 'C:\src\flutter\bin\flutter.bat' test ../../scratch/production-client-validation/mobile_auth_test.dart --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com
# In apps/desktop_flutter:
& 'C:\src\flutter\bin\flutter.bat' test ../../scratch/production-client-validation/desktop_auth_test.dart --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com

# Existing release workflow:
.\scripts\build_production.ps1 -Target android -ApiUrl https://xai-1-be9s.onrender.com -AllowDebugSigning
.\scripts\build_production.ps1 -Target windows -ApiUrl https://xai-1-be9s.onrender.com
# These invoke, in the corresponding app directory:
# flutter build apk --release --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com
# flutter build windows --release --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com
# Script sets GRADLE_USER_HOME=E:\GradleCache and Android XAI_ALLOW_DEBUG_SIGNING=true.

& 'C:\Users\ss\AppData\Local\Android\sdk\platform-tools\adb.exe' devices
& 'C:\Users\ss\AppData\Local\Android\sdk\emulator\emulator.exe' -list-avds
Start-Process -FilePath 'C:\Users\ss\AppData\Local\Android\sdk\emulator\emulator.exe' -ArgumentList '-avd','pixel_emulator','-no-window','-no-audio','-no-snapshot-save' -WindowStyle Hidden -PassThru
& 'C:\Users\ss\AppData\Local\Android\sdk\platform-tools\adb.exe' -s emulator-5554 shell getprop sys.boot_completed

git diff --check -- apps
```

URL locations and production impact: see url-audit.md.

Release AOT inspection:
`python scratch/production-client-validation/check_release_urls.py` passed for Windows app.so and Android arm64-v8a, armeabi-v7a, x86_64 app.so. Each contains the exact production HTTPS URL; none contains http://localhost:8000, http://127.0.0.1:8000, or http://10.0.2.2:8000.

Windows first build failed after 775.1 seconds: flutter_secure_storage_windows_plugin.cpp error C1083, missing atlstr.h. No ATL component found by vswhere or header search. Official Visual Studio Installer attempt returned 5007 (requires elevation); retried with Windows administrator elevation.

Installer command:
```powershell
$installer = Start-Process -FilePath 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\setup.exe' -Verb RunAs -ArgumentList 'modify','--installPath','"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools"','--channelId','VisualStudio.18.Release','--add','Microsoft.VisualStudio.Component.VC.ATL','--quiet','--norestart' -WindowStyle Hidden -PassThru -Wait
```
Component/installer syntax verified against [Microsoft command-line documentation](https://learn.microsoft.com/en-us/visualstudio/install/use-command-line-parameters-to-install-visual-studio) and [Microsoft component catalog](https://github.com/MicrosoftDocs/visualstudio-docs/blob/main/docs/install/includes/vs-2026/workload-component-id-vs-community.md).

Mobile runtime limitation: source search confirms ApiService.login/enrollTotp/confirmTotp have no UI call sites. ApiService is constructed in main.dart and stored by AppState, but current screens only provide lock/unlock, QR scanning, and manual TOTP enrollment. A packaged UI login-to-production flow cannot be demonstrated without adding application behavior, which was intentionally left unchanged. Live adapter authentication succeeded separately.

ATL remediation succeeded: elevated official installer exit code 0. Windows build retried with the exact same production build command; no plugin source or dependency versions changed.

Android build PASS: existing script completed, 1561.0 seconds Gradle time.
- Artifact: C:\Users\ss\Desktop\XAI\XAI\apps\mobile_authenticator_flutter\build\app\outputs\flutter-apk\app-release.apk (junction target E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk).
- Size: 66,651,161 bytes.
- SHA256: 225D2E1881D43E61868ACD1B7231E2C837D34548B1685B2F900F0F773D7D9EE3.
- apksigner verify --print-certs: verifies; signer C=US, O=Android, CN=Android Debug. This is test signing, not proper production signing.
- Packaged libapp.so in all three ABIs verified by check_apk.py: exact Render URL present, three development fallback URLs absent.
- aapt dump badging: minSdk 24 (Android 7+), targetSdk 36, arm64-v8a/armeabi-v7a/x86_64, applicationId com.example.xai_compress_authenticator, version 0.1.0+1.
- Emulator initially booted; adb install -r failed with package-service Broken pipe (32). Follow-up pm command reports Cannot find service: package. Emulator reboot attempted; APK startup not yet verified.

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
& 'C:\Users\ss\AppData\Local\Android\sdk\build-tools\36.0.0\apksigner.bat' verify --print-certs 'E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk'
python scratch/production-client-validation/check_apk.py
& 'C:\Users\ss\AppData\Local\Android\sdk\build-tools\36.0.0\aapt.exe' dump badging 'E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk'
& 'C:\Users\ss\AppData\Local\Android\sdk\platform-tools\adb.exe' -s emulator-5554 install -r 'E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk'
& 'C:\Users\ss\AppData\Local\Android\sdk\platform-tools\adb.exe' -s emulator-5554 shell pm list packages com.example.xai_compress_authenticator
& 'C:\Users\ss\AppData\Local\Android\sdk\platform-tools\adb.exe' -s emulator-5554 reboot
```

Windows retry after ATL installation first timed out in the existing 20-second production health preflight; next identical retry passed preflight and entered compilation.

Android runtime validation BLOCKED: after reboot, adb again reports `cmd: Can't find service: package`. The test emulator started for this task was stopped with `adb -s emulator-5554 emu kill`. No emulator wipe, authentication bypass, or APK modification attempted. Installation/startup on another physical device has not been verified.

Windows native secure-storage DLL now compiled successfully after ATL installation (2026-09-08 15:47:26), resolving the initial header blocker.


Final Windows evidence:
- Successful retry: 529.0 seconds, existing production build script exit 0.
- ZIP SHA256: D36433ABD21FD7DCDEA46DAA7CF10D763EB48CB5F049A8194C01158912A8DC95.
- Get-AuthenticodeSignature: NotSigned.
- Started EXE PID 20712, Responding=True, title XAI-Compress Desktop.
- desktop-startup.png verifies Cloud Hybrid V3 selected.
- Created a unique synthetic account on the production backend, entered generated credentials into the built application using native window messages, clicked Sign in. desktop-login-result.png verifies authenticated Share code / Redeem code / Download artifact controls, which are only displayed after ApiService.login succeeds.
- Registered account credentials were generated in memory; not stored in source/report. Registration refresh token revoked. Desktop test instance closed after validation; its access token was held only in process memory.
- check_windows_zip.py verifies ZIP integrity, required EXE/DLL/data entries and production URL in packaged data/app.so.
- dumpbin /dependents confirms Visual C++ runtime prerequisites; they are not included in the existing ZIP workflow.

Additional exact verification commands:
```powershell
python scratch/production-client-validation/check_release_urls.py
python scratch/production-client-validation/check_windows_zip.py
Get-AuthenticodeSignature -FilePath 'E:\GradleCache\xai-desktop-build\windows\x64\runner\Release\xai_compress_desktop.exe'
Start-Process -FilePath 'E:\GradleCache\xai-desktop-build\windows\x64\runner\Release\xai_compress_desktop.exe' -WorkingDirectory 'E:\GradleCache\xai-desktop-build\windows\x64\runner\Release' -WindowStyle Hidden -PassThru
Get-Process -Id 20712 | Select-Object Id,Responding,MainWindowTitle,MainWindowHandle
.\scratch\production-client-validation\desktop_ui.ps1 -ClickX 377 -ClickY 174
# $testEmail and $testPassword were generated in memory using Guid.NewGuid().
.\scratch\production-client-validation\desktop_ui.ps1 -ClickX 440 -ClickY 165 -Text $testEmail
.\scratch\production-client-validation\desktop_ui.ps1 -ClickX 440 -ClickY 213 -Text $testPassword
.\scratch\production-client-validation\desktop_ui.ps1 -ClickX 610 -ClickY 312 -ImageName desktop-login-result.png
.\scratch\production-client-validation\desktop_ui.ps1 -ImageName desktop-login-result.png
(Get-Process -Id 20712).CloseMainWindow()
& 'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64\dumpbin.exe' /dependents 'E:\GradleCache\xai-desktop-build\windows\x64\runner\Release\xai_compress_desktop.exe'
& 'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64\dumpbin.exe' /dependents 'E:\GradleCache\xai-desktop-build\windows\x64\runner\Release\flutter_windows.dll'
```
