# The Synthetic Firm Autonomous Ops

Phase 10K adds a bounded operations runner for autonomous code and deployment
work. It lets approved agent work move from code-change proposal to tested git
commit, optional branch push, and optional preview/staging deployment without
turning Telegram or the public website into a remote control panel.

## Operating Model

Forge proposes implementation patches through `code_change_proposals`. Internal
review must approve the proposal before any file write can happen. The
autonomous ops runner then applies only approved unified diffs, runs a bounded
test command, commits to the proposal branch, optionally pushes that branch, and
optionally triggers preview/staging deployment adapters.

The runner does not execute arbitrary shell commands. It does not deploy
production. It does not merge to `main`. It does not print credentials.

## Commands

These commands are internal developer/smoke tooling:

```bash
synthetic-firm autonomous-ops-status
synthetic-firm autonomous-ops-once
```

The scheduler also calls `autonomous-ops-once` after successful cycle
checkpoints.

## Environment Gates

All live behavior is disabled by default:

```bash
TSF_AUTONOMOUS_OPS_ENABLED=true
TSF_AUTONOMOUS_CODE_APPLY_ENABLED=true
TSF_AUTONOMOUS_CODE_PUSH_ENABLED=true
TSF_AUTONOMOUS_PREVIEW_DEPLOY_ENABLED=true
TSF_AUTONOMOUS_RENDER_DEPLOY_ENABLED=true
TSF_CODE_REPO_PATH=/opt/render/project/src
TSF_CODE_TEST_COMMAND="python -m pytest tests/synthetic_firm -q"
```

`TSF_AUTONOMOUS_CODE_PUSH_ENABLED=true` requires safe git credentials in the
runtime environment. Credential values must stay in provider/runtime secrets and
must not be committed or printed.

`TSF_AUTONOMOUS_PREVIEW_DEPLOY_ENABLED=true` still requires the Vercel adapter
gates. `TSF_AUTONOMOUS_RENDER_DEPLOY_ENABLED=true` still requires the Render
adapter gates. Production deployment remains blocked by deployment policy.

## Safety Rules

- Only approved code-change proposals are eligible.
- The target repository must be clean before a patch is applied.
- Sensitive paths such as `.env`, credentials, private keys, and token-bearing
  paths are blocked.
- Patch text is scanned for secret-like strings.
- Test commands are split without a shell and reject control operators.
- Failed tests fail the proposal closed.
- Push is branch-only and requires explicit env enablement.
- Deployments are preview/staging only and run through existing deployment,
  budget, and Sentinel policy checks.
- Failures create HumanTasks when founder action is needed.

## Public Boundary

The public Progress Window may show whether bounded autonomous ops are enabled
and whether code push or preview/staging deploy gates are active. It must not
show repo paths, credentials, service IDs, command output with secrets, or
private patch text.

## Founder Role

The founder is not expected to run cron or manually command the agents. The
founder only handles HumanTasks that agents cannot safely complete themselves,
such as providing credentials, confirming vendor costs, or approving future
policy expansions.
