# The Synthetic Firm Runtime

The Synthetic Firm is an autonomous AI agency OS with five internal agents: Atlas, Scout, Forge, Pulse, and Sentinel.

Phase 3 adds persistent local state and runtime controls without enabling live external-effect automation.

## Persistent state

The default SQLite store is:

```text
TSF_HOME/state/synthetic-firm.sqlite3
```

If `TSF_HOME` is not set, TSF uses:

```text
~/.synthetic-firm/state/synthetic-firm.sqlite3
```

The store initializes idempotently. It creates `TSF_HOME`, the `state/` directory, schema tables, and a runtime status row. Tests should set a temporary `TSF_HOME` so state is deterministic and disposable.

Persisted entities:

- tasks
- agent messages
- approval requests
- approval decisions
- budget usage records
- audit log entries
- worker proposals
- self-improvement proposals
- daily reports

Secrets must not be stored in the database. Runtime API keys, approval signing secrets, provider keys, tokens, and credentials stay in environment variables only.

## Runtime status

The company runtime has three states:

- `active`: normal safe internal work is allowed.
- `paused`: only status reads and report generation are allowed.
- `killed`: all agent work is refused except status and audit export.

Only a human/control actor can pause, resume, or kill the runtime in Phase 3 simulation. Kill is intentionally not reversible by agents.

## Safe CLI

Useful runtime commands:

```bash
synthetic-firm init-store
synthetic-firm store-status
synthetic-firm runtime-status
synthetic-firm pause
synthetic-firm resume
synthetic-firm kill
```

These commands use `TSF_HOME` and do not print secrets.

## Intentionally disabled

Phase 3 does not add live email, social posting, investor outreach, unreviewed Vercel deployment, Stripe, domain purchasing, production deployment, active worker creation, or unbounded autonomous self-upgrade execution. Repo edits, commits, pushes, Vercel preview changes, and Render changes may be handled by the coding-agent/operator path when Forge creates implementation work and the result is tested, audited, and budget-gated.

## Recommended Phase 4

Add a real approval inbox and execution queue that can consume signed approvals, while keeping every external-effect adapter disabled by default and covered by integration tests with network calls mocked.
