# XAI-Compress Admin Console (.NET)

Blazor Server administrative and security console for the XAI-Compress platform.

## Included screens

- Security dashboard
- User and role overview
- Compression jobs
- Security incidents
- Quarantined files
- Audit logs
- Service health

## Integration

The console is designed to connect to:

- FastAPI at `http://localhost:8000`
- Keycloak at `http://localhost:8080/realms/xai-compress`
- PostgreSQL, Redis, MinIO, ClamAV and the compression engine through backend APIs

For immediate UI development, demo data is enabled. The health page performs a real check against FastAPI.

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

## Production backlog

- Replace demo providers with dedicated admin REST endpoints
- Enforce Keycloak roles: `ADMIN`, `SUPER_ADMIN`, `SECURITY_ANALYST`
- Add incident workflow and analyst comments
- Add quarantine release/delete actions with step-up authentication
- Add user suspend/reactivate and session revocation
- Add paginated audit search and export
- Add Grafana links and ELK queries
- Add CSRF, CSP, secure headers and reverse-proxy hardening
- Add integration and authorization tests
- Add signed release images and vulnerability scanning
