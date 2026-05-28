# The Synthetic Firm Deployment Operations

Deployment Operations gives TSF a safe deployment-readiness layer. It prepares
plans, validates checks, writes audit records, checks tool/credential readiness,
and creates HumanTasks when provider access is missing.

It does not grant unrestricted production deploy power.

## Targets

- `vercel_frontend`: public Progress Window frontend
- `render_backend_api`: read-only TSF backend/API service
- `render_scheduler_worker`: autonomous scheduler worker
- `render_postgres_future`: future durable database migration planning

## Defaults

- dry-run: enabled by default
- preview deployment planning: allowed after validation
- production deployment: disabled by default
- Sentinel review: required
- credentials: environment-only, never stored in SQLite
- live Vercel preview: disabled until explicitly enabled
- live Render deploy: readiness/staging-only planning by default
- Vercel CLI: project-local binary preferred over global machine state

Missing deployment credentials create private HumanTasks for the founder instead
of attempting deploys.

## Internal Utilities

These commands are internal developer/test/smoke utilities. They are not the
founder product interface.

```bash
synthetic-firm deploy-status
synthetic-firm deploy-plan --target vercel_frontend --env preview
synthetic-firm deploy-checks --target vercel_frontend
synthetic-firm deploy-preview --target vercel_frontend --dry-run
synthetic-firm deploy-production --target vercel_frontend --dry-run
synthetic-firm deployment-history
synthetic-firm deployment-credentials-status
synthetic-firm deployment-setup-status
synthetic-firm create-deployment-setup-human-tasks
synthetic-firm validate-deploy-tools
synthetic-firm validate-vercel-setup
synthetic-firm validate-render-setup
synthetic-firm vercel-preview --dry-run
synthetic-firm render-readiness
synthetic-firm deployment-human-tasks
synthetic-firm deployment-notifications
```

Telegram remains the founder interface. The public site remains read-only.

## Still Blocked

- production deploy without explicit policy enablement
- domain or DNS changes
- Vercel/Render secret or environment mutation
- deleting projects, services, or databases
- destructive database commands
- public website deploy controls

## Related Notes

- [Deployment Credential Setup](the-synthetic-firm-deployment-credential-setup.md)
- [Vercel Preview Deployments](the-synthetic-firm-vercel-preview-deployments.md)
- [Render Readiness](the-synthetic-firm-render-readiness.md)
