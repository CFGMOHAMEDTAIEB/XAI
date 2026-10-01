# Local XAI-Compress demo E2E

Result: **PASS**

This is API-level E2E through the same backend contract used by the clients; no GUI automation is claimed.

## Checks

- health: PASS
- authentication: PASS
- round_trip: PASS
- anonymous_and_owner_boundaries: PASS
- share_email_captured_by_mailpit: PASS
- share_recipient_access: PASS
- invalid_unauthorized_and_exhausted: PASS
- recipient_round_trip: PASS

## Compression evidence

- original_size: `13056`
- compressed_size: `134`
- codec: `hybrid-v3-top3`
- route: `None`
- compression_seconds: `5.671734900000047`
- original_sha256: `6ee898a881139f963f2f0053e76d8ccbade632baf9fe7fa8ab145899e0f8c6ed`
- decompressed_sha256: `6ee898a881139f963f2f0053e76d8ccbade632baf9fe7fa8ab145899e0f8c6ed`
- sha256_match: `True`
