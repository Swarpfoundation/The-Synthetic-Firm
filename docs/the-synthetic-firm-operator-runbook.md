# The Synthetic Firm Operator Runbook

This runbook covers Phase 4 local operation.

## Initialize state

```bash
export TSF_HOME=/tmp/synthetic-firm-home
synthetic-firm init-store
synthetic-firm store-status
synthetic-firm verify-audit-log
```

## Inspect runtime

```bash
synthetic-firm runtime-status
synthetic-firm telegram-status
synthetic-firm list-approvals
synthetic-firm list-execution-queue
synthetic-firm list-notifications
```

## Approval inbox

```bash
synthetic-firm list-approvals
synthetic-firm show-approval APPROVAL_ID
synthetic-firm approve APPROVAL_ID --decided-by founder
synthetic-firm deny APPROVAL_ID --decided-by founder
```

Live approval signing requires `TSF_APPROVAL_SIGNING_SECRET`. If missing, approval fails closed.

## Reports

```bash
synthetic-firm generate-daily-report
synthetic-firm send-daily-report --dry-run
```

Daily report notifications are queued and dry-run by default.

## Safety checks

Run before operating:

```bash
python -m compileall -q synthetic_firm tests/synthetic_firm
ruff check synthetic_firm tests/synthetic_firm
pytest tests/synthetic_firm -q
scripts/check-brand-identity.sh
```

## Still intentionally unavailable

The Synthetic Firm still does not perform live email sending, social posting, investor outreach, production deployment, payment processing, domain purchasing, active worker creation, or unbounded autonomous self-upgrade execution. Repo changes are handled through the coding-agent/operator path: Forge may create implementation HumanTasks, and the coding agent may edit, test, commit, and push with audit/deployment evidence.

## Recommended Phase 5

Add an operator-reviewed execution queue dashboard and one mocked external adapter contract. Keep all live adapters disabled until each has explicit approval checks, budget checks, audit logging, and integration tests with network calls mocked.
