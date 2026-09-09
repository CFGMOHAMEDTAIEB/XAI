-- Additive PostgreSQL migration. Existing active User TOTP factors are unchanged.
-- Run before deploying the new API. Safe to run again.
CREATE TABLE IF NOT EXISTS totp_enrollments (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    enrollment_id VARCHAR(32) NOT NULL UNIQUE,
    secret VARCHAR(128),
    code_hash VARCHAR(64),
    expires_at TIMESTAMP NOT NULL,
    code_expires_at TIMESTAMP NOT NULL,
    disclosed BOOLEAN NOT NULL,
    attempts INTEGER NOT NULL,
    totp_attempts INTEGER NOT NULL,
    last_sent_at TIMESTAMP NOT NULL,
    send_window_at TIMESTAMP NOT NULL,
    send_count INTEGER NOT NULL
);
