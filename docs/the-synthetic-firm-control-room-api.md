# The Synthetic Firm Public Progress API

Phase 8C adds a read-only local HTTP API for the public progress website. The API
uses the same sanitized exporter as `synthetic-firm export-control-room-state`,
so public responses are real TSF runtime snapshots and not mock progress.

## Run Locally

```bash
env TSF_HOME=/tmp/synthetic-firm-home synthetic-firm serve-control-room-api \
  --host 127.0.0.1 \
  --port 8787
```

The server is intentionally read-only. It does not create tasks, approve
actions, process queues, pause runtime, call providers, or trigger external
business actions.

## Environment

- `TSF_CONTROL_ROOM_HOST`: default `127.0.0.1`
- `TSF_CONTROL_ROOM_PORT`: default `8787`
- `TSF_CONTROL_ROOM_ALLOWED_ORIGINS`: default `http://localhost:5173`
- `TSF_CONTROL_ROOM_PUBLIC_ENABLED`: default `true`
- `TSF_CONTROL_ROOM_FOUNDER_ENABLED`: default `false`
- `TSF_CONTROL_ROOM_FOUNDER_TOKEN`: required only for founder endpoints
- `TSF_CONTROL_ROOM_SSE_INTERVAL_SECONDS`: reserved for future incremental SSE

## Public Endpoints

- `GET /health`
- `GET /api/public/control-room/snapshot`
- `GET /api/public/control-room/events`
- `GET /api/public/reports/latest`
- `GET /api/public/human-tasks/summary`

Public endpoints return public-safe runtime data only. They exclude secrets,
provider keys, signing secrets, Telegram ids, raw prompts, raw audit metadata,
private leads, private emails, private customer/investor details, and private
human-task details.

## Founder Endpoints

Founder endpoints are disabled unless `TSF_CONTROL_ROOM_FOUNDER_ENABLED=true`.
When enabled, they require:

```http
Authorization: Bearer <TSF_CONTROL_ROOM_FOUNDER_TOKEN>
```

Available read-only endpoints:

- `GET /api/founder/control-room/snapshot`
- `GET /api/founder/control-room/events`
- `GET /api/founder/human-tasks`

Founder responses may include richer operational summaries but still never
include secrets.

## SSE Stream

`GET /api/public/control-room/events` emits browser-safe Server-Sent Events:

- `heartbeat`
- `snapshot`
- `runtime`
- `report`
- `human_task_summary`
- `audit`

Phase 8C emits sanitized snapshot-style events. True incremental delta
detection remains a later phase.

## CORS And Headers

Allowed origins are configured with `TSF_CONTROL_ROOM_ALLOWED_ORIGINS`. The API
does not use wildcard origins for founder data. Responses include conservative
headers such as `X-Content-Type-Options: nosniff`, `Referrer-Policy:
no-referrer`, and `Cache-Control: no-store` for JSON responses.

## Disabled

There are no mutation endpoints in Phase 8C. These are intentionally absent:

- `POST /approve`
- `POST /deny`
- `POST /pause`
- `POST /resume`
- `POST /kill`
- `POST /tasks`
- `POST /messages`
- `POST /commands`
- `POST /queue/process`
