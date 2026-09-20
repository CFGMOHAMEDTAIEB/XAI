# PFE evidence summary

This file separates evidence classes. Local results are not transformed into production claims.

## VERIFIED BY CURRENT AUTOMATED TESTS

- FastAPI: 166/166 current tests passed.
- XAI-Compress engine: 206 passed and 4 skipped in 94.96 seconds using a fresh OS temporary directory.
- The earlier 88 setup errors were a stale Windows ACL test-harness issue, not engine assertion failures.
- Rust: 2/2 tests passed.
- Angular: 24/24 tests passed.
- Next.js: 8/8 unit tests plus lint, typecheck, and build passed.
- Flutter Desktop: 37 passed, 2 skipped; Flutter Mobile: 22 passed.
- .NET Admin: two integration scenarios passed.
- Automated backend coverage includes authentication/MFA, fail-closed scanner behavior, migrations, ownership, sharing, and error sanitization.

## VERIFIED BY REAL LOCAL E2E

- Two distinct demo users authenticated through FastAPI.
- A harmless upload traversed mandatory security scanning and real Hybrid V3 compression.
- Decompression restored the exact original bytes; SHA-256 values match.
- USER A shared to USER B; USER B redeemed, downloaded, and decompressed the artifact.
- Anonymous and unrelated-user private access were denied.
- PostgreSQL persistence, pgAdmin, Mailpit, FastAPI, Angular, Next.js, and .NET Admin were exercised in the current local campaign.
- A true master-command cold start completed from separate fresh PowerShell processes without manual repair and retained the existing Docker volumes.
- PostgreSQL was healthy with 6 migrations recorded and 0 pending; pgAdmin reached PostgreSQL through the Docker network.
- All four real HTTP release downloads returned 200 and matched the manifest byte count and SHA-256 digest.

## VERIFIED BY BENCHMARK

- Four methods, 140 files each, 560 rows total, 368,446,658 original bytes.
- Every recorded round trip passes SHA-256 integrity.
- Brotli-11 produced the best aggregate compressed size.
- Hybrid V3 Top-3 recorded 71.72668457297502× Brotli-11's aggregate compression throughput (71.73× rounded).
- Brotli-11 also recorded substantially higher aggregate decompression throughput.
- The supported conclusion is an operational size/encoding-speed trade-off, not universal AI superiority.

## VERIFIED BUILD

- Current Next.js production build passed.
- A fresh Flutter Windows release and the four manifest-listed local packages were produced earlier in the current campaign.
- All release files match manifest size and SHA-256; all are explicitly unsigned/test distribution.

## CONFIGURED

- Architecture: Next.js public site, Angular portal, FastAPI, PostgreSQL, ClamAV/YARA, Mailpit, pgAdmin, .NET Admin, Flutter Desktop, Flutter Authenticator, Python/Rust compression engine.
- Versioned checksummed migrations, persistent Docker volumes, demo seeding, master command dispatch, local download routes, and deployment configuration are present.
- Render/Vercel or other deployment settings are configuration evidence only.

## NOT VERIFIED IN PRODUCTION

- Production uptime, production database migration, external email delivery, scanner signature freshness, signed binaries, physical Android behavior, and clean-PC Windows installation.
- Production URLs/configuration do not prove production functionality.
- The local two-user E2E is not a production or GUI automation claim.

## KNOWN LIMITATIONS

- Next.js has an unresolved direct critical npm advisory; Angular has unresolved high findings.
- Python vulnerability audit is not configured; .NET live advisory retrieval emitted NU1900.
- Research benchmark conclusions are limited by corpus composition, host conditions, and asymmetric repetition policy.
- Releases are unsigned/test-only.
