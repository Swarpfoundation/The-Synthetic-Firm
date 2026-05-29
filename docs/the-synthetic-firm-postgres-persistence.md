# The Synthetic Firm Postgres Persistence

The Synthetic Firm uses SQLite by default for local development and internal smoke tests. Deployed Render API and scheduler services need shared durable state, so production-style operation should use Postgres through an environment-provided database URL.

## Backends

- `TSF_STORE_BACKEND=sqlite` or unset: local/dev SQLite under `TSF_HOME/state/synthetic-firm.sqlite3`.
- `TSF_STORE_BACKEND=postgres`: requires `DATABASE_URL` or `TSF_DATABASE_URL`.

Database URLs are secret-bearing values. They must be configured in Render environment variables only and must not be pasted into Telegram, docs, public reports, or audit metadata.

## Internal Checks

These commands are internal developer/smoke utilities, not product UX:

```bash
synthetic-firm db-status
synthetic-firm db-migrate --dry-run
synthetic-firm db-migrate --apply
synthetic-firm db-verify
synthetic-firm db-smoke
synthetic-firm db-redaction-smoke
```

`db-migrate --dry-run` is the default posture. Applying Postgres migrations also requires `TSF_DB_MIGRATION_DRY_RUN=false`.

## Migration Policy

Postgres migrations are idempotent and non-destructive:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- no `DROP TABLE`
- no destructive `ALTER`
- no `TRUNCATE`
- no `DELETE FROM`

JSON payload columns currently use text-compatible storage for adapter
compatibility. Audit sequence ordering and hash-chain fields are preserved so
verification can remain compatible with persisted TSF state.

## Current Boundary

SQLite remains the default repository backend. `TSF_STORE_BACKEND=postgres`
selects the Postgres adapter for the runtime/export/scheduler paths once the
optional Postgres extra, database URL, and migrations are configured.
