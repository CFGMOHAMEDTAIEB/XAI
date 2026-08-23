# XAI-Compress Mobile Authenticator

Flutter MVP inspired by common authenticator workflows:

- TOTP codes refreshed every 30 seconds
- QR enrollment using `otpauth://totp/...`
- manual Base32 enrollment
- platform secure storage
- biometric/device-credential lock
- multiple accounts
- copy code
- delete account
- FastAPI client for login, TOTP enrollment, and confirmation

## Important security scope

This is a development MVP. Before production, add threat modeling, certificate pinning, hardened device registration, encrypted backups/recovery, root/jailbreak policy, push approval with number matching, secure screenshots policy, privacy review, and an external security assessment.

## Install Flutter

Verify:

```bat
flutter --version
flutter doctor
```

## Integrate into the monorepo

Copy the extracted folder to:

```text
XAI-COMPRESS-PLATFORM\apps\mobile_authenticator_flutter
```

If that folder already exists, rename the old folder first.

## Generate Android and iOS platform files

From the mobile folder:

```bat
flutter create .
flutter pub get
flutter test
flutter run
```

For Android emulator, the default backend URL is:

```text
http://10.0.2.2:8000
```

For a physical phone, replace the URL in `lib/services/api_service.dart` with the computer's LAN IP, for example:

```text
http://192.168.1.20:8000
```

## Backend enrollment flow

1. Register or login through FastAPI.
2. Call `POST /auth/totp/enroll` with the Bearer token.
3. Display the returned QR image or `otpauth_uri`.
4. Scan the QR with this application.
5. Enter the generated 6-digit code into `POST /auth/totp/confirm?code=...`.
6. Future logins require password plus the current TOTP code.

## Android permissions

After `flutter create .`, ensure `android/app/src/main/AndroidManifest.xml` contains:

```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.USE_BIOMETRIC" />
```

## iOS permissions

Add to `ios/Runner/Info.plist`:

```xml
<key>NSCameraUsageDescription</key>
<string>Scan an XAI-Compress TOTP enrollment QR code.</string>
<key>NSFaceIDUsageDescription</key>
<string>Unlock the XAI-Compress Authenticator.</string>
```

## Next development sprint

- push login approval
- number matching
- recovery codes
- device registration and revocation
- account export/import with encryption
- settings and language selection
- security notifications
- deep links
- Keycloak OIDC integration
