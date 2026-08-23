# Integration

The public website does not process private files and should not receive user credentials.

Environment variables:

```text
NEXT_PUBLIC_SITE_URL=https://www.example.com
NEXT_PUBLIC_APP_URL=https://app.example.com
```

Nginx/API Gateway routing target:

```text
/           -> Next.js public website
/app        -> Angular portal or separate app subdomain
/api        -> FastAPI
/auth       -> Keycloak
/status-api -> read-only sanitized health service
```

Do not expose internal Grafana, ELK, MinIO, Vault or administrative endpoints through the public site.
