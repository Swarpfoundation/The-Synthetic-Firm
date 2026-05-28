# The Synthetic Firm Deployment Policy

Deployment policy is fail-closed.

## Environment

- `TSF_DEPLOY_DRY_RUN=true`
- `TSF_DEPLOY_AUTONOMOUS_PREVIEW=true`
- `TSF_DEPLOY_AUTONOMOUS_PRODUCTION=false`
- `TSF_DEPLOY_MAX_PER_DAY=3`
- `TSF_DEPLOY_REQUIRE_SENTINEL=true`

## Preview

Preview deployment may be allowed only after validation checks pass, Sentinel
review passes, runtime is active, budget is known, and credentials exist.

## Production

Production deployment is disabled by default. To become a candidate it requires:

- explicit `TSF_DEPLOY_AUTONOMOUS_PRODUCTION=true`
- Sentinel review
- clean checks
- verified audit log
- health check plan
- rollback plan
- no secret-like output
- active runtime

This phase does not add domain purchase, DNS changes, payment integration, or
database destructive operations.

