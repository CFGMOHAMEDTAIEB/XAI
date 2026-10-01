# XAICD integrated platform

This monorepo combines the lossless XAI-Compress engine with a FastAPI API, PostgreSQL, Angular user portal, Next.js public site, .NET administration UI, ClamAV/YARA scanning, Flutter desktop client, and Flutter mobile authenticator.

## Quick start

Prerequisites: Docker Desktop with Compose, Windows PowerShell 5.1 or PowerShell 7, and enough free space for the scanner/model images. Flutter, Rust, Python, Node, and .NET are only required for native builds or the complete host test campaign.

```powershell
cd C:\Users\ss\Desktop\XAI\XAI
.\scripts\xai.ps1 start
```

If the host's PowerShell execution policy blocks direct script execution, use the process-scoped fallback below. It does not weaken the machine-wide policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\xai.ps1 start
```

The launcher creates an ignored `.env` when absent, generates random local-only secrets and two distinct demo passwords, checks ports, builds images, waits for PostgreSQL/Mailpit/ClamAV, applies migrations, starts the web stack, and reports readiness. Call `scripts/start-all.ps1 -SkipDesktop` directly to omit the host Flutter process.

| Service | Default address |
| --- | --- |
| Public Next.js site | http://localhost:3000 |
| Next.js downloads | http://localhost:3000/downloads |
| Angular portal | http://localhost:4200 |
| FastAPI health | http://localhost:18000/health |
| FastAPI/OpenAPI | http://localhost:18000/docs |
| .NET admin | http://localhost:5050 |
| pgAdmin | http://localhost:5051 |
| Mailpit | http://localhost:18025 |
| PostgreSQL | `127.0.0.1:15432` |

All ports are configurable in the ignored `.env`; `.env.example` is the placeholder-only, non-secret reference. The table shows baseline ports. The launcher prints the actual URLs selected by the current `.env` (the final validation campaign used FastAPI `18002`, Next.js `13000`, .NET `15051`, pgAdmin `15052`, Mailpit `18026`, and PostgreSQL `15432`). The launcher refuses conflicts and never stops unrelated containers.

```powershell
.\scripts\xai.ps1 status
.\scripts\xai.ps1 health
.\scripts\xai.ps1 stop
```

Use the same `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` prefix for any command if direct `.ps1` execution is restricted.

Ordinary stop/restart preserves the named database, pgAdmin, scanner, and artifact volumes. Do not use `docker compose down -v` when data must survive.

## One-click local launch

From the repository root, start the core platform, Flutter Desktop, the existing Android emulator, and the Mobile Authenticator with:

```powershell
run-all.bat
```

Optional starts:

```powershell
run-all.bat -NoBrowser
run-all.bat -NoMobile
run-all.bat -NoDesktop
```

Inspect or stop only the platform and host processes recorded by this launcher:

```powershell
status-all.bat
stop-all.bat
```

The first Flutter launch after generated files have been cleaned can take longer because dependencies and build outputs must be regenerated. The launcher reuses an online emulator, never wipes AVD data, retains Docker volumes, and does not stop a pre-existing emulator.

## Architecture and data flow

FastAPI is the authoritative identity, authorization, share, history, and compression service. PostgreSQL owns metadata; `xai-storage` owns inputs and `.xaic` artifacts. Uploads are scanned by ClamAV and production YARA rules; required scanner failure is fail-closed. Hybrid V3 uses the frozen Selector V2 model and verifies decompression by SHA-256 before committing a job.

Containers call `backend:8000` and `db:5432`; browsers and host applications use configured localhost ports. Angular nginx proxies `/api`. Next.js uses `INTERNAL_API_URL` server-side and `NEXT_PUBLIC_API_URL` in the browser. Flutter desktop defaults to localhost; Android emulators use `10.0.2.2`, while a phone needs the host LAN address via `--dart-define=XAI_API_URL=...`.

See [the architecture audit](docs/PROJECT_AUDIT.md) and [cleanup plan](docs/CLEANUP_PLAN.md) for the evidence-backed inventory and retained/deleted classifications.

## Database, migrations, and pgAdmin

The backend applies ordered, checksummed migrations under a PostgreSQL advisory lock before serving. Validate the complete schema without changing it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-db-schema.ps1
```

Open pgAdmin using generated local credentials in `.env`, then register host `db`, port `5432`, and the database/user named there. Never paste or commit the password. See [the pgAdmin guide](docs/DATABASE_GUI.md).

## Demo users and real API flow

Demo accounts are opt-in, development-only, idempotent, and use the normal password hasher. Random passwords live only in ignored `.env`.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 seed
powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 demo
```

The demo campaign authenticates two users, uploads a harmless fixture, compresses/downloads/decompresses it, verifies SHA-256, confirms anonymous denial and owner isolation, then exercises sharing and redemption. Its sanitized report contains no secrets. This is API-level evidence, not a claim that every GUI was clicked.

## Tests and analysis

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 test
powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 benchmark
powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 notebook
```

The campaign covers FastAPI, the Python engine, Rust, Angular, Next.js, both Flutter clients, and .NET. See [current results](reports/TEST_REPORT.md). Benchmark outputs are under `reports/benchmark/`; the executed, French presentation notebook is [XAI_Compress_Model_Analysis.ipynb](notebooks/XAI_Compress_Model_Analysis.ipynb) and marks unavailable evidence rather than inventing it.

## Releases and downloads

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 release
```

The builder writes `releases/manifest.json` with size, SHA-256, architecture, minimum requirements, build status, and signing status. `/downloads` reads this allow-listed manifest and streams only files that exist under `releases/`. Binaries are Git-ignored; metadata remains reviewable.

Unsigned or debug artifacts are explicitly test-only. Production Android needs legitimate signing material through the existing secure environment-variable mechanism. Windows remains unsigned unless a legitimate certificate workflow is supplied.

## Troubleshooting

- If scripts are disabled, use the explicit `powershell -ExecutionPolicy Bypass -File ...` form; it changes no machine-wide policy.
- For a port conflict, edit only the related `.env` port and keep `PUBLIC_API_URL`/`CORS_ORIGINS` aligned.
- Inspect with `scripts/health-check.ps1` and `docker compose logs --tail 200 <service>`.
- ClamAV's first start can take several minutes while signatures initialize.
- Physical Android startup, signed releases, clean-PC installation, and live Render recovery still require their actual device, credentials, or environment.
- Remove only approved generated outputs with `powershell -ExecutionPolicy Bypass -File .\scripts\xai.ps1 clean`.
