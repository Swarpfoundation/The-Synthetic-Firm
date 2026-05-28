# The Synthetic Firm Public Progress Frontend

The public progress frontend lives in `apps/control-room`. It is a game-style,
birdview office interface for the five TSF agents:

- Atlas: Supervisor / CEO
- Scout: Research & Opportunity
- Forge: Builder / Product
- Pulse: Growth / Sales
- Sentinel: Guardian / QA / Compliance

The public website role is an Open Company Progress Window. It shows real,
public-safe progress, Atlas daily manager reports, agent activity summaries,
completed and blocked work, sanitized human-task summaries, budget/status
summaries, and an audit/truthfulness indicator. Public visitors cannot command
agents or change TSF runtime state.

## Run It

```bash
npm run frontend:install
npm run frontend:dev
npm run frontend:build
npm run frontend:typecheck
```

The app can also be run directly:

```bash
cd apps/control-room
npm install
npm run dev
```

## Mock Mode

Mock mode uses local mock state and a local mock event stream:

- `src/mocks/tsf-state.ts`
- `src/mocks/tsf-events.ts`
- `src/utils/eventReducer.ts`
- `src/store/useTsfStore.ts`

The frontend is not the source of truth. Local approve, deny, pause, resume, and
kill controls are simulated UI actions only. Mock mode is labeled Development
Mock Mode and is for local development only.

## Public Observer Snapshot Mode

Read-only JSON snapshots come from the TSF SQLite store. Public export is the
default and contains only sanitized real runtime data:

```bash
env TSF_HOME=/tmp/synthetic-firm-home synthetic-firm export-control-room-state \
  --audience public \
  --output apps/control-room/public/control-room-snapshot.json
```

Run the frontend against the snapshot:

```bash
cd apps/control-room
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=snapshot npm run dev
```

Snapshot mode displays persisted runtime state, public task summaries, approval
status, execution queue summaries, budget usage, Atlas public reports, audit
verification, human-task public summaries, and projected recent events. It hides
approval/runtime mutation controls in public observer mode.

## Public API And SSE Modes

Start the read-only API:

```bash
env TSF_HOME=/tmp/synthetic-firm-home synthetic-firm serve-control-room-api
```

Run the frontend against the public API:

```bash
cd apps/control-room
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=api \
VITE_TSF_API_BASE_URL=http://localhost:8787 \
npm run dev
```

Run the frontend against the public SSE stream:

```bash
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=sse npm run dev
```

API/SSE mode is labeled Public Observer Mode and uses real public runtime data
only. If the API connection fails, the UI shows a connection error instead of
falling back to mock progress.

Founder export is available for local/private review, but still excludes
secrets:

```bash
synthetic-firm export-control-room-state --audience founder --stdout
```

## What Is Real

The frontend structure, TSF identity, agent model, event reducer, room layout,
approval cards, budget panel, report panel, and runtime display are real
frontend components. Snapshot, API, and SSE modes consume real TSF runtime
exports and remain read-only.

## Intentionally Disabled

The frontend does not let visitors talk to agents, approve/deny actions,
pause/resume/kill runtime, create tasks, edit data, send email, post socially,
contact investors, deploy apps, write to GitHub, buy domains, connect payment
systems, read browser cookies, store secrets, or call provider model APIs.

If real data is missing, public mode says so directly, for example: "No public
report generated yet" or "No completed tasks today." It must not fabricate
customers, leads, meetings, revenue, or completed work.

## Deployment Notes

Recommended later deployment path:

- Frontend: Vercel static site
- Backend: Render web service serving the read-only API/SSE layer
- `VITE_TSF_API_BASE_URL`: points to the Render API

SQLite is local/dev-friendly. Production should move state to Postgres in a
future phase and avoid relying on ephemeral filesystem storage.

## Phase 8D Direction

Add authenticated founder-only actions routed through the signed approval
runtime. Public observer mode should remain read-only.
