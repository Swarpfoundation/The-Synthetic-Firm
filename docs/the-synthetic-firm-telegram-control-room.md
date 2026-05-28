# The Synthetic Firm Telegram Founder Interface

Telegram is the founder's private Atlas inbox and Human Task Inbox. It is not a
remote-control console for the agents. Atlas receives founder notes, task
completion updates, clarification, new constraints, and urgent override messages,
then reviews them at workday checkpoints or after bounded autonomous cycles.

Telegram remains disabled by default and dry-run-first. It can show status,
private manager reports, budget summaries, and HumanTasks. It cannot execute
external business actions directly.

## Environment

```bash
export TSF_TELEGRAM_ENABLED=false
export TSF_TELEGRAM_MODE=dry_run
export TSF_TELEGRAM_ALLOWED_CHAT_IDS="123456789"
export TSF_TELEGRAM_BOT_TOKEN="..."
export TSF_APPROVAL_SIGNING_SECRET="..."
```

Defaults:

- `TSF_TELEGRAM_ENABLED=false`
- `TSF_TELEGRAM_MODE=dry_run`

The bot token and approval signing secret must never be printed, logged, stored in SQLite, written to reports, or included in prompts.

## Atlas Inbox Commands

Supported Telegram commands:

- `/status`
- `/report`
- `/budget`
- `/human_tasks`
- `/human_task HUMAN_TASK_ID`
- `/done HUMAN_TASK_ID`
- `/blocked HUMAN_TASK_ID`
- `/note HUMAN_TASK_ID MESSAGE`
- `/urgent MESSAGE`
- `/clarify MESSAGE`
- `/constraint MESSAGE`
- `/help`

Normal free-text founder messages are queued for Atlas. They are not treated as
immediate agent commands. Urgent messages are flagged and audited.

Unknown chat IDs are rejected and audited.

## Dry-run operation

```bash
synthetic-firm telegram-status
synthetic-firm telegram-dry-run-command "/status"
synthetic-firm telegram-poll-once
```

Dry-run polling performs no network access.

## Still disabled

Telegram cannot send email, post to social media, perform investor outreach, deploy production, write to GitHub, connect payments, buy domains, create active workers, or execute self-upgrades.
