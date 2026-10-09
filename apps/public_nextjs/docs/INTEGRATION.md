# Integration

The public website does not process private files and should not receive user credentials.

Environment variables:

```text
NEXT_PUBLIC_SITE_URL=https://www.example.com
NEXT_PUBLIC_APP_URL=https://app.example.com
```

For the local Docker stack, `Open portal` points to `http://localhost:4200`.
Next.js embeds public URLs during compilation, so Compose supplies
`NEXT_PUBLIC_SITE_URL` and `NEXT_PUBLIC_APP_URL` as Docker build arguments.
After changing either URL, rebuild the public site with
`docker compose up -d --build --no-deps nextjs`; runtime environment changes
alone do not update links in generated pages.

Local account verification emails are captured by Mailpit at
`http://localhost:18026` with the current local port configuration. Open the
latest verification email after requesting a new code in the portal. Mailpit
does not deliver messages to external inboxes.

Nginx/API Gateway routing target:

```text
/           -> Next.js public website
/app        -> Angular portal or separate app subdomain
/api        -> FastAPI
/auth       -> Keycloak
/status-api -> read-only sanitized health service
```

Do not expose internal Grafana, ELK, MinIO, Vault or administrative endpoints through the public site.
