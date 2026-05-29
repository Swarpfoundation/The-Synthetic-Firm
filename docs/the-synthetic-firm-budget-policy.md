# The Synthetic Firm Budget Policy

The Synthetic Firm has a hard infrastructure budget of `EUR 100/month`.
This covers hosting and deployment infrastructure, not model/API spend unless
that is explicitly enabled later.

Included by default: Render services, Vercel plan or usage, Neon/Postgres,
storage, monitoring/logging, deployment services, domains/DNS when introduced,
and other infrastructure subscriptions.

Excluded by default: Kimi/OpenAI/DeepSeek/Qwen/model API spend.

Thresholds:

- Budget: `EUR 100/month`
- Operating target: `EUR 70/month`
- Warning: `EUR 50/month`
- High: `EUR 75/month`
- Critical: `EUR 90/month`
- Hard stop: `EUR 100/month`

Unknown-cost paid actions fail closed. New recurring paid services require a
HumanTask approval before TSF treats them as allowed.

TSF does not scrape billing dashboards and does not call billing APIs in this
phase. Exact costs are accepted only from founder input or explicit config.
Estimates must remain labeled as estimates.

Internal commands are developer/smoke tooling, not product UX:

```bash
synthetic-firm budget-status
synthetic-firm budget-add-cost --provider vercel --service "Vercel" --amount-eur 0 --recurrence monthly --confidence estimated
synthetic-firm budget-list-costs
synthetic-firm budget-monthly-report
synthetic-firm budget-check-action vercel_preview_deploy
synthetic-firm budget-create-confirmation-tasks
synthetic-firm budget-public-summary
```

Never put tokens, database URLs, card details, provider account IDs, or invoice
documents into cost ledger text.
