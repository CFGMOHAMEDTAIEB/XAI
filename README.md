# XAI-Compress Platform Monorepo

A modular MVP for a cross-platform lossless-compression ecosystem.

## Included modules

- `apps/desktop_flutter`: desktop compression client skeleton.
- `apps/mobile_authenticator_flutter`: TOTP authenticator skeleton with 30-second codes.
- `apps/web_angular`: authenticated cloud portal skeleton.
- `services/api_fastapi`: runnable REST API for accounts, TOTP enrollment, file metadata, one-time sharing codes, history, and health.
- `engines/ai_compression`: the previously validated PyTorch + Rust lossless compression engine.
- `analytics`: benchmark, visualization, and reporting suite.
- `packages/protobuf_contracts`: versioned contracts for compression jobs.
- `infrastructure`: Docker Compose, Keycloak realm, Nginx, PostgreSQL, Redis, MinIO, ClamAV, Grafana, and ELK placeholders.

## Important scope

This package is a **working foundation/MVP**, not a production-ready bank-grade platform. The FastAPI module and engine are executable. Flutter and Angular include application code and project manifests, but platform-generated folders should be created with the official CLIs before final builds. ClamAV, Vault, Kafka, Kubernetes, C++, Qt, Spring, Symfony, .NET, RAG, and enterprise connectors are represented as documented extension points rather than falsely claimed as finished implementations.

## Quick start: backend

```bash
cd services/api_fastapi
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs`.

## Quick start: Docker infrastructure

```bash
docker compose up -d postgres redis minio keycloak
```

## Default local Keycloak admin

Change these before any deployment:

```text
username: admin
password: change-me-now
```

## Security notes

- TOTP follows the 30-second model and secrets must be stored in platform secure storage on mobile.
- Share codes are hashed server-side, expire, support download limits, and are rate-limited in production through Redis/API gateway.
- Passwords are hashed. No plaintext password is stored.
- File contents are not stored by the sample API. Integrate MinIO and AES-GCM before cloud file transfer.
- Never send sensitive user files to external LLM APIs without explicit consent.

Read `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and `docs/SECURITY.md`.
