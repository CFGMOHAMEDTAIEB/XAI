-- Existing shares have no trustworthy creation timestamp; retain NULL for them.
ALTER TABLE share_codes ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NULL;
