# The Synthetic Firm Deployment Credential Setup

Deployment credentials are operator-managed environment values. TSF records only
safe readiness metadata: provider name, enabled state, CLI availability,
credential presence, project readiness, and missing setup steps.

Raw credentials are never stored in SQLite, audit entries, reports, Telegram
messages, public snapshots, or frontend code.

## Vercel

Frontend preview deployment readiness uses:

- `TSF_VERCEL_ENABLED=false`
- `TSF_VERCEL_PREVIEW_DEPLOY_ENABLED=false`
- `TSF_VERCEL_PRODUCTION_DEPLOY_ENABLED=false`
- `TSF_VERCEL_TOKEN` or `VERCEL_TOKEN`
- `TSF_VERCEL_PROJECT_PATH=apps/control-room`
- `TSF_VERCEL_DEPLOY_TIMEOUT_SECONDS=300`

The Vercel access value is passed through the child process environment only,
never as a command-line argument.

Vercel CLI is installed as project-local development tooling in
`apps/control-room`. TSF checks that local binary before looking for a global
binary.

## Render

Backend readiness uses:

- `TSF_RENDER_ENABLED=false`
- `TSF_RENDER_DEPLOY_ENABLED=false`
- `TSF_RENDER_API_KEY` or `RENDER_API_KEY`
- `TSF_RENDER_API_SERVICE_ID`
- `TSF_RENDER_SCHEDULER_SERVICE_ID`
- `TSF_RENDER_BLUEPRINT_PATH=render.yaml`

Render service identifiers are founder/private operational details and are not
exported to the public Progress Window.

## HumanTasks

When tools or credentials are missing, Forge creates HumanTasks for the founder,
such as:

- install Vercel CLI
- create or rotate Vercel deployment access in the provider dashboard
- configure Vercel access through environment variables
- link the frontend Vercel project
- confirm preview deployment is allowed
- confirm production remains blocked
- install Render CLI
- create Render API access in the Render dashboard
- configure Render API access through environment variables
- provide backend API and scheduler service identifiers
- confirm Render deploy mode: Git-connected service or Docker image
- confirm no production backend deploy should run in this phase

Public reports show only safe summaries like “Frontend deployment setup is
pending.”

## Internal Smoke Utilities

These commands are internal developer/test/smoke utilities only:

```bash
synthetic-firm deployment-setup-status
synthetic-firm create-deployment-setup-human-tasks
synthetic-firm validate-vercel-setup
synthetic-firm validate-render-setup
synthetic-firm deployment-notifications
```

Telegram remains the founder interface. Do not paste credential values into
Telegram.
