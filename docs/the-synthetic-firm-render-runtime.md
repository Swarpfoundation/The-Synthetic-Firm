# The Synthetic Firm Render Runtime

Render should host the read-only public API and a bounded scheduler checkpoint runner. Vercel hosts the static public Progress Window and reads Render API/SSE data.

## Recommended Render Components

- Web service: `synthetic-firm serve-control-room-api --host 0.0.0.0 --port $PORT`
- Cron job: `synthetic-firm scheduler-checkpoint-once`
- Postgres database: shared TSF runtime state

Use Render dashboard environment variables for secrets and database URLs. Do not commit `.env` values or service credentials.

## Required Environment Shape

```text
TSF_STORE_BACKEND=postgres
DATABASE_URL=<Render-managed Postgres connection string>
TSF_CONTROL_ROOM_PUBLIC_ENABLED=true
TSF_CONTROL_ROOM_FOUNDER_ENABLED=false
TSF_MODEL_PROVIDER=dry-run
```

Telegram and live model providers should remain disabled until the founder enables those channels intentionally.

The API and scheduler services also need the Postgres optional dependency. Use a
build command that installs the extra:

```bash
pip install -e ".[web,postgres]"
```

## Readiness Commands

These are internal developer/smoke utilities:

```bash
synthetic-firm render-api-readiness --api-url https://the-synthetic-firm-api-preview.onrender.com
synthetic-firm public-api-smoke --api-url https://the-synthetic-firm-api-preview.onrender.com
synthetic-firm public-progress-e2e-smoke --frontend-url https://the-synthetic-firm.vercel.app --api-url https://the-synthetic-firm-api-preview.onrender.com
```

Readiness output is sanitized. It must not include database URLs, passwords, Render API keys, service IDs, provider tokens, Telegram tokens, raw audit metadata, or private founder content.

## Blueprint

`render.yaml` is a safe starter blueprint with no secrets. Review it in Render before applying. It defines an API web service, a checkpoint cron job, and a Postgres database reference.

SQLite is acceptable for local/dev only. Serious deployed operation should move to Postgres before relying on Render scheduler checkpoints for real public progress.
