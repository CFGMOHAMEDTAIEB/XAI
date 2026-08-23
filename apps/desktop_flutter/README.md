# XAI-Compress Desktop Flutter

Cross-platform desktop MVP for Windows, Linux and macOS.

## Features

- file picker and drag-and-drop
- local static and neural compression
- verified decompression
- checkpoint selection
- Python executable and engine-directory configuration
- progress/status and cancellation
- compression metrics
- persistent local history
- FastAPI login and share-code redemption
- dark mode
- responsive NavigationRail UI

## Integrate

Replace `XAI-COMPRESS-PLATFORM/apps/desktop_flutter` with this folder. Avoid a duplicated nested folder.

## Requirements

- Flutter SDK
- Visual Studio with Desktop development with C++ for Windows builds
- the installed XAI-Compress Python engine
- optional FastAPI backend for login and file receipt

## Generate platform files and run

```bat
cd apps\desktop_flutter
flutter create .
flutter pub get
flutter test
flutter run -d windows
```

Or run:

```bat
SETUP_WINDOWS.bat
```

## Configure the engine

Open **Settings** and provide:

1. Python executable, for example `C:\XAI\engines\ai_compression\XAI-Compress\.venv\Scripts\python.exe`
2. Engine directory containing `xai_compress`
3. Neural checkpoint `checkpoints\gru_v3.pt`
4. FastAPI URL `http://localhost:8000`

## Current scope

Local compression/decompression is integrated through the existing Python CLI. Cloud upload, MinIO download, streaming process progress, Keycloak OIDC, automatic updates, signed installers and direct Rust/ONNX embedding remain production backlog items.
