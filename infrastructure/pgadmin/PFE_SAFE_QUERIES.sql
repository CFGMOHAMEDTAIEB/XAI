-- XAI-Compress PFE evidence queries.
-- These projections intentionally exclude credentials, hashes, secrets,
-- verification/reset codes, recovery codes, and bearer/share material.

-- Safe account overview.
SELECT
    id,
    email,
    display_name,
    full_name,
    role,
    account_status,
    email_verified,
    phone_verified,
    totp_enabled,
    created_at,
    updated_at
FROM public.users
ORDER BY created_at DESC;

-- Safe compression-file overview. Filesystem paths and SHA-256 values are
-- omitted because they are unnecessary for account/database screenshots.
SELECT
    id,
    owner_id,
    name,
    original_size,
    compressed_size,
    codec,
    integrity_verified,
    status,
    created_at
FROM public.files
ORDER BY created_at DESC;

-- Safe authentication-event overview. The free-form details column is
-- intentionally omitted because it may contain request context.
SELECT
    id,
    user_id,
    device_id,
    event_type,
    result,
    application,
    created_at
FROM public.auth_events
ORDER BY created_at DESC;

-- Safe audit-event overview. The free-form details column is intentionally
-- omitted; action/resource/result are sufficient for visual evidence.
SELECT
    id,
    user_id,
    action,
    resource,
    result,
    created_at,
    updated_at
FROM public.audit_events
ORDER BY created_at DESC;
