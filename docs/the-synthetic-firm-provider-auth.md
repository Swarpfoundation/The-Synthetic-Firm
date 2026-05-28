# The Synthetic Firm Provider Auth Bridge

Phase 5A adds safe provider authentication metadata for The Synthetic Firm.

The bridge supports:

- Kimi Code
- Kimi Platform
- OpenAI Codex
- OpenAI API key

It does not scrape browser cookies, automate ChatGPT web sessions, or store provider OAuth tokens in TSF SQLite.

## What TSF stores

TSF stores only safe metadata:

- provider
- auth method
- status
- redacted account label
- model route
- credential storage type
- timestamps
- safe summary
- redacted error text

## What TSF never stores

TSF never stores:

- API keys
- bearer tokens
- OAuth access tokens
- refresh tokens
- session cookies
- browser profile data
- provider credential files
- raw login output

## Kimi Code

Kimi Code is the membership route. It uses:

```text
provider: kimi-code
model: kimi-for-coding
```

Kimi Code should not be manually switched to `kimi-k2.6`. The stable API model ID is `kimi-for-coding`; the provider maps that route to the current coding model.

Supported credential sources:

- `TSF_KIMI_CODE_API_KEY`
- existing `TSF_KIMI_API_KEY`
- provider-owned Kimi CLI login metadata

## Kimi Platform

Kimi Platform is separate from Kimi Code membership billing. It uses:

```text
provider: kimi-platform
default model: kimi-k2.6
auth: TSF_KIMI_PLATFORM_API_KEY
```

Use this route when you want public Kimi Platform API billing rather than Kimi Code membership quota.

## OpenAI Codex

OpenAI Codex is a Codex-style agent route. It is not generic OpenAI API access.

Use official Codex sign-in flows only. Do not scrape ChatGPT cookies or browser storage.

```text
provider: openai-codex
model: codex-managed
auth: provider-owned Codex CLI sign-in
```

## OpenAI API key

OpenAI API-key route is separate from ChatGPT/Codex sign-in.

```text
provider: openai-api-key
auth: TSF_OPENAI_API_KEY
```

## Telegram handoff

TSF can format a Telegram-safe login handoff:

```bash
synthetic-firm auth-start kimi-code --dry-run --telegram-dry-run
synthetic-firm auth-start openai-codex --dry-run --telegram-dry-run
```

Sensitive URLs are not sent. Telegram messages remind the founder never to paste tokens into chat.

## Status and revoke

```bash
synthetic-firm auth-status
synthetic-firm auth-status kimi-code
synthetic-firm auth-list
synthetic-firm auth-revoke kimi-code
```

`auth-revoke` only revokes TSF metadata. Provider-owned credentials must be revoked in the provider’s own tool or console.
