# The Synthetic Firm Render Adapter

The Render adapter prepares backend/API and scheduler worker deployment plans.
It is disabled by default and dry-runs by default.

Render typically deploys from a connected Git repository or Docker image. This
adapter does not pretend local source upload works like Vercel.

Staging deploys use Render's public API by default:
`POST https://api.render.com/v1/services/{serviceId}/deploys`. The API accepts
an optional `commitId`; TSF exposes that as `TSF_RENDER_DEPLOY_COMMIT_ID` for
future controlled branch/commit deploys. CLI deploys remain available only when
`TSF_RENDER_DEPLOY_METHOD=cli`.

## Environment

- `TSF_RENDER_ENABLED=false`
- `TSF_RENDER_DEPLOY_ENABLED=false`
- `TSF_RENDER_DEPLOY_METHOD=api`
- `TSF_RENDER_API_KEY`
- `TSF_RENDER_API_SERVICE_ID`
- `TSF_RENDER_WORKER_SERVICE_ID`
- `TSF_RENDER_SCHEDULER_SERVICE_ID`
- `TSF_RENDER_POSTGRES_ID` optional
- `TSF_RENDER_BLUEPRINT_PATH=render.yaml`
- `TSF_RENDER_CLEAR_CACHE=do_not_clear`
- `TSF_RENDER_DEPLOY_COMMIT_ID` optional

API keys and service identifiers are never exposed publicly. Raw API keys are
not stored in SQLite, audit logs, reports, Telegram, or frontend snapshots.

## Allowed Shape

- detect Render CLI availability
- trigger staging deploys through the Render API when explicitly enabled
- validate `render.yaml` if present
- plan deploy/status checks
- evaluate readiness without triggering production deploys
- allow only explicitly configured preview/staging deploy paths in this phase

## Blocked

- secret/environment changes
- `ssh`
- destructive database commands
- service/database deletion
- plan/billing mutation
- production restart/deploy in this phase
