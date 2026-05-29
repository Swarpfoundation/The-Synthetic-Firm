# The Synthetic Firm Telegram Human Task Inbox

Telegram is the founder's private Atlas inbox and Human Task Inbox. It is not a
remote-control console and not a public interface.

Atlas receives founder messages by default. Normal messages are persisted and
reviewed during scheduled workday checkpoints. Urgent messages are flagged and
audited for priority review.

HumanTask notifications are sent when agents need real-world action, access,
money, legal authority, or an impossible-to-infer clarification. Examples:

- buy a domain
- provide a provider key through a future secure path
- connect a provider account
- grant platform or repo access
- install Vercel or Render CLI in the runtime environment
- configure deployment provider access through environment variables
- link the public frontend project for preview deployment
- pay an invoice
- sign a document
- clarify a legal/business constraint

Reply commands:

- `/human_tasks`
- `/human_task HUMAN_TASK_ID`
- `/done HUMAN_TASK_ID`
- `/blocked HUMAN_TASK_ID`
- `/note HUMAN_TASK_ID MESSAGE`

In Render live mode these are the only mutating Telegram commands allowed. They
update HumanTasks and queue private FounderMessages for Atlas review; they do
not run shell commands, deployments, provider auth, or public runtime controls.

HumanTask notifications include only safe plain-English requests and public
summaries. They must not include provider tokens, API keys, Telegram ids, raw
prompts, raw audit metadata, private leads, private emails, or private repo
details.

Deployment-related HumanTasks may report preview deployment started, preview
deployment finished, health check failed, or production deployment blocked. They
must not include credential values, raw CLI output, private service identifiers,
or environment variable values.
