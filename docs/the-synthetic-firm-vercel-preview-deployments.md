# The Synthetic Firm Vercel Preview Deployments

Vercel preview deployment is the only live deployment path introduced in this
phase, and it remains disabled by default.

## Required Gates

A live preview requires all of the following:

- `TSF_VERCEL_ENABLED=true`
- `TSF_VERCEL_PREVIEW_DEPLOY_ENABLED=true`
- `TSF_DEPLOY_DRY_RUN=false`
- internal command invoked with live preview mode
- Vercel CLI available
- Vercel access configured through environment variables
- frontend project path exists and is linked
- deployment checks pass
- Sentinel deployment review passes
- audit log verifies
- runtime is active
- budget is available

Production deployment remains blocked in this phase.

## Project-Local CLI

The Control Room app carries Vercel CLI as a project-local dev dependency under
`apps/control-room`. TSF validation prefers:

1. `apps/control-room/node_modules/.bin/vercel`
2. a globally available `vercel` binary, if present

This avoids curl installers, sudo/global mutation, and machine-specific setup.
The local CLI is still deployment tooling: review `npm audit` output before
using it in a serious production environment.

## Project Link

TSF treats the frontend as Vercel-linked when either:

- `apps/control-room/.vercel/project.json` exists, or
- secure project metadata is available through environment configuration.

TSF does not commit Vercel project metadata automatically and does not run
interactive linking. If linking is missing, Forge creates a HumanTask asking the
founder to run `vercel link` locally/interactively or configure project metadata
securely.

## Health Check

After a preview URL is captured, TSF performs a public-safe health check:

- fetch the preview URL
- require a successful HTTP response
- reject obvious mutation-control or secret-like page content
- verify explicit read-only/public observer markers in bounded content:
  `Public Progress Window`, `Read-only public view`, `Real TSF runtime data only`,
  `data-tsf-public-progress-window="true"`, and `data-tsf-read-only="true"`
- persist only safe health status

Tests mock this check. No live network calls are made in the test suite.

## Blocked Vercel Commands

TSF does not run commands that mutate secrets, domains, aliases, projects, teams,
or accounts. Production deployment is policy-blocked even if a command plan can
be represented for review.
