# The Synthetic Firm Human Task Inbox

Telegram is the founder's private Human Task Inbox. It is not the public command
surface for The Synthetic Firm.

Agents create HumanTasks only for real-world blockers they cannot complete
autonomously:

- buy a domain
- create or connect an account
- provide a provider/API key through a future secure path
- pay an invoice
- sign a document
- grant platform or repo access
- approve a legal or financial commitment
- clarify a business/legal constraint impossible to infer from available data

Provider-backed agents follow the same rule. Model reasoning may propose a
HumanTask for real-world access, authority, money, or unavailable capability,
but it may not execute those actions.

Commands:

- `/human_tasks`
- `/human_task HUMAN_TASK_ID`
- `/done HUMAN_TASK_ID`
- `/blocked HUMAN_TASK_ID`
- `/note HUMAN_TASK_ID MESSAGE`

During scheduler checkpoints, new pending HumanTasks are queued as Telegram
notifications for the founder. Notifications are deduped by HumanTask id and
include safe reply hints:

- `/done HUMAN_TASK_ID`
- `/blocked HUMAN_TASK_ID`
- `/note HUMAN_TASK_ID MESSAGE`

Normal founder messages are queued for Atlas review during scheduled workday
checkpoints. Urgent messages are flagged and audited, but they still do not turn
Telegram into a public control console.

Public reports may include only `public_summary` and status. Private details,
founder notes, provider/account details, chat ids, leads, emails, and secrets do
not appear in public exports or the public progress API.
