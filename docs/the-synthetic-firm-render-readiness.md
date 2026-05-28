# The Synthetic Firm Render Readiness

Render support in this phase is readiness-first. TSF can validate whether the
backend/API and scheduler worker are configured for future deployment, but live
production deployment remains blocked.

## Readiness Checks

TSF checks:

- Render CLI availability
- Render API access presence
- backend API and scheduler service identifiers
- `render.yaml` presence for blueprint validation planning
- deploy mode clarification: Git-connected service or Docker image
- deployment policy gates
- Sentinel review

Render typically deploys from a connected Git repository or Docker image. TSF
does not pretend local source upload behaves like the Vercel frontend path.

## Live Deploy Boundary

`TSF_RENDER_DEPLOY_ENABLED=false` by default. Even when enabled in a later
controlled environment, this phase allows only explicitly configured
preview/staging paths. Production deploys, restarts, secret mutations, database
operations, SSH, billing changes, and service deletion remain blocked.

## Public Visibility

The public Progress Window may show a safe backend readiness state. It must not
show service identifiers, API access values, private logs, or internal command
output.
