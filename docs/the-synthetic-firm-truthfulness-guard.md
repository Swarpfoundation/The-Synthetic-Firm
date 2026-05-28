# The Synthetic Firm Truthfulness Guard

The Truthfulness Guard protects public reports from unsupported claims.

Public facts must be backed by persisted TSF evidence, such as tasks, messages,
approval records, human tasks, reports, execution queue entries, audit entries,
explicit company configuration, or future approved research source records.

The guard blocks or downgrades unsupported claims about:

- revenue
- customers
- leads
- investor interest
- meetings
- proposals
- pull requests
- deployments
- users
- sent outreach
- payments
- account creation
- domain purchases

Unsupported claims become assumptions, proposals, next actions, or missing-data
notes. Public empty states remain empty when no real work happened.

The guard never treats model speculation as evidence.
Provider-backed structured reasoning is checked before persistence when it may
affect public reports or task claims.
