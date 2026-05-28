# The Synthetic Firm Provider Runtime

Phase 5B adds provider-owned runtime adapters for model work. The adapters consume
safe provider-auth status from Phase 5A and prepare or invoke provider CLIs
without storing tokens in TSF state.

## Supported runtime routes

| Provider | Runtime path | Model route |
| --- | --- | --- |
| `kimi-code` | Kimi Code CLI or compatible provider-owned runtime | `kimi-code:kimi-for-coding` |
| `openai-codex` | OpenAI Codex CLI sign-in runtime | `openai-codex:codex-managed` |

All five TSF agents route to Kimi Code by default:

- Atlas
- Scout
- Forge
- Pulse
- Sentinel

The Kimi Code model id is always `kimi-for-coding`. TSF does not manually switch
that route to a platform model id.

Kimi Code rejects generic OpenAI-compatible HTTP clients for this model route.
Live Kimi Code runtime work must go through a provider-owned coding-agent client
such as the Kimi CLI or a compatible coding-agent runtime. TSF can detect that an
API key is present, but live execution is not runtime-ready until the provider CLI
is available.

## Runtime commands

```bash
synthetic-firm provider-runtime-status kimi-code
synthetic-firm provider-runtime-plan kimi-code --agent-id atlas --prompt "Draft a safe task plan"
synthetic-firm provider-runtime-invoke kimi-code --agent-id atlas --prompt "Draft a safe task plan" --dry-run
```

Live invocation requires a persisted task id:

```bash
synthetic-firm create-task \
  --title "Provider runtime check" \
  --objective "Run one bounded provider-runtime request" \
  --created-by atlas \
  --assigned-agent atlas \
  --summary "Atlas runs a bounded provider-runtime check."

synthetic-firm provider-runtime-invoke kimi-code \
  --agent-id atlas \
  --task-id TASK_ID \
  --prompt "Draft a short internal note"
```

## Safety boundary

Provider runtime execution is gated by:

- provider auth status
- persisted task existence for live invocation
- persisted budget checks
- append-only audit logging
- redacted command previews
- redacted provider stdout and stderr
- a narrow child-process environment

Dry-runs never execute provider commands. CLI command previews replace prompt
content with `<prompt redacted>`.

## Secret handling

TSF does not store provider tokens in SQLite. The runtime adapter may pass
required environment variables to a provider-owned child process, but it does not
print, audit, report, or persist the secret value.

Kimi Code runtime credentials may come from:

- `TSF_KIMI_CODE_API_KEY`
- `TSF_KIMI_API_KEY`
- provider-owned Kimi CLI login state

OpenAI Codex runtime credentials are provider-owned by the Codex CLI. TSF does
not read browser cookies and does not automate ChatGPT web sessions.

## Still disabled

Phase 5B does not add live external business adapters. Email, social posting,
investor outreach, deployments, repository writes, payments, domain purchasing,
active worker creation, and autonomous self-upgrades remain disabled.
