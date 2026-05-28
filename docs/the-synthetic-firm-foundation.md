# The Synthetic Firm Foundation

The Synthetic Firm is an autonomous AI agency OS with five internal agents:
Atlas, Scout, Forge, Pulse, and Sentinel.

This foundation layer defines private agent profiles, provider policy,
budget metadata, and project permission policy. It is the product identity
surface for TSF commands and documentation.

## Agent Profiles

- Atlas: Supervisor / CEO
- Scout: Research and Opportunity
- Forge: Builder / Product
- Pulse: Growth / Sales
- Sentinel: Guardian / QA / Compliance

Profile configuration lives in `agents/profiles.yaml`. Each profile defines:

- display name and description
- model policy
- TSF API-key alias metadata
- symbolic permissions
- budget fields
- TSF toolset labels

## Configure Kimi Code For The Synthetic Firm

Use TSF-prefixed environment variables. Do not put raw keys in prompts, docs,
logs, browser-visible code, memory, or checked-in configuration files.

```bash
export TSF_KIMI_API_KEY="..."
export TSF_KIMI_BASE_URL="https://api.kimi.com/coding"
export TSF_HOME=/tmp/synthetic-firm-home
synthetic-firm atlas --dry-run
```

Keep `KIMI_API_KEY` and `KIMI_BASE_URL` empty unless you intentionally need
provider-native overrides. TSF copies the TSF-prefixed values into the child
provider process without printing secret values.

## Storage

Use:

- `TSF_HOME`
- `~/.synthetic-firm`
- `.synthetic-firm/`
- `synthetic_firm/`

Budget metadata is written to:

```text
$TSF_HOME/logs/synthetic-firm-budget.jsonl
```

## Policy

Project policy lives in `agents/policy.yaml`. The policy rejects forbidden
permissions such as:

- changing agent permissions
- modifying approval rules
- reading raw environment files
- sending external communications
- deploying production
- merging to main
- disabling audit logs
- payment tools
- social posting
- email sending
- repository write automation

## Run Examples

Dry-run an agent profile:

```bash
synthetic-firm atlas --dry-run
```

Run a one-shot Atlas profile invocation:

```bash
synthetic-firm atlas -- -z "Summarize the current repository state."
```

Show workday status:

```bash
synthetic-firm show-workday-status
```

## Legal Notices

See `THIRD_PARTY_NOTICES.md` and `docs/legal/upstream-attribution.md` for
third-party license notices.
