-- Repair the AuditEvent invariant for databases whose migration ledger records
-- 004 but whose audit_events table predates that schema alignment. This is
-- additive, idempotent, and preserves every existing audit row.
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
UPDATE audit_events
SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE updated_at IS NULL;
ALTER TABLE audit_events ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE audit_events ALTER COLUMN updated_at DROP DEFAULT;
