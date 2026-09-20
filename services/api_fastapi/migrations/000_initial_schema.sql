-- Baseline tables that predate the numbered additive migrations.
-- Every statement is idempotent so existing databases are left intact.
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    totp_secret VARCHAR(128),
    totp_enabled BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(512) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    original_size INTEGER NOT NULL,
    compressed_size INTEGER NOT NULL,
    codec VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_files_owner_id ON files(owner_id);

CREATE TABLE IF NOT EXISTS share_codes (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id),
    sender_id INTEGER NOT NULL REFERENCES users(id),
    recipient_email VARCHAR(320) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    max_downloads INTEGER NOT NULL,
    download_count INTEGER NOT NULL,
    anonymous_sender BOOLEAN NOT NULL,
    revoked BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_share_codes_file_id ON share_codes(file_id);
CREATE INDEX IF NOT EXISTS ix_share_codes_recipient_email ON share_codes(recipient_email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_share_codes_code_hash ON share_codes(code_hash);

CREATE TABLE IF NOT EXISTS audit_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR(120) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    result VARCHAR(32) NOT NULL,
    details TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_events_user_id ON audit_events(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_action ON audit_events(action);
