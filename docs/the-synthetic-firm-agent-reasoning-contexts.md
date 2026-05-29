# The Synthetic Firm Agent Reasoning Contexts

Agent reasoning uses compact, evidence-based context generated from persisted
TSF state. Raw private founder messages, provider keys, Telegram ids, raw audit
metadata, and secrets are excluded.

## Agent Context Rules

- Atlas sees workday state, task summaries, public-safe HumanTask summaries,
  founder-message counts, budget usage, and report summaries.
- Scout sees research task state and missing research capability. Scout may not
  invent leads or market findings.
- Forge sees repo/runtime/frontend summaries and build blockers. Forge may
  propose repo edits, tests, commits, Vercel preview work, and Render runtime
  changes for the coding agent, but may not claim code changes, pushes, PRs, or
  deployments without persisted evidence.
- Pulse sees only approved offer or CRM summaries when they exist. Pulse may not
  claim outreach was sent without audited sending capability.
- Sentinel sees candidate claims and evidence summaries, then blocks unsupported
  claims.

## Structured Output

Agents return JSON with:

- `summary`
- `proposed_tasks`
- `messages_to_agents`
- `human_tasks`
- `assumptions`
- `evidence_refs`
- `blocked_reasons`
- `public_report_notes`
- `private_founder_notes`

Factual claims need `evidence_refs`; otherwise they must be assumptions,
proposals, next actions, blockers, or HumanTask requests.
