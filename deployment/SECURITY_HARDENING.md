# Production prerequisites and operational bounds

Production deployment remains blocked until a real backend HTTPS URL, the Angular
portal URL, PostgreSQL, durable storage, private scanner hosting and a reviewed
production YARA rule set are supplied. The only supplied public frontend origin is
https://xai-usg.vercel.app. Add the exact portal origin once it exists. Development
Compose retains separate localhost origins and test rules.

The Render API environment template requires scanning and a private `clamav` DNS
service; it does not provision that service. Supply private service discovery on
the chosen host, permit backend-to-daemon traffic only, and never publish 3310.
ClamAV needs persistent signatures, outbound signature-update access and sufficient
memory for initialization/reload. Compose waits on PONG health; a backend started
independently still rejects protected requests while scanners initialize.

Production YARA rules are administrator-provisioned in security/yara/production.
The shipped directory deliberately has no rules and therefore fails closed. Test
rules are separate and explicitly rejected in production. Syntax errors, duplicate
names and empty rule sets are errors; restart backend after approved rule changes.

The backend runs as UID/GID 10001. Provision /data with that ownership. Existing
root-owned Docker volumes require an operator migration of ownership before the
non-root image starts. Runtime models/configs stay read-only in /opt/xai-compress.
New files use umask 077. Source and verification files are deleted after a successful
compression; only its artifact is retained. Failed request directories are removed.
Cleanup failures emit a path-free error; filesystem failure may leave private files
that an operator must remove after investigating. Do not automatically delete
arbitrary storage paths or active jobs.

Default limits: 1 GiB upload, 1 GiB restored output, 2 simultaneous heavy requests
per Python process, 30s upload inactivity, 300s total body receipt, 60s scanner socket
and YARA scan timeout. Streaming byte limits apply before multipart parsing, even
without Content-Length. Admission holds until the response finishes. A pessimistic
disk reserve covers concurrent multipart spooling, source/artifact/output plus a
1 GiB free-space floor. Provision at least 10 GiB free per single backend process;
enforce an external filesystem quota and artifact-retention policy as stored
artifacts accumulate. Multipart spool and /data free space are both checked.
ClamAV scan limits may reject files below the API limit; exceeded limits are never
silently treated as clean. XAIC max_output_size is enforced for both verification
and explicit decompression. No recursive archive extraction is added.

There is no distributed rate limiter or background worker system. Run one backend
worker with this local admission control, and enforce per-account/IP request rates,
connection/body limits and a 600s upstream response timeout at the production edge.
A response timeout cannot safely cancel synchronous engine work; its admitted slot
must remain held until work ends. A forcibly cancellable processing deadline would
require an isolated worker lifecycle and is deferred. Keep scanner and backend
memory/CPU/container quotas appropriate to measured workload. Do not increase
workers without budgeting the aggregate per-process limits.

Sanitized security outcomes use the existing AuditEvent table, avoiding migrations.
Logs add request ID, account ID, hash, duration and timestamp. Public responses do
not contain scanner hostnames, paths, rule names or exceptions. Scanner details
remain internal. Artifact access and history are owner-scoped; diagnostics require
admin authorization.

Brevo still needs a verified sender and configured credentials for actual delivery.
The existing adapter rejects .xaic for its HTTPS attachment allowlist; provider
acceptance of the required exact artifact remains a separate blocker. Do not send
test emails or build/deploy mobile/desktop production clients until the real backend
HTTPS URL and required infrastructure are ready.
