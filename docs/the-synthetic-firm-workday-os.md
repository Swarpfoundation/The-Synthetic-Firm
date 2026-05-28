# The Synthetic Firm Workday OS

The Synthetic Firm Workday OS is a safe orchestration model for a five-agent
autonomous AI agency:

- Atlas: Supervisor / CEO
- Scout: Research and Opportunity
- Forge: Builder / Product
- Pulse: Growth / Sales
- Sentinel: Guardian / QA / Compliance

Agents communicate through the orchestrator. They do not directly spawn each
other or execute uncontrolled agent-to-agent calls.

## Workday Loop

The default workday configuration is `agents/workday.yaml`:

- timezone: `Europe/Paris`
- workdays: Monday through Friday
- hours: `10:00-16:00`

Phase 2.5 keeps this as a schedule model. It does not start a background
daemon.

The commands below are internal developer smoke utilities, not the founder's
primary operating interface.

```bash
synthetic-firm show-workday-status
```

## Task State Machine

Internal company work is represented by a strict task state machine:

- proposed
- accepted
- assigned
- in_progress
- blocked
- review_required
- approval_required
- completed
- cancelled
- failed

Invalid transitions are rejected.

```bash
synthetic-firm create-dry-run-task \
  --title "Draft QA checklist" \
  --objective "Prepare a Sentinel review checklist" \
  --created-by atlas \
  --assigned-agent sentinel
```

## Internal Message Bus

Supported channels:

- company
- atlas
- scout
- forge
- pulse
- sentinel

Messages are routed through the orchestrator and can be logged. They do not
trigger direct execution.

```bash
synthetic-firm simulate-agent-message \
  --sender atlas \
  --channel company \
  --content "Today we review pending approvals first."
```

## Telegram Approval Formatting

Approval requests are Telegram-ready but do not require or start a live bot.
Formatted messages include:

- `/approve APPROVAL_ID`
- `/deny APPROVAL_ID`
- `/status`
- `/pause`
- `/budget`

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

## Budget Controls

Budget evaluation supports:

- per-agent daily budget
- per-task budget
- per-company daily budget
- maximum loop steps per task
- maximum tool calls per task
- dry-run mode
- fail-closed behavior when required budget data is unknown

```bash
synthetic-firm show-budget-status \
  --agent-limit 10 \
  --task-limit 5 \
  --company-limit 25 \
  --max-loop-steps 40 \
  --max-tool-calls 80 \
  --agent-spend 1 \
  --task-spend 1 \
  --company-spend 2 \
  --loop-steps 3 \
  --tool-calls 4 \
  --dry-run
```

## Worker Proposals

Agents may propose new workers, but they may not activate them. Any requested
external tool triggers Sentinel review and a high-risk classification.

## Self-Improvement Proposals

Agents may propose prompt, skill, documentation, and test improvements. They
may not directly change their authority. Permission or budget increases are
flagged high risk.

Forbidden targets include:

- approval rules
- secrets and API-key code
- raw environment files
- logging disablement
- main-branch merge logic

## Daily Reports

Daily reports summarize:

- tasks completed
- tasks blocked
- approval requests pending
- new worker proposals
- self-improvement proposals
- budget usage
- Sentinel risks
- questions for the founder
- next recommended actions

```bash
synthetic-firm generate-daily-report \
  --question "Should Sentinel review all medium-risk tasks?" \
  --next-action "Review pending approvals."
```

## Intentionally Not Implemented

The Synthetic Firm does not currently add:

- live email sending
- social media posting
- investor outreach sending
- production deployment
- payment integration
- repository write automation
- autonomous merge to main
- active new worker creation
- autonomous permission escalation
- live Telegram bot operation
