# Production client URL audit — 2026-09-08

Scope: apps/mobile_authenticator_flutter and apps/desktop_flutter. Both are Flutter applications. No application environment files or alternate production URL mechanism were found. Existing build workflow: scripts/build_production.ps1, C:\src\flutter\bin\flutter.bat, build junctions under E:\GradleCache.

| Location | Meaning and production impact |
| --- | --- |
| Both apps: lib/services/deployment_config.dart:4-5 | Existing XAI_API_URL Dart define. Now defaults to https://xai-1-be9s.onrender.com in release only. Explicit overrides retain existing HTTPS/local-host validation. |
| Both apps: lib/services/deployment_config.dart:10 | localhost, 127.0.0.1, 10.0.2.2, backend, ::1 are release rejection entries, not connection destinations. |
| Mobile lib/services/deployment_config.dart:14 | http://10.0.2.2:8000 development fallback; release validates before this return and cannot silently reach it. |
| Desktop lib/services/deployment_config.dart:14 | http://localhost:8000 development fallback; release validates before this return and cannot silently reach it. |
| Mobile lib/services/api_service.dart:8 | API constructor resolves configuredApiUrl; optional injected baseUrl exists, no production call site supplying a local URL found. |
| Desktop lib/services/api_service.dart:4 | API constructor resolves configuredApiUrl; all login/history/share/compression requests derive from baseUrl. No local retry. |
| Desktop lib/services/settings_service.dart:4-5 | DesktopSettings resolves configuredApiUrl; SharedPreferences apiUrl is used only outside release. Release ignores previously saved local URLs. |
| Desktop lib/core/app_state.dart:4,12 | Initialization and settings save force configuredApiUrl in release; initial mode is cloud (line 3). Cloud errors are displayed; local static/neural modes require explicit selection. |
| Desktop lib/screens/settings_screen.dart:24,60 | Existing editable saved API URL field; release API selection remains enforced by AppState. |
| Mobile run_android.ps1:122 | Explicit emulator Dart define http://10.0.2.2:8000 for flutter run; development launcher, not production build workflow. |
| Mobile README.md:52,58 | Emulator development default and LAN development command http://192.168.1.20:8000; documentation only. LAN guidance corrected to use existing Dart define. |
| Desktop README.md:53 | localhost example labeled development only. |
| Mobile flutter_verbose2.txt:140,171,174 and flutter_error.txt:140,171,174,590 | Historical debug logs containing emulator Dart define and encoded equivalent; not compiled source. |
| scripts/build_production.ps1:11,33,37 | Validates HTTPS origin, checks health/model, passes explicit XAI_API_URL to Android or Windows release build. No production localhost fallback. |
| Desktop SETUP_WINDOWS.bat | Legacy generic Flutter scaffold/build launcher, no URL override; release now receives production default. Not used for this build. |

No backend:8000 connection destination was found in these applications. Mobile android/gradle.properties values 180000 are HTTP timeout milliseconds, not port 8000. XML namespace, Flutter/plugin documentation, and the https://example.com malformed-enrollment test are not backend URLs. Generated dependency files and historical build outputs are not configuration sources.

No compression, authentication, biometric, scanning, API contract, or TLS implementation was changed.
