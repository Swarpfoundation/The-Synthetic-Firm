# TSF Public Progress Frontend Integration

The public progress frontend is a TSF-owned app. It visualizes a birdview office
where Atlas, Scout, Forge, Pulse, and Sentinel work through tasks, approvals,
messages, reports, runtime state, and budget events.

## Source Of Truth

The frontend is not the source of truth. It supports local mock state, read-only
static snapshots, the read-only public API, and the public SSE stream. TSF
runtime state remains owned by the Python runtime, SQLite store, approval
runtime, budget layer, audit log, autonomous scheduler, and internal runtime.

In mock mode, approve, deny, pause, resume, and kill controls are simulation-only.
In public snapshot, API, and SSE modes, those controls are hidden. Public
visitors may observe company progress only; they cannot command agents, create
tasks, approve actions, or alter runtime state.

The initial HTML and top-level app shell include stable read-only markers for
deployment health checks: `Public Progress Window`, `Read-only public view`,
`Real TSF runtime data only`, `data-tsf-public-progress-window="true"`, and
`data-tsf-read-only="true"`. These markers are intentionally outside lazy-loaded
3D content so TSF can verify public observer mode before any frontend action is
available.

## Mock Files

- `src/mocks/tsf-state.ts` defines the initial office, agent, budget, task, and
  report state.
- `src/mocks/tsf-events.ts` emits bounded mock TSF events.
- `src/utils/eventReducer.ts` maps events to UI state.
- `src/store/useTsfStore.ts` owns local view state and event playback.
- `src/adapters/controlRoomDataSource.ts` chooses mock, snapshot, API, or SSE mode.
- `src/adapters/controlRoomApiClient.ts` reads the public API snapshot.
- `src/adapters/controlRoomSseClient.ts` subscribes to the public SSE stream.
- `src/utils/snapshotToState.ts` maps backend snapshot JSON into frontend state.
- `src/utils/snapshotToEvents.ts` maps backend event projections into the
  timeline model.

## Snapshot Mode

Generate a frontend-safe public snapshot:

```bash
env TSF_HOME=/tmp/synthetic-firm-home synthetic-firm export-control-room-state \
  --audience public \
  --output apps/control-room/public/control-room-snapshot.json
```

Run the frontend in snapshot mode:

```bash
cd apps/control-room
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=snapshot npm run dev
```

Optional snapshot URL override:

```bash
VITE_TSF_CONTROL_ROOM_SNAPSHOT_URL=/control-room-snapshot.json
```

Snapshot mode reads a static JSON file served by Vite. The browser does not read
SQLite directly and does not mutate backend state. The public snapshot includes
`audience=public`, `dataMode=real_snapshot`, and
`truthfulness=real_runtime_data_only`.

Founder snapshots are local/private and still secret-free:

```bash
synthetic-firm export-control-room-state --audience founder --stdout
```

## API And SSE Modes

Start the read-only API:

```bash
env TSF_HOME=/tmp/synthetic-firm-home synthetic-firm serve-control-room-api
```

Run against the public API:

```bash
cd apps/control-room
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=api \
VITE_TSF_API_BASE_URL=http://localhost:8787 \
npm run dev
```

Run against the public SSE stream:

```bash
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=sse npm run dev
```

API/SSE modes use public endpoints only and send no browser credentials. If the
connection fails, the UI shows a connection error instead of falling back to mock
progress.

## Event Contract

The future runtime adapter should stream frontend-safe events with these types:

- `task.created`
- `task.assigned`
- `task.started`
- `task.blocked`
- `task.review_required`
- `approval.requested`
- `approval.approved`
- `approval.denied`
- `message.sent`
- `meeting.started`
- `meeting.ended`
- `budget.warning`
- `runtime.paused`
- `runtime.resumed`
- `runtime.killed`
- `daily_report.generated`

Events should contain plain-English summaries and frontend-safe identifiers. They
must not contain API keys, provider tokens, approval signing secrets, browser
cookies, raw audit metadata, raw prompt payloads, or long transcripts.

## Runtime Mapping

- TSF `active` maps to active office animation and event playback.
- TSF `paused` maps to a dimmed office and stopped mock event playback.
- TSF `killed` maps to locked-down UI with no pretend agent work.

## Approval Mapping

Approval cards display approval id, task id, requester, requested action, risk,
external-effect flag, Sentinel review, and status. Local approve and deny buttons
only change mock state. In public snapshot, API, and SSE modes they are not rendered. A future
authenticated founder mode must call the signed approval runtime and then
reconcile the UI through a read-only event stream.

## Budget Mapping

Budget display uses company daily budget, per-agent usage, and warning thresholds
at 50%, 80%, 95%, and 100%. Mock mode uses local values. Snapshot, API, and SSE
modes use read-only backend data.

## Report Mapping

The daily report panel displays Atlas public manager reports, completed tasks,
blocked tasks, pending approvals, public-safe human-task summaries, budget usage,
Sentinel risks, and next recommended actions. Reports must be summarized, plain
English, and generated from real persisted TSF data only.

## Autonomous Workday Mapping

Snapshots may include `autonomousWorkday` with status, cycle count, Atlas plan
id, report ids, and summary. Public Observer Mode shows this as read-only
company operating status. The frontend must not start cycles, run agent turns,
close workdays, or create tasks; those remain backend/CLI or future
authenticated-founder flows.

## Autonomous Scheduler Mapping

Snapshots may include `scheduler` with the last checkpoint, next checkpoint,
workday window, and scheduler summary. The UI displays this under Autonomous
Scheduler Status. It is observability only: the frontend must not run
checkpoints, acquire locks, send Telegram notifications, process queues, or
change runtime state.

## Deployment Status Mapping

Snapshots may include `deploymentSummary` with a public-safe deployment state,
preview URL, backend health status, and blocked reason. This is observability
only. The frontend must not trigger Vercel or Render deploys, mutate deployment
configuration, edit environment variables, change domains, or expose service
ids/tokens/logs.

## Human Task Boundary

Telegram is the founder's private Human Task Inbox. Agents may ask for real-world
actions such as buying a domain, creating an account, granting platform access,
authorizing a provider, paying an invoice, or clarifying a legal/business
constraint. Public snapshots may include only each task's public summary and
status. Private details, chat ids, provider credentials, prompts, leads, emails,
and raw audit metadata must not appear in public frontend data.

## Forbidden Frontend Responsibilities

The frontend must not:

- send email
- post to social platforms
- contact investors
- deploy software
- write to GitHub
- buy domains
- connect payment systems
- read browser cookies
- store secrets
- call provider model APIs
- command TSF agents
- create tasks
- approve or deny approvals
- pause, resume, or kill runtime
- claim simulated actions executed in TSF
- bypass approval or budget controls

## Phase 8D Adapter Direction

Add an authenticated founder-only command adapter. Keep public frontend actions
disabled; any future founder action must route through signed, audited,
approval-aware runtime boundaries.

<!-- Git integration redeploy marker: 2026-05-28T22:27:22Z -->
