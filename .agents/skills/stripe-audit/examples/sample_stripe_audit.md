# Sample Stripe Financial Audit Report

Below is an authentic sample execution of `audit_stripe.py` against live production accounts.

---

```
========================================================================
 STRIPE FINANCIAL AUDIT - STATUS: HEALTHY
 Timestamp: 2026-10-10T14:01:50.728936+00:00
========================================================================

FINANCIAL OVERVIEW:
  • Available Balance : $3,581.73 USD
  • Pending Balance   : $0.00
  • Active SaaS MRR   : $300.00/mo (2 paying clients)
  • Gross Collected   : $3,693.65 (Fees: $111.92)
  • Net Deposits      : $3,581.73

DATABASE RECONCILIATION:
  • Total DB Tenants  : 13
  • Reconciled Subs   : 2
  • Ghost Subs        : 0
  • Entitlement Leaks : 0

AUDIT FINDINGS:
  [OK] All balances, subscriptions, and database entitlements are in sync.

========================================================================
TOTAL FINDINGS: 0 (Critical: 0, Error: 0, Warning: 0, Info: 0)
========================================================================
```

---

## Triage Walkthrough

1. **Cash Liquidity**:
   - Total available balance is positive ($3,581.73) with $0 pending or disputed balances.
2. **Subscription Health**:
   - 2 active subscriptions generating $300.00 in MRR:
     - Tenant #1: *Figueredo Property Management* ($150.00/mo Growth)
     - Tenant #184: *Sunnyvale Plumbing* ($150.00/mo Growth)
3. **Entitlement & Database Parity**:
   - 100% parity between paying Stripe subscriptions and database tenants. Zero entitlement leaks or unmapped subscriptions.
