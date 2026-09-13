-- Additive alignment for model changes not covered by migrations 001-003.
-- This migration never drops tables, columns, constraints, indexes, or row data.

-- User.role is non-null in the ORM and uses a Python-side default of 'user'.
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32);
UPDATE users SET role = 'user' WHERE role IS NULL;
ALTER TABLE users ALTER COLUMN role SET NOT NULL;
ALTER TABLE users ALTER COLUMN role DROP DEFAULT;

-- File fields added after the original database baseline.
ALTER TABLE files ADD COLUMN IF NOT EXISTS source_path VARCHAR(1024);
ALTER TABLE files ADD COLUMN IF NOT EXISTS artifact_path VARCHAR(1024);
ALTER TABLE files ADD COLUMN IF NOT EXISTS integrity_verified BOOLEAN;
UPDATE files SET integrity_verified = FALSE WHERE integrity_verified IS NULL;
ALTER TABLE files ALTER COLUMN integrity_verified SET NOT NULL;
ALTER TABLE files ALTER COLUMN integrity_verified DROP DEFAULT;
ALTER TABLE files ADD COLUMN IF NOT EXISTS status VARCHAR(32);
UPDATE files SET status = 'completed' WHERE status IS NULL;
ALTER TABLE files ALTER COLUMN status SET NOT NULL;
ALTER TABLE files ALTER COLUMN status DROP DEFAULT;

-- AuditEvent.updated_at is DateTime, non-null, with Python-side insert/update
-- callbacks. Backfill existing rows from created_at before enforcing NOT NULL.
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
UPDATE audit_events
SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE updated_at IS NULL;
ALTER TABLE audit_events ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE audit_events ALTER COLUMN updated_at DROP DEFAULT;

-- Refresh tokens were added to the ORM without a corresponding SQL migration.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_refresh_tokens_token_hash ON refresh_tokens(token_hash);
