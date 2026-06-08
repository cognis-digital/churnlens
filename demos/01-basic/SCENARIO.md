# Demo 01 - Basic SaaS metrics from a subscription ledger

`subscriptions.csv` is a minimal Stripe-style subscription-event ledger for a
small SaaS over three months (Jan-Mar 2026). Each row records a state change and
the customer's MRR *after* the change.

## Run it

```bash
# Full per-month report (MRR, churn, LTV) as a table
python -m churnlens report demos/01-basic/subscriptions.csv

# Same report as machine-readable JSON
python -m churnlens report demos/01-basic/subscriptions.csv --format json

# Latest-month MRR movement breakdown
python -m churnlens mrr demos/01-basic/subscriptions.csv
```

## What to look for

- **acme** signs up in Jan at $100, upgrades to $150 in Feb -> $50 *expansion* MRR.
- **globex** signs up in Jan at $50, then churns in Mar -> $50 *churned* MRR and a
  customer-churn event in March.
- **initech** downgrades $80 -> $40 in Mar -> $40 *contraction* MRR.
- **umbrella** is a brand-new Feb signup; **soylent** reactivates in Mar.

March should therefore show positive gross/net revenue churn driven by the
globex cancellation and the initech downgrade, partially offset by the soylent
reactivation. The report's `ltv` column is ARPA divided by that month's
customer churn rate.
