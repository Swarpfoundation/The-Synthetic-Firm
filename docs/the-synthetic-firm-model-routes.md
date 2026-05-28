# The Synthetic Firm Model Routes

Phase 5A defines provider routes. Phase 5B adds runtime adapters for provider-owned CLIs.

## Routes

| Provider | Route type | Model | Auth |
| --- | --- | --- | --- |
| `kimi-code` | Kimi Code membership route | `kimi-for-coding` | `TSF_KIMI_CODE_API_KEY` or provider-owned Kimi CLI auth |
| `kimi-platform` | Kimi Platform API route | `kimi-k2.6` by default | `TSF_KIMI_PLATFORM_API_KEY` |
| `openai-codex` | OpenAI Codex route | `codex-managed` | provider-owned Codex CLI sign-in |
| `openai-api-key` | OpenAI API-key route | configurable | `TSF_OPENAI_API_KEY` |

## Why routes are separate

Kimi Code and Kimi Platform are different provider paths with different billing and base URLs.

OpenAI Codex sign-in and OpenAI API keys are also different paths. Codex sign-in can power Codex-style agent runtimes, but it must not be treated as unrestricted generic OpenAI API access.

## Forbidden auth paths

TSF does not support:

- browser cookie scraping
- browser profile reads
- ChatGPT web scraping
- OAuth token printing
- OAuth token storage in SQLite
- sending provider tokens through Telegram

## Commands

```bash
synthetic-firm provider-routes
synthetic-firm provider-route-status kimi-code
synthetic-firm provider-route-status kimi-platform
synthetic-firm provider-route-status openai-codex
synthetic-firm provider-route-status openai-api-key
synthetic-firm provider-runtime-status kimi-code
synthetic-firm provider-runtime-plan kimi-code --agent-id atlas --prompt "Draft a short plan"
```
