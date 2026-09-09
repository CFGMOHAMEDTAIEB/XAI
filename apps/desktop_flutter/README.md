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
4. Development FastAPI URL `http://localhost:8000`

## Windows release configuration

Release builds use `https://xai-1-be9s.onrender.com` by default, with the existing
`--dart-define=XAI_API_URL=...` override. Release mode rejects non-HTTPS and known
local backend URLs and ignores saved development API URLs. Cloud mode is the
initial mode; failures are displayed without falling back to a local engine.
The explicit static and neural local engine modes remain available and require
the separately installed Python engine and relevant checkpoint.

From the repository root:

```powershell
.\scripts\build_production.ps1 -Target windows -ApiUrl https://xai-1-be9s.onrender.com
```

The existing workflow packages the entire release folder as an unsigned ZIP.
Distribute the EXE together with its DLLs and data folder, not the EXE alone.

## Current scope

Local compression/decompression is integrated through the existing Python CLI.
Cloud compression uses the synchronous `/compression/jobs` endpoint, artifact
download, and `/compression/decompress`. Production scanning must be available
for these operations. MinIO download, streaming process progress, Keycloak OIDC,
automatic updates, signed installers and direct Rust/ONNX embedding remain
production backlog items.
