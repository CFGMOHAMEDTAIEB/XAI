# Production rule provisioning required

No production detection rules have been approved or supplied. This directory is
intentionally empty of .yar/.yara files. Production scanning reports unavailable
and protected operations fail closed until an administrator provisions a reviewed,
nonempty rule set. Synthetic rules live only in ../test and are rejected in
production. No community rules are downloaded automatically. Restart backend after
rule changes. Duplicate rule names, invalid syntax and empty rule sets are errors.
