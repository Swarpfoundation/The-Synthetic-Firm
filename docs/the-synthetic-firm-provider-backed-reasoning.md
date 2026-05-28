# The Synthetic Firm Provider-Backed Reasoning

Phase 9B lets TSF agents use bounded model reasoning during autonomous workday
cycles. It does not add external business-action tools.

## Routes

- `dry-run`: default. No live model call.
- `kimi-code`: Kimi Code API route using `kimi-for-coding`.
- `kimi-platform`: separate Kimi Platform API route.
- `openai-api`: OpenAI API-key route, separate from ChatGPT/Codex sign-in.

Environment:

```bash
export TSF_MODEL_PROVIDER=dry-run
export TSF_MODEL_DRY_RUN=true
export TSF_MODEL_TIMEOUT_SECONDS=60
export TSF_MODEL_MAX_INPUT_CHARS=12000
export TSF_MODEL_MAX_OUTPUT_CHARS=4000
```

Kimi Code:

```bash
export TSF_MODEL_PROVIDER=kimi-code
export TSF_KIMI_CODE_API_KEY="..."
```

The compatibility key `TSF_KIMI_API_KEY` is also detected for the Kimi Code
route, but new configuration should prefer `TSF_KIMI_CODE_API_KEY`.

Kimi Platform:

```bash
export TSF_MODEL_PROVIDER=kimi-platform
export TSF_KIMI_PLATFORM_API_KEY="..."
export TSF_KIMI_PLATFORM_MODEL=kimi-k2.6
```

OpenAI API:

```bash
export TSF_MODEL_PROVIDER=openai-api
export TSF_OPENAI_API_KEY="..."
export TSF_OPENAI_MODEL="gpt-5.5"
```

## Boundaries

- No browser-cookie scraping.
- No ChatGPT web automation.
- No raw provider tokens in SQLite, reports, prompts, audit logs, Telegram, or
  frontend output.
- Provider errors are redacted.
- Missing credentials fail closed.
- Tests use dry-run or mocked providers only.
- CLI commands are internal developer/test/smoke utilities, not the product UX.

Telegram remains the founder interface. The public website remains read-only.
