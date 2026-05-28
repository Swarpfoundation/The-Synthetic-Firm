# The Synthetic Firm Vercel Adapter

The Vercel adapter prepares the public Progress Window frontend for preview
deployment. It is disabled by default and dry-runs by default.

## Environment

- `TSF_VERCEL_ENABLED=false`
- `TSF_VERCEL_PREVIEW_DEPLOY_ENABLED=false`
- `TSF_VERCEL_PRODUCTION_DEPLOY_ENABLED=false`
- `TSF_VERCEL_TOKEN`
- `TSF_VERCEL_PROJECT_PATH=apps/control-room`
- `TSF_VERCEL_ALLOWED_PROJECT_NAME` optional
- `TSF_VERCEL_ORG_ID` optional
- `TSF_VERCEL_PROJECT_ID` optional
- `TSF_VERCEL_SCOPE` optional
- `TSF_VERCEL_DEPLOY_TIMEOUT_SECONDS=300`

Tokens must be configured outside the repo. They are never printed, persisted,
placed in audit metadata, sent to Telegram, or exposed to the frontend.

## Allowed Shape

- detect Vercel CLI availability
- validate frontend path
- require frontend typecheck/build and brand guard before deploy
- create dry-run preview command plans
- optionally run live preview deployment only when all explicit preview gates pass
- run a post-preview public-safe health check

## Blocked

- `vercel env ...`
- domain and alias changes
- project deletion
- account/team mutation
- production deploy in this phase
