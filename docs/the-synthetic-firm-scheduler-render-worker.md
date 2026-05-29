# The Synthetic Firm Scheduler Render Worker

The Render scheduler should run checkpoint-once jobs only. It must not become an uncontrolled daemon.

## Checkpoint Model

Use:

```bash
synthetic-firm scheduler-checkpoint-once
```

Do not run `scheduler-loop` on Render production services in this phase. The loop command is for bounded local development only.

## Readiness

Run:

```bash
synthetic-firm scheduler-render-readiness
synthetic-firm scheduler-checkpoint-smoke --dry-run
```

The readiness check verifies whether the runtime is configured for shared deployed state. If Postgres or scheduler configuration is missing, TSF creates safe HumanTasks for the founder:

- create Render Postgres database
- set `TSF_STORE_BACKEND=postgres`
- set `DATABASE_URL` on API and scheduler services
- create a Render cron job or worker for `scheduler-checkpoint-once`
- install the TSF Postgres extra if the driver is missing
- run/apply TSF Postgres migrations if schema is missing

HumanTasks must not contain database credentials or service secrets.

## Safety Rules

- Locks prevent overlapping scheduler runs.
- Runtime paused/killed blocks autonomous work.
- Missing shared store fails closed.
- Missing provider creates blockers or HumanTasks, not fake progress.
- Telegram unavailable queues notifications only.
- Public export may show scheduler status, but never raw errors, credentials, service IDs, or internal logs.
