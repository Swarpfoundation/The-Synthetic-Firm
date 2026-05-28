# The Synthetic Firm Approval Runtime

Phase 3 approval decisions are signed with HMAC-SHA256 over canonical JSON.

## Signing secret

Live approval signing requires:

```bash
export TSF_APPROVAL_SIGNING_SECRET="use-a-long-random-secret"
```

If the variable is missing, live approval signing fails closed. Dry-run decisions can be simulated without a secret, but they are marked non-executable.

The signing secret must never be printed, logged, stored in SQLite, included in prompts, included in reports, or written to memory.

## Signed payload

Each signed approval decision includes:

- approval id
- task id
- requested action
- decision
- decided by
- decided at
- expires at
- approval version
- exact action hash

Verification fails if the signature is wrong, the decision is expired, the action hash does not match, or the signed action differs from the requested action.

## Dry-run Telegram flow

The Telegram adapter is dry-run only in Phase 3. It formats approval messages and parses command text:

```text
/approve APPROVAL_ID
/deny APPROVAL_ID
/status
/pause
/resume
/budget
/report
```

No webhook, bot token, or network send is required or used by tests.

## External actions

Approved external actions are still non-executable in Phase 3. The approval runtime can sign and verify decisions, but there are no live execution adapters for external-effect work.
