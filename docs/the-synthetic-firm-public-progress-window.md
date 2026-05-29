# The Synthetic Firm Public Progress Window

The public website is an Open Company Progress Window. It lets
visitors observe verified public progress from The Synthetic Firm. It is not a
control panel.

## Visitors Can See

- Atlas public daily manager report
- Agent progress summaries
- Completed, in-progress, and blocked task summaries
- Public-safe human task summaries
- Public-safe budget and runtime status
- Public-safe report notes
- Audit verification and truthfulness indicators

## Visitors Cannot Do

- command agents
- chat with agents
- approve or deny actions
- pause, resume, or kill runtime
- create or edit tasks
- process execution queues
- see private leads, emails, investor/customer details, provider secrets,
  Telegram ids, raw prompts, raw audit metadata, or private repo details

## Read-Only Markers

The deployed public page includes explicit observer-mode markers in the initial
HTML and top-level app shell:

- `Public Progress Window`
- `Read-only public view`
- `Real TSF runtime data only`
- `data-tsf-public-progress-window="true"`
- `data-tsf-read-only="true"`

TSF preview health checks verify these markers and reject actual public mutation
controls such as approve/deny buttons, runtime pause/resume/kill controls,
command inputs, chat inputs, and task creation controls. All real action remains
internal to the runtime, Telegram HumanTasks, and audited internal tooling.

## Data Modes

Frontend modes:

- `mock`: local development simulation, visibly labeled Development Mock Mode
- `snapshot`: static real snapshot JSON, visibly labeled Real Snapshot Mode
- `api`: read-only public API snapshot, visibly labeled Public API Mode
- `sse`: read-only public SSE stream, visibly labeled Public Observer Mode

Public/production mode must use real TSF runtime data only. If data is missing,
the UI must say so directly, for example:

- "No public report generated yet."
- "No public tasks completed yet."
- "No public human tasks pending."

It must not fabricate customers, leads, revenue, meetings, tasks, or reports.

## Human Task Boundary

Telegram remains the founder's private Human Task Inbox. Public reports may show
only each task's `public_summary` and status. Exact private instructions,
founder notes, provider/account details, and any credential-like material remain
out of the public export and API.

## Autonomous Workday Status

The public snapshot and API include autonomous workday status, Atlas report
metadata, public-safe agent progress, and the truthfulness indicator. The public
site may say that provider setup or a founder task is pending, but it must not
pretend that agents completed work, contacted leads, deployed systems, or earned
revenue without persisted evidence.

The public snapshot also includes autonomous scheduler status:

- last checkpoint time
- next expected checkpoint
- current workday window
- latest scheduler summary

This is observability only. Visitors cannot trigger checkpoints, run agent
cycles, or alter runtime state.

## Deployment Visibility

The public snapshot may include a sanitized deployment summary:

- latest deployment-readiness state
- latest safe preview URL if one exists
- public-safe blocked reason
- backend health public status
- last public-safe preview health state
- last deployment setup check time

It must not include tokens, service ids, private deployment logs, environment
variables, project secrets, or internal Render/Vercel account details. Visitors
cannot trigger deployment from the public site.

## Deployment Direction

Recommended later deployment shape:

- Frontend: Vercel static site
- Backend: Render web service running the read-only API/SSE server
- `VITE_TSF_API_BASE_URL`: points the frontend to the Render API

SQLite is acceptable for local development. Render-hosted API/scheduler
operation should use shared Postgres state so Atlas reports, HumanTasks,
scheduler checkpoints, and audit entries survive deploys and are visible to both
the API service and checkpoint job.

The public snapshot may expose only sanitized storage status:

- `sqlite_preview`
- `postgres_ready`
- `postgres_unavailable`

It must not expose database URLs, usernames, hosts, passwords, service IDs, raw
database errors, or internal schema details.
