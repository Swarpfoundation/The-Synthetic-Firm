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

## Scheduler

Use checkpoint-once mode from a scheduled job where possible. It exits after one
safe checkpoint and uses persisted locks to avoid overlaps. Local loop mode is
only for internal development and must be bounded by runtime/checkpoint limits.

## Still Disabled

The Synthetic Firm still does not implement live email sending, social posting,
investor outreach sending, production deployment, GitHub write automation,
Stripe/payment/domain purchasing, active worker creation, or autonomous
self-upgrade execution.

## Deployment Operations v0.1

The deployment adapters now support dry-run-first Vercel and Render deployment
planning. Vercel preview deployment has a live path only when explicit preview
flags, checks, Sentinel review, audit verification, runtime state, and budget
all pass. Render remains readiness/staging-oriented in this phase.

Credential values stay in environment variables and are never printed or stored.
Production deploy remains blocked.
