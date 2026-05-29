# The Synthetic Firm Forge Patch Pipeline

Phase 10J gives Forge a bounded path for real repo work without granting the
autonomous runtime an unrestricted shell.

## Model

- Forge creates a `code_change_proposal` with a unified diff, rationale, test
  command, target branch, and public-safe summary.
- Atlas and Sentinel perform internal review before any patch can be applied.
- The coding adapter applies only approved proposals.
- The adapter requires a clean git worktree, validates patch paths, blocks
  secret-like content, runs tests, commits to a controlled branch, and can push
  that branch when credentials are already available.
- Production deployment remains blocked by separate deployment policy.

## Safety Boundaries

The pipeline must not:

- read or print secrets
- edit `.env`, git internals, credential files, or private keys
- run shell pipelines or arbitrary shell control operators as test commands
- claim code was changed, tested, committed, pushed, or deployed without
  persisted audit evidence
- deploy production

## Internal Commands

These commands are internal/dev tooling. The founder should normally interact
through Telegram HumanTasks.

```bash
synthetic-firm code-proposal-create --title "..." --summary "..." --rationale "..." --patch-file change.patch
synthetic-firm code-proposal-list
synthetic-firm code-proposal-review CODE_PROPOSAL_ID
synthetic-firm code-proposal-apply CODE_PROPOSAL_ID
synthetic-firm code-proposal-apply CODE_PROPOSAL_ID --live
synthetic-firm code-proposal-apply CODE_PROPOSAL_ID --live --push
synthetic-firm code-proposal-public-summary
```

`code-proposal-apply` without `--live` is a dry-run policy check. With `--live`,
it applies the patch locally, runs tests, and commits. With `--push`, it pushes
the controlled branch. Git credentials stay outside TSF state and are never
stored in SQLite/Postgres.

## Public Progress Window

The public export may show proposal counts, public summaries, test status, target
branch after commit/push, and short commit ids. It must not show patch text,
private notes, credentials, or raw command output.
