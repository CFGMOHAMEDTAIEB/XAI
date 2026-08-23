# Security Checklist

- [ ] Use Keycloak OIDC and role-based authorization.
- [ ] Disable demo data outside Development.
- [ ] Store client secrets in Vault or protected deployment secrets.
- [ ] Require MFA and step-up authentication for destructive operations.
- [ ] Restrict quarantine release and download permissions.
- [ ] Add anti-CSRF and strict Content Security Policy.
- [ ] Add rate limiting and account/session revocation.
- [ ] Redact sensitive values from logs and UI.
- [ ] Make audit logs append-only and integrity protected.
- [ ] Add security headers at Nginx/API gateway.
- [ ] Add SonarQube, Trivy and dependency scans.
- [ ] Run authorization tests and an external security assessment.
