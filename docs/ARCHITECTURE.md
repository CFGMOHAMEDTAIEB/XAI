# Architecture

Each module runs independently and integrates through explicit contracts.

1. Mobile and desktop use Flutter/Dart.
2. Web portal uses Angular/TypeScript.
3. FastAPI provides the MVP REST API.
4. Keycloak is the target identity provider. The sample API also includes local auth to enable standalone development.
5. PostgreSQL stores users, file metadata, shares, and audits.
6. Redis is for rate limiting, short-lived state, token revocation, and job progress.
7. MinIO stores encrypted objects. It is not wired to the sample API yet.
8. The PyTorch/Rust engine performs local or worker-based compression.
9. Protobuf defines future internal service contracts.

## Vertical flow 1: authentication

Register → enroll TOTP → confirm code → login with password + TOTP → receive token.

## Vertical flow 2: sharing

Record compressed file metadata → create recipient-bound one-time share code → deliver code externally → recipient authenticates → redeems code → sees file metadata → storage integration supplies encrypted download.

## Vertical flow 3: local desktop compression

Select file → Flutter launches local Python CLI → engine creates `.xaic` → Flutter presents metrics → API stores history metadata if user chooses cloud sync.
