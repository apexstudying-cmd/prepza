-- Prepza migration ledger.
-- Historical migrations remain hand-managed; this table gives future migrations
-- an explicit applied-file record without pretending old deployments were tracked.
CREATE TABLE IF NOT EXISTS schema_migration (
    migration_name VARCHAR(255) PRIMARY KEY,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
