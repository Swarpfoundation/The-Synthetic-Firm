# The Synthetic Firm Postgres Runtime Adapter

The Postgres runtime adapter is selected only when `TSF_STORE_BACKEND=postgres`.
SQLite remains the default local/dev backend.

## Optional Dependency

Install Postgres support explicitly:

```bash
pip install -e ".[postgres]"
```

The optional extra installs `psycopg[binary]`. A normal `pip install -e .`
continues to work without Postgres dependencies.

## Selection Rules

- unset or `TSF_STORE_BACKEND=sqlite`: use local SQLite under `TSF_HOME`
- `TSF_STORE_BACKEND=postgres`: require `DATABASE_URL` or `TSF_DATABASE_URL`
- missing URL fails closed
- missing `psycopg` fails closed
- database URLs are redacted from output, audit, public export, and logs

## Repository Coverage

The selected backend facade now covers the core runtime/export/scheduler paths:

- runtime status
- tasks and task events
- agent messages
- approval requests and decisions
- budget usage
- audit append and verification
- daily reports
- HumanTasks
- FounderMessages
- workdays and daily plans
- scheduler runs and locks
- notification queue
- deployment records and credential snapshots
- public Control Room export/API snapshot paths

Code paths that call `Store()` with no explicit SQLite path use the selected
backend. Passing an explicit SQLite path remains a local/dev escape hatch.

## Safety

The adapter uses parameterized SQL translation for the existing repository
surface. It does not run destructive commands, does not store database URLs, and
redacts database connection errors.
