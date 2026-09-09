# Physical Flutter navigation verification

Device: 816f7f5f / CPH2307. Debug command:
`flutter run -d 816f7f5f --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com`

## Root cause and fix

MainActivity.kt:5 extended FlutterActivity. local_auth requires FragmentActivity.
The physical-device Flutter output before the fix was:

```text
[XAI startup] Unlock pressed; authentication begin
[XAI startup] local_auth supported=true
[XAI startup] local_auth failed: LocalAuthException(code uiUnavailable, The current Activity must be a FragmentActivity., null)
[XAI startup] authentication complete; unlocked=false
```

BiometricService.authenticate catches the exception and returns false (current lines 17-19).
AppState.unlock assigns false to unlocked (current line 45), so main.dart:56 keeps LockScreen visible.
The fix changes only the activity import and superclass to FlutterFragmentActivity.
Temporary kDebugMode logging was added in AppState and BiometricService. No account secrets are logged.
A widget regression test verifies rejection stays locked, success shows home, and locking hides home.

## Complete startup flow

1. main.dart initializes Flutter bindings and runs ChangeNotifierProvider. Provider creation calls AppState.initialize without awaiting it in main.
2. MaterialApp.home consumes AppState. loading=true initially renders a scaffold with a spinner.
3. initialize awaits SecureAccountStore.loadAccounts. This reads xai_authenticator_accounts_v1 from FlutterSecureStorage, then decodes JSON when present. There are no other startup storage reads.
4. After storage returns, loading=false and notifyListeners shows LockScreen because unlocked=false.
5. A periodic one-second timer updates the TOTP clock and notifies listeners. It neither delays nor triggers navigation and is cancelled on dispose.
6. LockScreen's Unlock button calls AppState.unlock. It awaits BiometricService.authenticate.
7. Authentication awaits isDeviceSupported, then authenticate with biometricOnly=false and persistAcrossBackgrounding=true. Existing unsupported-device behavior is unchanged. False/cancellation or a caught exception keeps the app locked; true enables HomeScreen after notifyListeners.
8. No backend request, health check, login, token restoration, session check, or permission request gates startup. ApiService is constructed with the configured URL; its login/enrollment methods are not called by startup.
9. No go_router or Navigator call controls lock-to-home navigation: the Consumer condition replaces the home widget. HomeScreen can push the QR scanner, pop a detected TOTP URI, or open/dismiss the manual entry dialog. Camera access is deferred to MobileScanner on the scanner page.
10. loading can remain true if the storage Future hangs or throws; there is no try/finally. This did not occur on the device: logs confirm storage completed and loading=false. The scanner's handled flag only prevents duplicate scans; it is unrelated to startup.

## Fixed device output

The following excerpts were captured from the second flutter run tool session (PID 8260):

```text
Installing build\app\outputs\flutter-apk\app-debug.apk...           4,5s
[XAI startup] storage read begin; API=https://xai-1-be9s.onrender.com
[XAI startup] storage read complete
[XAI startup] loading=false; showing LockScreen
[XAI startup] Unlock pressed; authentication begin
[XAI startup] local_auth supported=true
[XAI startup] authentication complete; unlocked=true
```

UI inspection confirmed the Android system Verify identity prompt with description Unlock XAI-Compress Authenticator. Following successful authentication, runtime output continued with taps and Flutter text input/keyboard activity. No Dart exception appeared in the captured fixed run.

flutter analyze: no issues. flutter test: all 5 passed.

Install, startup, first page, authentication/navigation, and configured Render URL passed. The app remained running through the captured post-authentication interactions. The device subsequently disconnected from ADB before the final independent PID/UI snapshot; sustained runtime beyond that point is not verified. No production release was built. No Gradle, backend, compression, or authentication-policy changes were made.
