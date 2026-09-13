-- Additive professional account and verification storage. Run after 001 and 002.
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(16);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status VARCHAR(32) NOT NULL DEFAULT 'PENDING_VERIFICATION';
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Preserve existing accounts and operator behavior during the additive rollout.
UPDATE users SET email_verified=TRUE, account_status='ACTIVE', full_name=COALESCE(NULLIF(display_name,''), '')
WHERE account_status='PENDING_VERIFICATION' AND created_at < CURRENT_TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_number ON users(phone_number) WHERE phone_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_users_account_status ON users(account_status);

CREATE TABLE IF NOT EXISTS account_verification_challenges (
 id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), channel VARCHAR(16) NOT NULL,
 purpose VARCHAR(40) NOT NULL, code_hash VARCHAR(64) NOT NULL, expires_at TIMESTAMP NOT NULL,
 attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5,
 used_at TIMESTAMP, verified_at TIMESTAMP, reset_token_hash VARCHAR(64) UNIQUE,
 reset_token_expires_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT ck_verification_channel CHECK (channel IN ('email','phone')),
 CONSTRAINT ck_verification_purpose CHECK (purpose IN ('ACCOUNT_EMAIL_VERIFY','ACCOUNT_PHONE_VERIFY','PASSWORD_RESET'))
);
CREATE INDEX IF NOT EXISTS ix_account_verification_user ON account_verification_challenges(user_id);
CREATE INDEX IF NOT EXISTS ix_account_verification_purpose ON account_verification_challenges(purpose);
CREATE INDEX IF NOT EXISTS ix_account_verification_expires ON account_verification_challenges(expires_at);
