# The Synthetic Firm

The Synthetic Firm is an autonomous AI agency OS with five internal agents:
Atlas, Scout, Forge, Pulse, and Sentinel.

It is designed as a private operating layer for internal company work:
planning, research, product building, growth drafting, QA review, approvals,
budget controls, and daily reporting. The system is intentionally conservative:
external-effect actions require explicit approval models, and live external
automation is not enabled by default.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party license
notices.

## Agents

- Atlas: Supervisor / CEO
- Scout: Research and Opportunity
- Forge: Builder / Product
- Pulse: Growth / Sales
- Sentinel: Guardian / QA / Compliance

## Internal Developer Setup

The Synthetic Firm is operated by its autonomous runtime, the founder's private
Telegram interface, and the read-only public progress website. The CLI remains
an internal developer/test/smoke utility; it is not the product interface and
the founder is not expected to operate TSF from a terminal.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
synthetic-firm --help
synthetic-firm show-workday-status
```

Configure Kimi Code for The Synthetic Firm without putting secrets in repository
files:

```bash
export TSF_KIMI_API_KEY="..."
export TSF_KIMI_BASE_URL="https://api.kimi.com/coding"
export TSF_HOME=/tmp/synthetic-firm-home
synthetic-firm atlas --dry-run
```

## Workday OS

The Workday OS models internal operations during business hours:

- default timezone: `Europe/Paris`
- default workdays: Monday through Friday
- default hours: `09:00-16:00`
- internal task state machine
- local message bus
- Telegram-ready approval request formatting
- budget and loop-limit evaluation
- worker proposals without active worker creation
- self-improvement proposals without permission escalation
- plain-English daily reports

```bash
synthetic-firm create-dry-run-task \
  --title "Draft QA checklist" \
  --objective "Prepare a Sentinel review checklist" \
  --created-by atlas \
  --assigned-agent sentinel
```

## Autonomous Workday

Atlas can run a bounded autonomous workday cycle from persisted TSF state:

```bash
synthetic-firm start-workday
synthetic-firm run-workday-cycle
synthetic-firm generate-atlas-report
synthetic-firm autonomous-status
```

Agents decide work within their roles. Missing providers, access, or real-world
capabilities create blocked tasks or private HumanTasks instead of fake progress.

Provider-backed reasoning remains dry-run by default and is configured only for
the internal runtime:

```bash
export TSF_MODEL_PROVIDER=dry-run
export TSF_MODEL_DRY_RUN=true
```

Supported internal routes are `kimi-code`, `kimi-platform`, and `openai-api`.
Telegram remains the founder interface; the CLI remains internal developer/test
tooling.

## Autonomous Scheduler

The internal scheduler runs bounded checkpoints during the Paris workday:

- `09:00`: Atlas starts the day
- `10:00`, `11:30`, `13:00`, `14:30`: bounded cycles
- `15:30`: Atlas reports
- `16:00`: close workday

Scheduler commands are internal developer/test/smoke utilities only:

```bash
synthetic-firm scheduler-dry-run-plan
synthetic-firm scheduler-checkpoint-once
synthetic-firm scheduler-status
```

Founder-facing work still flows through Telegram HumanTasks, and public progress
remains read-only.

## Deployment Operations

TSF can prepare deployment-readiness plans for the public frontend on Vercel and
backend/API/scheduler services on Render. This is internal adapter plumbing, not
public product UX. Vercel preview deployment has an explicit live gate; Render
remains readiness/staging-oriented in this phase.

The Vercel CLI is installed as project-local tooling for `apps/control-room`.
TSF uses the local binary before any global executable.

```bash
synthetic-firm deploy-status
synthetic-firm deploy-plan --target vercel_frontend --env preview
synthetic-firm deploy-preview --target vercel_frontend --dry-run
synthetic-firm deployment-credentials-status
synthetic-firm create-deployment-setup-human-tasks
synthetic-firm validate-vercel-setup
synthetic-firm validate-render-setup
synthetic-firm vercel-preview --dry-run
synthetic-firm render-readiness
```

Production deploy remains disabled. Missing deployment tools or access create
private HumanTasks for the founder. Credential values stay in environment
variables and are not stored or printed.

## Infrastructure Budget

TSF has a hard infrastructure/deployment budget of `EUR 100/month`. It covers
Render, Vercel, Neon/Postgres, cron/worker/backend hosting, storage,
monitoring/logging, deployment services, and future domains/DNS. Model/API spend
is excluded by default unless `model_api_budget_included` is enabled in the
budget config.

Unknown infrastructure cost blocks paid actions and creates HumanTasks for
founder confirmation. New recurring paid resources require HumanTask approval.

```bash
synthetic-firm budget-status
synthetic-firm budget-create-confirmation-tasks
synthetic-firm budget-add-cost --provider render --service "Render API service" --amount-eur 7 --recurrence monthly --confidence estimated
synthetic-firm budget-public-summary
```

## Public Progress Website

```bash
npm run frontend:install
npm run frontend:dev
```

To view a read-only snapshot of persisted TSF state:

```bash
synthetic-firm export-control-room-state --audience public --output apps/control-room/public/control-room-snapshot.json
cd apps/control-room
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=snapshot npm run dev
```

To serve the read-only public progress API/SSE layer locally:

```bash
synthetic-firm serve-control-room-api --host 127.0.0.1 --port 8787
cd apps/control-room
VITE_TSF_CONTROL_ROOM_DATA_SOURCE=sse VITE_TSF_API_BASE_URL=http://localhost:8787 npm run dev
```

The public website is an Open Company Progress Window. It shows sanitized
real runtime progress and does not let visitors command agents, approve actions,
create tasks, or change runtime state. The deployed page includes explicit
health-check markers: `Public Progress Window`, `Read-only public view`,
`Real TSF runtime data only`, `data-tsf-public-progress-window="true"`, and
`data-tsf-read-only="true"`.

```bash
synthetic-firm format-telegram-approval \
  --task-id task_123 \
  --agent-id forge \
  --requested-action "Use an external service" \
  --risk-level high \
  --external-effect \
  --request "Forge requests human approval before an external effect." \
  --sentinel-review "Sentinel requires founder approval."
```

## Safety Boundaries

The Synthetic Firm does not currently implement:

- live email sending
- social media posting
- investor outreach sending
- production deployment
- payment processing
- unbounded autonomous repository write automation
- autonomous merge to main
- active worker creation
- autonomous permission escalation
- autonomous self-upgrade execution

Forge may create implementation work for the coding-agent/operator path. The
coding agent may edit this repo, run tests, commit, push, and prepare
Vercel/Render changes when the work is founder-visible, budget-aware, and
auditable. Production deployment remains separately blocked.

## Documentation

- [Foundation](docs/the-synthetic-firm-foundation.md)
- [Workday OS](docs/the-synthetic-firm-workday-os.md)
- [Runtime](docs/the-synthetic-firm-runtime.md)
- [Approval runtime](docs/the-synthetic-firm-approval-runtime.md)
- [Audit boundary](docs/the-synthetic-firm-audit-boundary.md)
- [Telegram Founder Interface](docs/the-synthetic-firm-telegram-control-room.md)
- [Execution Queue](docs/the-synthetic-firm-execution-queue.md)
- [Operator Runbook](docs/the-synthetic-firm-operator-runbook.md)
- [Provider Auth Bridge](docs/the-synthetic-firm-provider-auth.md)
- [Model Routes](docs/the-synthetic-firm-model-routes.md)
- [Provider Runtime](docs/the-synthetic-firm-provider-runtime.md)
- [Provider-Backed Reasoning](docs/the-synthetic-firm-provider-backed-reasoning.md)
- [Agent Reasoning Contexts](docs/the-synthetic-firm-agent-reasoning-contexts.md)
- [Model Budgeting](docs/the-synthetic-firm-model-budgeting.md)
- [Infrastructure Budget Policy](docs/the-synthetic-firm-budget-policy.md)
- [Infrastructure Burn](docs/the-synthetic-firm-infrastructure-burn.md)
- [Public Progress Frontend](docs/the-synthetic-firm-control-room-frontend.md)
- [Public Progress API](docs/the-synthetic-firm-control-room-api.md)
- [Public Progress Window](docs/the-synthetic-firm-public-progress-window.md)
- [Autonomous Workday Engine](docs/the-synthetic-firm-autonomous-workday-engine.md)
- [Autonomous Scheduler](docs/the-synthetic-firm-autonomous-scheduler.md)
- [Truthfulness Guard](docs/the-synthetic-firm-truthfulness-guard.md)
- [Human Task Inbox](docs/the-synthetic-firm-human-task-inbox.md)
- [Telegram Founder Inbox](docs/the-synthetic-firm-telegram-founder-inbox.md)
- [Telegram Human Task Inbox](docs/the-synthetic-firm-telegram-human-task-inbox.md)
- [Deployment Notes](docs/the-synthetic-firm-deployment-notes.md)
- [Deployment Operations](docs/the-synthetic-firm-deployment-operations.md)
- [Deployment Policy](docs/the-synthetic-firm-deployment-policy.md)
- [Deployment Credential Setup](docs/the-synthetic-firm-deployment-credential-setup.md)
- [Vercel Preview Deployments](docs/the-synthetic-firm-vercel-preview-deployments.md)
- [Vercel Adapter](docs/the-synthetic-firm-vercel-adapter.md)
- [Render Readiness](docs/the-synthetic-firm-render-readiness.md)
- [Render Adapter](docs/the-synthetic-firm-render-adapter.md)
- [Postgres Persistence](docs/the-synthetic-firm-postgres-persistence.md)
- [Postgres Runtime Adapter](docs/the-synthetic-firm-postgres-runtime-adapter.md)
- [Postgres Migrations](docs/the-synthetic-firm-postgres-migrations.md)
- [Render Runtime](docs/the-synthetic-firm-render-runtime.md)
- [Scheduler Render Worker](docs/the-synthetic-firm-scheduler-render-worker.md)
- [Upstream attribution](docs/legal/upstream-attribution.md)
