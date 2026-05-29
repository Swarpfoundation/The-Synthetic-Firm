# The Synthetic Firm Infrastructure Burn

Infrastructure burn is tracked in a persisted monthly ledger. The ledger stores
only redacted, founder-safe operational cost metadata.

Each cost item records provider, service, category, EUR amount, recurrence,
confidence, source, public summary, and redacted private notes. Exact means
founder/config supplied the value. TSF does not fabricate provider pricing.

The default runtime expects founder confirmation for:

- Vercel monthly cost
- Render API service monthly cost
- Render scheduler cron monthly cost
- Neon/Postgres monthly cost

Until these are recorded, public status may show that some costs need founder
confirmation. Paid actions that depend on unknown costs are blocked by the
budget gate.

Public export may show the `EUR 100/month` infrastructure budget, safe status,
known monthly burn estimate, unknown-cost counts, and a public-safe budget note.
It must not show invoices, payment/card data, provider account IDs, database
URLs, tokens, private service IDs, or raw billing errors.
