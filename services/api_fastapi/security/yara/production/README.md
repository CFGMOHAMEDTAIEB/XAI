# Defensive production rules

Container path: `/app/security/yara/production`. The backend Dockerfile copies
this directory into the image. Rebuild/redeploy the backend after rule changes;
compiled rules are cached within each running backend process.

This initial, project-authored baseline contains **two detection rules and one
private helper** in `php_request_execution.yar`:

- `XAI_PHP_Direct_Request_Eval`: PHP source evaluating raw HTTP input, directly
  or through base64 decoding.
- `XAI_PHP_Direct_Request_Command`: PHP source passing raw HTTP input directly
  to an OS command function.
- `XAI_PHP_Source` (private): anchors a PHP opening tag at offset zero or after
  a UTF-8 BOM. It never reports a detection by itself.

Review scope: deliberately narrow source signatures, no synthetic markers,
no downloaded third-party rules, no broad entropy/string heuristics. Clean
text/JSON/CSV, benign PHP, project sources/model and XAIC-prefixed samples are
covered by real YARA matching tests. Inert positive examples are scanned as
bytes only, never executed. These are defensive behavior detections, not a claim
of comprehensive malware-family coverage or external security approval.

Limitations: comments/string literals in executable PHP containing these exact
patterns can match; obfuscation, alternate encodings, non-PHP threats and PHP
with preceding content may evade these rules. ClamAV remains independently
required. Extend the rules only after reviewing detection and false-positive
fixtures. Do not permit unscanned files because these rules are narrow.

Development rules remain in `../test`; production never loads them. Empty,
unreadable, invalid or duplicate rulesets still fail closed. Scanner health is
operational only when both the configured ClamAV daemon and YARA are available.
Local rule tests do not prove that production has deployed this ruleset.
