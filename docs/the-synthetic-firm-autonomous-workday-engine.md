# The Synthetic Firm Autonomous Workday Engine

Phase 9 adds a bounded Autonomous Workday Engine. It is not a daemon and does
not run forever. A human or scheduler starts a day and runs discrete cycles.

## Lifecycle

- `synthetic-firm start-workday`
- `synthetic-firm run-workday-cycle`
- `synthetic-firm run-agent-turn AGENT_ID`
- `synthetic-firm generate-atlas-report`
- `synthetic-firm close-workday`

The engine persists workday state with status, cycle count, Atlas plan id,
report ids, timestamps, and a plain-English summary. Runtime `paused` or
`killed` blocks autonomous cycles.

## Operating Model

Atlas reviews persisted TSF state, creates a daily plan, assigns work, and writes
public/private reports. Scout, Forge, Pulse, and Sentinel act within their
bounded roles. If provider auth, source data, repo access, outreach capability,
or another real-world capability is missing, the engine creates blocked tasks or
private HumanTasks instead of pretending progress happened.

## Limits

Defaults are conservative:

- max cycles per day: 6
- max agent turns per cycle: 5
- max tasks per cycle: 5
- max messages per cycle: 8
- max human tasks per cycle: 3

Budget checks use existing persisted budget totals and fail closed if the runtime
cannot determine budget state.

## Still Disabled

No email sending, social posting, investor outreach, Vercel deployment, GitHub
write automation, payments, domain purchasing, active worker creation, or
autonomous self-upgrade execution is added in this phase.
