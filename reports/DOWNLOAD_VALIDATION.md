# Download validation

Validated against `releases/manifest.json` on 2026-09-20.

All four release files exist. Their local byte lengths and SHA-256 digests match the manifest exactly. Platform, architecture, version, and signing labels are present and reasonable for the produced filenames/packages. No artifact is claimed to be production signed; every manifest entry remains `signed: false`.

| PRODUCT | PLATFORM | HTTP | SIZE_MATCH | SHA256_MATCH | SIGNED | RESULT |
| --- | --- | --- | --- | --- | --- | --- |
| XAI-Compress Mobile Authenticator | Android; Flutter multi-ABI APK | 200 | PASS | PASS | false | PASS |
| XAI-Compress Desktop | Windows x64 ZIP | 200 | PASS | PASS | false | PASS |
| XAI-Compress CLI | Cross-platform `py3-none-any` wheel | 200 | PASS | PASS | false | PASS |
| XAI-Compress Administration | Windows x64 framework-dependent ZIP | 200 | PASS | PASS | false | PASS |

After the successful cold start, `/downloads` returned HTTP 200 at `http://localhost:13000/downloads` and displayed all four manifest filenames. Each real `/api/releases/<filename>` endpoint returned HTTP 200. The downloaded byte count and SHA-256 digest matched `releases/manifest.json` for every artifact. Validation copies were written only beneath the OS temporary directory and were deleted after verification.

Artifact paths:

- `releases/android/xai-compress-authenticator-0.1.0-debug.apk`
- `releases/windows/xai-compress-desktop-0.1.0-windows-x64.zip`
- `releases/cli/xai_compress-0.2.0-py3-none-any.whl`
- `releases/windows/xai-compress-admin-0.1.0-win-x64.zip`
- `releases/manifest.json`
