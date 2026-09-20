# Real local two-user E2E acceptance

Source: `reports/demo_e2e_report.json`, `reports/demo_e2e_report.md`, and the current E2E runner contract. This is API-level local integration evidence, not GUI automation or production evidence.

| STEP | EXPECTED | ACTUAL | RESULT |
| --- | --- | --- | --- |
| USER A authentication | Valid demo account obtains an authenticated session | Authentication completed | PASS |
| USER B authentication | Second distinct demo account obtains an authenticated session | Authentication completed | PASS |
| Upload | Harmless fixture accepted | 13,056-byte fixture accepted | PASS |
| Mandatory scanning | Upload passes required fail-closed scanner pipeline before publication | Compression job completed through the mandatory pipeline | PASS |
| Compression | Real Hybrid V3 artifact produced | 134-byte `hybrid-v3-top3` artifact | PASS |
| Owner download | USER A downloads the private artifact | Download completed | PASS |
| Decompression | Artifact restores original bytes | Restored bytes equal original bytes | PASS |
| Integrity | SHA256(original) == SHA256(restored) | Digests are equal | PASS |
| Anonymous denial | Anonymous private download rejected | HTTP 401 expected and observed | PASS |
| Unrelated-user denial | USER B cannot directly access USER A's private file | HTTP 404 expected and observed | PASS |
| Share creation | USER A creates a recipient-bound share | Share created | PASS |
| Share redemption | USER B redeems the share | Redeemed file digest matches original | PASS |
| Authorized shared download | USER B downloads the shared artifact | Downloaded bytes equal owner's artifact | PASS |
| Recipient round trip | USER B decompresses shared artifact | Restored bytes equal original | PASS |

Required invariant: `SHA256(original) == SHA256(decompressed)` — **PASS**.
