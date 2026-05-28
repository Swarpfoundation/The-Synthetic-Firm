# The Synthetic Firm Execution Queue

The execution queue is the persistent handoff point between approvals and action processing.

Phase 4 consumes signed approvals safely but does not add external-effect business adapters.

## Queue states

- `queued`
- `approval_required`
- `approved_waiting_adapter`
- `blocked_missing_adapter`
- `executed`
- `failed`
- `cancelled`
- `expired`

## Safe internal actions

The queue can process these internal actions:

- `create_task`
- `create_message`
- `generate_daily_report`
- `budget_check`
- `status_check`
- `create_approval_request`

External-effect actions require exact signed approval. Since Phase 4 intentionally has no external-effect adapters, approved external-effect actions remain blocked with `blocked_missing_adapter`.

## Approval consumption

A signed approval decision can only be consumed once. The queued action hash must match the signed action hash exactly. Tampered, expired, reused, or wrong-action decisions fail closed.

## CLI

```bash
synthetic-firm list-execution-queue
synthetic-firm process-execution-queue --dry-run
```

Every queue transition writes an audit entry.
