# The Synthetic Firm Audit Boundary

Phase 3 adds an append-only audit log for important orchestrator actions.

## Audit entries

Each audit entry includes:

- audit id
- sequence number
- UTC timestamp
- actor type and actor id
- action
- target type and target id
- risk level
- external-effect flag
- plain-English summary
- JSON metadata
- previous hash
- entry hash

The hash chain is verified with:

```bash
synthetic-firm verify-audit-log
```

Tampering with an existing row changes the expected hash and fails verification.

## Runtime permission boundary

Before tool-like work, TSF checks:

- the runtime is not paused or killed for that action
- the task exists
- the action is known
- the action is not forbidden
- budget and loop limits are available
- budget and loop limits are within configured caps
- external-effect actions have exact signed approval

Forbidden actions fail closed in Phase 3:

- email sending
- social posting
- investor outreach
- Vercel deployment
- GitHub write or merge
- Stripe/payment connection
- domain purchasing
- production deployment
- active worker creation
- policy modification
- permission escalation
- secret reads
- audit log disablement

Allowed safe simulated actions include internal notes, task creation, message creation, approval request creation, daily report generation, worker proposals, self-improvement proposals, budget checks, and status checks.

## Budget persistence

Budget usage records persist to SQLite. Budget checks fail closed when limits or usage cannot be determined. Budget logs and audit entries must not contain provider keys, approval signing secrets, tokens, or credentials.
