# The Synthetic Firm Autonomous Scheduler

The autonomous scheduler runs bounded checkpoints for the private TSF runtime.
It is not a public CLI workflow. Product operation is:

- autonomous scheduler and runtime
- Telegram as Atlas inbox and Human Task Inbox
- public website as a read-only progress window

## Workday

Default schedule:

- timezone: `Europe/Paris`
- workdays: Monday-Friday
- hours: `09:00-16:00`

Checkpoint cadence:

- `09:00`: Atlas starts the workday
- `10:00`: bounded workday cycle
- `11:30`: bounded workday cycle
- `13:00`: bounded workday cycle
- `14:30`: bounded workday cycle
- `15:30`: Atlas public/private manager reports
- `16:00`: close workday

## Runner Modes

`checkpoint_once` evaluates exactly one checkpoint, runs it if due, and exits.
This is the recommended shape for cron or scheduled worker execution.

`local_loop` is internal/dev only. It has hard maximum runtime and checkpoint
limits and handles SIGINT/SIGTERM safely. It must not be used as an uncontrolled
forever loop.

## Safety Checks

Before work runs, the scheduler checks:

- runtime is active
- audit log verifies
- budget is configured and within limit
- infrastructure budget state is evaluated
- workday window permits the checkpoint
- scheduler lock is available
- daily checkpoint limits are not exceeded

Paused runtime blocks agent cycles. Killed runtime blocks scheduler work except
status inspection. Provider unavailability creates blocked tasks or HumanTasks
instead of fake progress.

Atlas reviews queued FounderMessages during scheduler checkpoints. Public
exports include only founder-message counts and safe summaries; private Telegram
message content stays out of the public API and Progress Window.

Infrastructure budget evaluation does not stop safe internal reasoning simply
because provider/model spend is separate. It does create HumanTasks for unknown
infrastructure costs and blocks new paid infrastructure actions at the hard
`EUR 100/month` stop.

## Locks

Scheduler locks are persisted in SQLite with an expiry time. Overlapping runs are
blocked. Stale locks expire and all lock acquire/release/expire events are
audited.

## Internal Smoke Commands

These commands are internal developer/test utilities, not founder product UX:

```bash
synthetic-firm scheduler-dry-run-plan
synthetic-firm scheduler-checkpoint-once
synthetic-firm scheduler-status
synthetic-firm scheduler-lock-status
synthetic-firm scheduler-loop --max-runtime-seconds 300 --max-checkpoints 3
```
