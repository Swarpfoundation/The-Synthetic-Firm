# The Synthetic Firm Telegram Founder Inbox

Telegram is the private Atlas inbox and HumanTask delivery channel. It is not a
remote control panel, deployment surface, shell, provider-auth surface, or public
command interface.

## Allowed Founder Commands

- Free text queues a FounderMessage for Atlas.
- `/urgent MESSAGE` queues an urgent FounderMessage.
- `/clarify MESSAGE` queues a clarification FounderMessage.
- `/constraint MESSAGE` queues a business-constraint FounderMessage.
- `/human_tasks` lists pending HumanTasks.
- `/human_task HUMAN_TASK_ID` shows one HumanTask.
- `/done HUMAN_TASK_ID` marks a HumanTask done.
- `/blocked HUMAN_TASK_ID` marks a HumanTask blocked.
- `/note HUMAN_TASK_ID MESSAGE` records a private founder note.
- `/status` shows safe private runtime status.
- `/report` shows a safe private report summary.

Atlas reviews queued FounderMessages during scheduler checkpoints. Normal
messages are asynchronous by default; urgent messages are prioritized but still
remain inside the bounded scheduler/runtime policy.

## Blocked Commands

Render live Founder Inbox mode blocks remote-control commands, including:

- `/approve`
- `/deny`
- `/pause`
- `/resume`
- `/kill`
- `/deploy`
- `/run`
- `/exec`
- `/shell`
- `/provider`
- `/auth`
- `/create_task`

This keeps Telegram focused on founder communication and HumanTask resolution.

## Render Environment

Configure values only in Render environment variables. Never paste token values
into Telegram, docs, reports, logs, or public export.

- `TSF_TELEGRAM_ENABLED=true`
- `TSF_TELEGRAM_BOT_TOKEN=<secret>`
- `TSF_TELEGRAM_ALLOWED_CHAT_IDS=<secret>`
- `TSF_TELEGRAM_MODE=bounded_polling`
- `TSF_STORE_BACKEND=postgres`
- `DATABASE_URL=<secret>`

Readiness output reports only whether token and allowed-chat settings are
present. It never prints chat IDs or token values.

## Bounded Polling

Recommended Render cron command:

```bash
synthetic-firm telegram-poll-once && synthetic-firm telegram-send-pending-notifications --live
```

Run it every 1-5 minutes. The poller processes at most one update per run and
persists the Telegram update offset in shared Postgres state.

## Safety Boundaries

- Unknown chat IDs are rejected and audited without storing the raw ID.
- Public export shows only founder-message counts and HumanTask public
  summaries.
- Public export never includes Telegram IDs, bot tokens, raw founder message
  content, private HumanTask details, or founder notes.
- The public Progress Window remains read-only.
