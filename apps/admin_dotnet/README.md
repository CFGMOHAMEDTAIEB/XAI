# XAICD Admin Console (.NET)

Blazor Server administrative and security console for the XAICD platform.

## Included screens

- Live dashboard backed by protected FastAPI statistics
- Read-only user and role overview
- Stored files and compression jobs
- Audit and authentication/security activity
- Authenticator-device and recovery-code summaries
- Scanner, email-configuration and system-readiness views
- Explicit unavailable/not-implemented states for incident and quarantine workflows

## Integration

The console connects to:

- FastAPI at `http://localhost:8000`
- PostgreSQL, ClamAV, email delivery and the compression engine through protected backend APIs

Demo fallback is disabled in the project Compose stack. The normal sign-in form
authenticates against FastAPI and retains a session only after the protected
`GET /admin/stats` role check succeeds.

Administrator accounts are provisioned explicitly with the backend's
environment-gated `app.scripts.create_admin` command. The command uses the same
password hasher as normal authentication, refuses silent promotion of existing
users, and never prints credentials. Keep bootstrap values in an ignored local
environment file; do not add them to Compose or source control.

## Required software

Install the .NET 8 SDK:

```bat
dotnet --version
```

## Run

```bat
cd apps\admin_dotnet
dotnet restore
dotnet run
```

Open:

```text
http://localhost:5050
```

Health endpoint:

```text
http://localhost:5050/health
```

## Enable Keycloak OIDC

Use user secrets or environment variables. Do not commit a client secret.

```bat
dotnet user-secrets init
dotnet user-secrets set "Authentication:OidcEnabled" "true"
dotnet user-secrets set "Authentication:Authority" "http://localhost:8080/realms/xai-compress"
dotnet user-secrets set "Authentication:ClientId" "xai-admin"
dotnet user-secrets set "Authentication:ClientSecret" "YOUR-SECRET"
```

Create a confidential Keycloak client named `xai-admin` with a redirect URI similar to:

```text
http://localhost:5050/signin-oidc
```

## Integrate into the monorepo

Extract or copy this folder to:

```text
XAI-COMPRESS-PLATFORM\apps\admin_dotnet
```

Rename the existing placeholder first.

## Not implemented

- Incident-management workflow and analyst comments
- Quarantine listing and release/delete actions
- User suspension, role editing and session revocation
- Paginated audit export
- Historical uptime and per-service latency

These capabilities are not simulated by the UI. Existing pages are read-only
and label unavailable data explicitly.
