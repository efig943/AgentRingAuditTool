---
name: stripe-audit
description: >-
  Inspect, audit, and reconcile live Stripe financial records, balances, subscriptions,
  MRR, customer cards, and transaction fees. Reconciles Stripe customer and subscription
  IDs against PostgreSQL tenants to prevent entitlement leaks and ghost billing.
---

# Stripe Financials & Subscription Audit Skill

This skill provides automated financial auditing of live Stripe balances, subscription lifecycles, and transaction ledgers, coupled with deep cross-system reconciliation against PostgreSQL `tenants`.

---

## Capabilities & Audit Pillars

1. **Cash Reserves & Balances (`BAL`)**:
   - Queries real-time available and pending cash balances.
   - Detects negative balances and unexpected chargeback reserves.

2. **Subscription & MRR Intelligence (`SUB`)**:
   - Computes live monthly recurring revenue (MRR) across all pricing tiers (Starter, Growth, Scale).
   - Audits subscription lifecycle states (`active`, `past_due`, `unpaid`, `canceled`).
   - Surfaces at-risk accounts requiring payment method updates.

3. **Transaction Fees & Processing Economics (`CHG`)**:
   - Calculates gross collections, net deposits, and total Stripe processing fees.
   - Measures effective payment processing fee percentage.
   - Audits recent succeeded and failed charge attempts with receipt links.

4. **PostgreSQL Database Reconciliation (`REC`)**:
   - **Ghost Subscriptions (`REC-GHOST-SUB`)**: Detects active paying Stripe subscriptions that have no corresponding record in the database.
   - **Entitlement Leaks (`REC-ENTITLEMENT-LEAK`)**: Detects tenants marked `subscription_status = 'active'` in the database who have no attached Stripe subscription.
   - **Status & Plan Mismatches**: Validates parity between Stripe billing states and database tenant records.

---

## Tooling & Usage

Use [`audit_stripe.py`](./scripts/audit_stripe.py) from the workspace root:

### 1. Terminal Summary (Balances, MRR & Reconciliation)
```bash
python3 .agents/skills/stripe-audit/scripts/audit_stripe.py --format summary
```

### 2. Export Markdown Report (Financial Incident / P&L Review)
```bash
python3 .agents/skills/stripe-audit/scripts/audit_stripe.py --format markdown --export stripe_audit_report.md
```

### 3. Machine-Readable JSON Output (CI/CD Gates)
```bash
python3 .agents/skills/stripe-audit/scripts/audit_stripe.py --format json --min-severity warning
```

### 4. Stripe-Only Audit (Skip Database Cross-Check)
```bash
python3 .agents/skills/stripe-audit/scripts/audit_stripe.py --no-db
```

---

## Exit Codes

| Exit Code | Status | Meaning |
|---|---|---|
| `0` | `CLEAN` | Balances positive, subscriptions active, and 100% database parity. |
| `1` | `WARNING` | Past due subscriptions, failed charges, or unlinked ghost subscriptions. |
| `2` | `ERROR / CRITICAL` | Negative balance, authentication failure, or entitlement leaks. |
| `3` | `FATAL` | Missing `STRIPE_SECRET_KEY` or unhandled execution error. |

---

## References

- [stripe_rules.md](./references/stripe_rules.md) &mdash; Detailed taxonomy of billing and reconciliation rules.
- [sample_stripe_audit.md](./examples/sample_stripe_audit.md) &mdash; Example report and output walk-through.
