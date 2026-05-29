# The Synthetic Firm Postgres Migrations

Postgres migrations are internal developer/deployment operations. They are not a
public product interface.

## Commands

```bash
synthetic-firm db-status
synthetic-firm db-migrate --dry-run
synthetic-firm db-migrate --apply
synthetic-firm db-verify
```

`--dry-run` is the default. `--apply` also requires:

```text
TSF_DB_MIGRATION_DRY_RUN=false
```

## Migration Policy

Migrations are intentionally non-destructive:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- schema version record
- no `DROP TABLE`
- no destructive `ALTER TABLE`
- no `TRUNCATE`
- no `DELETE FROM`

JSON payload columns currently use text-compatible storage to keep the selected
backend adapter compatible with SQLite-origin repository methods. This can be
upgraded to JSONB-specific casts in a later hardening phase after live Render
Postgres verification.

## Verification

`db-verify` checks connectivity, required tables, and schema version without
printing connection details. `verify-audit-log` must pass after migrations and
after scheduler checkpoints.
