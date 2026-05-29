# The Synthetic Firm Deployment Notes

These are preparation notes only. This phase does not deploy production systems
or add external business automation.

## Recommended Shape

- public frontend: Vercel static site
- read-only public API/SSE: Render web service
- autonomous scheduler: Render scheduled job or bounded worker process
- founder interface: Telegram Human Task Inbox

The public site remains read-only. It must not expose mutation endpoints,
approval controls, task creation, runtime controls, private founder messages, or
secrets.

## State

SQLite is acceptable for local/dev. Serious production should migrate TSF state
to Postgres or another durable database before relying on the runtime. Do not
depend on an ephemeral filesystem for company state.

Phase 10G adds the Postgres persistence foundation:

- explicit `TSF_STORE_BACKEND=postgres`
- `DATABASE_URL`/`TSF_DATABASE_URL` redaction
- non-destructive Postgres migration dry-runs
- Render API and scheduler readiness checks
- a safe `render.yaml` starter blueprint with no committed secrets

Database credentials belong only in Render environment variables.

## Scheduler

Use checkpoint-once mode from a scheduled job where possible. It exits after one
safe checkpoint and uses persisted locks to avoid overlaps. Local loop mode is
only for internal development and must be bounded by runtime/checkpoint limits.

For Render, start with a cron job that runs:

```bash
synthetic-firm scheduler-checkpoint-once
```

Do not run the bounded local scheduler loop as a deployed daemon in this phase.

## Still Disabled

The Synthetic Firm still does not implement live email sending, social posting,
investor outreach sending, production deployment, Stripe/payment/domain
purchasing, active worker creation, or unbounded autonomous self-upgrade
execution. Repo changes are routed through the coding-agent/operator path:
Forge may ask for code work, and the coding agent may edit, test, commit, and
push with budget/deployment gates and audit evidence.

## Deployment Operations v0.1

The deployment adapters now support dry-run-first Vercel and Render deployment
planning. Vercel preview deployment has a live path only when explicit preview
flags, checks, Sentinel review, audit verification, runtime state, and budget
all pass. Render remains readiness/staging-oriented in this phase.

Credential values stay in environment variables and are never printed or stored.
Production deploy remains blocked.
