# File security gate

Uploads are hashed and scanned with ClamAV and YARA before compression. Restored
bytes are hashed and scanned before release. The engine algorithms are unchanged.
Only internally staged files within configured storage can be scanned; no scan
endpoint accepts filesystem paths.

ClamAV uses the official image and INSTREAM protocol over a dedicated Docker
network with no published daemon ports. FreshClam updates persistent signatures.
The image enables AlertExceedsMax so exceeded engine limits cause rejection.
Compose waits for the daemon's responsive health probe before starting backend.

Configuration: CLAMAV_HOST, CLAMAV_PORT, SECURITY_SCAN_REQUIRED (default true),
SECURITY_SCAN_TIMEOUT (seconds), and YARA_RULES_PATH (administrator configuration).
Standalone backend installations also need requirements-security.txt. YARA rules
are compiled lazily and cached; restart backend after modifying the rule set.

HTTP 422 means policy rejection. HTTP 503 means verification could not complete.
No unscanned bytes are allowed even if SECURITY_SCAN_REQUIRED is false; that flag
is deployment metadata, not a bypass. Public status exposes availability only.
Internal structured logs record stages, hashes, and matches without input paths.
Authenticated admin stats expose scanner component health.

The bundled YARA rule is only a harmless synthetic integration-test rule, not a
general malware rule set. No real malware samples are included.

Run scripts/test_security_pipeline.py with the repository's engine-capable Python
for the real Docker test. It temporarily stops only ClamAV, tests rejection, then
restarts it in finally. Evidence is saved under scratch/security-validation.

References:
- https://docs.clamav.net/manual/Usage/ClamdProtocol.html
- https://docs.clamav.net/manual/Installing/Docker.html
- https://yara.readthedocs.io/en/stable/yarapython.html
