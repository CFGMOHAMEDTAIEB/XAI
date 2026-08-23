# Security baseline

Implemented in the MVP:
- password hashing
- short-lived JWTs
- TOTP enrollment and verification
- cryptographically random share codes
- server-side share-code hashing
- expiry and download limits
- recipient binding
- audit events
- engine SHA-256 and corrupted-container rejection

Required before production:
- use Keycloak exclusively for credentials and MFA
- Argon2id policy and breached-password screening
- TLS everywhere and certificate pinning where appropriate
- Redis-backed rate limits and distributed locks
- AES-256-GCM envelope encryption with Vault-managed keys
- MinIO private buckets and short-lived signed URLs
- ClamAV and YARA scan orchestration
- quarantine and sandbox policy
- refresh-token rotation and device revocation
- CSRF protection for browser flows
- secure email provider and anti-enumeration responses
- privacy, retention, deletion, and incident-response policies
- external penetration test
